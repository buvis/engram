from dataclasses import replace

import pytest
from _cli_helpers import _refuse

import engram.indexer as indexer
from engram import symbols
from engram.cli import main
from engram.client import EmbeddingEntry, EngramConfig, Vector
from engram.corpora import CorpusFile, hash_source
from engram.store import (
    Chunk,
    ChunkWithVector,
    Scope,
    StoreModelMismatchError,
    open_store,
)


def _chunk(
    *,
    corpus="code",
    repo="repoA",
    doc_type="function",
    path="/src/repoA/mod.py",
    heading="function run",
    body="def run(): pass",
    line_start=1,
    line_end=1,
    content_hash="hash-default",
    chunk_ordinal=0,
):
    return Chunk(
        corpus=corpus,
        repo=repo,
        doc_type=doc_type,
        path=path,
        heading=heading,
        body=body,
        line_start=line_start,
        line_end=line_end,
        content_hash=content_hash,
        chunk_ordinal=chunk_ordinal,
    )


def _item(chunk, values, model_id, dim):
    return ChunkWithVector(chunk=chunk, vector=Vector(values, model_id, dim))


# --- code_chunks_with_vectors ---


_HEADINGS = ["zeta", "theta", "lambda", "delta", "alpha"]  # reverse alphabetical
_DOC_TYPES = ["function", "class", "method", "module", "constant"]


def _distinct_chunk(path, ordinal):
    # Every stored column differs per ordinal, so a reader must return real values.
    name = _HEADINGS[ordinal]
    return _chunk(
        path=path,
        doc_type=_DOC_TYPES[ordinal],
        heading=f"function {name}",
        body=f"def {name}(): return {ordinal}",
        line_start=10 * ordinal + 1,
        line_end=10 * ordinal + 3 + ordinal,
        content_hash=f"hash-{ordinal}-{name}",
        chunk_ordinal=ordinal,
    )


@pytest.mark.parametrize(
    ("model_id", "values"),
    [
        (
            "model-a",
            [[0.5, -1.0, 2.0], [0.25, 4.0, -0.125], [-8.0, 0.75, 1.5]]
            + [[3.5, 0.0, -2.25], [1.0, 1.0, 64.0]],
        ),
        (
            "model-b",
            [[1.0, 2.0, 3.0, 4.0], [-0.5, 0.0, 0.5, 16.0], [3.0, -2.0, 1.0, 0.0]]
            + [[0.125, -0.25, 8.0, 2.0], [-1.0, 5.0, 0.0, -32.0]],
        ),
    ],
)
def test_code_chunks_with_vectors_round_trips_stored_vectors(
    tmp_path, model_id, values
):
    store = open_store(tmp_path / "engram.db")
    path = "/src/repoA/mod.py"
    dim = len(values[0])
    # Written out of ordinal order so insertion order differs from the result order.
    written = [
        _item(_distinct_chunk(path, ordinal), values[ordinal], model_id, dim)
        for ordinal in (2, 4, 0, 3, 1)
    ]
    store.replace_chunks_for_source("code", path, written)
    # Near misses: same path in another corpus, and paths sharing a prefix/suffix.
    store.upsert_chunks(
        [
            _item(
                _chunk(corpus="docs", path=path, content_hash="hash-docs"),
                [9.0] * dim,
                model_id,
                dim,
            ),
            _item(_chunk(path=path + ".bak"), [7.0] * dim, model_id, dim),
            _item(_chunk(path="/other" + path), [6.0] * dim, model_id, dim),
        ]
    )

    result = store.code_chunks_with_vectors(path)

    assert len(result) == len(written) == 5
    assert [item.chunk.chunk_ordinal for item in result] == [0, 1, 2, 3, 4]
    assert [item.chunk.heading for item in result] == [
        f"function {name}" for name in _HEADINGS
    ]
    assert [item.chunk.doc_type for item in result] == _DOC_TYPES
    assert [item.vector.values for item in result] == values
    assert all(item.vector.model_id == model_id for item in result)
    assert all(item.vector.dim == dim for item in result)
    assert result == sorted(written, key=lambda item: item.chunk.chunk_ordinal)


def test_code_chunks_with_vectors_returns_empty_before_vector_table_exists(tmp_path):
    store = open_store(tmp_path / "engram.db")

    assert store.code_chunks_with_vectors("/src/repoA/mod.py") == []


def test_code_chunks_with_vectors_returns_empty_for_unknown_path(tmp_path):
    store = open_store(tmp_path / "engram.db")
    store.upsert_chunks([_item(_chunk(path="/src/repoA/mod.py"), [1.0, 2.0], "m1", 2)])

    store.upsert_chunks([_item(_chunk(path="/src/repoA/aXb.py"), [3.0, 4.0], "m1", 2)])

    assert store.code_chunks_with_vectors("/src/repoA/mod") == []
    assert store.code_chunks_with_vectors("/src/repoA/other.py") == []
    # Exact match: no case folding, and "_" is a literal, not a wildcard.
    assert store.code_chunks_with_vectors("/src/repoA/MOD.py") == []
    assert store.code_chunks_with_vectors("/src/repoA/a_b.py") == []


def test_code_chunks_with_vectors_returns_single_chunk_for_other_path(tmp_path):
    store = open_store(tmp_path / "engram.db")
    store.upsert_chunks(
        [
            _item(_chunk(path="/src/repoA/a.py"), [1.0, 2.0], "m1", 2),
            _item(_chunk(path="/src/repoA/b.py"), [-3.0, 0.5], "m1", 2),
        ]
    )

    result = store.code_chunks_with_vectors("/src/repoA/b.py")

    assert len(result) == 1
    assert result[0].chunk.path == "/src/repoA/b.py"
    assert result[0].vector == Vector([-3.0, 0.5], "m1", 2)


# --- unmark_empty_source ---


def test_unmark_empty_source_deletes_only_the_matching_row(tmp_path):
    store = open_store(tmp_path / "engram.db")
    store.mark_empty_source("code", "repoA", "/src/a.py", "h1")
    store.mark_empty_source("code", "repoA", "/src/a.py.bak", "h2")
    store.mark_empty_source("docs", "repoA", "/src/a.py", "h3")
    store.mark_empty_source("code", "repoB", "/src/a.py", "h4")

    result = store.unmark_empty_source("code", "repoA", "/src/a.py")

    assert result is None
    assert store.known_empty_sources_by_corpus(Scope("portfolio", None), None) == {
        ("code", "repoA", "/src/a.py.bak", "h2"),
        ("docs", "repoA", "/src/a.py", "h3"),
        ("code", "repoB", "/src/a.py", "h4"),
    }


def test_unmark_empty_source_uses_each_argument_to_pick_the_row(tmp_path):
    store = open_store(tmp_path / "engram.db")
    store.mark_empty_source("code", "repoA", "/src/a.py", "h1")
    store.mark_empty_source("docs", "repoB", "/src/b.md", "h2")
    # Same corpus and path under repos sorting before and after repoB.
    store.mark_empty_source("docs", "repoA", "/src/b.md", "h3")
    store.mark_empty_source("docs", "repoC", "/src/b.md", "h4")

    store.unmark_empty_source("docs", "repoB", "/src/b.md")

    assert store.known_empty_sources_by_corpus(Scope("portfolio", None), None) == {
        ("code", "repoA", "/src/a.py", "h1"),
        ("docs", "repoA", "/src/b.md", "h3"),
        ("docs", "repoC", "/src/b.md", "h4"),
    }


def test_unmark_empty_source_is_noop_when_no_row_matches(tmp_path):
    store = open_store(tmp_path / "engram.db")
    store.mark_empty_source("code", "repoA", "/src/a.py", "h1")

    store.unmark_empty_source("code", "repoA", "/src/missing.py")
    store.unmark_empty_source("docs", "repoA", "/src/a.py")

    assert store.known_empty_sources_by_corpus(Scope("portfolio", None), None) == {
        ("code", "repoA", "/src/a.py", "h1"),
    }


# --- backfill_code ---


_MODEL = "test-model"
_EMBEDDED = [0.0, 0.0, 1.0, 1.0]
_VECTORS_A = [[0.5, -1.0, 2.0, 0.25], [-4.0, 0.125, 8.0, 3.0]]
_VECTORS_B = [[16.0, 0.75, -0.5, 2.0], [1.5, -32.0, 0.25, -8.0]]
_VECTORS_C = _VECTORS_B + [[-0.25, 64.0, 4.0, -1.5]]
_PORTFOLIO = Scope("portfolio", None)


def _zero_report():
    return indexer.BackfillReport(
        sources_rechunked=0,
        chunks_embedded=0,
        vectors_reused=0,
        empty_cleared=0,
        failed_sources=[],
    )


def _config(tmp_path, exclude_globs=()):
    return EngramConfig(
        embeddings=[EmbeddingEntry(id=_MODEL, endpoint="http://127.0.0.1:8081/v1")],
        pinned_id=None,
        config_path=tmp_path / "config.toml",
        exclude_globs=exclude_globs,
    )


def _source(tmp_path, repo, name, text):
    path = tmp_path / repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _symbol(path, repo, content_hash, name, ordinal, line):
    return _chunk(
        repo=repo,
        path=str(path),
        heading=f"function {name}",
        body=f"def {name}(): return '{name}-marker'",
        line_start=line,
        line_end=line + 1,
        content_hash=content_hash,
        chunk_ordinal=ordinal,
    )


def _module_context(path, repo, content_hash, marker):
    return _chunk(
        repo=repo,
        path=str(path),
        doc_type=symbols.MODULE_CONTEXT_DOC_TYPE,
        heading="Module context",
        body=f"import os  # {marker}",
        content_hash=content_hash,
        chunk_ordinal=0,
    )


def _seed_pre_00013(
    store, tmp_path, repo, name, vectors, names=("alpha", "beta"), model_id=_MODEL
):
    # Only symbol chunks under the current hash: what a pre-00013 index wrote.
    path = _source(tmp_path, repo, name, f"# {repo} {name}\n")
    content_hash = hash_source(path)
    prefix = f"{repo}_{path.stem}"
    old = [
        _symbol(path, repo, content_hash, f"{prefix}_{sym}", ordinal, 10 * ordinal + 3)
        for ordinal, sym in enumerate(names)
    ]
    stored = [_item(c, v, model_id, 4) for c, v in zip(old, vectors, strict=True)]
    store.replace_chunks_for_source("code", str(path), stored)
    # The current chunker adds module context at ordinal 0 and shifts the symbols.
    fresh = [_module_context(path, repo, content_hash, f"{repo}-{name}-context-marker")]
    fresh += [replace(c, chunk_ordinal=c.chunk_ordinal + 1) for c in old]
    return path, content_hash, stored, fresh


def _seed_backfilled(store, tmp_path, repo, name, vectors):
    # Module context plus one symbol: already what the current chunker emits.
    path = _source(tmp_path, repo, name, f"# {repo} {name}\n")
    content_hash = hash_source(path)
    chunks = [
        _module_context(path, repo, content_hash, f"{repo}-{name}-context-marker"),
        _symbol(path, repo, content_hash, f"{repo}_{path.stem}_alpha", 1, 3),
    ]
    stored = [_item(c, v, _MODEL, 4) for c, v in zip(chunks, vectors, strict=True)]
    store.replace_chunks_for_source("code", str(path), stored)
    return path, stored, chunks


def _fake_enumerate(monkeypatch, files):
    calls = []

    def fake(*args, **kwargs):
        calls.append(kwargs)
        return iter(list(files))

    monkeypatch.setattr("engram.indexer.symbols.enumerate", fake)
    return calls


def _fake_chunker(monkeypatch, by_path, failing=()):
    calls = []

    def fake(path, repo, content_hash):
        calls.append((path, repo, content_hash))
        if str(path) in failing:
            raise RuntimeError("tree-sitter blew up")
        return list(by_path.get(str(path), []))

    monkeypatch.setattr("engram.indexer.symbols.chunk", fake)
    return calls


def _recording_embed(monkeypatch):
    calls = []

    def fake(texts, entry):
        calls.append((list(texts), entry.id))
        return [Vector(list(_EMBEDDED), entry.id, 4) for _ in texts]

    monkeypatch.setattr("engram.indexer.embed", fake)
    return calls


def _texts(embed_calls):
    return [text for texts, _ in embed_calls for text in texts]


def test_backfill_adds_module_context_and_reuses_symbol_vectors(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    path, h, _, fresh = _seed_pre_00013(store, tmp_path, "repoA", "mod.py", _VECTORS_A)
    _fake_enumerate(monkeypatch, [CorpusFile("code", "repoA", path)])
    chunk_calls = _fake_chunker(monkeypatch, {str(path): fresh})
    embed_calls = _recording_embed(monkeypatch)

    report = indexer.backfill_code(store, _config(tmp_path), _PORTFOLIO)

    assert chunk_calls == [(path, "repoA", h)]
    assert len(embed_calls) == 1
    texts, model_id = embed_calls[0]
    assert model_id == _MODEL
    # Full embedding text: heading, repo-relative path, then body.
    assert texts == [fresh[0].text_for_embedding]
    stored = store.code_chunks_with_vectors(str(path))
    assert [item.chunk for item in stored] == fresh
    assert [item.vector.values for item in stored] == [_EMBEDDED] + _VECTORS_A
    assert report == indexer.BackfillReport(
        sources_rechunked=1,
        chunks_embedded=1,
        vectors_reused=2,
        empty_cleared=0,
        failed_sources=[],
    )


def test_backfill_indexes_source_cached_as_empty_and_clears_mark(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    parsed = _source(tmp_path, "repoA", "grammar.py", "def gamma(): pass\n")
    blank = _source(tmp_path, "repoA", "blank.py", "\n")
    h_parsed, h_blank = hash_source(parsed), hash_source(blank)
    store.mark_empty_source("code", "repoA", str(parsed), h_parsed)
    store.mark_empty_source("code", "repoA", str(blank), h_blank)
    fresh = [
        _module_context(parsed, "repoA", h_parsed, "gamma-context-marker"),
        _symbol(parsed, "repoA", h_parsed, "gamma", 1, 1),
    ]
    _fake_enumerate(
        monkeypatch, [CorpusFile("code", "repoA", parsed), CorpusFile("code", "repoA", blank)]
    )
    _fake_chunker(monkeypatch, {str(parsed): fresh})
    embed_calls = _recording_embed(monkeypatch)

    report = indexer.backfill_code(store, _config(tmp_path), _PORTFOLIO)

    texts = _texts(embed_calls)
    assert sorted(texts) == sorted(c.text_for_embedding for c in fresh)
    stored = store.code_chunks_with_vectors(str(parsed))
    assert [item.chunk for item in stored] == fresh
    assert all(item.vector.values == _EMBEDDED for item in stored)
    assert store.code_chunks_with_vectors(str(blank)) == []
    # Only the source that now chunks loses its empty mark.
    assert store.known_empty_sources_by_corpus(_PORTFOLIO, "code") == {
        ("code", "repoA", str(blank), h_blank)
    }
    # The blank source still chunks to nothing, so it is not rechunked.
    assert report == indexer.BackfillReport(
        sources_rechunked=1,
        chunks_embedded=2,
        vectors_reused=0,
        empty_cleared=1,
        failed_sources=[],
    )


def test_backfill_second_run_embeds_nothing(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    a, _, _, fresh_a = _seed_pre_00013(store, tmp_path, "repoA", "one.py", _VECTORS_A)
    # Pre-00013 with three symbols: more rows than a backfilled two-symbol source.
    wide, _, _, fresh_wide = _seed_pre_00013(
        store, tmp_path, "repoA", "wide.py", _VECTORS_C, ("alpha", "beta", "gamma")
    )
    # Two rows that already match the current chunker, module context included.
    done, done_stored, done_fresh = _seed_backfilled(
        store, tmp_path, "repoA", "done.py", _VECTORS_B
    )
    paths = (a, wide, done)
    _fake_enumerate(monkeypatch, [CorpusFile("code", "repoA", p) for p in paths])
    _fake_chunker(
        monkeypatch, {str(a): fresh_a, str(wide): fresh_wide, str(done): done_fresh}
    )
    embed_calls = _recording_embed(monkeypatch)

    first = indexer.backfill_code(store, _config(tmp_path), _PORTFOLIO)
    assert first == indexer.BackfillReport(
        sources_rechunked=2,
        chunks_embedded=2,
        vectors_reused=5,
        empty_cleared=0,
        failed_sources=[],
    )
    expected = [fresh_a[0].text_for_embedding, fresh_wide[0].text_for_embedding]
    assert sorted(_texts(embed_calls)) == sorted(expected)
    assert store.code_chunks_with_vectors(str(done)) == done_stored
    after_first = {p: store.code_chunks_with_vectors(str(p)) for p in paths}
    assert [item.chunk for item in after_first[wide]] == fresh_wide
    embed_calls.clear()

    second = indexer.backfill_code(store, _config(tmp_path), _PORTFOLIO)

    assert embed_calls == []
    assert second == _zero_report()
    assert {p: store.code_chunks_with_vectors(str(p)) for p in paths} == after_first


def test_backfill_skips_new_and_changed_sources(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    known, h, _, fresh = _seed_pre_00013(store, tmp_path, "repoA", "mod.py", _VECTORS_A)
    # Same path prefix as the known source, stored under an outdated hash.
    changed = _source(tmp_path, "repoA", "mod.py.bak", "edited since last index\n")
    stale_chunk = _symbol(changed, "repoA", "stale-hash", "changed", 0, 1)
    stale = _item(stale_chunk, _VECTORS_B[0], _MODEL, 4)
    store.replace_chunks_for_source("code", str(changed), [stale])
    was_empty = _source(tmp_path, "repoA", "was_empty.py", "def now_code(): pass\n")
    store.mark_empty_source("code", "repoA", str(was_empty), "stale-empty-hash")
    new = _source(tmp_path, "repoA", "new_mod.py", "def brand_new(): pass\n")
    others = (changed, was_empty, new)
    _fake_enumerate(monkeypatch, [CorpusFile("code", "repoA", p) for p in (*others, known)])
    by_path = {
        str(p): [_symbol(p, "repoA", hash_source(p), f"skip{i}", 0, 1)]
        for i, p in enumerate(others)
    }
    chunk_calls = _fake_chunker(monkeypatch, {**by_path, str(known): fresh})
    embed_calls = _recording_embed(monkeypatch)

    report = indexer.backfill_code(store, _config(tmp_path), _PORTFOLIO)

    assert chunk_calls == [(known, "repoA", h)]
    texts = _texts(embed_calls)
    assert len(texts) == 1
    assert "repoA-mod.py-context-marker" in texts[0]
    assert store.code_chunks_with_vectors(str(changed)) == [stale]
    assert store.code_chunks_with_vectors(str(was_empty)) == []
    assert store.code_chunks_with_vectors(str(new)) == []
    assert store.known_sources(_PORTFOLIO, "code") == {
        ("repoA", str(known), h),
        ("repoA", str(changed), "stale-hash"),
    }
    assert store.known_empty_sources_by_corpus(_PORTFOLIO, "code") == {
        ("code", "repoA", str(was_empty), "stale-empty-hash")
    }
    assert report.sources_rechunked == 1
    assert report.failed_sources == []


def test_backfill_chunker_failure_keeps_existing_rows(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    bad, _, bad_stored, bad_fresh = _seed_pre_00013(store, tmp_path, "repoA", "bad.py", _VECTORS_A)
    good, _, _, good_fresh = _seed_pre_00013(store, tmp_path, "repoA", "good.py", _VECTORS_B)
    missing = tmp_path / "repoA" / "gone.py"
    blank = _source(tmp_path, "repoA", "blank.py", "\n")
    h_blank = hash_source(blank)
    store.mark_empty_source("code", "repoA", str(blank), h_blank)
    files = [CorpusFile("code", "repoA", p) for p in (bad, missing, blank, good)]
    _fake_enumerate(monkeypatch, files)
    failing = {str(bad), str(blank)}
    _fake_chunker(monkeypatch, {str(bad): bad_fresh, str(good): good_fresh}, failing)
    embed_calls = _recording_embed(monkeypatch)

    report = indexer.backfill_code(store, _config(tmp_path), _PORTFOLIO)

    # Chunker exceptions (known and empty-marked) and the unreadable file surface.
    assert sorted(report.failed_sources) == sorted([str(bad), str(missing), str(blank)])
    assert store.code_chunks_with_vectors(str(bad)) == bad_stored
    assert store.known_empty_sources_by_corpus(_PORTFOLIO, "code") == {
        ("code", "repoA", str(blank), h_blank)
    }
    texts = _texts(embed_calls)
    assert len(texts) == 1
    assert "repoA-good.py-context-marker" in texts[0]
    assert not any("bad" in t for t in texts)
    good_stored = store.code_chunks_with_vectors(str(good))
    assert [item.chunk for item in good_stored] == good_fresh
    assert [item.vector.values for item in good_stored] == [_EMBEDDED] + _VECTORS_B
    assert report.sources_rechunked == 1


def test_backfill_repo_scope_leaves_other_repos_untouched(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    a, h_a, _, fresh_a = _seed_pre_00013(store, tmp_path, "repoA", "mod.py", _VECTORS_A)
    b, _, stored_b, _ = _seed_pre_00013(store, tmp_path, "repoB", "mod.py", _VECTORS_B)
    config = _config(tmp_path, exclude_globs=("vendor/**", "*.min.js"))
    enum_calls = _fake_enumerate(
        monkeypatch, [CorpusFile("code", "repoB", b), CorpusFile("code", "repoA", a)]
    )
    chunk_calls = _fake_chunker(monkeypatch, {str(a): fresh_a, str(b): []})
    embed_calls = _recording_embed(monkeypatch)

    # "repo" prefixes both repo names but matches neither.
    assert indexer.backfill_code(store, config, Scope("repo", "repo")) == _zero_report()
    assert chunk_calls == []
    assert embed_calls == []

    report = indexer.backfill_code(store, config, Scope("repo", "repoA"))

    assert enum_calls
    assert all(call.get("exclude_globs") == ("vendor/**", "*.min.js") for call in enum_calls)
    assert chunk_calls == [(a, "repoA", h_a)]
    texts = _texts(embed_calls)
    assert len(texts) == 1
    assert "repoA-mod.py-context-marker" in texts[0]
    assert not any("repoB" in t for t in texts)
    assert [item.chunk for item in store.code_chunks_with_vectors(str(a))] == fresh_a
    assert store.code_chunks_with_vectors(str(b)) == stored_b
    assert report.sources_rechunked == 1
    assert report.vectors_reused == 2


def test_backfill_reuses_vectors_by_symbol_content_not_position(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    path, h, stored, _ = _seed_pre_00013(store, tmp_path, "repoA", "mod.py", _VECTORS_A)
    alpha, beta = (item.chunk for item in stored)
    gamma = _symbol(path, "repoA", h, "repoA_mod_gamma", 2, 30)
    # The current chunker reorders and moves the symbols and adds a new one.
    fresh = [
        _module_context(path, "repoA", h, "reorder-context-marker"),
        replace(beta, chunk_ordinal=1, line_start=5, line_end=6),
        gamma,
        replace(alpha, chunk_ordinal=3, line_start=40, line_end=41),
    ]
    _fake_enumerate(monkeypatch, [CorpusFile("code", "repoA", path)])
    _fake_chunker(monkeypatch, {str(path): fresh})
    embed_calls = _recording_embed(monkeypatch)

    report = indexer.backfill_code(store, _config(tmp_path), _PORTFOLIO)

    assert len(embed_calls) == 1
    expected = [fresh[0].text_for_embedding, gamma.text_for_embedding]
    assert sorted(_texts(embed_calls)) == sorted(expected)
    result = store.code_chunks_with_vectors(str(path))
    assert [item.chunk for item in result] == fresh
    # Each reused vector follows its own symbol, wherever the symbol moved.
    assert [item.vector.values for item in result] == [
        _EMBEDDED,
        _VECTORS_A[1],
        _EMBEDDED,
        _VECTORS_A[0],
    ]
    assert report == indexer.BackfillReport(
        sources_rechunked=1,
        chunks_embedded=2,
        vectors_reused=2,
        empty_cleared=0,
        failed_sources=[],
    )


def test_backfill_refuses_store_indexed_with_another_model(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    path, _, stored, fresh = _seed_pre_00013(
        store, tmp_path, "repoA", "mod.py", _VECTORS_A, model_id="other-model"
    )
    _fake_enumerate(monkeypatch, [CorpusFile("code", "repoA", path)])
    chunk_calls = _fake_chunker(monkeypatch, {str(path): fresh})
    embed_calls = _recording_embed(monkeypatch)

    with pytest.raises(StoreModelMismatchError):
        indexer.backfill_code(store, _config(tmp_path), _PORTFOLIO)

    # The mismatch is caught before any chunking or embedding work.
    assert chunk_calls == []
    assert embed_calls == []
    assert store.code_chunks_with_vectors(str(path)) == stored


def test_backfill_embeds_with_the_pinned_model(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    path, _, _, fresh = _seed_pre_00013(
        store, tmp_path, "repoA", "mod.py", _VECTORS_A, model_id="pinned-model"
    )
    # Pinned entry is neither the first nor the last in the shortlist.
    config = EngramConfig(
        embeddings=[
            EmbeddingEntry(id=model, endpoint="http://127.0.0.1:8081/v1")
            for model in ("first-model", "pinned-model", "last-model")
        ],
        pinned_id="pinned-model",
        config_path=tmp_path / "config.toml",
    )
    _fake_enumerate(monkeypatch, [CorpusFile("code", "repoA", path)])
    _fake_chunker(monkeypatch, {str(path): fresh})
    embed_calls = _recording_embed(monkeypatch)

    report = indexer.backfill_code(store, config, _PORTFOLIO)

    assert embed_calls[0][1] == "pinned-model"
    assert [model_id for _, model_id in embed_calls] == ["pinned-model"]
    assert [item.chunk for item in store.code_chunks_with_vectors(str(path))] == fresh
    assert report.chunks_embedded == 1
    assert report.vectors_reused == 2


def test_backfill_marks_known_source_empty_when_chunker_now_returns_nothing(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    path, h, _, _ = _seed_pre_00013(store, tmp_path, "repoA", "gutted.py", _VECTORS_A)
    kept, kept_stored, kept_fresh = _seed_backfilled(
        store, tmp_path, "repoA", "kept.py", _VECTORS_B
    )
    files = [CorpusFile("code", "repoA", p) for p in (path, kept)]
    _fake_enumerate(monkeypatch, files)
    _fake_chunker(monkeypatch, {str(path): [], str(kept): kept_fresh})
    embed_calls = _recording_embed(monkeypatch)

    report = indexer.backfill_code(store, _config(tmp_path), _PORTFOLIO)

    assert _texts(embed_calls) == []
    # Rows are cleared and the source is recorded as known-empty under its hash.
    assert store.code_chunks_with_vectors(str(path)) == []
    assert store.known_empty_sources_by_corpus(_PORTFOLIO, "code") == {
        ("code", "repoA", str(path), h)
    }
    assert store.known_sources(_PORTFOLIO, "code") == {
        ("repoA", str(kept), kept_fresh[0].content_hash)
    }
    assert store.code_chunks_with_vectors(str(kept)) == kept_stored
    assert report == indexer.BackfillReport(
        sources_rechunked=1,
        chunks_embedded=0,
        vectors_reused=0,
        empty_cleared=0,
        failed_sources=[],
    )


# --- CLI: engram index --backfill-code ---


@pytest.mark.parametrize(
    "conflict",
    [["--corpus", "code"], ["--corpus", "docs"], ["--rebuild"], ["--reembed-code"]],
)
def test_cli_backfill_rejects_corpus_rebuild_and_reembed(
    tmp_path, monkeypatch, capsys, conflict
):
    # Keep every write path off the production DB, even if a branch misroutes.
    monkeypatch.setattr("engram.cli.DEFAULT_DB_PATH", tmp_path / "engram.db")
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.load_config", _refuse)
    monkeypatch.setattr("engram.cli.reembed_code", _refuse)
    monkeypatch.setattr("engram.cli.index", _refuse)

    with pytest.raises(SystemExit) as exc_info:
        main(["index", "--backfill-code", *conflict])

    # argparse's parser.error() exit code, not some other non-zero exit.
    assert exc_info.value.code == 2
    # A conflict rejection, not argparse failing to recognise the flag.
    assert "unrecognized arguments" not in capsys.readouterr().err
    assert not (tmp_path / "engram.db").exists()


def _seed_one_pre_00013(store, tmp_path, monkeypatch):
    path, _, _, fresh = _seed_pre_00013(store, tmp_path, "repoA", "mod.py", _VECTORS_A)
    _fake_enumerate(monkeypatch, [CorpusFile("code", "repoA", path)])
    _fake_chunker(monkeypatch, {str(path): fresh})
    # One source rechunked: its new module context embedded, every symbol reused.
    return {path: fresh}, (1, 1, len(_VECTORS_A), 0), []


def _seed_two_repos_with_failure(store, tmp_path, monkeypatch):
    wide, _, _, fresh_wide = _seed_pre_00013(
        store, tmp_path, "repoA", "wide.py", _VECTORS_C, ("alpha", "beta", "gamma")
    )
    parsed = _source(tmp_path, "repoB", "grammar.py", "def gamma(): pass\n")
    h = hash_source(parsed)
    store.mark_empty_source("code", "repoB", str(parsed), h)
    fresh_parsed = [
        _module_context(parsed, "repoB", h, "gamma-context-marker"),
        _symbol(parsed, "repoB", h, "gamma", 1, 1),
    ]
    missing = tmp_path / "repoA" / "gone.py"
    files = [("repoA", wide), ("repoB", parsed), ("repoA", missing)]
    _fake_enumerate(monkeypatch, [CorpusFile("code", r, p) for r, p in files])
    _fake_chunker(monkeypatch, {str(wide): fresh_wide, str(parsed): fresh_parsed})
    # wide: module context embedded, its symbols reused; parsed: every chunk
    # embedded and its empty mark cleared; the unreadable file fails.
    counts = (2, 1 + len(fresh_parsed), len(_VECTORS_C), 1)
    return {wide: fresh_wide, parsed: fresh_parsed}, counts, [str(missing)]


def _seed_unrelated_counts(store, tmp_path, monkeypatch):
    # Every count differs from the others and from any sum of the others.
    wide, _, _, fresh_wide = _seed_pre_00013(
        store, tmp_path, "repoA", "wide.py", _VECTORS_C, ("alpha", "beta", "gamma")
    )
    one, _, _, fresh_one = _seed_pre_00013(store, tmp_path, "repoB", "one.py", _VECTORS_A)
    parsed = _source(tmp_path, "repoB", "grammar.py", "def g1(): pass\n")
    h = hash_source(parsed)
    store.mark_empty_source("code", "repoB", str(parsed), h)
    fresh_parsed = [_module_context(parsed, "repoB", h, "grammar-context-marker")]
    fresh_parsed += [_symbol(parsed, "repoB", h, f"g{i}", i, 10 * i) for i in (1, 2, 3)]
    gone_a = tmp_path / "repoA" / "gone.py"
    gone_b = tmp_path / "repoB" / "gone.py"
    files = [("repoA", wide), ("repoA", gone_a), ("repoB", parsed)]
    files += [("repoB", one), ("repoB", gone_b)]
    _fake_enumerate(monkeypatch, [CorpusFile("code", r, p) for r, p in files])
    by_path = {str(wide): fresh_wide, str(one): fresh_one, str(parsed): fresh_parsed}
    _fake_chunker(monkeypatch, by_path)
    # wide and one: module context embedded, symbols reused; parsed: every chunk
    # embedded and its empty mark cleared; both unreadable files fail.
    counts = (3, 1 + 1 + len(fresh_parsed), len(_VECTORS_C) + len(_VECTORS_A), 1)
    rows = {wide: fresh_wide, one: fresh_one, parsed: fresh_parsed}
    return rows, counts, [str(gone_a), str(gone_b)]


@pytest.mark.parametrize(
    "seed", [_seed_one_pre_00013, _seed_two_repos_with_failure, _seed_unrelated_counts]
)
def test_cli_backfill_prints_summary(tmp_path, monkeypatch, capsys, seed):
    db = tmp_path / "engram.db"
    store = open_store(db)
    expected_rows, counts, failed = seed(store, tmp_path, monkeypatch)
    store.conn.close()
    embed_calls = _recording_embed(monkeypatch)
    monkeypatch.setattr("engram.cli.DEFAULT_DB_PATH", db)
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: _config(tmp_path))
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: open_store(db))

    exit_code = main(["index", "--backfill-code", "--scope", "portfolio"])

    captured = capsys.readouterr()
    rechunked, embedded, reused, cleared = counts
    assert captured.out.splitlines() == [
        f"backfilled {rechunked} code sources: {embedded} chunks embedded, "
        f"{reused} vectors reused, {cleared} empty marks cleared"
    ]
    # One stderr line per failed source, in any order.
    assert sorted(captured.err.splitlines()) == sorted(
        f"failed (existing rows kept): {path}" for path in failed
    )
    assert exit_code == 0
    assert len(_texts(embed_calls)) == embedded
    # The backfill landed in the tmp_path store the CLI opened.
    check = open_store(db)
    for path, fresh in expected_rows.items():
        assert [item.chunk for item in check.code_chunks_with_vectors(str(path))] == fresh
