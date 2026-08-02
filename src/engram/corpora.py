from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

GITA_REPOS_CSV: Path = Path.home() / ".config" / "gita" / "repos.csv"
CLAUDE_PROJECTS_DIR: Path = Path.home() / ".claude" / "projects"

missing_dirs: list[str] = []


@dataclass(frozen=True)
class CorpusFile:
    corpus: str
    repo: str
    path: Path


def _enumerate_memory_corpora(
    projects_dir: Path, slug_to_name: dict[str, str]
) -> Iterator[CorpusFile]:
    if not projects_dir.is_dir():
        return
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        memory_dir = project_dir / "memory"
        if not memory_dir.is_dir():
            continue
        project_slug = project_dir.name
        resolved_repo = slug_to_name.get(project_slug, "_unmapped")
        for md_file in sorted(memory_dir.glob("*.md")):
            if md_file.is_file():
                yield CorpusFile("memory", resolved_repo, md_file)


def _enumerate_repo_corpora(root: Path, name: str) -> Iterator[CorpusFile]:
    # PRD (recursive)
    prds_dir = root / "dev" / "local" / "prds"
    if prds_dir.is_dir():
        for md_file in sorted(prds_dir.rglob("*.md")):
            if md_file.is_file():
                yield CorpusFile("prd", name, md_file)
    else:
        missing_dirs.append(f"prd:{name}")

    # Decision (single file)
    decisions_file = root / "dev" / "local" / "decisions.md"
    if decisions_file.is_file():
        yield CorpusFile("decision", name, decisions_file)
    else:
        missing_dirs.append(f"decision:{name}")

    # Discovery (non-recursive)
    discovery_dir = root / "dev" / "local" / "discovery"
    if discovery_dir.is_dir():
        for md_file in sorted(discovery_dir.glob("*.md")):
            if md_file.is_file():
                yield CorpusFile("discovery", name, md_file)
    else:
        missing_dirs.append(f"discovery:{name}")


def enumerate_corpora(
    repos_csv: Path = GITA_REPOS_CSV,
    projects_dir: Path = CLAUDE_PROJECTS_DIR,
) -> Iterator[CorpusFile]:
    missing_dirs.clear()

    # Build slug -> name mapping from repos.csv
    slug_to_name: dict[str, str] = {}
    rows: list[tuple[str, str]] = []
    text = repos_csv.read_text()
    if text.strip():
        reader = csv.reader(text.splitlines())
        for row in reader:
            if len(row) < 2:
                continue
            repo_path, name = row[0], row[1]
            slug = repo_path.replace("/", "-")
            slug_to_name[slug] = name
            rows.append((repo_path, name))

    # Memory corpus (once, not per repo)
    yield from _enumerate_memory_corpora(projects_dir, slug_to_name)

    # Per-repo corpora
    for repo_path, name in rows:
        yield from _enumerate_repo_corpora(Path(repo_path), name)


def hash_source(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}".encode() + b"\0"
    return hashlib.sha1(header + data).hexdigest()
