from __future__ import annotations

import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from engram import corpora, findings
from engram.client import (
    EmbeddingModelIdentityError,
    EmbeddingPreflightError,
    EmbeddingServerError,
    EngramConfig,
)
from engram.corpora import GITA_REPOS_CSV
from engram.store import Store, StoreModelMismatchError


@dataclass(frozen=True)
class FileHarvestResult:
    path: Path
    outcome: Literal["upserted", "parse_failed", "upsert_failed", "no_repo"]
    records_count: int
    error: str | None = None


@dataclass(frozen=True)
class HarvestReport:
    results: list[FileHarvestResult]

    @property
    def any_failed(self) -> bool:
        return any(r.outcome != "upserted" for r in self.results)


def _resolve_repo_for_path(path: Path, repos_csv: Path = GITA_REPOS_CSV) -> str | None:
    cwd = path.parent
    try:
        result = subprocess.run(
            [
                "git",
                "rev-parse",
                "--path-format=absolute",
                "--show-toplevel",
                "--git-common-dir",
            ],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        home = Path.home()
        try:
            resolved = path.resolve()
            under_claude_home = resolved.is_relative_to((home / ".claude").resolve())
        except (OSError, RuntimeError):
            return None
        if under_claude_home:
            return "claude-home"
        return None

    toplevel_out, common_dir_out = result.stdout.strip().splitlines()
    toplevel = Path(toplevel_out).resolve()
    common_dir = Path(common_dir_out).resolve()
    # A linked worktree of a non-bare repo shares <main>/.git; map it to <main>.
    main_checkout = common_dir.parent if common_dir.name == ".git" else None
    try:
        rows = corpora.read_repos_csv(repos_csv)
    except OSError:
        return None

    resolved_rows = [(Path(repo_path).resolve(), name) for repo_path, name in rows]
    for root in (toplevel, main_checkout):
        for repo_root, name in resolved_rows:
            if root is not None and repo_root == root:
                return name
    return None


def registry_root(name: str, repos_csv: Path = GITA_REPOS_CSV) -> Path | None:
    try:
        rows = corpora.read_repos_csv(repos_csv)
    except OSError:
        return None
    for repo_path, row_name in rows:
        if row_name == name:
            return Path(repo_path)
    return None


def _harvest_path(store: Store, config: EngramConfig, path: Path) -> FileHarvestResult:
    try:
        resolved_path = path.resolve()
    except (OSError, RuntimeError) as e:
        return FileHarvestResult(
            path=path,
            outcome="no_repo",
            records_count=0,
            error=str(e),
        )
    path = resolved_path

    repo = _resolve_repo_for_path(path, GITA_REPOS_CSV)
    if repo is None:
        return FileHarvestResult(path=path, outcome="no_repo", records_count=0)

    try:
        records = findings.parse(path)
    except ValueError as e:
        return FileHarvestResult(
            path=path,
            outcome="parse_failed",
            records_count=0,
            error=str(e),
        )

    try:
        n = findings.upsert(store, config, repo, path, records)
    except (
        StoreModelMismatchError,
        EmbeddingPreflightError,
        EmbeddingServerError,
        EmbeddingModelIdentityError,
        OSError,
        sqlite3.Error,
    ) as e:
        return FileHarvestResult(
            path=path,
            outcome="upsert_failed",
            records_count=0,
            error=str(e),
        )

    return FileHarvestResult(path=path, outcome="upserted", records_count=n)


def harvest(store: Store, config: EngramConfig, paths: list[Path]) -> HarvestReport:
    results = [_harvest_path(store, config, path) for path in paths]
    return HarvestReport(results=results)
