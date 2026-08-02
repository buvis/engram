"""Engram CLI entry point."""

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

from engram.client import load_config
from engram.corpora import GITA_REPOS_CSV
from engram.indexer import index
from engram.query import query
from engram.store import DEFAULT_DB_PATH, Scope, StoreModelMismatchError, open_store

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

    return parser


def _run_query(args: argparse.Namespace) -> int:
    scope = _resolve_scope(args.scope)
    if scope is None:
        print(_NOT_IN_REPO_MSG, file=sys.stderr)
        return 1

    config = load_config()
    store = open_store()
    try:
        pointers = query(store, config, args.text, scope, corpus=args.corpus, k=args.k)
    except StoreModelMismatchError as e:
        print(f"{e}; run `engram index --rebuild` to rebuild the store", file=sys.stderr)
        return 1

    for p in pointers:
        print(f"{p.rank}\t{p.score}\t{p.path}:{p.line_start}-{p.line_end}\t{p.heading}")
    return 0


def _run_index(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.rebuild:
        if args.scope is not None or args.corpus is not None:
            parser.error("--rebuild cannot be combined with --scope or --corpus")

        tmp_path = Path(str(DEFAULT_DB_PATH) + ".rebuild-tmp")
        config = load_config()
        try:
            tmp_store = open_store(tmp_path)
            index(tmp_store, config, Scope("portfolio", None))
        except Exception as e:
            print(f"rebuild failed: {e}", file=sys.stderr)
            return 1

        os.replace(tmp_path, DEFAULT_DB_PATH)
        return 0

    scope = _resolve_scope(args.scope or "repo")
    if scope is None:
        print(_NOT_IN_REPO_MSG, file=sys.stderr)
        return 1

    config = load_config()
    store = open_store()
    try:
        index(store, config, scope, corpus=args.corpus)
    except StoreModelMismatchError as e:
        print(f"{e}; run `engram index --rebuild` to rebuild the store", file=sys.stderr)
        return 1

    return 0


def _run_status(args: argparse.Namespace) -> int:
    scope = _resolve_scope(args.scope or "repo")
    if scope is None:
        print(_NOT_IN_REPO_MSG, file=sys.stderr)
        return 1

    store = open_store()
    report = store.status(scope)
    for corpus, cs in report.per_corpus.items():
        print(f"{corpus}\t{cs.row_count}\tstale={len(cs.stale_files)}\tdead={cs.dead_rows}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "query":
        return _run_query(args)
    if args.command == "index":
        return _run_index(args, parser)
    return _run_status(args)
