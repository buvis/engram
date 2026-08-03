"""Engram CLI entry point."""

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

from engram import corpora, symbols
from engram.client import EngramConfig, embed, load_config, resolve_pinned_entry
from engram.corpora import GITA_REPOS_CSV, enumerate_corpora
from engram.findings import FINDINGS_CORPUS
from engram.harvest import harvest
from engram.indexer import index
from engram.query import query
from engram.store import (
    DEFAULT_DB_PATH,
    Chunk,
    ChunkWithVector,
    Scope,
    Store,
    StoreModelMismatchError,
    open_store,
)

_NOT_IN_REPO_MSG = "not inside a registered repo; pass --scope portfolio instead"


def _resolve_repo_name() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    toplevel = result.stdout.strip()
    if not GITA_REPOS_CSV.exists():
        return None

    with GITA_REPOS_CSV.open(newline="") as f:
        for row in csv.reader(f):
            if len(row) >= 2 and row[0] == toplevel:
                return row[1]
    return None


def _resolve_scope(kind: str) -> Scope | None:
    if kind == "portfolio":
        return Scope("portfolio", None)
    repo_name = _resolve_repo_name()
    if repo_name is None:
        return None
    return Scope("repo", repo_name)


def _repo_scope_error_msg() -> str:
    if not GITA_REPOS_CSV.exists():
        return f"{GITA_REPOS_CSV} not found; register repos with gita first"
    return _NOT_IN_REPO_MSG


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engram")
    subparsers = parser.add_subparsers(dest="command", required=True)

    query_parser = subparsers.add_parser("query")
    query_parser.add_argument("--scope", choices=["repo", "portfolio"], required=True)
    query_parser.add_argument("--corpus", default=None)
    query_parser.add_argument("-k", "--k", type=int, default=5)
    query_parser.add_argument("text")

    index_parser = subparsers.add_parser("index")
    index_parser.add_argument("--scope", choices=["repo", "portfolio"], default=None)
    index_parser.add_argument("--corpus", default=None)
    index_parser.add_argument("--rebuild", action="store_true")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--scope", choices=["repo", "portfolio"], default=None)

    harvest_parser = subparsers.add_parser("harvest")
    harvest_parser.add_argument("paths", nargs="+", type=Path)

    return parser


def _run_query(args: argparse.Namespace) -> int:
    scope = _resolve_scope(args.scope)
    if scope is None:
        print(_repo_scope_error_msg(), file=sys.stderr)
        return 1

    if args.k <= 0:
        print("-k must be positive", file=sys.stderr)
        return 1

    config = load_config()
    store = open_store()
    try:
        pointers = query(store, config, args.text, scope, corpus=args.corpus, k=args.k)
    except StoreModelMismatchError as e:
        print(
            f"{e}; run `engram index --rebuild` to rebuild the store",
            file=sys.stderr,
        )
        return 1

    for p in pointers:
        print(
            f"{p.rank}\t{p.score:.4f}\t{p.path}:{p.line_start}-{p.line_end}\t{p.heading}",
        )
        if p.body is not None:
            print(p.body)
    return 0


def _run_harvest(args: argparse.Namespace) -> int:
    config = load_config()
    store = open_store()
    report = harvest(store, config, args.paths)
    for r in report.results:
        line = f"{r.path}\t{r.outcome}\t{r.records_count}"
        if r.error is not None:
            line += f"\t{r.error}"
        print(line)
    return 1 if report.any_failed else 0


def _print_missing(missing: list[str], scope: Scope, corpus: str | None = None) -> None:
    if scope.kind == "repo":
        missing = [m for m in missing if m.endswith(f":{scope.repo}")]
    if corpus is not None:
        missing = [m for m in missing if m.startswith(f"{corpus}:")]
    for m in missing:
        print(m)


def _preserve_findings(tmp_store: Store, config: EngramConfig) -> None:
    findings_chunks: list[Chunk] = []
    if DEFAULT_DB_PATH.exists():
        live_store = open_store(DEFAULT_DB_PATH)
        try:
            findings_chunks = live_store.chunks_for_corpus(FINDINGS_CORPUS)
        finally:
            live_store.conn.close()

    if findings_chunks:
        entry = resolve_pinned_entry(config)
        by_source: dict[str, list[Chunk]] = {}
        for c in findings_chunks:
            by_source.setdefault(c.path, []).append(c)
        for path, chunks in by_source.items():
            texts = [c.text_for_embedding for c in chunks]
            vectors = embed(texts, entry)
            items = [
                ChunkWithVector(chunk=c, vector=v) for c, v in zip(chunks, vectors)
            ]
            tmp_store.replace_chunks_for_source(FINDINGS_CORPUS, path, items)


def _run_index(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.rebuild:
        if args.scope is not None or args.corpus is not None:
            parser.error("--rebuild cannot be combined with --scope or --corpus")

        tmp_path = Path(str(DEFAULT_DB_PATH) + ".rebuild-tmp")
        tmp_path.unlink(missing_ok=True)
        config = load_config()
        try:
            tmp_store = open_store(tmp_path)
            report = index(tmp_store, config, Scope("portfolio", None))
        except Exception as e:
            print(f"rebuild failed: {e}", file=sys.stderr)
            return 1

        try:
            _preserve_findings(tmp_store, config)
        except Exception as e:
            tmp_store.conn.close()
            tmp_path.unlink(missing_ok=True)
            print(f"rebuild failed: {e}", file=sys.stderr)
            return 1

        tmp_store.conn.close()
        os.replace(tmp_path, DEFAULT_DB_PATH)
        _print_missing(report.corpora_missing, Scope("portfolio", None))
        return 0

    scope = _resolve_scope(args.scope or "repo")
    if scope is None:
        print(_repo_scope_error_msg(), file=sys.stderr)
        return 1

    config = load_config()
    store = open_store()
    try:
        report = index(store, config, scope, corpus=args.corpus)
    except StoreModelMismatchError as e:
        print(
            f"{e}; run `engram index --rebuild` to rebuild the store",
            file=sys.stderr,
        )
        return 1
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1

    _print_missing(report.corpora_missing, scope, args.corpus)
    return 0


def _run_status(args: argparse.Namespace) -> int:
    scope = _resolve_scope(args.scope or "repo")
    if scope is None:
        print(_repo_scope_error_msg(), file=sys.stderr)
        return 1

    store = open_store()
    report = store.status(scope)
    exit_code = 0
    for corpus, cs in report.per_corpus.items():
        print(
            f"{corpus}\t{cs.row_count}\tstale={len(cs.stale_files)}\tdead={cs.dead_rows}",
        )
        if cs.stale_files or cs.dead_rows > 0:
            exit_code = 1

    try:
        list(enumerate_corpora())
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1

    skipped = symbols.count_skipped()
    if skipped > 0:
        print(f"code\tskipped={skipped}")

    _print_missing(corpora.missing_dirs, scope)

    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "query":
        return _run_query(args)
    if args.command == "index":
        return _run_index(args, parser)
    if args.command == "harvest":
        return _run_harvest(args)
    return _run_status(args)
