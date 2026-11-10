"""Score fusion and rerank variants on the frozen agent-session questions.

PYTHONPATH=src:. .venv/bin/python -m eval.agent_session_variants freeze
PYTHONPATH=src:. .venv/bin/python -m eval.agent_session_variants run

Same questions, labels, pool, leakage rule and metrics as
eval/agent_session_eval.py. Query vectors come from the pinned production
embedder (port 8083); the reranker runs on port 18181 only.
"""

import json
import statistics
import sys
import tempfile
import time
import tomllib
from dataclasses import asdict
from pathlib import Path

from engram.client import embed, load_config, resolve_pinned_entry
from engram.query import query
from eval.agent_session_eval import (
    CONFIG,
    DEPTH,
    PASS_LOWER,
    PASS_RATE,
    POOL,
    PRIVATE,
    QUESTION_FILES,
    file_ranks,
    fingerprint,
    full_session_ids,
    sha256,
    wilson,
)
from eval.benchmark_runtime import Server
from eval.probe_fusion import SCOPE, bm25_or, variants
from eval.probe_rerank_fixed import (
    open_readonly,
    require_free_port,
    rerank_documents,
)

FREEZE = PRIVATE / "freeze_variants.json"
PUBLIC = Path(__file__).resolve().parent / "results-agent-session-variants.json"
RERANKER = "qwen3-reranker-06b-q8"
BUDGET = 8000  # characters per reranked chunk, as in the November campaign
FUSION = {
    "production": "rrf_prod_order_20_20",
    "or_dense1": "rrf_bm25or_20_20",
    "or_dense2": "rrf_bm25or_20_20_dense2x",
}


def freeze_print() -> dict[str, str]:
    return {**fingerprint(), "variant_script": sha256(Path(__file__))}


def candidates(questions: list[dict]) -> dict[str, list[dict]]:
    """Fused chunk lists per fusion variant, checked against production query()."""
    config = load_config(CONFIG)
    entry = resolve_pinned_entry(config)
    out: dict[str, list[dict]] = {name: [] for name in FUSION}
    with open_readonly(POOL) as store:
        for q in questions:
            started = time.monotonic()
            vector = embed([q["question"]], entry)[0]
            dense = store.search_knn(vector, SCOPE, None, 20)
            lexical = store.search_bm25(q["question"], SCOPE, None, 20)
            base = time.monotonic() - started
            started = time.monotonic()
            or_hits = bm25_or(store, q["question"], None, 20)
            or_seconds = time.monotonic() - started
            fused = variants(
                dict.fromkeys((20, 40, 100), dense),
                dict.fromkeys((20, 40, 100), lexical),
                or_hits,
            )
            prod = query(store, config, q["question"], SCOPE, k=DEPTH, vector=vector)
            if [p.path for p in prod] != [
                h.chunk.path for h in fused[FUSION["production"]]
            ]:
                raise SystemExit(f"{q['q']}: production fusion not reproduced")
            for name, key in FUSION.items():
                out[name].append(
                    {
                        "chunks": [asdict(h.chunk) for h in fused[key]],
                        "seconds": base + (or_seconds if "or" in name else 0.0),
                    },
                )
            print(q["q"], "candidates", flush=True)
    return out


def rerank(
    server: Server,
    question: str,
    chunks: list[dict],
) -> tuple[list[dict], float]:
    started = time.monotonic()
    scores = server.rerank(question, rerank_documents(chunks, BUDGET))
    order = sorted(
        zip(scores, chunks, strict=True),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [c for _, c in order], time.monotonic() - started


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    ranks = [r["rank"] for r in rows]
    top3 = sum(r is not None and r <= 3 for r in ranks)
    top5 = sum(r is not None and r <= 5 for r in ranks)
    seconds = sorted(r["seconds"] for r in rows)
    low, high = wilson(top3, n)
    return {
        "n": n,
        "top3": top3,
        "top5": top5,
        "top3_wilson95": [low, high],
        "top5_wilson95": list(wilson(top5, n)),
        "mrr": sum(1 / r for r in ranks if r) / n,
        "no_label_in_candidates": [r["q"] for r in rows if r["rank"] is None],
        "misses_top3": [r["q"] for r in rows if not (r["rank"] and r["rank"] <= 3)],
        "latency_seconds": {
            "median": statistics.median(seconds),
            "p95": seconds[int((n - 1) * 0.95)],
        },
        "pass": top3 / n >= PASS_RATE and low > PASS_LOWER,
        "ranks": {r["q"]: r["rank"] for r in rows},
    }


def run() -> None:
    frozen = json.loads(FREEZE.read_text())
    if frozen != freeze_print():
        raise SystemExit("frozen inputs changed after freeze")
    questions = [
        q for name in QUESTION_FILES for q in json.loads((PRIVATE / name).read_text())
    ]
    sessions = full_session_ids()
    pools = candidates(questions)
    toml = tomllib.loads((Path(__file__).parent / "models.toml").read_text())
    spec = next(s for s in toml["rerankers"] if s["name"] == RERANKER)
    results: dict[str, list[dict]] = {}

    def row(q: dict, chunks: list[dict], seconds: float) -> dict:
        paths = [c["path"] for c in chunks]
        rank = file_ranks(paths, set(q["labels"]), sessions[q["session"]])
        return {"q": q["q"], "rank": rank, "seconds": seconds}

    for name, pool in pools.items():
        results[name] = [
            row(q, p["chunks"], p["seconds"])
            for q, p in zip(questions, pool, strict=True)
        ]
    require_free_port()
    with tempfile.TemporaryDirectory(prefix="engram-variants-") as scratch:
        with Server(spec, Path(scratch), reranking=True) as server:
            smoke = server.rerank(
                "How do plants make food using sunlight?",
                [
                    "Paris is the capital of France.",
                    "Plants use photosynthesis to convert sunlight into chemical energy.",
                ],
            )
            if smoke[1] - smoke[0] <= 0.05:
                raise SystemExit(f"reranker sanity check failed: {smoke}")
            for name, pool in pools.items():
                rows = []
                for q, p in zip(questions, pool, strict=True):
                    ranked, elapsed = rerank(server, q["question"], p["chunks"])
                    rows.append(row(q, ranked, p["seconds"] + elapsed))
                    print(
                        name,
                        "rerank",
                        q["q"],
                        rows[-1]["rank"],
                        f"{elapsed:.2f}s",
                        flush=True,
                    )
                results[f"{name}+rerank06b"] = rows
    summary = {
        "freeze": frozen,
        "reranker": spec,
        "variants": {name: summarize(rows) for name, rows in results.items()},
    }
    PUBLIC.write_text(json.dumps(summary, indent=2) + "\n")
    for name, s in summary["variants"].items():
        print(name, {k: v for k, v in s.items() if k != "ranks"})


def main() -> None:
    action = sys.argv[1]
    if action == "freeze":
        with FREEZE.open("x") as stream:
            json.dump(freeze_print(), stream, indent=2)
    elif action == "run":
        run()
    else:
        raise SystemExit("usage: freeze | run")


if __name__ == "__main__":
    main()
