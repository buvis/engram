"""Fusion and candidate-recall probe over the frozen full-snapshot indexes.

Reuses the per-model indexes built by ``eval.compare_models`` (read only) and
re-runs the 55 gold queries with alternative retrieval pools and fusion
weights, so the production RRF settings (20 dense + 20 lexical, k=60) can be
compared against dense-only, lexical-only, larger pools and weighted fusion.
Also reports candidate recall: whether the expected file is in the pool a
reranker would receive.

    uv run python -m eval.probe_fusion [--models NAME...] [--out PATH]
"""

import argparse
import json
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from engram.client import Vector
from engram.store import Scope, open_store
from eval.benchmark_runtime import Server
from eval.compare_models import CACHE, ROOT, _aggregate, format_input, metrics

DEFAULT_MODELS = ["bge-m3-q8", "gemma2-q8", "jina-v5-small-q8", "qwen3-8b-q8"]
RRF_K = 60
SCOPE = Scope("portfolio", None)


def fuse(
    legs: list[tuple[list[Any], float]], k: int = RRF_K, limit: int = 40
) -> list[Any]:
    """Weighted reciprocal-rank fusion over ranked hit lists."""
    scores: dict[int, float] = {}
    hits: dict[int, Any] = {}
    for hit_list, weight in legs:
        for i, hit in enumerate(hit_list):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + weight / (k + i + 1)
            hits.setdefault(hit.chunk_id, hit)
    order = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:limit]
    return [hits[cid] for cid in order]


def rows(hits: list[Any]) -> list[dict[str, Any]]:
    return [{"path": h.chunk.path, "line_start": h.chunk.line_start} for h in hits]


def bm25_or(store: Any, text: str, corpus: str, k: int) -> list[Any]:
    """Lexical search with OR semantics (production requires every token)."""
    where, params = store._scope_conditions(SCOPE, corpus, "c")
    sql = (
        "SELECT c.id, bm25(chunks_fts) AS score, c.corpus, c.repo, c.doc_type, "
        "c.path, c.heading, c.body, c.line_start, c.line_end, c.content_hash, "
        "c.chunk_ordinal FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid "
        f"WHERE chunks_fts MATCH ? AND {where} ORDER BY score LIMIT ?"
    )
    tokens = [t.replace('"', '""') for t in text.split()]
    if not tokens:
        return []
    match = " OR ".join(f'"{t}"' for t in tokens)
    rows = store.conn.execute(sql, [match, *params, k]).fetchall()
    return [store._row_to_hit(r) for r in rows]


def variants(
    dense: dict[int, list[Any]],
    bm25: dict[int, list[Any]],
    bm25_or_hits: list[Any] | None = None,
) -> dict[str, list[Any]]:
    """Ranked lists per named strategy; pool sizes are leg depths."""

    def rrf(n: int, wd: float = 1.0, wb: float = 1.0) -> list[Any]:
        return fuse([(dense[n][:n], wd), (bm25[n][:n], wb)])

    out = {
        "dense_only_40": dense[100][:40],
        "rrf_prod_order_20_20": fuse([(bm25[20][:20], 1.0), (dense[20][:20], 1.0)]),
        "bm25_only_40": bm25[100][:40],
        "rrf_prod_20_20": rrf(20),
        "rrf_40_40": rrf(40),
        "rrf_100_100": rrf(100),
        "rrf_20_20_dense2x": rrf(20, wd=2.0),
        "rrf_100_100_dense2x": rrf(100, wd=2.0),
        "rrf_100_100_dense4x": rrf(100, wd=4.0),
    }
    if bm25_or_hits is not None:
        out["bm25_or_only_40"] = bm25_or_hits[:40]
        out["rrf_bm25or_20_20"] = fuse(
            [(dense[20][:20], 1.0), (bm25_or_hits[:20], 1.0)]
        )
        out["rrf_bm25or_20_20_dense2x"] = fuse(
            [(dense[20][:20], 2.0), (bm25_or_hits[:20], 1.0)]
        )
    return out


def recall(
    dense: dict[int, list[Any]], bm25: dict[int, list[Any]], path: str
) -> dict[str, int]:
    """Whether the expected file appears in each candidate pool."""

    def has(hits: list[Any]) -> int:
        return int(any(h.chunk.path == path for h in hits))

    out = {f"dense_{n}": has(dense[n][:n]) for n in (20, 40, 100)}
    out["bm25_20"] = has(bm25[20][:20])
    out["bm25_100"] = has(bm25[100][:100])
    out["union_20_20"] = has(dense[20][:20] + bm25[20][:20])
    out["union_100_100"] = has(dense[100][:100] + bm25[100][:100])
    return out


def mean_recall(per_query: list[dict[str, Any]]) -> dict[str, float]:
    keys = per_query[0]["recall"]
    return {k: sum(q["recall"][k] for q in per_query) / len(per_query) for k in keys}


def probe_model(spec: dict[str, Any], gold: list[dict[str, Any]]) -> dict[str, Any]:
    matches = sorted(
        p for p in CACHE_DIR.glob(f"{spec['name']}-*") if (p / "index.db").exists()
    )
    if len(matches) != 1:
        raise RuntimeError(f"expected one index for {spec['name']}, found {matches}")
    store = open_store(matches[0] / "index.db")
    per_variant: dict[str, list[dict[str, Any]]] = {}
    per_query: list[dict[str, Any]] = []
    try:
        with tempfile.TemporaryDirectory() as scratch:
            with Server(spec, Path(scratch)) as server:
                for i, g in enumerate(gold):
                    text = format_input(
                        spec["style"], g["query"], query=True, corpus=g["corpus"]
                    )
                    values = server.embed([text])[0]
                    vector = Vector(values, spec["id"], len(values))
                    dense = {
                        n: store.search_knn(vector, SCOPE, g["corpus"], 100)
                        for n in (20, 40, 100)
                    }
                    bm25_all = store.search_bm25(g["query"], SCOPE, g["corpus"], 100)
                    bm25 = {n: bm25_all for n in (20, 40, 100)}
                    or_hits = bm25_or(store, g["query"], g["corpus"], 100)
                    for name, ranked in variants(dense, bm25, or_hits).items():
                        per_variant.setdefault(name, []).append(
                            {
                                "corpus": g["corpus"],
                                "metrics": metrics(rows(ranked), g),
                            }
                        )
                    per_query.append(
                        {
                            "query_id": i,
                            "corpus": g["corpus"],
                            "recall": recall(dense, bm25, g["path"]),
                            "bm25_hits": len(bm25_all),
                        }
                    )
    finally:
        store.conn.close()
    return {
        "variants": {k: _aggregate(v) for k, v in per_variant.items()},
        "recall": mean_recall(per_query),
        "recall_by_corpus": {
            c: mean_recall([q for q in per_query if q["corpus"] == c])
            for c in sorted({q["corpus"] for q in per_query})
        },
        "bm25_empty_queries": sum(q["bm25_hits"] == 0 for q in per_query),
        "queries": len(per_query),
    }


CACHE_DIR = (
    Path((CACHE / "full.txt").read_text().strip())
    if (CACHE / "full.txt").exists()
    else CACHE
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument("--out", type=Path, default=ROOT / "probe-fusion.json")
    args = parser.parse_args()
    snapshot = json.loads((CACHE_DIR / "snapshot.json").read_text())
    specs = {
        s["name"]: {**s, "max_chars": snapshot["max_chars"]}
        for s in tomllib.loads((ROOT / "models.toml").read_text())["models"]
    }
    results: dict[str, Any] = {"snapshot": CACHE_DIR.name, "models": {}}
    for name in args.models:
        print(f"probing {name}", flush=True)
        results["models"][name] = probe_model(specs[name], snapshot["gold"])
        args.out.write_text(json.dumps(results, indent=2))
        for v, s in results["models"][name]["variants"].items():
            a = s["all"]
            print(
                f"{name:18} {v:22} hit5={a['file_hit5']:.3f} mrr={a['file_rr']:.3f}",
                flush=True,
            )
        print(f"{name:18} recall {results['models'][name]['recall']}", flush=True)


if __name__ == "__main__":
    main()
