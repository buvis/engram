"""Transcript Corpus: enumerate cellar transcript JSONL files and chunk their kept turns."""

from __future__ import annotations

import functools
import json
import re
import tomllib
from collections.abc import Iterator
from pathlib import Path

from engram import client
from engram.corpora import CorpusFile
from engram.store import Chunk

CELLAR_PROJECTS_DIR: Path = (
    Path.home()
    / "git"
    / "src"
    / "github.com"
    / "buvis"
    / "cellar"
    / ".claude"
    / "projects"
)

# Turns that are machine scaffolding rather than conversation. PRD 00002's corpus
# spec is "keep only turns worth recalling", and these are not: they arrive as
# user-type messages, so the text-turn filter below would otherwise keep them, and
# being near-identical across every session makes them beat real prose on vague
# queries. Matched as a *prefix* of the turn, never as a substring — 6 turns in the
# live corpus discuss these markers in real analysis prose, and a substring test
# would delete exactly those.
SCAFFOLDING_PREFIXES: tuple[str, ...] = (
    "<task-notification>",
    "<system-reminder>",
    "<local-command-stdout>",
    "Caveat: The messages below were generated",
)

DEFAULT_ERROR_PATTERNS: list[str] = [
    r"Traceback \(most recent call last\)",
    r"panic:",
    r"\bERROR\b",
    r"\bFAIL\b",
    r"exit code [1-9]",
]


def enumerate(projects_dir: Path = CELLAR_PROJECTS_DIR) -> Iterator[CorpusFile]:
    if not projects_dir.is_dir():
        raise FileNotFoundError(
            f"{projects_dir} not found; cellar transcripts corpus requires this path",
        )
    for session_dir in sorted(projects_dir.iterdir()):
        for jsonl_file in sorted(session_dir.glob("*.jsonl")):
            if jsonl_file.is_file():
                yield CorpusFile(corpus="transcripts", repo="cellar", path=jsonl_file)


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def _has_error_match(content, error_patterns: list[str]) -> bool:
    if not isinstance(content, list):
        return False
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_result":
            continue
        text = block.get("content")
        if not isinstance(text, str):
            continue
        if any(re.search(pat, text) for pat in error_patterns):
            return True
    return False


def chunk(
    path: Path,
    repo: str,
    content_hash: str,
    error_patterns: list[str] | None = None,
) -> list[Chunk]:
    if error_patterns is None:
        error_patterns = _load_error_patterns()

    lines = path.read_text(errors="replace").split("\n")
    chunks: list[Chunk] = []
    for line_number in range(1, len(lines) + 1):
        try:
            record = json.loads(lines[line_number - 1])
        except json.JSONDecodeError:
            continue

        if not isinstance(record, dict):
            continue

        if record.get("type") not in {"user", "assistant"}:
            continue
        if record.get("isMeta"):
            continue
        if record.get("isSidechain"):
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue

        content = message.get("content")
        text = _extract_text(content)
        if not text.strip() and not _has_error_match(content, error_patterns):
            continue
        if text.lstrip().startswith(SCAFFOLDING_PREFIXES):
            continue

        chunks.append(
            Chunk(
                corpus="transcripts",
                repo=repo,
                doc_type="turn",
                path=str(path),
                heading=f"{record['type']} turn",
                body=text,
                line_start=line_number,
                line_end=line_number,
                content_hash=content_hash,
                chunk_ordinal=line_number,
            ),
        )

    return chunks


@functools.cache
def _load_error_patterns(config_path: Path = client.DEFAULT_CONFIG_PATH) -> list[str]:
    """Read [transcripts].error_patterns, validating every regex here.

    Cached per config path: chunk() is called once per transcript file, so an
    uncached read re-parsed the TOML ~630 times a run. A raising call is not
    memoized, so a bad config keeps failing rather than being cached as good.
    A config edited mid-process is not picked up, which is fine for a CLI.
    """
    if not config_path.exists():
        return DEFAULT_ERROR_PATTERNS

    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    patterns = raw.get("transcripts", {}).get("error_patterns")
    if not isinstance(patterns, list):
        return DEFAULT_ERROR_PATTERNS

    # Compile here, at the config boundary, so a bad pattern names itself and
    # its key instead of surfacing later as a bare re.error from inside a
    # chunking pass, mid-run, with no clue where it came from.
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as e:
            raise ValueError(
                f"config {config_path} has an invalid regex in "
                f"[transcripts] error_patterns: {pattern!r} ({e})",
            ) from e
    return patterns
