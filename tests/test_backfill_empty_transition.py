from dataclasses import replace

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
    _module_context,
    _recording_embed,
    _seed_backfilled,
    _seed_pre_00013,
    _source,
    _symbol,
    _texts,
    _zero_report,
)

import engram.indexer as indexer
from engram.corpora import CorpusFile, hash_source
from engram.store import open_store

# The backfill guards that are not specific to the empty-source crash window
# (repo scope, exclude_globs pass-through, the pinned model, and the refusal of a
# store indexed with another model) are pinned in tests/test_backfill.py by
# test_backfill_repo_scope_leaves_other_repos_untouched,
# test_backfill_embeds_with_the_pinned_model and
# test_backfill_refuses_store_indexed_with_another_model. This module adds the
# new/changed-source guard below, in
# test_backfill_keeps_the_mark_of_a_source_that_still_chunks_to_nothing.


class _Interrupted(Exception):
    """Stands in for a crash part-way through a write (disk error, signal)."""


class _FailingConn:
    """Delegates to a real connection, recording writes and failing the nth one."""

    def __init__(self, conn, nth=None, writes=None):
        self._conn = conn
        self._nth = nth
        self.writes = [] if writes is None else writes

    def _check(self, sql):
        verb = sql.strip().split(None, 1)[0].upper()
        if verb not in {"INSERT", "DELETE", "UPDATE", "REPLACE"}:
            return
        self.writes.append(" ".join(sql.split()))
        if self._nth is not None and len(self.writes) >= self._nth:
            raise _Interrupted(f"interrupted at write {len(self.writes)}")

    def execute(self, sql, *args):
        self._check(sql)
        return self._conn.execute(sql, *args)

    def executemany(self, sql, *args):
        self._check(sql)
        return self._conn.executemany(sql, *args)

    def cursor(self):
        return _FailingConn(self._conn.cursor(), self._nth, self.writes)

    def __getattr__(self, name):
        return getattr(self._conn, name)


class _SnapshotConn:
    """Delegates writes, recording what another connection sees after each one."""

    def __init__(self, conn, observer):
        self._conn = conn
        self._observer = observer
        self.seen = []

    def _snapshot(self, sql):
        verb = sql.strip().split(None, 1)[0].upper()
        if verb in {"INSERT", "DELETE", "UPDATE", "REPLACE"}:
            self.seen.append(_state(self._observer))

    def execute(self, sql, *args):
        result = self._conn.execute(sql, *args)
        self._snapshot(sql)
        return result

    def executemany(self, sql, *args):
        result = self._conn.executemany(sql, *args)
        self._snapshot(sql)
        return result

    def cursor(self):
        return _SnapshotConn(self._conn.cursor(), self._observer)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _report(rechunked, embedded, reused, cleared, failed=()):
    return indexer.BackfillReport(
        sources_rechunked=rechunked,
        chunks_embedded=embedded,
        vectors_reused=reused,
        empty_cleared=cleared,
        failed_sources=list(failed),
    )


def _crash_window(store, tmp_path, repo, name, vectors):
    """Chunk rows committed, empty mark never cleared: the interrupted state."""
    path, content_hash, stored, fresh = _seed_pre_00013(
        store, tmp_path, repo, name, vectors
    )
    store.mark_empty_source("code", repo, str(path), content_hash)
    return path, content_hash, stored, fresh


def _rows(store, path):
    stored = store.code_chunks_with_vectors(str(path))
    return [item.chunk for item in stored], [item.vector.values for item in stored]


# --- backfill_code: the crash window between row write and empty mark ---


def test_backfill_reuses_stored_rows_of_source_left_with_rows_and_empty_mark(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    a, h_a, stored_a, _ = _crash_window(store, tmp_path, "repoA", "mod.py", _VECTORS_A)
    b, h_b, _, fresh_b = _crash_window(
        store, tmp_path, "repoB", "other.py", _VECTORS_B
    )
    alpha, beta = (item.chunk for item in stored_a)
    gamma = _symbol(a, "repoA", h_a, "repoA_mod_gamma", 2, 30)
    # repoA's chunker now reorders its symbols and adds one.
    fresh_a = [
        _module_context(a, "repoA", h_a, "repoA-mod.py-context-marker"),
        replace(beta, chunk_ordinal=1, line_start=5, line_end=6),
        gamma,
        replace(alpha, chunk_ordinal=3, line_start=40, line_end=41),
    ]
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

    # Only chunks whose embedding text is new reach the embedder.
    assert sorted(_texts(embed_calls)) == sorted(
        c.text_for_embedding for c in (fresh_a[0], gamma, fresh_b[0])
    )
    assert all(model_id == _MODEL for _, model_id in embed_calls)
    assert sorted(chunk_calls) == sorted(
        [(a, "repoA", h_a), (b, "repoB", h_b), (bak, "repoA", h_bak)]
    )
    # Each reused vector follows its own symbol, wherever the symbol moved.
    assert _rows(store, a) == (
        fresh_a,
        [_EMBEDDED, _VECTORS_A[1], _EMBEDDED, _VECTORS_A[0]],
    )
    assert _rows(store, b) == (fresh_b, [_EMBEDDED] + _VECTORS_B)
    assert store.known_empty_sources_by_corpus(_PORTFOLIO, "code") == {
        ("code", "repoA", str(bak), h_bak)
    }
    assert report == _report(2, 3, 4, 2, [str(missing)])


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
    assert report == _report(2, 0, 4, 2)


def test_backfill_keeps_rows_and_mark_when_the_chunker_fails_in_the_crash_window(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    bad, h_bad, bad_stored, _ = _crash_window(
        store, tmp_path, "repoA", "bad.py", _VECTORS_A
    )
    good, _, _, fresh_good = _crash_window(
        store, tmp_path, "repoB", "good.py", _VECTORS_B
    )
    files = [CorpusFile("code", "repoA", bad), CorpusFile("code", "repoB", good)]
    _fake_enumerate(monkeypatch, files)
    _fake_chunker(monkeypatch, {str(good): fresh_good}, failing={str(bad)})
    embed_calls = _recording_embed(monkeypatch)

    report = indexer.backfill_code(store, _config(tmp_path), _PORTFOLIO)

    # The parse failure is reported and leaves that source exactly as it was.
    assert report == _report(1, 1, 2, 1, [str(bad)])
    assert store.code_chunks_with_vectors(str(bad)) == bad_stored
    assert store.known_empty_sources_by_corpus(_PORTFOLIO, "code") == {
        ("code", "repoA", str(bad), h_bad)
    }
    assert _texts(embed_calls) == [fresh_good[0].text_for_embedding]
    assert _rows(store, good) == (fresh_good, [_EMBEDDED] + _VECTORS_B)


def test_backfill_keeps_the_mark_of_a_source_that_still_chunks_to_nothing(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    blank = _source(tmp_path, "repoA", "blank.py", "\n")
    h_blank = hash_source(blank)
    store.mark_empty_source("code", "repoA", str(blank), h_blank)
    # Neither a brand-new source nor one changed since indexing may be touched.
    new = _source(tmp_path, "repoA", "new_mod.py", "def brand_new(): pass\n")
    changed = _source(tmp_path, "repoA", "changed.py", "edited since last index\n")
    stale_chunk = _symbol(changed, "repoA", "stale-hash", "changed", 0, 1)
    stale = _item(stale_chunk, _VECTORS_B[0], _MODEL, 4)
    store.replace_chunks_for_source("code", str(changed), [stale])
    files = [blank, new, changed]
    _fake_enumerate(monkeypatch, [CorpusFile("code", "repoA", p) for p in files])
    skipped = {
        str(p): [_symbol(p, "repoA", hash_source(p), f"late{i}", 0, 1)]
        for i, p in enumerate((new, changed))
    }
    chunk_calls = _fake_chunker(monkeypatch, skipped)
    embed_calls = _recording_embed(monkeypatch)

    report = indexer.backfill_code(store, _config(tmp_path), _PORTFOLIO)

    assert chunk_calls == [(blank, "repoA", h_blank)]
    assert embed_calls == []
    assert store.code_chunks_with_vectors(str(blank)) == []
    assert store.code_chunks_with_vectors(str(new)) == []
    assert store.code_chunks_with_vectors(str(changed)) == [stale]
    assert store.known_empty_sources_by_corpus(_PORTFOLIO, "code") == {
        ("code", "repoA", str(blank), h_blank)
    }
    assert report == _zero_report()


# --- Store.replace_source_chunks_and_empty_mark ---


_PATH = "/src/repoA/mod.py"
_NEAR = _PATH + ".bak"


def _corpus_chunk(corpus, path, ordinal, content_hash=None):
    chunk = replace(_distinct_chunk(path, ordinal), corpus=corpus)
    return chunk if content_hash is None else replace(chunk, content_hash=content_hash)


def _source_row(items):
    return {(i.chunk.repo, i.chunk.path, i.chunk.content_hash) for i in items}


def _fresh_items():
    return [
        _item(_distinct_chunk(_PATH, 2), _VECTORS_B[1], _MODEL, 4),
        _item(_distinct_chunk(_PATH, 3), _VECTORS_A[1], _MODEL, 4),
    ]


def _seed_interrupted_source(db):
    """Two committed chunk rows plus an empty mark on the very same source."""
    store = open_store(db)
    old = [
        _item(_distinct_chunk(_PATH, 0), _VECTORS_A[0], _MODEL, 4),
        _item(_distinct_chunk(_PATH, 1), _VECTORS_B[0], _MODEL, 4),
    ]
    store.replace_chunks_for_source("code", _PATH, old)
    store.mark_empty_source("code", "repoA", _PATH, "before-hash")
    return store, (old, {("code", "repoA", _PATH, "before-hash")})


def _state(store):
    return (
        store.code_chunks_with_vectors(_PATH),
        store.known_empty_sources_by_corpus(_PORTFOLIO, None),
    )


@pytest.mark.parametrize("corpus", ["code", "docs"])
def test_replace_source_chunks_and_empty_mark_commits_rows_and_drops_the_mark(
    tmp_path, corpus
):
    db = tmp_path / "engram.db"
    store = open_store(db)
    code_rows = [_item(_distinct_chunk(_PATH, 0), _VECTORS_A[0], _MODEL, 4)]
    store.replace_chunks_for_source("code", _PATH, code_rows)
    near = [_item(_distinct_chunk(_NEAR, 1), _VECTORS_B[0], _MODEL, 4)]
    store.replace_chunks_for_source("code", _NEAR, near)
    store.mark_empty_source("code", "repoA", _PATH, "mark-code")
    store.mark_empty_source("docs", "repoA", _PATH, "mark-docs")
    store.mark_empty_source("code", "repoA", _NEAR, "keep-bak")
    store.mark_empty_source("code", "repoB", _PATH, "keep-repo-b")
    fresh = [
        _item(_corpus_chunk(corpus, _PATH, 2, "h-new"), _VECTORS_B[1], _MODEL, 4),
        _item(_corpus_chunk(corpus, _PATH, 3, "h-new"), _VECTORS_A[1], _MODEL, 4),
    ]

    result = store.replace_source_chunks_and_empty_mark(
        corpus, "repoA", _PATH, "h-new", fresh
    )

    assert result is None
    # A second connection sees both effects, so they were committed, not pending.
    check = open_store(db)
    assert check.code_chunks_with_vectors(_PATH) == (
        fresh if corpus == "code" else code_rows
    )
    assert check.code_chunks_with_vectors(_NEAR) == near
    assert check.known_sources(_PORTFOLIO, "docs") == (
        {("repoA", _PATH, "h-new")} if corpus == "docs" else set()
    )
    # Only the mark of the corpus that was replaced is gone.
    assert check.known_empty_sources_by_corpus(_PORTFOLIO, None) == {
        ("code", "repoA", _PATH, "mark-code"),
        ("docs", "repoA", _PATH, "mark-docs"),
        ("code", "repoA", _NEAR, "keep-bak"),
        ("code", "repoB", _PATH, "keep-repo-b"),
    } - {(corpus, "repoA", _PATH, f"mark-{corpus}")}


def test_replace_source_chunks_and_empty_mark_replaces_the_rows_of_its_path_argument(
    tmp_path,
):
    db = tmp_path / "engram.db"
    store = open_store(db)
    old = [
        _item(_distinct_chunk(_PATH, 0), _VECTORS_A[0], _MODEL, 4),
        _item(_distinct_chunk(_PATH, 1), _VECTORS_B[0], _MODEL, 4),
    ]
    store.replace_chunks_for_source("code", _PATH, old)
    store.mark_empty_source("code", "repoA", _PATH, "doomed-hash")
    store.mark_empty_source("code", "repoA", _NEAR, "keep-bak")
    # The items carry another path, so only the path argument can pick the rows.
    elsewhere = [_item(_distinct_chunk(_NEAR, 2), _VECTORS_B[1], _MODEL, 4)]

    store.replace_source_chunks_and_empty_mark(
        "code", "repoA", _PATH, "h-new", elsewhere
    )

    check = open_store(db)
    assert check.code_chunks_with_vectors(_PATH) == []
    assert check.code_chunks_with_vectors(_NEAR) == elsewhere
    assert check.known_empty_sources_by_corpus(_PORTFOLIO, None) == {
        ("code", "repoA", _NEAR, "keep-bak")
    }


@pytest.mark.parametrize(
    ("corpus", "other", "content_hash"),
    [("code", "docs", "h-first"), ("docs", "code", "h-second")],
)
def test_replace_source_chunks_and_empty_mark_commits_the_mark_for_empty_items(
    tmp_path, corpus, other, content_hash
):
    db = tmp_path / "engram.db"
    store = open_store(db)
    doomed = [
        _item(_corpus_chunk(corpus, _PATH, 0), _VECTORS_A[0], _MODEL, 4),
        _item(_corpus_chunk(corpus, _PATH, 1), _VECTORS_B[0], _MODEL, 4),
    ]
    store.replace_chunks_for_source(corpus, _PATH, doomed)
    kept = [_item(_corpus_chunk(corpus, _NEAR, 2), _VECTORS_B[1], _MODEL, 4)]
    store.replace_chunks_for_source(corpus, _NEAR, kept)
    survivor = [_item(_corpus_chunk(other, _PATH, 3), _VECTORS_A[1], _MODEL, 4)]
    store.replace_chunks_for_source(other, _PATH, survivor)
    store.mark_empty_source(corpus, "repoA", _PATH, "superseded-hash")
    store.mark_empty_source(other, "repoA", _PATH, "keep-other")

    store.replace_source_chunks_and_empty_mark(corpus, "repoA", _PATH, content_hash, [])

    check = open_store(db)
    assert check.known_sources(_PORTFOLIO, corpus) == _source_row(kept)
    assert check.known_sources(_PORTFOLIO, other) == _source_row(survivor)
    assert check.known_empty_sources_by_corpus(_PORTFOLIO, None) == {
        (corpus, "repoA", _PATH, content_hash),
        (other, "repoA", _PATH, "keep-other"),
    }


@pytest.mark.parametrize("direction", ["mark_empty", "clear_mark"])
def test_replace_source_chunks_and_empty_mark_commits_nothing_when_any_write_fails(
    tmp_path, direction
):
    items = [] if direction == "mark_empty" else _fresh_items()
    # Count the writes of a complete call, then interrupt each one of them in turn.
    probe, _ = _seed_interrupted_source(tmp_path / "probe.db")
    counter = _FailingConn(probe.conn)
    probe.conn = counter
    probe.replace_source_chunks_and_empty_mark("code", "repoA", _PATH, "after", items)
    # A row write and a mark write at least, so there is a window to interrupt.
    assert len(counter.writes) >= 2

    for nth in range(1, len(counter.writes) + 1):
        db = tmp_path / f"fail-{nth}.db"
        store, before = _seed_interrupted_source(db)
        store.conn = _FailingConn(store.conn, nth)
        with pytest.raises(_Interrupted):
            store.replace_source_chunks_and_empty_mark(
                "code", "repoA", _PATH, "after-hash", items
            )
        assert _state(open_store(db)) == before, f"interrupted write {nth}"


@pytest.mark.parametrize("direction", ["mark_empty", "clear_mark"])
def test_replace_source_chunks_and_empty_mark_never_shows_the_rows_apart_from_the_mark(
    tmp_path, direction
):
    db = tmp_path / "engram.db"
    store, before = _seed_interrupted_source(db)
    items = [] if direction == "mark_empty" else _fresh_items()
    observer = open_store(db)
    assert _state(observer) == before
    watcher = _SnapshotConn(store.conn, observer)
    store.conn = watcher

    store.replace_source_chunks_and_empty_mark("code", "repoA", _PATH, "after", items)

    # No write of the pair is visible on its own: they land in one commit.
    assert watcher.seen
    assert watcher.seen == [before] * len(watcher.seen)
    expected_marks = {("code", "repoA", _PATH, "after")} if items == [] else set()
    assert _state(open_store(db)) == (items, expected_marks)
