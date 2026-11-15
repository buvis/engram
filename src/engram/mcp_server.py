"""Minimal MCP stdio server exposing the engram_query tool."""

from __future__ import annotations

import importlib.metadata
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from engram.client import (
    EmbeddingModelIdentityError,
    EmbeddingPreflightError,
    EmbeddingServerError,
    load_config,
)
from engram.corpora import GITA_REPOS_CSV
from engram.harvest import _resolve_repo_for_path
from engram.query import Pointer, query
from engram.store import Scope, StoreModelMismatchError, open_store

Search = Callable[[str, str, int], list[Pointer]]

INSTRUCTIONS: str = (
    "engram is the portfolio memory: past agent sessions, PRDs, decisions, memory files, and code "
    "across all repositories. Call engram_query before a broad rg/grep/git-log sweep for prior "
    "decisions, history, or cross-repo where/why questions. Do not use it to search a known file."
)
DEFAULT_PROTOCOL_VERSION: str = "2025-06-18"
TOOL: dict = {
    "name": "engram_query",
    "description": "Search prior sessions, PRDs, memory, and code. Returns ranked path:line hits.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Question in plain words"},
            "scope": {
                "type": "string",
                "enum": ["repo", "portfolio"],
                "default": "portfolio",
            },
            "k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
        },
        "required": ["query"],
    },
}


class RepoScopeError(ValueError):
    pass


def search_pointers(text: str, scope: str, k: int) -> list[Pointer]:
    if scope == "repo":
        name = _resolve_repo_for_path(Path.cwd() / "_", repos_csv=GITA_REPOS_CSV)
        if name is None:
            if not GITA_REPOS_CSV.exists():
                raise RepoScopeError(
                    f"{GITA_REPOS_CSV} not found; register repos with gita first",
                )
            raise RepoScopeError(
                "not inside a registered repo; use scope portfolio instead",
            )
        scope_obj = Scope("repo", name)
    else:
        scope_obj = Scope("portfolio", None)
    config = load_config()
    store = open_store()
    try:
        return query(store, config, text, scope_obj, k=k)
    finally:
        store.conn.close()


def format_pointer_lines(pointers: list[Pointer]) -> list[str]:
    lines = []
    for p in pointers:
        lines.append(
            f"{p.rank}\t{p.score:.4f}\t{p.path}:{p.line_start}-{p.line_end}\t{p.heading}",
        )
        if p.body is not None:
            lines.append(p.body)
    return lines


def _tool_result(text: str, is_error: bool) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _validate_arguments(arguments: object) -> str | None:
    if not isinstance(arguments, dict):
        return "arguments must be an object"
    text = arguments.get("query")
    if not isinstance(text, str) or not text.strip():
        return "query must be a non-empty string"
    if "scope" in arguments and arguments["scope"] not in ("repo", "portfolio"):
        return "scope must be 'repo' or 'portfolio'"
    if "k" in arguments:
        k = arguments["k"]
        if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 20:
            return "k must be an integer from 1 to 20"
    return None


def run_query_tool(arguments: object, search: Search | None = None) -> dict:
    if arguments is None:
        arguments = {}
    problem = _validate_arguments(arguments)
    if problem is not None:
        return _tool_result(f"invalid arguments: {problem}", True)
    if search is None:
        search = search_pointers
    try:
        hits = search(
            arguments["query"],
            arguments.get("scope", "portfolio"),
            arguments.get("k", 5),
        )
    except StoreModelMismatchError as e:
        return _tool_result(
            f"{e}; run `engram index --rebuild` to rebuild the store",
            True,
        )
    except (
        EmbeddingServerError,
        EmbeddingPreflightError,
        EmbeddingModelIdentityError,
        ValueError,
        OSError,
        sqlite3.Error,
    ) as e:
        return _tool_result(str(e), True)
    if not hits:
        return _tool_result("no hits", False)
    return _tool_result("\n".join(format_pointer_lines(hits)), False)


def _server_version() -> str:
    try:
        return importlib.metadata.version("engram")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _dispatch(
    method: object,
    params: dict,
    search: Search | None,
) -> tuple[str, object]:
    if method == "initialize":
        version = params.get("protocolVersion")
        if not isinstance(version, str) or not version:
            version = DEFAULT_PROTOCOL_VERSION
        return "result", {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "engram", "version": _server_version()},
            "instructions": INSTRUCTIONS,
        }
    if method == "ping":
        return "result", {}
    if method == "tools/list":
        return "result", {"tools": [TOOL]}
    if method == "tools/call":
        name = params.get("name")
        if name == "engram_query":
            return "result", run_query_tool(params.get("arguments"), search)
        return "error", {"code": -32602, "message": f"unknown tool: {name}"}
    return "error", {"code": -32601, "message": "method not found"}


def handle_mcp_message(message: object, search: Search | None = None) -> dict | None:
    if not isinstance(message, dict):
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "invalid request"},
        }
    if "id" not in message:
        return None
    params = message.get("params")
    if not isinstance(params, dict):
        params = {}
    try:
        key, value = _dispatch(message.get("method"), params, search)
    except Exception as e:
        key = "error"
        value = {"code": -32603, "message": f"internal error: {type(e).__name__}: {e}"}
    return {"jsonrpc": "2.0", "id": message["id"], key: value}


def serve_mcp(stdin: TextIO, stdout: TextIO, search: Search | None = None) -> int:
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except (ValueError, RecursionError):
            reply = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "parse error"},
            }
        else:
            reply = handle_mcp_message(message, search)
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
    return 0
