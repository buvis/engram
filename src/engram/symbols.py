"""Code Corpus: enumerate git-tracked repo files and chunk their symbols."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from fnmatch import fnmatchcase
from pathlib import Path

from tree_sitter_language_pack import ProcessConfig, detect_language_from_path, process

from engram import corpora
from engram.client import load_corpus_settings
from engram.corpora import GITA_REPOS_CSV, CorpusFile
from engram.store import Chunk

skipped_files: list[str] = []
excluded_files: list[str] = []
EXCLUDED_SEGMENTS = {"node_modules", "vendor", "dist", "build", ".venv", "third_party"}


def is_excluded(path: Path, exclude_globs: tuple[str, ...] = ()) -> bool:
    if EXCLUDED_SEGMENTS.intersection(path.parts) or fnmatchcase(path.name, "*.min.*"):
        return True
    if any(fnmatchcase(path.as_posix(), glob) for glob in exclude_globs):
        return True
    try:
        with path.open(errors="replace") as source:
            return any(len(line.rstrip("\r\n")) > 1000 for line in source)
    except OSError:
        # Let the indexer report the failed read and retain the old rows.
        return False


def enumerate(
    repos_csv: Path = GITA_REPOS_CSV,
    *,
    exclude_globs: tuple[str, ...] | None = None,
) -> Iterator[CorpusFile]:
    skipped_files.clear()
    excluded_files.clear()
    if exclude_globs is None:
        exclude_globs, _ = load_corpus_settings()

    for repo_path, name in corpora.read_repos_csv(repos_csv):
        result = subprocess.run(
            ["git", "-C", repo_path, "ls-files"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            corpora.missing_dirs.append(f"code:{name}")
            continue

        # A repo with unmerged index entries lists the path once per stage;
        # duplicates would collide on the chunks unique key.
        for rel_path in dict.fromkeys(result.stdout.splitlines()):
            file_path = Path(repo_path) / rel_path
            if file_path.is_file():
                if any(fnmatchcase(rel_path, g) for g in exclude_globs) or is_excluded(
                    file_path, exclude_globs
                ):
                    excluded_files.append(str(file_path))
                    continue
                yield CorpusFile("code", name, file_path)


def chunk(path: Path, repo: str, content_hash: str) -> list[Chunk]:
    language = detect_language_from_path(str(path))
    if language is None:
        skipped_files.append(str(path))
        return []

    # Let the indexer count and retry failures. Returning [] would persist a
    # successful-empty result and suppress retries until the source changes.
    source = path.read_text(errors="replace")

    if not source.strip():
        return []

    result = process(source, ProcessConfig(language, structure=True))
    lines = source.splitlines()

    chunks: list[Chunk] = []
    chunk_ordinal = 1

    def _walk(items, named_ancestor: bool = False) -> None:
        nonlocal chunk_ordinal
        for item in items:
            kind = str(item.kind)
            if item.name is None and named_ancestor:
                _walk(item.children, named_ancestor=True)
                continue
            chunks.append(
                Chunk(
                    corpus="code",
                    repo=repo,
                    doc_type=kind.lower(),
                    path=str(path),
                    heading=f"{kind} {item.name if item.name is not None else '(anonymous)'}",
                    body="\n".join(
                        lines[item.span.start_line : item.span.end_line + 1]
                    ),
                    line_start=item.span.start_line + 1,
                    line_end=item.span.end_line + 1,
                    content_hash=content_hash,
                    chunk_ordinal=chunk_ordinal,
                ),
            )
            chunk_ordinal += 1
            _walk(item.children, named_ancestor or item.name is not None)

    _walk(result.structure)

    return chunks


def count_skipped(repos_csv: Path = GITA_REPOS_CSV) -> int:
    return sum(
        1
        for cf in enumerate(repos_csv=repos_csv)
        if detect_language_from_path(str(cf.path)) is None
    )


def count_excluded() -> int:
    """Count exclusions from the last enumeration (also run by count_skipped)."""
    return len(excluded_files)
