#!/usr/bin/env python3
"""Spike demo: run from anywhere. Shows validator, MCP handshake, per-host nudge, clash guards."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE / "engram"
NUDGE = PLUGIN / "nudge" / "engram_nudge.py"
VALIDATOR = Path.home() / "git/src/github.com/buvis/agent-plugins/scripts/validate.py"
ENGRAM_REPO = str(HERE.parents[4])
BROAD = "rg -l migration-placeholder /Users/bob/git/src/github.com/buvis --glob '!**/.git/**'"
NARROW = "rg -n def src/engram/corpora.py"


def nudge(host: str, payload: dict, env: dict | None = None) -> str:
    done = subprocess.run(
        [sys.executable, str(NUDGE), host],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
    return done.stdout.strip() + (
        f"  [stderr: {done.stderr.strip()}]" if done.stderr.strip() else ""
    )


def title(text: str) -> None:
    print(f"\n== {text}")


title("1. agent-plugins validator on the spike plugin")
done = subprocess.run(
    [sys.executable, str(VALIDATOR), str(PLUGIN)], capture_output=True, text=True
)
print(done.returncode, (done.stdout + done.stderr).strip())

title("2. MCP handshake + tools/list + tools/call")
requests = [
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18"},
    },
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "engram_query",
            "arguments": {"query": "migration placeholder origin", "k": 2},
        },
    },
]
done = subprocess.run(
    [sys.executable, str(PLUGIN / "server" / "engram_mcp.py")],
    input="\n".join(json.dumps(r) for r in requests),
    capture_output=True,
    text=True,
)
for line in done.stdout.splitlines():
    print(line[:300])

title("3. broad search, each host payload shape")
snake = {"tool_name": "Bash", "tool_input": {"command": BROAD}, "cwd": ENGRAM_REPO}
camel = {
    "toolName": "bash",
    "toolArgs": json.dumps({"command": BROAD}),
    "cwd": ENGRAM_REPO,
}
for host, payload in (
    ("claude", snake),
    ("codex", snake),
    ("gemini", snake),
    ("copilot", camel),
    ("kiro", snake),
):
    print(f"[{host}] {nudge(host, payload)[:420]}")

title("4. narrow search inside the repo (must be silent)")
print(
    repr(
        nudge(
            "claude",
            {
                "tool_name": "Bash",
                "tool_input": {"command": NARROW},
                "cwd": ENGRAM_REPO,
            },
        )
    )
)

title("5. clash guard: orchestrator sets ENGRAM_NUDGE=off (must be silent)")
print(repr(nudge("claude", snake, {"ENGRAM_NUDGE": "off"})))

title("6. clash guard: orchestrator pack already holds the top hit (hit is dropped)")
first = (
    nudge("plain", snake)
    .splitlines()[1]
    .removeprefix("- ")
    .split("  (")[0]
    .rsplit(":", 1)[0]
)
with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as pack:
    pack.write(f"## Prior work\n- {first}\n")
print(f"pack holds: {first}")
print(nudge("plain", snake, {"ENGRAM_PACK_FILE": pack.name}))
os.unlink(pack.name)
