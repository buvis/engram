"""Rerank saved embedding candidates without reloading the embedding models."""

import argparse
import hashlib
import json
import statistics
import time
import tomllib
from pathlib import Path
from typing import Any

from eval.benchmark_runtime import Server
from eval.compare_models import CACHE, ROOT, _aggregate, metrics


def rerank(
    spec: dict[str, Any],
    result_path: Path,
    directory: Path,
    snapshot: dict[str, Any],
    server_type: type = Server,
) -> None:
    original = json.loads(result_path.read_text())
    signature = hashlib.sha256(
        result_path.read_bytes() + json.dumps(spec, sort_keys=True).encode()
    ).hexdigest()[:12]
    target = directory / f"{spec['name']}-on-{original['spec']['name']}-{signature}"
    target.mkdir(exist_ok=True)
    if (target / "result.json").exists():
        print(f"{target.name}: already complete", flush=True)
        return
    completed = {}
    cache = target / "queries.jsonl"
    if cache.exists():
        for line in cache.read_text().splitlines():
            row = json.loads(line)
            completed[row["query_id"]] = row
    with server_type(spec, target, reranking=True) as server:
        smoke = server.rerank(
            "How do plants make food using sunlight?",
            [
                "Paris is the capital of France.",
                "Plants use photosynthesis to convert sunlight into chemical energy.",
            ],
        )
        if not smoke[1] - smoke[0] > 0.05:
            raise ValueError(f"reranker failed relevance sanity check: {smoke}")
        for row in original["results"]:
            i = row["query_id"]
            if i in completed:
                continue
            gold = snapshot["gold"][i]
            documents = [
                f"{p['heading']}\n{p['path']}\n{p['body']}"[: snapshot["max_chars"]]
                for p in row["ranked"]
            ]
            start = time.monotonic()
            scores = server.rerank(gold["query"], documents)
            seconds = time.monotonic() - start
            ordered = sorted(
                zip(scores, row["ranked"]), key=lambda pair: pair[0], reverse=True
            )
            ranked = [
                {
                    **p,
                    "retrieval_rank": p["rank"],
                    "rank": rank + 1,
                    "rerank_score": score,
                }
                for rank, (score, p) in enumerate(ordered)
            ]
            result = {
                "query_id": i,
                "corpus": gold["corpus"],
                "metrics": metrics(ranked, gold),
                "rerank_seconds": seconds,
                "seconds": seconds + row["seconds"],
                "candidate_count": len(documents),
                "ranked": ranked,
            }
            completed[i] = result
            with cache.open("a") as stream:
                stream.write(json.dumps(result) + "\n")
            print(
                f"{spec['name']} on {original['spec']['name']}: query {i + 1}/{len(original['results'])} ({seconds:.2f}s)",
                flush=True,
            )
    results = [completed[i] for i in sorted(completed)]
    latencies = sorted(r["seconds"] for r in results)
    report = {
        "spec": spec,
        "embedding": original["spec"],
        "snapshot": str(directory),
        "summary": _aggregate(results),
        "results": results,
        "smoke_scores": smoke,
        "peak_server_rss_kib": server.peak_rss_kib,
        "memory_sampling_error": server.memory_sampling_error,
        "runtime_allocation_lines": server.allocation_lines(),
        "latency_seconds": {
            "median": statistics.median(latencies),
            "p95": latencies[int((len(latencies) - 1) * 0.95)],
        },
    }
    (target / "result.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                "reranker": spec["name"],
                "embedding": original["spec"]["name"],
                "summary": report["summary"],
                "latency": report["latency_seconds"],
            }
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    directory = Path(
        (CACHE / ("full.txt" if args.full else "screen.txt")).read_text().strip()
    )
    snapshot = json.loads((directory / "snapshot.json").read_text())
    specs = tomllib.loads((ROOT / "models.toml").read_text())["rerankers"]
    for spec in specs:
        for name in args.models:
            paths = sorted(
                directory.glob(f"{name}-*/result.json"), key=lambda p: p.stat().st_mtime
            )
            paths = [p for p in paths if "embedding" not in json.loads(p.read_text())]
            if not paths:
                raise ValueError(f"no completed embedding result for {name}")
            rerank(spec, paths[-1], directory, snapshot)


if __name__ == "__main__":
    main()
