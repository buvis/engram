"""Code Corpus: enumerate git-tracked repo files and chunk their symbols."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

from tree_sitter_language_pack import ProcessConfig, detect_language_from_path, process

from engram import corpora
from engram.corpora import GITA_REPOS_CSV, CorpusFile
from engram.store import Chunk

skipped_files: list[str] = []


def enumerate(repos_csv: Path = GITA_REPOS_CSV) -> Iterator[CorpusFile]:
    skipped_files.clear()

    for repo_path, name in corpora.read_repos_csv(repos_csv):
        result = subprocess.run(
            ["git", "-C", repo_path, "ls-files"], capture_output=True, text=True,
        )
        if result.returncode != 0:
            corpora.missing_dirs.append(f"code:{name}")
            continue

        for rel_path in result.stdout.splitlines():
            if rel_path:
                yield CorpusFile("code", name, Path(repo_path) / rel_path)


def chunk(path: Path, repo: str, content_hash: str) -> list[Chunk]:
    language = detect_language_from_path(str(path))
    if language is None:
        skipped_files.append(str(path))
        return []

    try:
        source = path.read_text(errors="replace")
    except OSError:
        skipped_files.append(str(path))
        return []

    if not source.strip():
        return []

    result = process(source, ProcessConfig(language, structure=True))
    lines = source.splitlines()

    chunks: list[Chunk] = []
    chunk_ordinal = 1

    def _walk(items):
        nonlocal chunk_ordinal
        for item in items:
            kind = str(item.kind)
            chunks.append(
                Chunk(
                    corpus="code",
                    repo=repo,
                    doc_type=kind.lower(),
                    path=str(path),
                    heading=f"{kind} {item.name}",
                    body="\n".join(lines[item.span.start_line : item.span.end_line + 1]),
                    line_start=item.span.start_line + 1,
                    line_end=item.span.end_line + 1,
                    content_hash=content_hash,
                    chunk_ordinal=chunk_ordinal,
                ),
            )
            chunk_ordinal += 1
            _walk(item.children)

    _walk(result.structure)

    return chunks


def count_skipped(repos_csv: Path = GITA_REPOS_CSV) -> int:
    return sum(
        1
        for cf in enumerate(repos_csv=repos_csv)
        if detect_language_from_path(str(cf.path)) is None
    )
