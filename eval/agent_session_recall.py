"""Candidate-recall probe on the frozen agent-session questions.

PYTHONPATH=src:. .venv/bin/python -m eval.agent_session_recall

Asks why labels miss the production pool (20 chunks per leg): scores wider
pools, an identifier-phrase lexical leg, and a pool without transcripts and
findings, each fused by RRF and again after the Qwen3 0.6B reranker.
Same questions, labels, pool copy and leakage rule as agent_session_eval.py.
The set is development data from here on: nothing tuned on it may set the
adoption decision.
"""

import json
import re
import statistics
import tempfile
import time
import tomllib
from dataclasses import asdict
from pathlib import Path
from typing import Any

from engram.client import embed, load_config, resolve_pinned_entry
from eval.agent_session_eval import (
    CONFIG,
    FREEZE,
    POOL,
    PRIVATE,
    QUESTION_FILES,
    file_ranks,
    full_session_ids,
    sha256,
)
from eval.agent_session_variants import BUDGET, RERANKER, summarize
from eval.benchmark_runtime import Server
from eval.probe_fusion import SCOPE, bm25_or, fuse
from eval.probe_rerank_fixed import open_readonly, require_free_port, rerank_documents

PUBLIC = Path(__file__).resolve().parent / "results-agent-session-recall.json"
DEEP = 500  # chunks fetched per leg; narrower pools are prefixes of this
NOISY = {"transcripts", "findings"}  # no label lives here; they crowd the top 20
# A token that looks like code: has _ . / - or a digit inside, or is ALLCAPS.
IDENTIFIER = re.compile(r"\w+[_./-]\w[\w./-]*|\w*\d\w*|[A-Z]{3,}")


def identifier_tokens(text: str) -> list[str]:
    tokens = [t.strip(".,:;") for t in text.split()]
    return [t for t in tokens if IDENTIFIER.fullmatch(t)]


def identifier_leg(store: Any, text: str, k: int) -> list[Any]:
    """Lexical OR over the question's code-like tokens only, each as a phrase."""
    idents = " ".join(identifier_tokens(text))
    return bm25_or(store, idents, None, k) if idents else []


def check_inputs() -> None:
    frozen = json.loads(FREEZE.read_text())
    now = {name: sha256(PRIVATE / name) for name in QUESTION_FILES}
    now |= {"pool.db": sha256(POOL), "config.toml": sha256(CONFIG)}
    if any(frozen[name] != digest for name, digest in now.items()):
        raise SystemExit("frozen questions, pool or config changed")


def legs(store: Any, question: str, entry: Any) -> tuple[dict[str, list[Any]], float]:
    started = time.monotonic()
    vector = embed([question], entry)[0]
    out = {
        "dense": store.search_knn(vector, SCOPE, None, DEEP),
        "and": store.search_bm25(question, SCOPE, None, DEEP),
        "or": bm25_or(store, question, None, DEEP),
        "ident": identifier_leg(store, question, DEEP),
    }
    return out, time.monotonic() - started


def quiet(hits: list[Any]) -> list[Any]:
    return [h for h in hits if h.chunk.corpus not in NOISY]


def pools(leg: dict[str, list[Any]]) -> dict[str, list[Any]]:
    """Fused candidate lists per variant; every chunk in the list is a candidate."""
    dense, lex_and, lex_or, ident = (leg[k] for k in ("dense", "and", "or", "ident"))
    q_dense, q_or, q_ident = quiet(dense), quiet(lex_or), quiet(ident)

    def rrf(*parts: list[Any]) -> list[Any]:
        return fuse([(p, 1.0) for p in parts], limit=10_000)

    return {
        "production_20": rrf(lex_and[:20], dense[:20]),
        "or_20": rrf(lex_or[:20], dense[:20]),
        "or_100": rrf(lex_or[:100], dense[:100]),
        "or_100+ident": rrf(lex_or[:100], dense[:100], ident[:20]),
        "quiet_or_20": rrf(q_or[:20], q_dense[:20]),
        "quiet_or_20+ident": rrf(q_or[:20], q_dense[:20], q_ident[:20]),
        "quiet_or_50+ident": rrf(q_or[:50], q_dense[:50], q_ident[:20]),
        "quiet_or_100+ident": rrf(q_or[:100], q_dense[:100], q_ident[:20]),
    }


def main() -> None:
    check_inputs()
    questions = [
        q for name in QUESTION_FILES for q in json.loads((PRIVATE / name).read_text())
    ]
    sessions = full_session_ids()
    entry = resolve_pinned_entry(load_config(CONFIG))
    toml = tomllib.loads((Path(__file__).parent / "models.toml").read_text())
    spec = next(s for s in toml["rerankers"] if s["name"] == RERANKER)
    results: dict[str, list[dict]] = {}
    sizes: dict[str, list[int]] = {}
    deep: dict[str, dict] = {}

    def record(name: str, q: dict, hits: list[Any], seconds: float) -> None:
        rank = file_ranks(
            [h.chunk.path for h in hits],
            set(q["labels"]),
            sessions[q["session"]],
        )
        results.setdefault(name, []).append(
            {"q": q["q"], "rank": rank, "seconds": seconds},
        )
        sizes.setdefault(name, []).append(len(hits))

    require_free_port()
    with (
        open_readonly(POOL) as store,
        tempfile.TemporaryDirectory(prefix="engram-recall-") as scratch,
        Server(spec, Path(scratch), reranking=True) as server,
    ):
        for q in questions:
            leg, seconds = legs(store, q["question"], entry)
            labels, leaked = set(q["labels"]), sessions[q["session"]]
            deep[q["q"]] = {
                name: file_ranks([h.chunk.path for h in hits], labels, leaked)
                for name, hits in {**leg, "quiet_dense": quiet(leg["dense"])}.items()
            }
            for name, hits in pools(leg).items():
                record(name, q, hits, seconds)
                if name == "production_20":
                    continue
                started = time.monotonic()
                chunks = [asdict(h.chunk) for h in hits]
                scores = server.rerank(q["question"], rerank_documents(chunks, BUDGET))
                order = sorted(zip(scores, hits, strict=True), key=lambda p: -p[0])
                elapsed = seconds + time.monotonic() - started
                record(f"{name}+rerank", q, [h for _, h in order], elapsed)
            print(q["q"], {n: r[-1]["rank"] for n, r in results.items()}, flush=True)
    summary = {
        "n": len(questions),
        "leg_file_rank_within_500_chunks": deep,
        "variants": {
            name: {
                **summarize(rows),
                "median_candidates": statistics.median(sizes[name]),
            }
            for name, rows in results.items()
        },
    }
    PUBLIC.write_text(json.dumps(summary, indent=2) + "\n")
    for name, s in summary["variants"].items():
        print(name, {k: v for k, v in s.items() if k != "ranks"})


if __name__ == "__main__":
    main()
