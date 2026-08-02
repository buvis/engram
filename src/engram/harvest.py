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
)
from engram.corpora import GITA_REPOS_CSV
from engram.store import StoreModelMismatchError


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
    cwd = path.parent if path.is_file() else path
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        if path.resolve().is_relative_to(Path.home() / ".claude"):
            return "claude-home"
        return None

    toplevel = result.stdout.strip()
    try:
        rows = corpora.read_repos_csv(repos_csv)
    except FileNotFoundError:
        return None

    for repo_path, name in rows:
        if repo_path == toplevel:
            return name
    return None


def harvest(store, config, paths: list[Path]) -> HarvestReport:
    results: list[FileHarvestResult] = []

    for path in paths:
        try:
            resolved_path = path.resolve()
        except (OSError, RuntimeError) as e:
            results.append(
                FileHarvestResult(
                    path=path,
                    outcome="no_repo",
                    records_count=0,
                    error=str(e),
                ),
            )
            continue
        path = resolved_path

        repo = _resolve_repo_for_path(path, GITA_REPOS_CSV)
        if repo is None:
            results.append(FileHarvestResult(path=path, outcome="no_repo", records_count=0))
            continue

        try:
            records = findings.parse(path)
        except ValueError as e:
            results.append(
                FileHarvestResult(
                    path=path,
                    outcome="parse_failed",
                    records_count=0,
                    error=str(e),
                ),
            )
            continue

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
            results.append(
                FileHarvestResult(
                    path=path,
                    outcome="upsert_failed",
                    records_count=0,
                    error=str(e),
                ),
            )
            continue

        results.append(FileHarvestResult(path=path, outcome="upserted", records_count=n))

    return HarvestReport(results=results)
