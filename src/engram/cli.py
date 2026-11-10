"""Engram CLI entry point."""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from engram import corpora, symbols, transcripts
from engram.client import (
    EmbeddingModelIdentityError,
    EmbeddingPreflightError,
    EmbeddingServerError,
    EngramConfig,
    embed,
    load_config,
    resolve_pinned_entry,
)
from engram.corpora import GITA_REPOS_CSV, enumerate_corpora
from engram.findings import FINDINGS_CORPUS
from engram.harvest import _resolve_repo_for_path, harvest
from engram.indexer import index, reembed_code
from engram.memory import MEMORY_SUBDIR, check_directory, memory_dir
from engram.pack import build
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
    # _resolve_repo_for_path runs git with cwd=path.parent and checks
    # path.resolve() for the ~/.claude sentinel; append a synthetic filename
    # so both land on the process cwd.
    return _resolve_repo_for_path(Path.cwd() / "_", repos_csv=GITA_REPOS_CSV)


def _resolve_scope(kind: str) -> Scope | None:
    if kind == "portfolio":
        return Scope("portfolio", None)
    repo_name = _resolve_repo_name()
    if repo_name is None:
        return None
    return Scope("repo", repo_name)


def _repo_scope_error_msg(mention_scope: bool = True) -> str:
    if not GITA_REPOS_CSV.exists():
        return f"{GITA_REPOS_CSV} not found; register repos with gita first"
    if mention_scope:
        return _NOT_IN_REPO_MSG
    return f"not inside a registered repo; register it in {GITA_REPOS_CSV}"


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
    index_parser.add_argument(
        "--reembed-code",
        action="store_true",
        help="regenerate vectors of indexed code chunks without a full rebuild",
    )

    lookup_parser = subparsers.add_parser("lookup")
    lookup_mode = lookup_parser.add_mutually_exclusive_group(required=True)
    lookup_mode.add_argument("--name")
    lookup_mode.add_argument("--file", type=Path)
    lookup_parser.add_argument("--scope", choices=["repo", "portfolio"])
    lookup_parser.add_argument("--repo")

    status_parser = subparsers.add_parser(
        "status",
        description=(
            "Exit 1 for degraded stale files, dead rows, or missing indexed sources; "
            "recently modified transcripts are reported as in-flight and do not fail status."
        ),
    )
    status_parser.add_argument("--scope", choices=["repo", "portfolio"], default=None)

    harvest_parser = subparsers.add_parser("harvest")
    harvest_parser.add_argument("paths", nargs="+", type=Path)

    pack_parser = subparsers.add_parser("pack")
    pack_parser.add_argument("--cycle", default=None)
    pack_parser.add_argument("--diff", default=None)
    pack_parser.add_argument("--prd", default=None)
    pack_parser.add_argument("--capsule", default=None)

    _add_memory_parser(subparsers)

    return parser


def _add_memory_parser(subparsers: argparse._SubParsersAction) -> None:
    memory_parser = subparsers.add_parser("memory")
    memory_sub = memory_parser.add_subparsers(dest="memory_command", required=True)
    check_parser = memory_sub.add_parser("check")
    check_parser.add_argument("path", nargs="?", type=Path, default=None)


def _run_memory_check(args: argparse.Namespace) -> int:
    if args.path is None:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(
                "engram memory check: not inside a git worktree; pass PATH",
                file=sys.stderr,
            )
            return 1
        target = memory_dir(Path(result.stdout.strip()))
    else:
        resolved = args.path.resolve()
        if resolved.parts[-len(MEMORY_SUBDIR) :] == MEMORY_SUBDIR:
            target = resolved
        else:
            target = memory_dir(resolved)
    lines = check_directory(target)
    for line in lines:
        print(line)
    return 1 if lines else 0


def _run_lookup(args: argparse.Namespace) -> int:
    if args.name is not None:
        if not args.scope:
            print("lookup --name requires --scope", file=sys.stderr)
            return 1
        scope = _resolve_scope(args.scope)
        if scope is None:
            print(_repo_scope_error_msg(), file=sys.stderr)
            return 1
        if args.repo:
            if scope.kind == "repo" and args.repo != scope.repo:
                print("--repo conflicts with the current repo scope", file=sys.stderr)
                return 1
            scope = Scope("repo", args.repo)
        chunks = open_store().lookup_by_name(args.name, scope)
    else:
        if args.scope or args.repo:
            print("lookup --file does not accept --scope or --repo", file=sys.stderr)
            return 1
        resolved = _resolve_pack_repo()
        if resolved is None:
            return 1
        _, root = resolved
        chunks = open_store().lookup_by_path(str((root / args.file).resolve()))
    if not chunks:
        print("no symbol matched", file=sys.stderr)
        return 1
    for chunk in chunks:
        print(f"{chunk.path}:{chunk.line_start}-{chunk.line_end}\t{chunk.heading}")
    return 0


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
    except (EmbeddingServerError, EmbeddingPreflightError) as e:
        print(str(e), file=sys.stderr)
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


def _print_failed(failed: list[str]) -> None:
    for path in failed:
        print(f"failed (existing rows kept): {path}", file=sys.stderr)


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
        _print_failed(report.failed_sources)
        return 0

    if args.reembed_code:
        if args.scope is not None or args.corpus is not None:
            parser.error("--reembed-code cannot be combined with --scope or --corpus")
        try:
            count = reembed_code(open_store(), load_config())
        except StoreModelMismatchError as e:
            print(
                f"{e}; run `engram index --rebuild` to rebuild the store",
                file=sys.stderr,
            )
            return 1
        except (EmbeddingServerError, EmbeddingPreflightError) as e:
            print(str(e), file=sys.stderr)
            return 1
        print(f"re-embedded {count} code chunks")
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
    except (FileNotFoundError, EmbeddingServerError, EmbeddingPreflightError) as e:
        print(str(e), file=sys.stderr)
        return 1

    _print_missing(report.corpora_missing, scope, args.corpus)
    _print_failed(report.failed_sources)
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
        in_flight = (
            f"\tin-flight={len(cs.in_flight_files)}" if corpus == "transcripts" else ""
        )
        print(
            f"{corpus}\t{cs.row_count}\tstale={len(cs.stale_files)}{in_flight}\tdead={cs.dead_rows}",
        )
        if cs.stale_files or cs.dead_rows > 0:
            exit_code = 1

    try:
        list(enumerate_corpora())
        # One next() is enough: enumerate() raises for a missing cellar root
        # before yielding anything, so this fails loud without walking ~1,800
        # transcript files on every status call.
        next(transcripts.enumerate(), None)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1

    skipped = symbols.count_skipped()
    if skipped > 0:
        print(f"code\tskipped={skipped}")
    excluded = symbols.count_excluded()
    if excluded > 0:
        print(f"code\texcluded={excluded}")

    _print_missing(corpora.missing_dirs, scope)
    if any(
        item.startswith("code:")
        and (scope.kind == "portfolio" or item == f"code:{scope.repo}")
        for item in corpora.missing_dirs
    ):
        exit_code = 1

    return exit_code


def _resolve_pack_repo() -> tuple[str, Path] | None:
    scope = _resolve_scope("repo")
    if scope is None:
        print(_repo_scope_error_msg(mention_scope=False), file=sys.stderr)
        return None

    repo_name = scope.repo
    toplevel_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )
    if toplevel_result.returncode != 0:
        print("engram pack must run inside a git worktree", file=sys.stderr)
        return None
    repo_root = Path(toplevel_result.stdout.strip())
    return repo_name, repo_root


def _resolve_pack_diff(
    args: argparse.Namespace,
    repo_root: Path,
    out_dir: Path,
) -> tuple[Path, str, str | None] | None:
    if args.cycle is not None:
        cycle_slug = re.sub(r"[^A-Za-z0-9_-]", "-", args.cycle)
        diff_path = out_dir / f"review-diff-{cycle_slug}.diff"
        if not diff_path.exists():
            print(f"no staged diff found at {diff_path}", file=sys.stderr)
            return None
        return diff_path, cycle_slug, None

    range_str = args.diff
    range_match = re.fullmatch(r"(.*?)\.{2,3}(.*)", range_str)
    if range_match is None:
        print(
            f"--diff must be in <base>..<head> form, got {range_str!r}",
            file=sys.stderr,
        )
        return None
    _, head = range_match.groups()
    if range_str.startswith("-") or head.startswith("-"):
        bad = range_str if range_str.startswith("-") else head
        print(
            f"--diff range must not start with '-', got {bad!r}",
            file=sys.stderr,
        )
        return None
    id_ = re.sub(r"[^A-Za-z0-9_-]", "-", range_str)
    source_ref = head or "HEAD"
    result = subprocess.run(
        ["git", "-C", str(repo_root), "diff", range_str, "--"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout:
        print(f"git diff {range_str} failed or produced no output", file=sys.stderr)
        return None
    diff_path = out_dir / f"engram-pack-diff-{id_}.diff"
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text(result.stdout)
    return diff_path, id_, source_ref


def _resolve_pack_prd_and_capsule(
    args: argparse.Namespace,
    repo_root: Path,
) -> tuple[Path | None, Path | None]:
    prd_path: Path | None = None
    if args.prd is not None:
        prd_path = Path(args.prd)
    else:
        wip_dir = repo_root / "docs" / "dev" / "project-management" / "prds" / "wip"
        if wip_dir.is_dir():
            prd_files = list(wip_dir.glob("*.md"))
            if len(prd_files) == 1:
                prd_path = prd_files[0]

    capsule_path: Path | None = None
    if args.capsule is not None:
        capsule_path = Path(args.capsule)
    else:
        default_capsule = (
            repo_root
            / "docs"
            / "dev"
            / "project-management"
            / "meta"
            / "project-capsule.md"
        )
        if default_capsule.exists():
            capsule_path = default_capsule

    return prd_path, capsule_path


def _run_pack(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.cycle is not None and args.diff is not None:
        parser.error("--cycle and --diff are mutually exclusive")
    if args.cycle is None and args.diff is None:
        parser.error("exactly one of --cycle or --diff is required")

    try:
        repo = _resolve_pack_repo()
        if repo is None:
            return 1
        repo_name, repo_root = repo
        out_dir = repo_root / "docs" / "dev" / "tmp"
        diff_resolved = _resolve_pack_diff(args, repo_root, out_dir)
        if diff_resolved is None:
            return 1
        diff_path, id_, source_ref = diff_resolved
        prd_path, capsule_path = _resolve_pack_prd_and_capsule(args, repo_root)
        config = load_config()
        store = open_store()
        report = build(
            store,
            config,
            repo_name,
            repo_root,
            id_,
            diff_path,
            source_ref=source_ref,
            prd_path=prd_path,
            capsule_path=capsule_path,
            out_dir=out_dir,
        )
    except StoreModelMismatchError as e:
        print(
            f"{e}; run `engram index --rebuild` to rebuild the store",
            file=sys.stderr,
        )
        return 1

    except (
        OSError,
        ValueError,
        EmbeddingServerError,
        EmbeddingPreflightError,
        EmbeddingModelIdentityError,
    ) as e:
        print(f"engram pack failed: {e}", file=sys.stderr)
        return 1

    print(report.path)
    print(report.total_estimated_tokens)
    print(report.index_report.files_scanned)
    print(report.index_report.chunks_added)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "query":
        return _run_query(args)
    if args.command == "lookup":
        return _run_lookup(args)
    if args.command == "index":
        return _run_index(args, parser)
    if args.command == "harvest":
        return _run_harvest(args)
    if args.command == "pack":
        return _run_pack(args, parser)
    if args.command == "memory":
        return _run_memory_check(args)
    return _run_status(args)
