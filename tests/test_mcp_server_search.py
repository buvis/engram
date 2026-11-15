from pathlib import Path

import pytest

from engram import mcp_server
from engram.client import EmbeddingServerError
from engram.query import Pointer
from engram.store import Scope

POINTER_A = Pointer(
    rank=1,
    score=0.98765,
    path="notes/alpha.md",
    line_start=10,
    line_end=11,
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


def _refuse_search(*args, **kwargs):
    raise AssertionError("search must not be called")


# --- real search_pointers body ---


class _FakeConn:
    def __init__(self):
        self.closed = 0

    def close(self):
        self.closed += 1


class _FakeStore:
    def __init__(self):
        self.conn = _FakeConn()


class _Backend:
    def __init__(self, repos_csv):
        self.config = object()
        self.stores = []
        self.resolve_calls = []
        self.load_config_calls = []
        self.open_store_calls = []
        self.repos_csv = repos_csv


def _patch_backend(monkeypatch, tmp_path, query_impl, repo_name):
    backend = _Backend(tmp_path / "gita" / "repos.csv")

    def fake_load_config(*args, **kwargs):
        backend.load_config_calls.append((args, kwargs))
        return backend.config

    def fake_open_store(*args, **kwargs):
        backend.open_store_calls.append((args, kwargs))
        store = _FakeStore()
        backend.stores.append(store)
        return store

    def fake_resolve(path, repos_csv=None):
        backend.resolve_calls.append((path, repos_csv))
        return repo_name

    monkeypatch.setattr("engram.mcp_server.load_config", fake_load_config)
    monkeypatch.setattr("engram.mcp_server.open_store", fake_open_store)
    monkeypatch.setattr("engram.mcp_server.query", query_impl)
    monkeypatch.setattr("engram.mcp_server._resolve_repo_for_path", fake_resolve)
    monkeypatch.setattr("engram.mcp_server.GITA_REPOS_CSV", backend.repos_csv)
    return backend


def test_search_pointers_queries_store_with_scope_and_k_then_closes_connection(
    monkeypatch,
    tmp_path,
):
    query_calls = []
    hits = [POINTER_A, POINTER_B]

    def fake_query(*args, **kwargs):
        query_calls.append((args, kwargs))
        return hits

    backend = _patch_backend(monkeypatch, tmp_path, fake_query, "repoB")
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    portfolio = mcp_server.search_pointers("portfolio question", "portfolio", 7)
    repo = mcp_server.search_pointers("repo question", "repo", 2)

    assert portfolio == hits
    assert repo == hits
    stores, config = backend.stores, backend.config
    assert len(stores) == 2
    assert [store.conn.closed for store in stores] == [1, 1]
    assert backend.open_store_calls == [((), {}), ((), {})]
    assert backend.load_config_calls
    assert all(call == ((), {}) for call in backend.load_config_calls)
    assert query_calls == [
        (
            (stores[0], config, "portfolio question", Scope("portfolio", None)),
            {"k": 7},
        ),
        ((stores[1], config, "repo question", Scope("repo", "repoB")), {"k": 2}),
    ]
    assert backend.resolve_calls == [(Path.cwd() / "_", backend.repos_csv)]


def test_search_pointers_closes_connection_and_propagates_query_error(
    monkeypatch,
    tmp_path,
):
    error = EmbeddingServerError("embedding server down")

    def failing_query(*args, **kwargs):
        raise error

    backend = _patch_backend(monkeypatch, tmp_path, failing_query, "repoA")

    with pytest.raises(EmbeddingServerError) as exc_info:
        mcp_server.search_pointers("q", "portfolio", 5)

    assert exc_info.value is error
    assert len(backend.stores) == 1
    assert backend.stores[0].conn.closed == 1


@pytest.mark.parametrize("csv_exists", [False, True])
def test_unresolvable_repo_scope_returns_is_error_through_run_query_tool(
    monkeypatch,
    tmp_path,
    csv_exists,
):
    backend = _patch_backend(monkeypatch, tmp_path, _refuse_search, None)
    repos_csv = backend.repos_csv
    if csv_exists:
        repos_csv.parent.mkdir(parents=True)
        repos_csv.write_text(f"{tmp_path / 'elsewhere'},elsewhere\n")
        expected = "not inside a registered repo; use scope portfolio instead"
    else:
        expected = f"{repos_csv} not found; register repos with gita first"

    result = mcp_server.run_query_tool({"query": "where", "scope": "repo"})

    assert result == {"content": [{"type": "text", "text": expected}], "isError": True}
    assert len(backend.resolve_calls) == 1
    with pytest.raises(mcp_server.RepoScopeError):
        mcp_server.search_pointers("where", "repo", 5)
    assert all(store.conn.closed == 1 for store in backend.stores)
