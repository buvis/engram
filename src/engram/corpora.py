from __future__ import annotations

import csv
import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from engram.memory import memory_dir, memory_files

GITA_REPOS_CSV: Path = Path.home() / ".config" / "gita" / "repos.csv"
CLAUDE_PROJECTS_DIR: Path = Path.home() / ".claude" / "projects"

missing_dirs: list[str] = []
repo_memory_dirs: list[tuple[str, Path]] = []
legacy_shadowed: list[str] = []


@dataclass(frozen=True)
class CorpusFile:
    corpus: str
    repo: str
    path: Path


def _unique_slugs(rows: list[tuple[str, str]]) -> dict[str, tuple[str, str]]:
    # Claude replaces every non-ASCII-alphanumeric character, including dots
    # and underscores. This encoding is lossy: never choose between collisions.
    slug_to_rows: dict[str, set[tuple[str, str]]] = {}
    for repo_path, name in rows:
        slug = re.sub(r"[^a-zA-Z0-9]", "-", repo_path)
        slug_to_rows.setdefault(slug, set()).add((repo_path, name))
    return {
        slug: next(iter(matches))
        for slug, matches in slug_to_rows.items()
        if len(matches) == 1
    }


def _enumerate_memory_corpora(
    projects_dir: Path,
    slug_to_name: dict[str, str],
    skip_slugs: frozenset[str] = frozenset(),
) -> Iterator[CorpusFile]:
    if not projects_dir.is_dir():
        return
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir() or project_dir.name in skip_slugs:
            continue
        memory_dir = project_dir / "memory"
        if not memory_dir.is_dir():
            continue
        project_slug = project_dir.name
        resolved_repo = slug_to_name.get(project_slug, "_unmapped")
        for md_file in sorted(memory_dir.glob("*.md")):
            if md_file.is_file():
                yield CorpusFile("memory", resolved_repo, md_file.resolve())


def _enumerate_repo_corpora(root: Path, name: str) -> Iterator[CorpusFile]:
    # PRD (recursive)
    prds_dir = root / "docs" / "dev" / "project-management" / "prds"
    if prds_dir.is_dir():
        for md_file in sorted(prds_dir.rglob("*.md")):
            if md_file.is_file():
                yield CorpusFile("prd", name, md_file)
    else:
        missing_dirs.append(f"prd:{name}")

    # Decision (single file)
    decisions_file = (
        root / "docs" / "dev" / "project-management" / "meta" / "decisions.md"
    )
    if decisions_file.is_file():
        yield CorpusFile("decision", name, decisions_file)
    else:
        missing_dirs.append(f"decision:{name}")

    # Discovery (non-recursive)
    discovery_dir = root / "docs" / "dev" / "project-management" / "discovery"
    if discovery_dir.is_dir():
        for md_file in sorted(discovery_dir.glob("*.md")):
            if md_file.is_file():
                yield CorpusFile("discovery", name, md_file)
    else:
        missing_dirs.append(f"discovery:{name}")

    # Repository memory (absent dir is not a missing dir)
    repo_memory = memory_dir(root)
    if repo_memory.is_dir():
        repo_memory_dirs.append((name, repo_memory))
    for md_file in memory_files(repo_memory):
        yield CorpusFile("memory", name, md_file)


def read_repos_csv(repos_csv: Path) -> list[tuple[str, str]]:
    """Return [(repo_path, name), ...] from a gita repos.csv, skipping rows with
    fewer than 2 fields. Raises FileNotFoundError with the gita-registration hint
    when repos_csv is missing."""
    if not repos_csv.exists():
        raise FileNotFoundError(
            f"{repos_csv} not found; register repos with gita first"
        )

    rows: list[tuple[str, str]] = []
    text = repos_csv.read_text()
    if text.strip():
        reader = csv.reader(text.splitlines())
        for row in reader:
            if len(row) < 2:
                continue
            rows.append((row[0], row[1]))
    return rows


def enumerate_corpora(
    repos_csv: Path = GITA_REPOS_CSV,
    projects_dir: Path = CLAUDE_PROJECTS_DIR,
) -> Iterator[CorpusFile]:
    missing_dirs.clear()
    repo_memory_dirs.clear()
    legacy_shadowed.clear()

    rows = read_repos_csv(repos_csv)
    unique = _unique_slugs(rows)
    slug_to_name = {slug: name for slug, (_, name) in unique.items()}
    skip_slugs = frozenset(
        slug
        for slug, (repo_path, _) in unique.items()
        if memory_files(memory_dir(Path(repo_path)))
    )
    legacy_shadowed.extend(
        sorted(
            {
                unique[slug][1]
                for slug in skip_slugs
                if any(
                    p.is_file() for p in (projects_dir / slug / "memory").glob("*.md")
                )
            }
        )
    )

    # Memory corpus (once, not per repo)
    yield from _enumerate_memory_corpora(projects_dir, slug_to_name, skip_slugs)

    # Per-repo corpora
    for repo_path, name in rows:
        yield from _enumerate_repo_corpora(Path(repo_path), name)


def hash_source(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}".encode() + b"\0"
    return hashlib.sha1(header + data).hexdigest()
