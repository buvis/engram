#!/usr/bin/env python3
"""Spike: host-neutral engram nudge. After a broad search, add engram hits to context.

Usage: engram_nudge.py <claude|codex|copilot|kiro|gemini|plain>   (hook JSON on stdin)
Always exits 0: a nudge must never block or fail a tool call.
"""

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

SEARCHERS = {"rg", "grep", "find"}
HISTORY_FLAGS = ("-S", "-G", "--grep")


def read_event(raw: str) -> tuple[str, str]:
    """Return (shell command, cwd) from any host's post-tool payload."""
    event = json.loads(raw)
    args = event.get("tool_input") or event.get("toolArgs") or {}
    if isinstance(args, str):  # Copilot may pass toolArgs as a JSON string
        args = json.loads(args)
    return args.get("command", ""), event.get("cwd") or os.getcwd()


def repo_root(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def parse_search(command: str, cwd: str) -> str | None:
    """Return the search pattern when the command is a broad search, else None."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens:
        return None
    tool = Path(tokens[0]).name
    if tool == "git" and "log" in tokens:
        for i, tok in enumerate(tokens):  # history search is always broad
            for flag in HISTORY_FLAGS:
                if tok == flag and i + 1 < len(tokens):
                    return tokens[i + 1]
                if tok.startswith(flag) and len(tok) > len(flag):
                    return tok[len(flag):].lstrip("=")
        return None
    if tool not in SEARCHERS:
        return None
    # ponytail: flags that take a value (-g, -e, -t) are not modelled; first bare token wins
    bare = [t for t in tokens[1:] if not t.startswith("-")]
    if not bare:
        return None
    pattern, paths = bare[0], bare[1:]
    home_repo = repo_root(Path(cwd))
    roots = set()
    for raw in paths:
        path = Path(os.path.expanduser(raw))
        path = path if path.is_absolute() else Path(cwd) / path
        if ".claude/projects" in str(path):
            return pattern  # transcript store sweep
        roots.add(repo_root(path) or path)
    outside = any(root != home_repo for root in roots)
    return pattern if outside or len(roots) > 1 else None


def to_query(pattern: str) -> str:
    words = [w for w in re.split(r"[^A-Za-z0-9_-]+", pattern) if len(w) >= 3]
    return " ".join(words)


def run_engram(query: str) -> list[str]:
    try:
        done = subprocess.run(
            ["engram", "query", "--scope", "portfolio", query, "-k", "3"],
            capture_output=True, text=True, timeout=10, check=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"engram-nudge: query failed: {error}", file=sys.stderr)
        return []
    return [line for line in done.stdout.splitlines() if line.strip()]


def drop_packed(hits: list[str]) -> list[str]:
    """Drop hits the orchestrator already injected (clash guard, part 2)."""
    pack = os.environ.get("ENGRAM_PACK_FILE")
    if not pack or not Path(pack).is_file():
        return hits
    packed = Path(pack).read_text(errors="replace")
    return [h for h in hits if h.split("\t")[2].rsplit(":", 1)[0] not in packed]


def emit(host: str, text: str) -> None:
    if host in ("kiro", "plain"):
        print(text)
    elif host == "copilot":
        print(json.dumps({"additionalContext": text}))
    else:
        name = "AfterTool" if host == "gemini" else "PostToolUse"
        print(json.dumps({"hookSpecificOutput": {"hookEventName": name, "additionalContext": text}}))


def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else "plain"
    if os.environ.get("ENGRAM_NUDGE") == "off":  # clash guard, part 1
        return 0
    raw = sys.stdin.read()
    if len(sys.argv) > 2:  # spike only: capture the real host payload for inspection
        Path(sys.argv[2]).mkdir(parents=True, exist_ok=True)
        (Path(sys.argv[2]) / f"{host}-{os.getpid()}.json").write_text(raw)
    try:
        command, cwd = read_event(raw)
    except (ValueError, AttributeError) as error:
        print(f"engram-nudge: unreadable hook payload: {error}", file=sys.stderr)
        return 0
    pattern = parse_search(command, cwd)
    query = to_query(pattern) if pattern else ""
    if not query:
        return 0
    hits = drop_packed(run_engram(query))
    if hits:
        lines = "\n".join(f"- {h.split(chr(9))[2]}  ({h.split(chr(9))[3]})" for h in hits)
        emit(host, f'engram recall for "{query}" (prior sessions, PRDs, memory, code):\n{lines}\n'
                   "Read a cited range if it is relevant; ignore it if not.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
