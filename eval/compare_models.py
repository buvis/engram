"""Resumable model trials over a frozen, private copy of local search material.

Run with `python -m eval.compare_models prepare`, then `... run`.
The screening corpus includes every gold file, lexical hard negatives, and
deterministic random distractors. Its scores are not full-portfolio scores.
"""

import argparse
import hashlib
import inspect
import json
import random
import re
import sqlite3
import statistics
import subprocess
import time
import tomllib
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from engram.client import EmbeddingEntry, EngramConfig, Vector
from engram.corpora import CorpusFile, hash_source
from engram.indexer import _chunk_file
from engram.query import query
from engram.store import Chunk, ChunkWithVector, Scope, open_store
from eval.benchmark_runtime import Server, request

ROOT = Path(__file__).resolve().parent
CACHE = Path.home() / ".cache/engram/compare"
SOURCE = Path.home() / ".local/share/engram/engram.db"
INSTRUCTION = "Given a question, retrieve passages that can help answer the question."
MAX_CHARS = 4000


def format_input(
    style: str, text: str, *, query: bool, corpus: str, title: str = "none"
) -> str:
    if style in {"qwen", "f2"} and query:
        text = f"Instruct: {INSTRUCTION}\nQuery: {text}"
    elif style == "jina":
        text = ("Query: " if query else "Document: ") + text
    elif style == "gemma":
        task = "code retrieval" if corpus == "code" else "search result"
        text = (
            f"task: {task} | query: {text}"
            if query
            else f"title: {title} | text: {text}"
        )
    return text + "<|im_end|>" if style == "f2" else text


def metrics(ranked: list[dict[str, Any]], gold: dict[str, Any]) -> dict[str, float]:
    file_rank = next(
        (i + 1 for i, row in enumerate(ranked) if row["path"] == gold["path"]), 0
    )
    result = {
        "file_hit5": int(0 < file_rank <= 5),
        "file_rr": 1 / file_rank if file_rank else 0.0,
    }
    if "acceptable_starts" in gold:
        rank = next(
            (
                i + 1
                for i, row in enumerate(ranked)
                if row["path"] == gold["path"]
                and row["line_start"] in gold["acceptable_starts"]
            ),
            0,
        )
        result.update(
            passage_hit5=int(0 < rank <= 5), passage_rr=1 / rank if rank else 0.0
        )
    return result


def select_snapshot(
    rows: list[dict[str, Any]],
    gold: list[dict[str, Any]],
    negatives: set[int],
    random_per_corpus: int = 100,
) -> list[dict[str, Any]]:
    targets = {(g["corpus"], g["path"]) for g in gold}
    selected = set(negatives)
    groups: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        groups[row["corpus"]].append(row["id"])
        if (row["corpus"], row["path"]) in targets:
            selected.add(row["id"])
    rng = random.Random(20261101)
    for corpus in sorted(groups):
        ids = sorted(groups[corpus])
        selected.update(rng.sample(ids, min(len(ids), random_per_corpus)))
    return [
        row for row in sorted(rows, key=lambda row: row["id"]) if row["id"] in selected
    ]


def prepare(full: bool = False, max_chars: int = MAX_CHARS) -> Path:
    labels = yaml.safe_load((ROOT / "passage_labels.yaml").read_text())
    gold = yaml.safe_load((ROOT / "goldset.yaml").read_text())
    conn = sqlite3.connect(f"file:{SOURCE}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in conn.execute("SELECT * FROM chunks ORDER BY id")]
        by_source = {
            (g["corpus"], str(Path(g["expected_path"]).resolve())) for g in gold
        }
        repos = {row["path"]: row["repo"] for row in rows}
        # Gold files can move after production indexing. Refresh only in the
        # snapshot, and fail instead of silently scoring an absent gold file.
        rows = [row for row in rows if (row["corpus"], row["path"]) not in by_source]
        next_id = max(row["id"] for row in rows) + 1
        for corpus, path in sorted(by_source):
            source = Path(path)
            repo = repos.get(
                path,
                source.parts[source.parts.index("github.com") + 2]
                if "github.com" in source.parts
                else "engram",
            )
            chunks = _chunk_file(
                CorpusFile(corpus=corpus, repo=repo, path=source), hash_source(source)
            )
            if not chunks:
                raise ValueError(f"gold source has no chunks: {path}")
            for chunk in chunks:
                rows.append({"id": next_id, **asdict(chunk)})
                next_id += 1
        negatives: set[int] = set()
        for g in gold:
            tokens = re.findall(r"[a-zA-Z0-9_]{3,}", g["query"])
            match = " OR ".join(f'"{t}"' for t in tokens)
            negatives.update(
                row[0]
                for row in conn.execute(
                    "SELECT c.id FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.rowid WHERE chunks_fts MATCH ? AND c.corpus=? ORDER BY bm25(chunks_fts) LIMIT 20",
                    (match, g["corpus"]),
                )
            )
    finally:
        conn.close()
    for i, g in enumerate(gold):
        g["path"] = str(Path(g.pop("expected_path")).resolve())
        if i in labels:
            g["acceptable_starts"] = labels[i]
            available = {
                r["line_start"]
                for r in rows
                if r["path"] == g["path"] and r["corpus"] == g["corpus"]
            }
            if not set(labels[i]) <= available:
                raise ValueError(
                    f"passage labels moved for query {i}: {set(labels[i]) - available}"
                )
    all_rows = rows
    if not full:
        rows = select_snapshot(rows, gold, negatives)
    else:
        rows = [r for r in rows if r["corpus"] in {g["corpus"] for g in gold}]
    payload = {
        "mode": "full" if full else "screen",
        "max_chars": max_chars,
        "gold": gold,
        "rows": rows,
        "portfolio_rows": len(all_rows),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    directory = CACHE / hashlib.sha256(encoded).hexdigest()[:16]
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    (directory / "snapshot.json").write_bytes(encoded)
    (directory / "snapshot.json").chmod(0o600)
    (CACHE / ("full.txt" if full else "screen.txt")).write_text(str(directory))
    print(
        json.dumps(
            {
                "snapshot": str(directory),
                "mode": payload["mode"],
                "rows": len(rows),
                "portfolio_rows": len(all_rows),
                "queries": len(gold),
            }
        ),
        flush=True,
    )
    return directory


def _chunk(row: dict[str, Any]) -> Chunk:
    return Chunk(**{k: v for k, v in row.items() if k != "id"})


def _document(spec: dict[str, Any], row: dict[str, Any]) -> str:
    chunk = _chunk(row)
    text = chunk.text_for_embedding[: spec.get("max_chars", MAX_CHARS)]
    return format_input(
        spec["style"],
        text,
        query=False,
        corpus=chunk.corpus,
        title=chunk.heading or Path(chunk.path).name,
    )


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for group in ["all", *sorted({r["corpus"] for r in results})]:
        subset = (
            results if group == "all" else [r for r in results if r["corpus"] == group]
        )
        keys = {k for row in subset for k in row["metrics"]}
        summary[group] = {
            k: statistics.mean(r["metrics"][k] for r in subset if k in r["metrics"])
            for k in sorted(keys)
        }
    return summary


def _embed_documents(
    server: Server, spec: dict[str, Any], rows: list[dict[str, Any]], store: Any
) -> dict[str, Any]:
    done = {
        tuple(row)
        for row in store.conn.execute(
            "SELECT corpus,path,chunk_ordinal,content_hash FROM chunks"
        )
    }
    pending = [
        r
        for r in rows
        if (r["corpus"], r["path"], r["chunk_ordinal"], r["content_hash"]) not in done
    ]
    start = time.monotonic()
    characters = 0
    count = 0
    batch: list[dict[str, Any]] = []
    texts: list[str] = []

    def flush() -> None:
        nonlocal count, characters
        if not batch:
            return
        vectors = server.embed(texts)
        store.upsert_chunks(
            [
                ChunkWithVector(_chunk(row), Vector(vector, spec["id"], len(vector)))
                for row, vector in zip(batch, vectors, strict=True)
            ]
        )
        characters += sum(map(len, texts))
        old_count = count
        count += len(batch)
        if count // 100 != old_count // 100 or count == len(pending):
            print(
                f"{spec['name']}: embedded {count}/{len(pending)} ({time.monotonic() - start:.1f}s)",
                flush=True,
            )
        batch.clear()
        texts.clear()

    for row in pending:
        text = _document(spec, row)
        if sum(map(len, texts)) + len(text) > 30000 or len(batch) == 64:
            flush()
        batch.append(row)
        texts.append(text)
    flush()
    seconds = time.monotonic() - start
    return {
        "new_chunks": len(pending),
        "seconds": seconds,
        "characters": characters,
        "chars_per_second": characters / seconds if seconds else 0,
    }


def run_model(
    spec: dict[str, Any],
    directory: Path,
    snapshot: dict[str, Any],
    retest: bool = False,
) -> None:
    signature = hashlib.sha256(
        json.dumps(
            {
                "spec": spec,
                "max_chars": spec.get("max_chars", MAX_CHARS),
                "inputs": inspect.getsource(format_input)
                + inspect.getsource(_document),
                "version": 1,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:12]
    target = directory / f"{spec['name']}-{signature}"
    target.mkdir(exist_ok=True)
    previous = (
        json.loads((target / "result.json").read_text())
        if (target / "result.json").exists()
        else None
    )
    if previous is not None and not retest:
        print(f"{spec['name']}: using completed result {target}", flush=True)
        return
    store = open_store(target / "index.db")
    report: dict[str, Any] = {
        "spec": spec,
        "snapshot": str(directory),
        "mode": snapshot["mode"],
        "max_chars": spec.get("max_chars", MAX_CHARS),
    }
    try:
        with Server(spec, target) as server:
            if spec["style"] == "f2":
                # llama.cpp must parse EOS as one special token; tokenizer
                # metadata may already add it, in which case do not double it.
                raw = request("/tokenize", {"content": "hello", "add_special": True})[
                    "tokens"
                ]
                explicit = request(
                    "/tokenize",
                    {
                        "content": "hello<|im_end|>",
                        "add_special": True,
                        "parse_special": True,
                    },
                )["tokens"]
                report["eos_probe"] = {"raw": raw, "explicit": explicit}
                if raw[-1] == 151645:
                    spec = {**spec, "style": "qwen"}
                elif explicit[-1] != 151645:
                    raise ValueError(
                        "F2 EOS token is not preserved by this GGUF/runtime"
                    )
            report["indexing"] = _embed_documents(server, spec, snapshot["rows"], store)
            if report["indexing"]["new_chunks"] == 0 and previous:
                report["indexing"] = previous["indexing"]
            entry = EmbeddingEntry(spec["id"], "http://127.0.0.1:18181/v1")
            config = EngramConfig([entry], spec["id"], target / "unused.toml")
            results = []
            for i, gold in enumerate(snapshot["gold"]):
                text = format_input(
                    spec["style"], gold["query"], query=True, corpus=gold["corpus"]
                )
                started = time.monotonic()
                values = server.embed([text])[0]
                vector = Vector(values, spec["id"], len(values))
                pointers = query(
                    store,
                    config,
                    gold["query"],
                    Scope("portfolio", None),
                    corpus=gold["corpus"],
                    k=40,
                    vector=vector,
                    include_body=True,
                )
                seconds = time.monotonic() - started
                ranked = [asdict(p) for p in pointers]
                dense = [
                    asdict(hit.chunk)
                    for hit in store.search_knn(
                        vector, Scope("portfolio", None), gold["corpus"], 40
                    )
                ]
                results.append(
                    {
                        "query_id": i,
                        "corpus": gold["corpus"],
                        "seconds": seconds,
                        "metrics": metrics(ranked, gold),
                        "dense_metrics": metrics(dense, gold),
                        "ranked": ranked,
                    }
                )
            report["results"] = results
            report["summary"] = _aggregate(results)
            report["dense_summary"] = _aggregate(
                [{**r, "metrics": r["dense_metrics"]} for r in results]
            )
            latencies = sorted(r["seconds"] for r in results)
            report["latency_seconds"] = {
                "median": statistics.median(latencies),
                "p95": latencies[int((len(latencies) - 1) * 0.95)],
            }
            report["startup_seconds_including_download"] = server.startup_seconds
        report["peak_server_rss_kib"] = server.peak_rss_kib
        report["memory_sampling_error"] = server.memory_sampling_error
        report["runtime_allocation_lines"] = server.allocation_lines()
        report["benchmark_source_sha256"] = hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest()
        report["swap_after"] = subprocess.run(
            ["sysctl", "vm.swapusage"], capture_output=True, text=True
        ).stdout.strip()
        (target / "result.json").write_text(json.dumps(report, indent=2))
        print(
            json.dumps(
                {
                    "model": spec["name"],
                    "summary": report["summary"],
                    "latency": report["latency_seconds"],
                    "peak_server_rss_kib": server.peak_rss_kib,
                }
            ),
            flush=True,
        )
    finally:
        store.conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "run"])
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--models", nargs="*")
    parser.add_argument(
        "--max-chars",
        type=int,
        choices=[4000, 8000],
        default=4000,
        help="input budget when preparing a snapshot",
    )
    parser.add_argument(
        "--retest",
        action="store_true",
        help="repeat queries using cached document vectors",
    )
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.full, args.max_chars)
        return
    directory = Path(
        (CACHE / ("full.txt" if args.full else "screen.txt")).read_text().strip()
    )
    snapshot = json.loads((directory / "snapshot.json").read_text())
    specs = tomllib.loads((ROOT / "models.toml").read_text())["models"]
    names = {s["name"] for s in specs}
    if args.models and not set(args.models) <= names:
        parser.error(f"unknown model: {set(args.models) - names}")
    failures = 0
    for spec in specs:
        spec = {**spec, "max_chars": snapshot["max_chars"]}
        if args.models and spec["name"] not in args.models:
            continue
        print(f"Starting {spec['name']}", flush=True)
        try:
            run_model(spec, directory, snapshot, args.retest)
        except Exception as error:
            failures += 1
            with (directory / "failures.jsonl").open("a") as stream:
                stream.write(
                    json.dumps({"model": spec["name"], "error": str(error)}) + "\n"
                )
            print(f"FAILED {spec['name']}: {error}", flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
