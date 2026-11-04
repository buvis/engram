"""Rerank four fusion variants on read-only full-campaign indexes.

PYTHONPATH=src:. .venv/bin/python -m eval.probe_rerank_fixed
Only port 18181 is used; embedding and reranking servers never overlap.
Public output contains metrics and query IDs, never private source text.
"""

import argparse
import hashlib
import json
import socket
import sqlite3
import statistics
import tempfile
import time
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import sqlite_vec

from engram.client import Vector
from engram.store import Store
from eval.benchmark_runtime import Server
from eval.compare_models import CACHE, ROOT, _aggregate, format_input, metrics
from eval.probe_fusion import SCOPE, bm25_or, fuse, variants

SNAPSHOT = "fc9bf2e6e0038153"
MODELS = ["bge-m3-q8", "qwen3-8b-q8"]
RERANKERS = ["qwen3-reranker-06b-q8", "qwen3-reranker-4b-q8"]
VARIANTS = [
    "rrf_prod_order_20_20",
    "rrf_prod_20_20",
    "rrf_bm25or_20_20",
    "rrf_bm25or_20_20_dense2x",
]
LABEL_NOTE = "8 passage labels: 5 code, 3 decision; no transcript passage labels."


@contextmanager
def open_readonly(path: Path) -> Iterator[Store]:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        yield Store(connection)
    finally:
        connection.close()


def require_free_port() -> None:
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 18181)) == 0:
            raise RuntimeError("port 18181 is occupied; leave its owner untouched")


def rerank_documents(ranked: list[dict[str, Any]], budget: int) -> list[str]:
    return [f"{p['heading']}\n{p['path']}\n{p['body']}"[:budget] for p in ranked]


def score_ranking(
    ranked: list[dict[str, Any]],
    gold: dict[str, Any],
    query_id: int,
    retrieval_seconds: float,
    rerank_seconds: float = 0.0,
) -> dict[str, Any]:
    return {
        "query_id": query_id,
        "corpus": gold["corpus"],
        "metrics": metrics(ranked, gold),
        "candidate_count": len(ranked),
        "retrieval_seconds": retrieval_seconds,
        "rerank_seconds": rerank_seconds,
        "seconds": retrieval_seconds + rerank_seconds,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    groups = ["all", *sorted({r["corpus"] for r in results})]
    return {
        "summary": _aggregate(results),
        "counts": {
            group: {
                "queries": len(subset),
                "passage_labels": sum("passage_rr" in r["metrics"] for r in subset),
            }
            for group in groups
            for subset in [
                (
                    results
                    if group == "all"
                    else [r for r in results if r["corpus"] == group]
                )
            ]
        },
        "latency_seconds": {
            key: {
                "median": statistics.median(values),
                "p95": sorted(values)[int((len(values) - 1) * 0.95)],
            }
            for key in ("retrieval_seconds", "rerank_seconds", "seconds")
            for values in [[r[key] for r in results]]
        },
        "results": results,
        "passage_labels": LABEL_NOTE,
    }


def assert_baseline(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    """Fail closed unless every corpus/metric reproduces campaign precision."""
    if actual.keys() != expected.keys():
        raise ValueError("baseline corpus groups differ")
    for corpus, values in expected.items():
        if actual[corpus].keys() != values.keys():
            raise ValueError(f"baseline metric keys differ: {corpus}")
        for key, value in values.items():
            if abs(actual[corpus][key] - value) > 0.0005:
                raise ValueError(
                    f"baseline mismatch {corpus}.{key}: {actual[corpus][key]} != {value}"
                )


def unique_result(directory: Path, pattern: str) -> Path:
    paths = sorted(directory.glob(pattern))
    if len(paths) != 1:
        raise ValueError(
            f"expected one campaign result for {pattern}, found {len(paths)}"
        )
    return paths[0]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_identity(ranked: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return [
        tuple(p[key] for key in ("path", "line_start", "line_end", "heading", "body"))
        for p in ranked
    ]


def collect_candidates(
    spec: dict[str, Any], directory: Path, gold: list[dict[str, Any]], scratch: Path
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    campaign_path = unique_result(directory, f"{spec['name']}-*/result.json")
    campaign = json.loads(campaign_path.read_text())
    collected: dict[str, list[dict[str, Any]]] = {name: [] for name in VARIANTS}
    identical_orders = 0
    identical_sets = 0
    require_free_port()
    with open_readonly(campaign_path.parent / "index.db") as store:
        with Server(spec, scratch) as server:
            for i, g in enumerate(gold):
                started = time.monotonic()
                text = format_input(
                    spec["style"], g["query"], query=True, corpus=g["corpus"]
                )
                values = server.embed([text])[0]
                vector = Vector(values, spec["id"], len(values))
                dense = store.search_knn(vector, SCOPE, g["corpus"], 20)
                lexical = store.search_bm25(g["query"], SCOPE, g["corpus"], 20)
                base_seconds = time.monotonic() - started
                started = time.monotonic()
                or_hits = bm25_or(store, g["query"], g["corpus"], 20)
                or_seconds = time.monotonic() - started
                # Only 20-per-leg variants are consumed; discard wider-pool outputs.
                selected = variants(
                    dict.fromkeys((20, 40, 100), dense),
                    dict.fromkeys((20, 40, 100), lexical),
                    or_hits,
                )
                selected[VARIANTS[0]] = fuse([(lexical, 1.0), (dense, 1.0)])
                for name in VARIANTS:
                    ranked = [asdict(hit.chunk) for hit in selected[name]]
                    seconds = base_seconds + (or_seconds if "bm25or" in name else 0.0)
                    row = score_ranking(ranked, g, i, seconds)
                    row["ranked"] = ranked
                    collected[name].append(row)
                current = candidate_identity(collected[VARIANTS[0]][-1]["ranked"])
                previous = candidate_identity(campaign["results"][i]["ranked"])
                identical_orders += current == previous
                identical_sets += set(current) == set(previous)
                print(f"{spec['name']}: candidates {i + 1}/{len(gold)}", flush=True)
    assert_baseline(_aggregate(collected[VARIANTS[0]]), campaign["summary"])
    return collected, {
        "campaign_result": str(campaign_path.relative_to(directory)),
        "campaign_sha256": digest(campaign_path),
        "campaign_summary": campaign["summary"],
        "matching_candidate_orders": identical_orders,
        "matching_candidate_sets": identical_sets,
        "embedding_baseline_passed": True,
    }


def measure_reranking(
    server: Server,
    rows: list[dict[str, Any]],
    gold: list[dict[str, Any]],
    budget: int,
    label: str,
    private_path: Path,
) -> dict[str, Any]:
    results = []
    with private_path.open("w") as stream:
        for row in rows:
            i = row["query_id"]
            documents = rerank_documents(row["ranked"], budget)
            started = time.monotonic()
            scores = server.rerank(gold[i]["query"], documents)
            elapsed = time.monotonic() - started
            ranked = [
                p
                for _, p in sorted(
                    zip(scores, row["ranked"], strict=True),
                    key=lambda pair: pair[0],
                    reverse=True,
                )
            ]
            result = score_ranking(ranked, gold[i], i, row["seconds"], elapsed)
            results.append(result)
            stream.write(
                json.dumps(
                    {**result, "scores_in_input_order": scores, "ranked": ranked}
                )
                + "\n"
            )
            stream.flush()
            print(f"{label}: {i + 1}/{len(rows)} ({elapsed:.2f}s)", flush=True)
    return summarize(results)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", choices=MODELS, default=MODELS)
    parser.add_argument(
        "--rerankers", nargs="+", choices=RERANKERS, default=RERANKERS[:1]
    )
    parser.add_argument("--out", type=Path, default=ROOT / "probe-rerank-fixed.json")
    args = parser.parse_args()
    directory = CACHE / SNAPSHOT
    snapshot = json.loads((directory / "snapshot.json").read_text())
    if snapshot["max_chars"] != 8000:
        raise ValueError("expected the 8000-character full snapshot")
    gold = snapshot["gold"]
    specs = tomllib.loads((ROOT / "models.toml").read_text())
    models = {s["name"]: s for s in specs["models"]}
    rerankers = {s["name"]: s for s in specs["rerankers"]}
    private = Path(tempfile.mkdtemp(prefix="rerank-fixed-", dir=CACHE))
    report: dict[str, Any] = {
        "snapshot": SNAPSHOT,
        "snapshot_sha256": digest(directory / "snapshot.json"),
        "max_chars": 8000,
        "queries": len(gold),
        "passage_labels": LABEL_NOTE,
        "development_data": True,
        "private_artifacts": str(private),
        "source_sha256": {
            p.name: digest(p)
            for p in [
                Path(__file__),
                ROOT / "probe_fusion.py",
                ROOT / "compare_models.py",
                ROOT / "benchmark_runtime.py",
            ]
        },
        "latency_note": "Startup excluded. Separate model lifecycles; OR retrieval conservatively includes the measured AND lookup too. Fusion/serialization time excluded. Each variant is reranked independently; no score reuse.",
        "models": {},
        "complete": False,
    }

    def save() -> None:
        args.out.write_text(json.dumps(report, indent=2) + "\n")

    candidates = {}
    for name in args.models:
        with tempfile.TemporaryDirectory(prefix="engram-probe-server-") as scratch:
            rows, validation = collect_candidates(
                models[name], directory, gold, Path(scratch)
            )
        candidates[name] = rows
        (private / f"{name}-candidates.json").write_text(json.dumps(rows))
        report["models"][name] = {
            "embedding": models[name],
            "validation": validation,
            "fusion": {
                variant: summarize(
                    [{k: v for k, v in r.items() if k != "ranked"} for r in values]
                )
                for variant, values in rows.items()
            },
            "rerankers": {},
        }
        save()
    for reranker in args.rerankers:
        with tempfile.TemporaryDirectory(prefix="engram-probe-server-") as scratch:
            require_free_port()
            with Server(rerankers[reranker], Path(scratch), reranking=True) as server:
                smoke = server.rerank(
                    "How do plants make food using sunlight?",
                    [
                        "Paris is the capital of France.",
                        "Plants use photosynthesis to convert sunlight into chemical energy.",
                    ],
                )
                if smoke[1] - smoke[0] <= 0.05:
                    raise ValueError(f"relevance sanity check failed: {smoke}")
                for name in args.models:
                    campaign_path = unique_result(
                        directory, f"{reranker}-on-{name}-*/result.json"
                    )
                    campaign = json.loads(campaign_path.read_text())
                    output: dict[str, Any] = {
                        "spec": rerankers[reranker],
                        "smoke_scores": smoke,
                        "campaign_summary": campaign["summary"],
                        "campaign_latency_seconds": campaign["latency_seconds"],
                        "campaign_sha256": digest(campaign_path),
                        "variants": {},
                    }
                    report["models"][name]["rerankers"][reranker] = output
                    # First rerun the campaign's exact saved inputs, then gate new variants.
                    embedding_path = (
                        directory
                        / report["models"][name]["validation"]["campaign_result"]
                    )
                    original = json.loads(embedding_path.read_text())["results"]
                    baseline = measure_reranking(
                        server,
                        original,
                        gold,
                        8000,
                        f"{reranker}/{name}/campaign",
                        private / f"{reranker}-{name}-campaign.jsonl",
                    )
                    output["baseline"] = baseline
                    save()
                    assert_baseline(baseline["summary"], campaign["summary"])
                    output["baseline_passed"] = True
                    for variant in VARIANTS:
                        measured = measure_reranking(
                            server,
                            candidates[name][variant],
                            gold,
                            8000,
                            f"{reranker}/{name}/{variant}",
                            private / f"{reranker}-{name}-{variant}.jsonl",
                        )
                        output["variants"][variant] = measured
                        print(
                            json.dumps(
                                {
                                    "embedding": name,
                                    "reranker": reranker,
                                    "variant": variant,
                                    "all": measured["summary"]["all"],
                                    "latency": measured["latency_seconds"],
                                }
                            ),
                            flush=True,
                        )
                        save()
    report["complete"] = True
    save()


if __name__ == "__main__":
    main()
