import io
import json
import sqlite3
from pathlib import Path

import pytest

from engram import mcp_server
from engram.client import (
    EmbeddingModelIdentityError,
    EmbeddingPreflightError,
    EmbeddingServerError,
)
from engram.query import Pointer
from engram.store import Scope, StoreModelMismatchError

EXPECTED_INSTRUCTIONS = (
    "engram is the portfolio memory: past agent sessions, PRDs, decisions, memory files, "
    "and code across all repositories. Call engram_query before a broad rg/grep/git-log "
    "sweep for prior decisions, history, or cross-repo where/why questions. Do not use it "
    "to search a known file."
)

EXPECTED_TOOL = {
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

POINTER_A = Pointer(
    rank=1,
    score=0.98765,
    path="notes/alpha.md",
    line_start=10,
    line_end=14,
    heading="Alpha Section",
    corpus="docs",
    repo="repoA",
)
POINTER_B = Pointer(
    rank=2,
    score=0.5,
    path="findings/finding-2.md",
    line_start=1,
    line_end=5,
    heading="Beta Finding",
    corpus="findings",
    repo="repoB",
    body="stored finding body text",
)
LINE_A = "1\t0.9877\tnotes/alpha.md:10-14\tAlpha Section"
LINE_B = "2\t0.5000\tfindings/finding-2.md:1-5\tBeta Finding"


def _request(method, params=None, request_id=1):
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def _call(arguments, request_id=1):
    return _request(
        "tools/call",
        {"name": "engram_query", "arguments": arguments},
        request_id,
    )


def _serve(lines, search=None):
    stdin = io.StringIO("".join(f"{line}\n" for line in lines))
    stdout = io.StringIO()
    exit_code = mcp_server.serve_mcp(stdin, stdout, search=search)
    return exit_code, stdout.getvalue()


def _replies(output):
    return [json.loads(line) for line in output.splitlines()]


class _RecordingSearch:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, text, scope, k):
        self.calls.append((text, scope, k))
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def _refuse_search(*args, **kwargs):
    raise AssertionError("search must not be called")


# --- initialize ---


def test_initialize_returns_instructions_and_tools_capability():
    assert mcp_server.INSTRUCTIONS == EXPECTED_INSTRUCTIONS
    assert mcp_server.DEFAULT_PROTOCOL_VERSION == "2025-06-18"

    echoed = mcp_server.handle_mcp_message(
        _request("initialize", {"protocolVersion": "2024-11-05"}, request_id="init-1"),
        search=_refuse_search,
    )
    echoed_other = mcp_server.handle_mcp_message(
        _request("initialize", {"protocolVersion": "2025-03-26"}, request_id=7),
        search=_refuse_search,
    )

    assert echoed["jsonrpc"] == "2.0"
    assert echoed["id"] == "init-1"
    assert "error" not in echoed
    result = echoed["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"]["name"] == "engram"
    assert isinstance(result["serverInfo"]["version"], str)
    assert result["serverInfo"]["version"] != ""
    assert result["instructions"] == EXPECTED_INSTRUCTIONS
    assert echoed_other["id"] == 7
    assert echoed_other["result"]["protocolVersion"] == "2025-03-26"


@pytest.mark.parametrize(
    "params",
    [None, {}, {"protocolVersion": ""}, {"protocolVersion": 20250618}],
)
def test_initialize_defaults_protocol_version_when_client_gives_no_usable_value(params):
    reply = mcp_server.handle_mcp_message(
        _request("initialize", params),
        search=_refuse_search,
    )

    assert reply["result"]["protocolVersion"] == "2025-06-18"
    assert reply["result"]["capabilities"] == {"tools": {}}


# --- ping and tools/list ---


@pytest.mark.parametrize("request_id", [5, "ping-abc"])
def test_ping_returns_empty_result_echoing_id(request_id):
    reply = mcp_server.handle_mcp_message(
        _request("ping", request_id=request_id),
        search=_refuse_search,
    )

    assert reply == {"jsonrpc": "2.0", "id": request_id, "result": {}}


def test_tools_list_returns_the_engram_query_tool():
    assert mcp_server.TOOL == EXPECTED_TOOL

    reply = mcp_server.handle_mcp_message(
        _request("tools/list", request_id=3),
        search=_refuse_search,
    )

    assert reply == {"jsonrpc": "2.0", "id": 3, "result": {"tools": [EXPECTED_TOOL]}}


# --- tools/call success ---


def test_tools_call_returns_query_lines():
    search = _RecordingSearch([[POINTER_A, POINTER_B], [POINTER_B], []])

    first = mcp_server.handle_mcp_message(
        _call({"query": "why sqlite", "scope": "repo", "k": 3}, request_id=11),
        search=search,
    )
    second = mcp_server.handle_mcp_message(
        _call({"query": "where is the indexer"}, request_id="call-2"),
        search=search,
    )
    empty = mcp_server.handle_mcp_message(
        _call({"query": "nothing matches", "scope": "portfolio", "k": 20}),
        search=search,
    )

    assert first == {
        "jsonrpc": "2.0",
        "id": 11,
        "result": {
            "content": [{"type": "text", "text": "\n".join([LINE_A, LINE_B, POINTER_B.body])}],
            "isError": False,
        },
    }
    assert second["id"] == "call-2"
    assert second["result"]["content"] == [
        {"type": "text", "text": f"{LINE_B}\n{POINTER_B.body}"},
    ]
    assert second["result"]["isError"] is False
    assert empty["result"] == {
        "content": [{"type": "text", "text": "no hits"}],
        "isError": False,
    }
    assert search.calls == [
        ("why sqlite", "repo", 3),
        ("where is the indexer", "portfolio", 5),
        ("nothing matches", "portfolio", 20),
    ]


def test_format_pointer_lines_adds_body_line_only_when_body_present():
    assert mcp_server.format_pointer_lines([POINTER_A, POINTER_B]) == [
        LINE_A,
        LINE_B,
        POINTER_B.body,
    ]
    assert mcp_server.format_pointer_lines([POINTER_B, POINTER_A]) == [
        LINE_B,
        POINTER_B.body,
        LINE_A,
    ]
    assert mcp_server.format_pointer_lines([]) == []


def test_run_query_tool_ignores_unknown_extra_keys():
    search = _RecordingSearch([[POINTER_A]])

    result = mcp_server.run_query_tool(
        {"query": "history", "scope": "repo", "k": 1, "extra": "ignored"},
        search=search,
    )

    assert result == {"content": [{"type": "text", "text": LINE_A}], "isError": False}
    assert search.calls == [("history", "repo", 1)]


def test_default_search_resolves_module_search_pointers_at_call_time(monkeypatch):
    calls = []

    def fake_search_pointers(text, scope, k):
        calls.append((text, scope, k))
        return [POINTER_A]

    monkeypatch.setattr("engram.mcp_server.search_pointers", fake_search_pointers)

    exit_code, output = _serve(
        [json.dumps(_call({"query": "patched seam", "k": 2}, request_id=9))],
    )

    assert exit_code == 0
    assert _replies(output) == [
        {
            "jsonrpc": "2.0",
            "id": 9,
            "result": {"content": [{"type": "text", "text": LINE_A}], "isError": False},
        },
    ]
    assert calls == [("patched seam", "portfolio", 2)]


# --- tools/call argument validation ---


@pytest.mark.parametrize(
    "arguments,field",
    [
        (None, "query"),
        ({}, "query"),
        ({"query": ""}, "query"),
        ({"query": "   \t\n"}, "query"),
        ({"query": 42}, "query"),
        ({"query": "x", "scope": "global"}, "scope"),
        ({"query": "x", "scope": "repos"}, "scope"),
        ({"query": "x", "scope": "Repo"}, "scope"),
        ({"query": "x", "scope": None}, "scope"),
        ({"query": "x", "k": True}, "k"),
        ({"query": "x", "k": False}, "k"),
        ({"query": "x", "k": 0}, "k"),
        ({"query": "x", "k": 21}, "k"),
        ({"query": "x", "k": -1}, "k"),
        ({"query": "x", "k": "5"}, "k"),
        ({"query": "x", "k": 5.0}, "k"),
    ],
)
def test_run_query_tool_rejects_invalid_arguments_without_searching(arguments, field):
    result = mcp_server.run_query_tool(arguments, search=_refuse_search)

    assert result["isError"] is True
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    text = result["content"][0]["text"]
    assert text.startswith("invalid arguments: ")
    assert field in text[len("invalid arguments: ") :]


@pytest.mark.parametrize("arguments", ["query", ["query", "x"], 7])
def test_run_query_tool_rejects_non_object_arguments_without_searching(arguments):
    result = mcp_server.run_query_tool(arguments, search=_refuse_search)

    assert result["isError"] is True
    assert result["content"][0]["text"].startswith("invalid arguments: ")


@pytest.mark.parametrize("k", [1, 20])
def test_run_query_tool_accepts_k_at_range_bounds(k):
    search = _RecordingSearch([[POINTER_A]])

    result = mcp_server.run_query_tool({"query": "bounds", "k": k}, search=search)

    assert result["isError"] is False
    assert search.calls == [("bounds", "portfolio", k)]


# --- tools/call failures ---


@pytest.mark.parametrize(
    "error",
    [
        mcp_server.RepoScopeError("not inside a registered repo; use scope portfolio instead"),
        EmbeddingServerError("embedding server unreachable"),
        EmbeddingPreflightError("llama-server binary missing"),
        EmbeddingModelIdentityError("model id mismatch"),
        ValueError("bad vector dimension"),
        OSError("disk full"),
        sqlite3.OperationalError("database is locked"),
    ],
)
def test_run_query_tool_reports_search_failure_as_is_error(error):
    result = mcp_server.run_query_tool({"query": "boom"}, search=_RecordingSearch([error]))

    assert result == {"content": [{"type": "text", "text": str(error)}], "isError": True}


def test_store_model_mismatch_error_text_names_rebuild_command():
    error = StoreModelMismatchError("store built with model-a, config uses model-b")

    result = mcp_server.run_query_tool({"query": "boom"}, search=_RecordingSearch([error]))

    assert result == {
        "content": [
            {
                "type": "text",
                "text": (
                    "store built with model-a, config uses model-b; "
                    "run `engram index --rebuild` to rebuild the store"
                ),
            },
        ],
        "isError": True,
    }


def test_unexpected_search_exception_returns_32603_internal_error():
    reply = mcp_server.handle_mcp_message(
        _call({"query": "boom"}, request_id=4),
        search=_RecordingSearch([RuntimeError("unexpected crash")]),
    )

    assert reply["jsonrpc"] == "2.0"
    assert reply["id"] == 4
    assert "result" not in reply
    assert reply["error"]["code"] == -32603
    assert reply["error"]["message"].startswith("internal error: ")


def test_query_failure_sets_is_error_and_keeps_serving():
    search = _RecordingSearch([EmbeddingServerError("embedding server down"), [POINTER_A]])

    exit_code, output = _serve(
        [
            json.dumps(_call({"query": "first try"}, request_id=1)),
            json.dumps(_call({"query": "second try", "scope": "repo", "k": 4}, request_id=2)),
        ],
        search=search,
    )

    assert exit_code == 0
    assert output.endswith("\n")
    assert _replies(output) == [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "embedding server down"}],
                "isError": True,
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"content": [{"type": "text", "text": LINE_A}], "isError": False},
        },
    ]
    assert search.calls == [("first try", "portfolio", 5), ("second try", "repo", 4)]


# --- protocol errors ---


@pytest.mark.parametrize("name", ["engram_querys", "other_tool"])
def test_unknown_tool_returns_32602_naming_the_tool(name):
    reply = mcp_server.handle_mcp_message(
        _request("tools/call", {"name": name, "arguments": {"query": "x"}}, request_id=8),
        search=_refuse_search,
    )

    assert reply == {
        "jsonrpc": "2.0",
        "id": 8,
        "error": {"code": -32602, "message": f"unknown tool: {name}"},
    }


@pytest.mark.parametrize("method", ["resources/list", "tools/lists", "pings"])
def test_unknown_method_returns_32601(method):
    reply = mcp_server.handle_mcp_message(
        _request(method, request_id="m-1"),
        search=_refuse_search,
    )

    assert reply == {
        "jsonrpc": "2.0",
        "id": "m-1",
        "error": {"code": -32601, "message": "method not found"},
    }


@pytest.mark.parametrize("message", [["ping"], "ping", 5, None])
def test_non_object_message_returns_32600_with_null_id(message):
    reply = mcp_server.handle_mcp_message(message, search=_refuse_search)

    assert reply == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32600, "message": "invalid request"},
    }


def test_notification_gets_no_reply():
    initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    call_without_id = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "engram_query", "arguments": {"query": "x"}},
    }

    assert mcp_server.handle_mcp_message(initialized, search=_refuse_search) is None
    assert mcp_server.handle_mcp_message(call_without_id, search=_refuse_search) is None
    assert (
        mcp_server.handle_mcp_message({"jsonrpc": "2.0", "method": "ping"}, search=_refuse_search)
        is None
    )

    exit_code, output = _serve(
        [json.dumps(initialized), json.dumps(_request("ping", request_id=6))],
        search=_refuse_search,
    )

    assert exit_code == 0
    assert _replies(output) == [{"jsonrpc": "2.0", "id": 6, "result": {}}]


def test_invalid_json_returns_32700():
    parse_error = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
    deeply_nested = "[" * 200000 + "]" * 200000

    exit_code, output = _serve(
        [
            "{not json",
            "",
            "   ",
            deeply_nested,
            json.dumps(_request("ping", request_id=12)),
        ],
        search=_refuse_search,
    )

    assert exit_code == 0
    assert output.endswith("\n")
    assert _replies(output) == [
        parse_error,
        parse_error,
        {"jsonrpc": "2.0", "id": 12, "result": {}},
    ]


def test_serve_mcp_replies_once_per_request_in_input_order():
    exit_code, output = _serve(
        [
            json.dumps(_request("tools/list", request_id="b")),
            json.dumps(_request("ping", request_id="a")),
            json.dumps(_request("nope", request_id=3)),
        ],
        search=_refuse_search,
    )

    assert exit_code == 0
    assert [reply["id"] for reply in _replies(output)] == ["b", "a", 3]


def test_serve_mcp_returns_zero_on_empty_input():
    stdout = io.StringIO()

    assert mcp_server.serve_mcp(io.StringIO(""), stdout, search=_refuse_search) == 0
    assert stdout.getvalue() == ""


# --- real search_pointers body ---


class _FakeConn:
    def __init__(self):
        self.closed = 0

    def close(self):
        self.closed += 1


class _FakeStore:
    def __init__(self):
        self.conn = _FakeConn()


def _patch_backend(monkeypatch, tmp_path, query_impl, repo_name):
    config = object()
    stores = []
    resolve_calls = []
    repos_csv = tmp_path / "gita" / "repos.csv"

    def fake_open_store(*args, **kwargs):
        store = _FakeStore()
        stores.append(store)
        return store

    def fake_resolve(path, repos_csv=None):
        resolve_calls.append((path, repos_csv))
        return repo_name

    monkeypatch.setattr("engram.mcp_server.load_config", lambda *a, **k: config)
    monkeypatch.setattr("engram.mcp_server.open_store", fake_open_store)
    monkeypatch.setattr("engram.mcp_server.query", query_impl)
    monkeypatch.setattr("engram.mcp_server._resolve_repo_for_path", fake_resolve)
    monkeypatch.setattr("engram.mcp_server.GITA_REPOS_CSV", repos_csv)
    return config, stores, resolve_calls, repos_csv


def test_search_pointers_queries_store_with_scope_and_k_then_closes_connection(
    monkeypatch,
    tmp_path,
):
    query_calls = []
    hits = [POINTER_A, POINTER_B]

    def fake_query(store, config, text, scope, corpus=None, k=5, **kwargs):
        query_calls.append((store, config, text, scope, k))
        return hits

    config, stores, resolve_calls, repos_csv = _patch_backend(
        monkeypatch, tmp_path, fake_query, "repoB"
    )
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    portfolio = mcp_server.search_pointers("portfolio question", "portfolio", 7)
    repo = mcp_server.search_pointers("repo question", "repo", 2)

    assert portfolio == hits
    assert repo == hits
    assert len(stores) == 2
    assert [store.conn.closed for store in stores] == [1, 1]
    assert query_calls == [
        (stores[0], config, "portfolio question", Scope("portfolio", None), 7),
        (stores[1], config, "repo question", Scope("repo", "repoB"), 2),
    ]
    assert resolve_calls == [(Path.cwd() / "_", repos_csv)]


def test_search_pointers_closes_connection_and_propagates_query_error(
    monkeypatch,
    tmp_path,
):
    error = EmbeddingServerError("embedding server down")

    def failing_query(*args, **kwargs):
        raise error

    _, stores, _, _ = _patch_backend(monkeypatch, tmp_path, failing_query, "repoA")

    with pytest.raises(EmbeddingServerError) as exc_info:
        mcp_server.search_pointers("q", "portfolio", 5)

    assert exc_info.value is error
    assert len(stores) == 1
    assert stores[0].conn.closed == 1


@pytest.mark.parametrize("csv_exists", [False, True])
def test_unresolvable_repo_scope_returns_is_error_through_run_query_tool(
    monkeypatch,
    tmp_path,
    csv_exists,
):
    _, _, resolve_calls, repos_csv = _patch_backend(
        monkeypatch, tmp_path, _refuse_search, None
    )
    if csv_exists:
        repos_csv.parent.mkdir(parents=True)
        repos_csv.write_text(f"{tmp_path / 'elsewhere'},elsewhere\n")
        expected = "not inside a registered repo; use scope portfolio instead"
    else:
        expected = f"{repos_csv} not found; register repos with gita first"

    result = mcp_server.run_query_tool({"query": "where", "scope": "repo"})

    assert result == {"content": [{"type": "text", "text": expected}], "isError": True}
    assert len(resolve_calls) == 1
    with pytest.raises(mcp_server.RepoScopeError):
        mcp_server.search_pointers("where", "repo", 5)
