#!/usr/bin/env python3
"""Spike: minimal stdio MCP server wrapping `engram query`. Stands in for `engram mcp`."""

import json
import subprocess
import sys

INSTRUCTIONS = (
    "engram is the portfolio memory: past agent sessions, PRDs, decisions, memory files, and code "
    "across all repositories. Call engram_query before a broad rg/grep/git-log sweep for prior "
    "decisions, history, or cross-repo where/why questions. Do not use it to search a known file."
)
TOOL = {
    "name": "engram_query",
    "description": "Search prior sessions, PRDs, memory, and code. Returns ranked path:line hits.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Question in plain words"},
            "scope": {"type": "string", "enum": ["repo", "portfolio"], "default": "portfolio"},
            "k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
        },
        "required": ["query"],
    },
}


def run_query_tool(args: dict) -> dict:
    scope = args.get("scope", "portfolio")
    if scope not in ("repo", "portfolio") or not isinstance(args.get("query"), str):
        return {"content": [{"type": "text", "text": "invalid arguments"}], "isError": True}
    k = str(min(max(int(args.get("k", 5)), 1), 20))
    done = subprocess.run(
        ["engram", "query", "--scope", scope, args["query"], "-k", k],
        capture_output=True, text=True, timeout=30,
    )
    text = done.stdout if done.returncode == 0 else f"engram failed: {done.stderr.strip()}"
    return {"content": [{"type": "text", "text": text or "no hits"}], "isError": done.returncode != 0}


def handle(msg: dict) -> dict | None:
    method, params = msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "engram", "version": "0.0.1"},
            "instructions": INSTRUCTIONS,
        }
    if method == "tools/list":
        return {"tools": [TOOL]}
    if method == "tools/call" and params.get("name") == "engram_query":
        return run_query_tool(params.get("arguments") or {})
    if method == "ping":
        return {}
    return None


for line in sys.stdin:
    if not line.strip():
        continue
    msg = json.loads(line)
    if "id" not in msg:  # notification
        continue
    result = handle(msg)
    reply = {"jsonrpc": "2.0", "id": msg["id"]}
    reply |= {"result": result} if result is not None else {"error": {"code": -32601, "message": "method not found"}}
    print(json.dumps(reply), flush=True)
