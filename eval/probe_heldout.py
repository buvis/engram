"""Freeze source-authored questions before scoring on the read-only campaign.

This small set holds out target files, not authors or topics. No human-sourced
questions are claimed. Private questions and source text remain in the cache.
"""

import argparse
import json
import random
import tempfile
import time
import tomllib
from dataclasses import asdict
from pathlib import Path

from engram.client import Vector
from eval.benchmark_runtime import Server
from eval.compare_models import CACHE, ROOT, format_input
from eval.probe_fusion import SCOPE, bm25_or, variants
from eval.probe_rerank_fixed import (
    SNAPSHOT,
    VARIANTS,
    collect_candidates,
    digest,
    measure_reranking,
    open_readonly,
    require_free_port,
    score_ranking,
    summarize,
    unique_result,
)

QUESTIONS = {
    (
        "code",
        0,
    ): "Which Clara test checks that GET HEAD and OPTIONS do not need a CSRF token?",
    (
        "code",
        1,
    ): "Where is the autopilot local-path test helper that creates parent directories before writing fixture files?",
    (
        "memory",
        0,
    ): "Why did the MkDocs notes project feel out of control during its July evolution assessment?",
    (
        "memory",
        1,
    ): "What environment overrides let the gems tests run under Seatbelt without cargo cache permission failures?",
    (
        "prd",
        0,
    ): "Which workflow parity specification excludes publication and live installation from its scope?",
    (
        "prd",
        1,
    ): "Where are the regression tests for the portfolio builder writing output beside its inputs instead of the home default?",
    (
        "discovery",
        0,
    ): "Which autopilot planning dependencies would break the loop if retired during the specflow port?",
    (
        "discovery",
        1,
    ): "What happens when Victor cannot reproduce an environment-dependent single-reviewer HIGH finding?",
    (
        "transcripts",
        0,
    ): "In the ddb session, what verification followed the three sweep group A split commits?",
    (
        "transcripts",
        1,
    ): "When did I suggest automating updates of the Python minor version across the pipx entries in mise?",
}


def freeze(destination: Path) -> None:
    """Reproduce score-blind sampling; exclusive create prevents replacing labels."""
    snapshot_path = CACHE / SNAPSHOT / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text())
    excluded = {g["path"] for g in snapshot["gold"]}
    rng = random.Random(20261105)
    gold = []
    sources = []
    for corpus in ("code", "decision", "memory", "prd", "discovery", "transcripts"):
        pool = [
            r
            for r in snapshot["rows"]
            if r["corpus"] == corpus
            and r["path"] not in excluded
            and 150 < len(r["body"]) < 3500
        ]
        rng.shuffle(pool)
        for i, row in enumerate(pool[:2]):
            gold.append(
                {
                    "query": QUESTIONS[corpus, i],
                    "corpus": corpus,
                    "path": row["path"],
                    "acceptable_starts": [row["line_start"]],
                }
            )
            sources.append(row)
    payload = {
        "snapshot_sha256": digest(snapshot_path),
        "author": "Codex agent",
        "sampling_seed": 20261105,
        "independent_human_questions": 0,
        "gold": gold,
        "sources": sources,
    }
    with destination.open("x") as stream:
        json.dump(payload, stream, indent=2)
    destination.chmod(0o600)


def run(frozen: Path, output: Path) -> None:
    data = json.loads(frozen.read_text())
    directory = CACHE / SNAPSHOT
    if data["snapshot_sha256"] != digest(directory / "snapshot.json"):
        raise ValueError("snapshot changed after label freeze")
    specs = tomllib.loads((ROOT / "models.toml").read_text())
    model = next(s for s in specs["models"] if s["name"] == "bge-m3-q8")
    reranker = next(
        s for s in specs["rerankers"] if s["name"] == "qwen3-reranker-06b-q8"
    )
    gold = data["gold"]
    snapshot = json.loads((directory / "snapshot.json").read_text())
    # Reproduce the known 55-query embedding baseline before any new measurement.
    with tempfile.TemporaryDirectory() as scratch:
        _, validation = collect_candidates(
            model, directory, snapshot["gold"], Path(scratch)
        )
    collected = {name: [] for name in VARIANTS}
    campaign = unique_result(directory, "bge-m3-q8-*/result.json")
    require_free_port()
    with open_readonly(campaign.parent / "index.db") as store:
        for g in gold:
            if not store.conn.execute(
                "SELECT 1 FROM chunks WHERE path=? AND line_start=?",
                (g["path"], g["acceptable_starts"][0]),
            ).fetchone():
                raise ValueError("label absent from evaluation index")
        with tempfile.TemporaryDirectory() as scratch:
            with Server(model, Path(scratch)) as server:
                for i, g in enumerate(gold):
                    start = time.monotonic()
                    vector = server.embed(
                        [
                            format_input(
                                model["style"],
                                g["query"],
                                query=True,
                                corpus=g["corpus"],
                            )
                        ]
                    )[0]
                    dense = store.search_knn(
                        Vector(vector, model["id"], len(vector)), SCOPE, g["corpus"], 20
                    )
                    lexical = store.search_bm25(g["query"], SCOPE, g["corpus"], 20)
                    base = time.monotonic() - start
                    start = time.monotonic()
                    or_hits = bm25_or(store, g["query"], g["corpus"], 20)
                    extra = time.monotonic() - start
                    selected = variants(
                        dict.fromkeys((20, 40, 100), dense),
                        dict.fromkeys((20, 40, 100), lexical),
                        or_hits,
                    )
                    for name in VARIANTS:
                        ranked = [asdict(h.chunk) for h in selected[name]]
                        row = score_ranking(
                            ranked, g, i, base + (extra if "bm25or" in name else 0)
                        )
                        collected[name].append({**row, "ranked": ranked})
    report = {
        "snapshot": SNAPSHOT,
        "snapshot_sha256": data["snapshot_sha256"],
        "labels_sha256": digest(frozen),
        "source_sha256": digest(Path(__file__)),
        "author": data["author"],
        "independent_human_questions": 0,
        "note": "10 agent-authored questions; 10 exact passage labels; two each code, memory, prd, discovery, transcripts. No decision targets outside development files. Corpus-scoped; no cross-corpus claim.",
        "baseline_validation": validation,
        "fusion": {},
        "reranked": {},
    }
    for name, rows in collected.items():
        result = summarize(
            [{k: v for k, v in row.items() if k != "ranked"} for row in rows]
        )
        result.pop("passage_labels")
        report["fusion"][name] = result
    require_free_port()
    with tempfile.TemporaryDirectory() as scratch:
        with Server(reranker, Path(scratch), reranking=True) as server:
            smoke = server.rerank(
                "How do plants make food using sunlight?",
                [
                    "Paris is the capital of France.",
                    "Plants use photosynthesis to convert sunlight into chemical energy.",
                ],
            )
            if smoke[1] - smoke[0] <= 0.05:
                raise ValueError("reranker sanity check failed")
            for name, rows in collected.items():
                result = measure_reranking(
                    server, rows, gold, 8000, name, frozen.parent / f"{name}.jsonl"
                )
                result.pop("passage_labels")
                report["reranked"][name] = result
    output.write_text(json.dumps(report, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run"))
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "probe-heldout.json")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.labels)
    else:
        run(args.labels, args.out)


if __name__ == "__main__":
    main()
