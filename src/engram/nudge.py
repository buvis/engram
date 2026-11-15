"""Post-tool hook: recall prior work after a broad shell search."""

from __future__ import annotations

import itertools
import json
import os
import re
import shlex
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from engram import mcp_server

if TYPE_CHECKING:
    from collections.abc import Mapping

    from engram.query import Pointer

HOSTS: tuple[str, ...] = ("claude", "codex", "copilot", "plain")
HEADER: str = 'engram recall for "{query}" (prior sessions, PRDs, memory, code):'
FOOTER: str = "Read a cited range if it is relevant; ignore it if not."
NUDGE_K: int = 3
SEARCH_VALUE_FLAGS: frozenset[str] = frozenset(
    {
        "-g",
        "--glob",
        "-t",
        "--type",
        "-T",
        "--type-not",
        "-A",
        "-B",
        "-C",
        "-m",
        "--max-count",
        "--max-depth",
        "-f",
        "--file",
        "-j",
        "--threads",
        "-M",
        "--max-columns",
    },
)
PATTERN_FLAGS: frozenset[str] = frozenset({"-e", "--regexp"})
GIT_LOG_FLAGS: tuple[str, ...] = ("-S", "-G", "--grep")
OPERATOR_CHARS: str = ";<>|&\n"


def read_hook_event(raw: str) -> tuple[str, str]:
    event = json.loads(raw)
    if not isinstance(event, dict):
        raise ValueError("hook payload is not a JSON object")
    args = (
        event["tool_input"]
        if event.get("tool_input") is not None
        else event.get("toolArgs")
    )
    if isinstance(args, str):
        args = json.loads(args)
    if not isinstance(args, dict):
        raise ValueError("no tool arguments in hook payload")
    command = args.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("no shell command in hook payload")
    cwd = event.get("cwd")
    return command, cwd if isinstance(cwd, str) and cwd else os.getcwd()


def _git_log_pattern(args: list[str]) -> str | None:
    if "log" not in args:
        return None
    for i, tok in enumerate(args):
        if tok in GIT_LOG_FLAGS:
            value = args[i + 1] if i + 1 < len(args) else ""
        elif tok.startswith("--grep="):
            value = tok[len("--grep=") :]
        elif tok[:2] in ("-S", "-G"):
            value = tok[2:]
        else:
            continue
        if value:
            return value
    return None


def _grep_search(args: list[str]) -> tuple[str, list[str]] | None:
    explicit: str | None = None
    bare: list[str] = []
    after_dashdash = False
    i = 0
    while i < len(args):
        tok = args[i]
        value = None
        if after_dashdash or tok == "-" or not tok.startswith("-"):
            bare.append(tok)
        elif tok == "--":
            after_dashdash = True
        elif tok in PATTERN_FLAGS:
            value = args[i + 1] if i + 1 < len(args) else None
            i += 1
        elif tok.startswith("--regexp="):
            value = tok[len("--regexp=") :]
        elif tok.startswith("-e"):
            value = tok[2:]
        elif tok in SEARCH_VALUE_FLAGS:
            i += 1
        if explicit is None:
            explicit = value
        i += 1
    if explicit is not None:
        return explicit, bare
    return (bare[0], bare[1:]) if bare else None


def _find_search(args: list[str]) -> tuple[str, list[str]] | None:
    i = 0
    while i < len(args) and args[i] in ("-H", "-L", "-P"):
        i += 1
    paths: list[str] = []
    while i < len(args) and not args[i].startswith(("-", "(", "!")):
        paths.append(args[i])
        i += 1
    for tok, nxt in itertools.pairwise(args):
        if tok in ("-name", "-iname"):
            return nxt, paths
    return None


def _repo_root(path: str) -> str | None:
    while True:
        if os.path.lexists(os.path.join(path, ".git")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent


def _is_broad(paths: list[str], cwd: str) -> bool:
    cwd = os.path.normpath(os.path.abspath(os.path.expanduser(cwd)))
    resolved = [
        os.path.normpath(os.path.join(cwd, os.path.expandvars(os.path.expanduser(p))))
        for p in paths
    ]
    for p in resolved:
        parts = p.split(os.sep)
        if any(
            a == ".claude" and b == "projects" for a, b in itertools.pairwise(parts)
        ):
            return True
    cwd_root = _repo_root(cwd)
    if cwd_root is None:
        return any(
            os.path.commonpath([p, cwd]) != cwd or _repo_root(p) is not None
            for p in resolved
        )
    return {_repo_root(p) for p in resolved} != {cwd_root}


def find_broad_search(command: str, cwd: str) -> str | None:
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=OPERATOR_CHARS)
        lex.whitespace = " \t\r"
        lex.whitespace_split = True
        lex.commenters = ""
        tokens = list(lex)
    except ValueError:
        return None
    end = next(
        (i for i, t in enumerate(tokens) if t and set(t) <= set(OPERATOR_CHARS)),
        len(tokens),
    )
    tokens = tokens[:end]
    if not tokens:
        return None
    tool, args = Path(tokens[0]).name, tokens[1:]
    if tool == "git":
        return _git_log_pattern(args)
    if tool in ("rg", "grep", "egrep", "fgrep"):
        found = _grep_search(args)
    elif tool == "find":
        found = _find_search(args)
    else:
        return None
    if found is None:
        return None
    pattern, paths = found
    return pattern if paths and _is_broad(paths, cwd) else None


def build_recall_query(pattern: str) -> str:
    return " ".join(w for w in re.split(r"[^A-Za-z0-9_-]+", pattern) if len(w) >= 3)


def format_nudge(host: str, query: str, pointers: list[Pointer]) -> str:
    lines = "\n".join(
        f"- {p.path}:{p.line_start}-{p.line_end}  ({p.heading})" for p in pointers
    )
    text = HEADER.format(query=query) + "\n" + lines + "\n" + FOOTER
    if host in ("claude", "codex"):
        return json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": text,
                },
            },
        )
    if host == "copilot":
        return json.dumps({"additionalContext": text})
    if host == "plain":
        return text
    raise ValueError(f"unknown host: {host!r}")


def run_nudge(
    host: str,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    environ: Mapping[str, str],
) -> int:
    if environ.get("ENGRAM_NUDGE") == "off":
        return 0
    try:
        try:
            command, cwd = read_hook_event(stdin.read())
        except ValueError as e:
            print(f"engram nudge: unreadable hook payload: {e}", file=stderr)
            return 0
        pattern = find_broad_search(command, cwd)
        query = build_recall_query(pattern) if pattern is not None else ""
        if not query:
            return 0
        try:
            hits = mcp_server.search_pointers(query, "portfolio", NUDGE_K)
        except Exception as e:
            print(f"engram nudge: query failed: {type(e).__name__}: {e}", file=stderr)
            return 0
        pack = environ.get("ENGRAM_PACK_FILE")
        if pack:
            try:
                packed = Path(pack).read_text(errors="replace")
            except OSError:
                packed = ""
            hits = [p for p in hits if p.path not in packed]
        if hits:
            stdout.write(format_nudge(host, query, hits) + "\n")
            stdout.flush()
    except Exception as e:  # a post-tool hook must never fail the host's tool call
        print(f"engram nudge: {type(e).__name__}: {e}", file=stderr)
    return 0
