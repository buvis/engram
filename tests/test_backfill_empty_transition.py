import sqlite3

import pytest
from test_backfill import (
    _EMBEDDED,
    _MODEL,
    _PORTFOLIO,
    _VECTORS_A,
    _VECTORS_B,
    _config,
    _distinct_chunk,
    _fake_chunker,
    _fake_enumerate,
    _item,
    _recording_embed,
    _seed_backfilled,
    _seed_pre_00013,
    _source,
    _texts,
    _zero_report,
)

import engram.indexer as indexer
from engram.corpora import CorpusFile, hash_source
from engram.store import Scope, open_store


class _FailingConn:
    """Delegates to a real connection but raises on writes touching one table."""

    def __init__(self, conn, table):
        self._conn = conn
        self._table = table

    def _check(self, sql):
        verb = sql.strip().split(None, 1)[0].upper()
        if verb in {"INSERT", "DELETE", "UPDATE", "REPLACE"} and self._table in sql:
            raise sqlite3.OperationalError(f"disk I/O error writing {self._table}")

    def execute(self, sql, *args):
        self._check(sql)
        return self._conn.execute(sql, *args)

    def executemany(self, sql, *args):
        self._check(sql)
        return self._conn.executemany(sql, *args)

    def cursor(self):
        return _FailingConn(self._conn.cursor(), self._table)

    def __getattr__(self, name):
        return getattr(self._conn, name)


# --- backfill_code: the crash window between row write and empty mark ---


def test_backfill_reuses_stored_rows_of_source_left_with_rows_and_empty_mark(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    a, h_a, _, fresh_a = _seed_pre_00013(store, tmp_path, "repoA", "mod.py", _VECTORS_A)
    b, h_b, _, fresh_b = _seed_pre_00013(
        store, tmp_path, "repoB", "other.py", _VECTORS_B
    )
    # Crash window: the rows committed, the empty mark never got cleared.
    store.mark_empty_source("code", "repoA", str(a), h_a)
    store.mark_empty_source("code", "repoB", str(b), h_b)
    # Near miss: shares mod.py's prefix, still chunks to nothing, keeps its mark.
    bak = _source(tmp_path, "repoA", "mod.py.bak", "\n")
    h_bak = hash_source(bak)
    store.mark_empty_source("code", "repoA", str(bak), h_bak)
    missing = tmp_path / "repoA" / "gone.py"
    files = [("repoA", a), ("repoB", b), ("repoA", bak), ("repoA", missing)]
    _fake_enumerate(monkeypatch, [CorpusFile("code", r, p) for r, p in files])
    chunks = {str(a): fresh_a, str(b): fresh_b, str(bak): []}
    chunk_calls = _fake_chunker(monkeypatch, chunks)
    embed_calls = _recording_embed(monkeypatch)

    report = indexer.backfill_code(store, _config(tmp_path), _PORTFOLIO)

    # Only the module-context chunk of each source is new, so only it is embedded.
    assert sorted(_texts(embed_calls)) == sorted(
        [fresh_a[0].text_for_embedding, fresh_b[0].text_for_embedding]
    )
    assert (a, "repoA", h_a) in chunk_calls
    assert (b, "repoB", h_b) in chunk_calls
    assert all(model_id == _MODEL for _, model_id in embed_calls)
    rows_a = store.code_chunks_with_vectors(str(a))
    rows_b = store.code_chunks_with_vectors(str(b))
    assert [item.chunk for item in rows_a] == fresh_a
    assert [item.chunk for item in rows_b] == fresh_b
    assert [item.vector.values for item in rows_a] == [_EMBEDDED] + _VECTORS_A
    assert [item.vector.values for item in rows_b] == [_EMBEDDED] + _VECTORS_B
    assert store.known_empty_sources_by_corpus(_PORTFOLIO, "code") == {
        ("code", "repoA", str(bak), h_bak)
    }
    assert report.chunks_embedded == 2
    assert report.vectors_reused == 4
    assert report.failed_sources == [str(missing)]


def test_backfill_embeds_nothing_when_a_stale_mark_sits_on_current_rows(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    one, stored_one, fresh_one = _seed_backfilled(
        store, tmp_path, "repoA", "one.py", _VECTORS_A
    )
    two, stored_two, fresh_two = _seed_backfilled(
        store, tmp_path, "repoB", "two.py", _VECTORS_B
    )
    # Crash window again, this time on rows that already match the chunker.
    store.mark_empty_source("code", "repoA", str(one), fresh_one[0].content_hash)
    store.mark_empty_source("code", "repoB", str(two), fresh_two[0].content_hash)
    # Reject case of the same shape: chunks to nothing, so the mark stays.
    blank = _source(tmp_path, "repoA", "one.py.bak", "\n")
    h_blank = hash_source(blank)
    store.mark_empty_source("code", "repoA", str(blank), h_blank)
    files = [("repoA", one), ("repoB", two), ("repoA", blank)]
    _fake_enumerate(monkeypatch, [CorpusFile("code", r, p) for r, p in files])
    _fake_chunker(
        monkeypatch, {str(one): fresh_one, str(two): fresh_two, str(blank): []}
    )
    embed_calls = _recording_embed(monkeypatch)

    report = indexer.backfill_code(store, _config(tmp_path), _PORTFOLIO)

    assert embed_calls == []
    assert store.code_chunks_with_vectors(str(one)) == stored_one
    assert store.code_chunks_with_vectors(str(two)) == stored_two
    assert store.known_empty_sources_by_corpus(_PORTFOLIO, "code") == {
        ("code", "repoA", str(blank), h_blank)
    }
    assert report.chunks_embedded == 0
    assert report.failed_sources == []


def test_backfill_keeps_the_mark_of_a_source_that_still_chunks_to_nothing(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    blank = _source(tmp_path, "repoA", "blank.py", "\n")
    h_blank = hash_source(blank)
    store.mark_empty_source("code", "repoA", str(blank), h_blank)
    _fake_enumerate(monkeypatch, [CorpusFile("code", "repoA", blank)])
    chunk_calls = _fake_chunker(monkeypatch, {})
    embed_calls = _recording_embed(monkeypatch)

    report = indexer.backfill_code(store, _config(tmp_path), _PORTFOLIO)

    assert chunk_calls == [(blank, "repoA", h_blank)]
    assert embed_calls == []
    assert store.code_chunks_with_vectors(str(blank)) == []
    assert store.known_empty_sources_by_corpus(_PORTFOLIO, "code") == {
        ("code", "repoA", str(blank), h_blank)
    }
    assert report == _zero_report()


# --- Store.replace_source_chunks_and_empty_mark ---


_PATH = "/src/repoA/mod.py"
_NEAR = _PATH + ".bak"


def test_replace_source_chunks_and_empty_mark_commits_rows_and_drops_the_mark(
    tmp_path,
):
    db = tmp_path / "engram.db"
    store = open_store(db)
    store.replace_chunks_for_source(
        "code", _PATH, [_item(_distinct_chunk(_PATH, 0), _VECTORS_A[0], _MODEL, 4)]
    )
    near = [_item(_distinct_chunk(_NEAR, 1), _VECTORS_B[0], _MODEL, 4)]
    store.replace_chunks_for_source("code", _NEAR, near)
    store.mark_empty_source("code", "repoA", _PATH, "doomed-hash")
    store.mark_empty_source("code", "repoA", _NEAR, "keep-bak")
    store.mark_empty_source("docs", "repoA", _PATH, "keep-docs")
    store.mark_empty_source("code", "repoB", _PATH, "keep-repo-b")
    fresh = [
        _item(_distinct_chunk(_PATH, 2), _VECTORS_B[1], _MODEL, 4),
        _item(_distinct_chunk(_PATH, 3), _VECTORS_A[1], _MODEL, 4),
    ]

    result = store.replace_source_chunks_and_empty_mark(
        "code", "repoA", _PATH, "h-new", fresh
    )

    assert result is None
    # A second connection sees both effects, so they were committed, not pending.
    check = open_store(db)
    assert check.code_chunks_with_vectors(_PATH) == fresh
    assert check.code_chunks_with_vectors(_NEAR) == near
    assert check.known_empty_sources_by_corpus(Scope("portfolio", None), None) == {
        ("code", "repoA", _NEAR, "keep-bak"),
        ("docs", "repoA", _PATH, "keep-docs"),
        ("code", "repoB", _PATH, "keep-repo-b"),
    }


@pytest.mark.parametrize("content_hash", ["h-first", "h-second"])
def test_replace_source_chunks_and_empty_mark_commits_the_mark_for_empty_items(
    tmp_path, content_hash
):
    db = tmp_path / "engram.db"
    store = open_store(db)
    doomed = [
        _item(_distinct_chunk(_PATH, 0), _VECTORS_A[0], _MODEL, 4),
        _item(_distinct_chunk(_PATH, 1), _VECTORS_B[0], _MODEL, 4),
    ]
    store.replace_chunks_for_source("code", _PATH, doomed)
    kept = [_item(_distinct_chunk(_NEAR, 2), _VECTORS_B[1], _MODEL, 4)]
    store.replace_chunks_for_source("code", _NEAR, kept)
    store.mark_empty_source("code", "repoA", _PATH, "superseded-hash")
    store.mark_empty_source("docs", "repoA", _PATH, "keep-docs")

    store.replace_source_chunks_and_empty_mark("code", "repoA", _PATH, content_hash, [])

    check = open_store(db)
    assert check.code_chunks_with_vectors(_PATH) == []
    assert check.code_chunks_with_vectors(_NEAR) == kept
    assert check.known_empty_sources_by_corpus(Scope("portfolio", None), None) == {
        ("code", "repoA", _PATH, content_hash),
        ("docs", "repoA", _PATH, "keep-docs"),
    }


@pytest.mark.parametrize("failing_table", ["chunks", "empty_sources"])
@pytest.mark.parametrize("direction", ["mark_empty", "clear_mark"])
def test_replace_source_chunks_and_empty_mark_commits_nothing_when_a_write_fails(
    tmp_path, failing_table, direction
):
    store = open_store(tmp_path / "engram.db")
    old = [
        _item(_distinct_chunk(_PATH, 0), _VECTORS_A[0], _MODEL, 4),
        _item(_distinct_chunk(_PATH, 1), _VECTORS_B[0], _MODEL, 4),
    ]
    store.replace_chunks_for_source("code", _PATH, old)
    store.mark_empty_source("code", "repoA", _PATH, "before-hash")
    before_marks = store.known_empty_sources_by_corpus(_PORTFOLIO, None)
    assert before_marks == {("code", "repoA", _PATH, "before-hash")}
    items = (
        []
        if direction == "mark_empty"
        else [_item(_distinct_chunk(_PATH, 2), _VECTORS_B[1], _MODEL, 4)]
    )
    real = store.conn
    store.conn = _FailingConn(real, failing_table)

    with pytest.raises(sqlite3.OperationalError, match=failing_table):
        store.replace_source_chunks_and_empty_mark(
            "code", "repoA", _PATH, "after-hash", items
        )

    store.conn = real
    assert store.code_chunks_with_vectors(_PATH) == old
    assert store.known_empty_sources_by_corpus(_PORTFOLIO, None) == before_marks
