"""Retain exact gold-source bytes outside Git; keep labels and live paths intact."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from engram.harness import RetainedSource, load_goldset

ROOT = Path(__file__).resolve().parent
STORAGE = Path.home() / ".local/share/engram/eval/sources"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _targets(goldset: Path) -> set[str]:
    return {entry["expected_path"] for entry in yaml.safe_load(goldset.read_text())}


def _manifest(goldset: Path, manifest: Path) -> dict[str, Any]:
    raw = json.loads(manifest.read_text())
    if raw.get("version") != 1:
        raise ValueError("unsupported source manifest version")
    if raw.get("goldset_sha256") != _sha(goldset.read_bytes()):
        raise ValueError(
            "goldset fingerprint changed; create a separate explicit freeze"
        )
    if set(raw["sources"]) != _targets(goldset):
        raise ValueError("source manifest must cover exactly the gold targets")
    for record in raw["sources"].values():
        if not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
            raise ValueError("invalid source manifest hash")
        if not Path(record["expected_path"]).is_absolute():
            raise ValueError("source manifest identity must be absolute")
    return raw


def _location(storage: Path, record: dict[str, Any]) -> Path:
    # Keep the basename/extension for language detection and transcript headings.
    return storage / record["sha256"] / Path(record["expected_path"]).name


def _matches(data: bytes, record: dict[str, Any]) -> bool:
    return len(data) == record["size"] and _sha(data) == record["sha256"]


def _write_source(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(
                f"retained source is corrupt; preserve it for inspection: {path}"
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
    ) as stream:
        stream.write(data)


def _private_storage(storage: Path) -> None:
    storage = storage.resolve()
    if any((p / ".git").exists() for p in (storage, *storage.parents)):
        raise ValueError("private source storage must be outside Git")
    storage.mkdir(parents=True, exist_ok=True, mode=0o700)


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(
        ["git", "--literal-pathspecs", "-C", str(repo), *args],
        stderr=subprocess.PIPE,
    )


def _git_source(source: Path, repos: list[Path]) -> tuple[bytes, dict[str, str]] | None:
    """Read only explicitly nominated repositories, including committed deletions."""
    for repo in repos:
        repo = repo.resolve()
        if not source.is_relative_to(repo):
            continue
        relative = source.relative_to(repo).as_posix()
        revision = (
            _git(repo, "log", "-1", "--format=%H", "--diff-filter=AM", "--", relative)
            .decode()
            .strip()
        )
        if revision:
            data = _git(repo, "show", f"{revision}:{relative}")
            return data, {"repo": str(repo), "commit": revision, "path": relative}
    return None


def capture(
    goldset: Path,
    manifest: Path,
    storage: Path = STORAGE,
    *,
    git_repos: list[Path] | None = None,
) -> None:
    """Create a new freeze; never overwrite an existing manifest or source."""
    if manifest.exists():
        raise FileExistsError(f"source manifest already exists: {manifest}")
    _private_storage(storage)
    fingerprint = _sha(goldset.read_bytes())
    records = {}
    files = {}
    for source in sorted(_targets(goldset)):
        path = Path(source).resolve()
        version = _git_source(path, git_repos or [])
        if path.is_file():
            data = path.read_bytes()
        elif version is not None:
            data = version[0]
        else:
            raise ValueError(
                f"cannot retain source: {source}; supply its Git repository or exact backup"
            )
        record: dict[str, Any] = {
            "expected_path": str(path),
            "sha256": _sha(data),
            "size": len(data),
        }
        if version is not None and version[0] == data:
            record["git"] = version[1]
        retained = _location(storage, record)
        _write_source(retained, data)
        records[source] = record
        files[source] = RetainedSource(str(path), retained)
    load_goldset(goldset, source_paths=files)
    if _sha(goldset.read_bytes()) != fingerprint:
        raise ValueError("goldset changed during capture")
    with manifest.open("x") as stream:
        json.dump(
            {"version": 1, "goldset_sha256": fingerprint, "sources": records},
            stream,
            indent=2,
            sort_keys=True,
        )
        stream.write("\n")


def load_sources(
    goldset: Path = ROOT / "goldset.yaml",
    manifest: Path = ROOT / "sources.json",
    storage: Path = STORAGE,
) -> dict[str, RetainedSource]:
    """Validate every retained byte; never fall back to changing live sources."""
    raw = _manifest(goldset, manifest)
    files = {}
    for source, record in raw["sources"].items():
        retained = _location(storage, record)
        if not retained.is_file():
            raise ValueError(
                f"retained source missing: {source}; run python -m eval.sources restore"
            )
        if not _matches(retained.read_bytes(), record):
            raise ValueError(f"retained source hash mismatch: {source}")
        files[source] = RetainedSource(record["expected_path"], retained)
    load_goldset(goldset, source_paths=files)
    return files


def restore(goldset: Path, manifest: Path, storage: Path = STORAGE) -> None:
    """Recover missing copies only from matching live bytes or pinned Git history."""
    raw = _manifest(goldset, manifest)
    _private_storage(storage)
    for source, record in raw["sources"].items():
        retained = _location(storage, record)
        if retained.exists():
            if not _matches(retained.read_bytes(), record):
                raise ValueError(f"retained source hash mismatch: {source}")
            continue
        live = Path(record["expected_path"])
        data = live.read_bytes() if live.is_file() else b""
        if not _matches(data, record) and "git" in record:
            git = record["git"]
            data = _git(Path(git["repo"]), "show", f"{git['commit']}:{git['path']}")
        if not _matches(data, record):
            raise ValueError(
                f"cannot restore exact source: {source}; recover the private backup"
            )
        _write_source(retained, data)
    load_sources(goldset, manifest, storage)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "validate", "restore"])
    parser.add_argument("--goldset", type=Path, default=ROOT / "goldset.yaml")
    parser.add_argument("--manifest", type=Path, default=ROOT / "sources.json")
    parser.add_argument("--storage", type=Path, default=STORAGE)
    parser.add_argument("--git-repo", type=Path, action="append", default=[])
    args = parser.parse_args()
    if args.action == "capture":
        capture(args.goldset, args.manifest, args.storage, git_repos=args.git_repo)
    elif args.action == "restore":
        restore(args.goldset, args.manifest, args.storage)
    files = load_sources(args.goldset, args.manifest, args.storage)
    print(
        f"Validated {len(load_goldset(args.goldset, source_paths=files))} labels, {len(files)} retained sources"
    )


if __name__ == "__main__":
    main()
