"""Mine search bursts from Claude session transcripts.

PYTHONPATH=src:. .venv/bin/python -m eval.agent_session_mine SINCE UNTIL OUT [SKIP...]

SINCE and UNTIL are ISO timestamps: only tool calls between them count. OUT is
a private JSONL file. Each SKIP is an earlier bursts file whose sessions are left out.
A burst is three or more search calls where each is within six tool calls of
the one before. Each row keeps the stated intent, the commands, and the files
the agent read or edited next. Rows hold private text; keep OUT out of Git.
"""

import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
SKIP_PROJECT = re.compile(r"engram|-tmp-|-var-folders-")  # this repo and temp dirs
SEARCH = re.compile(r"^\s*(?:rg|grep|find|git\s+(?:-C\s+\S+\s+)?log)\b")
FILE_TOOLS = {"Read", "Edit", "Write"}
GAP = 6  # tool calls allowed between two searches of one burst
NEXT = 8  # tool calls after the burst scanned for settled files
MIN_SEARCHES = 3


def is_search(name: str, tool_input: dict) -> bool:
    if name in {"Grep", "Glob"}:
        return True
    return name == "Bash" and bool(SEARCH.match(str(tool_input.get("command", ""))))


def read_events(
    path: Path, since: str, until: str
) -> Iterator[tuple[str, str, dict, str]]:
    """Yield ("text", words, {}, time) and ("tool", name, input, time) in order."""
    with path.open() as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # a live session can end on a half-written line
            if row.get("isSidechain") or row.get("type") not in {"user", "assistant"}:
                continue
            stamp = row.get("timestamp", "")
            content = row.get("message", {}).get("content")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            for part in content or []:
                if part.get("type") == "text" and part.get("text", "").strip():
                    yield "text", part["text"], {}, stamp
                elif part.get("type") == "tool_use" and since < stamp < until:
                    yield "tool", part["name"], part.get("input", {}), stamp


def find_bursts(events: list[tuple[str, str, dict, str]]) -> list[dict]:
    tools = [(i, e) for i, e in enumerate(events) if e[0] == "tool"]
    hits = [n for n, (_, e) in enumerate(tools) if is_search(e[1], e[2])]
    bursts, run = [], []
    for n in [*hits, None]:
        if run and (n is None or n - run[-1] > GAP):
            if len(run) >= MIN_SEARCHES:
                first_event = tools[run[0]][0]
                intent = [e[1][:1500] for e in events[:first_event] if e[0] == "text"]
                after = tools[run[-1] + 1 : run[-1] + 1 + NEXT]
                bursts.append(
                    {
                        "time": tools[run[0]][1][3],
                        "search_calls": len(run),
                        "intent": intent[-2:],
                        "cmds": [
                            [tools[k][1][1], json.dumps(tools[k][1][2])[:600]]
                            for k in run
                        ],
                        "next": [
                            [e[1], e[2]["file_path"]]
                            for _, e in after
                            if e[1] in FILE_TOOLS and "file_path" in e[2]
                        ],
                    },
                )
            run = []
        if n is not None:
            run.append(n)
    return bursts


def main() -> None:
    since, until, out, *skips = sys.argv[1:]
    seen = {json.loads(line)["session"] for s in skips for line in Path(s).open()}
    sessions = bursts = 0
    with Path(out).open("x") as stream:
        for path in sorted(PROJECTS.glob("*/*.jsonl")):
            if SKIP_PROJECT.search(path.parent.name) or path.stem in seen:
                continue
            found = find_bursts(list(read_events(path, since, until)))
            sessions += 1
            for burst in found:
                row = {"project": path.parent.name, "session": path.stem, **burst}
                stream.write(json.dumps({"id": bursts, "path": str(path), **row}) + "\n")
                bursts += 1
    print(f"{sessions} sessions scanned, {bursts} bursts")


if __name__ == "__main__":
    main()
