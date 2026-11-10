#!/usr/bin/env python3
"""Spike: live nudge check for hosts the agent sandbox cannot run (Claude, Pi).

Run OUTSIDE the agent sandbox: python3 live_check.py [pi-model]
Writes docs/dev/tmp/engram-plugin-live.json and prints one line per host.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
NUDGE = HERE / "engram" / "nudge" / "engram_nudge.py"
PI_EXT = HERE / "engram" / "works.earendil.pi" / "engram-nudge.ts"
OUT = HERE.parents[2] / "tmp" / "engram-plugin-live.json"
TARGET = HERE.parents[1] / "prds"
PROMPT = (
    f"Run this exact shell command: rg -l migration-placeholder {TARGET}  "
    "If a hook blocks it and asks you to present facts first, present them briefly and retry "
    "the same command. Then reply with any text starting with 'engram recall' that appeared "
    "after the command ran, verbatim. If none appeared, reply NONE."
)


def run_host(name: str, cmd: list[str], cwd: Path, captured: Path) -> dict:
    if not shutil.which(cmd[0]):
        return {"host": name, "status": f"{cmd[0]} not on PATH"}
    subprocess.run(["git", "init", "-q", str(cwd)], check=True)
    try:
        done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"host": name, "status": "timeout after 300 s"}
    output = done.stdout + done.stderr
    payloads = [json.loads(p.read_text()) for p in captured.glob(f"{name}-*.json")]
    for payload in payloads:
        payload.pop("tool_response", None)  # keep the result file small
    return {
        "host": name,
        "status": "ran",
        "exit": done.returncode,
        "recall_seen": "engram recall" in done.stdout,
        "hook_payloads": payloads,
        "output_tail": output[-1500:],
    }


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="engram-plugin-live-"))
    captured = root / "captured"
    claude_dir, pi_dir = root / "claude", root / "pi"
    (claude_dir / ".claude").mkdir(parents=True)
    pi_dir.mkdir()
    hook = {"type": "command", "command": f"python3 {NUDGE} claude {captured}", "timeout": 15}
    (claude_dir / ".claude" / "settings.json").write_text(
        json.dumps({"hooks": {"PostToolUse": [{"matcher": "Bash", "hooks": [hook]}]}})
    )
    pi_cmd = ["pi", "-p", "--no-session", "-e", str(PI_EXT)]
    if len(sys.argv) > 1:
        pi_cmd += ["--model", sys.argv[1]]
    results = [
        run_host("claude", ["claude", "-p", PROMPT, "--model", "haiku",
                            "--allowedTools", "Bash(rg:*)"], claude_dir, captured),
        run_host("pi", [*pi_cmd, PROMPT], pi_dir, captured),
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))
    shutil.rmtree(root)
    for result in results:
        print(f"{result['host']}: {result['status']}, recall seen = {result.get('recall_seen')}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
