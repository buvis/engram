import os
import time

import pytest

from engram.client import Vector
from engram.store import (
    Chunk,
    ChunkWithVector,
    Scope,
    StoreModelMismatchError,
    open_store,
)


def _chunk(
    *,
    corpus="docs",
    repo="repoA",
    doc_type="markdown",
    path="doc.md",
    heading="Heading",
    body="body text",
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


# --- upsert / search_bm25 round trip ---


def test_upsert_then_search_bm25_round_trips_matching_chunk(tmp_path):
    store = open_store(tmp_path / "engram.db")
    chunk = _chunk(body="the quick zebra jumps over the lazy dog", content_hash="h1")
    vector = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)

    store.upsert_chunks([ChunkWithVector(chunk=chunk, vector=vector)])

    hits = store.search_bm25("zebra", Scope("portfolio", None), corpus=None, k=10)

    assert len(hits) == 1
    assert hits[0].chunk == chunk


# --- model mismatch (PRD key acceptance test) ---


def test_upsert_rejects_mismatched_model_before_writing(tmp_path):
    store = open_store(tmp_path / "engram.db")
    chunk1 = _chunk(content_hash="h1", body="alpha content")
    vector1 = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    store.upsert_chunks([ChunkWithVector(chunk=chunk1, vector=vector1)])

    before = store.status(Scope("portfolio", None)).per_corpus["docs"].row_count

    chunk2 = _chunk(content_hash="h2", path="bar.md", body="distinctive-mismatch-token")
    vector2 = Vector([0.5, 0.6, 0.7, 0.8], "m2", 4)

    with pytest.raises(StoreModelMismatchError):
        store.upsert_chunks([ChunkWithVector(chunk=chunk2, vector=vector2)])

    after = store.status(Scope("portfolio", None)).per_corpus["docs"].row_count
    assert after == before

    hits = store.search_bm25(
        "distinctive-mismatch-token", Scope("portfolio", None), corpus=None, k=10
    )
    assert hits == []


# --- search_knn ---


def test_search_knn_returns_empty_list_when_nothing_indexed(tmp_path):
    store = open_store(tmp_path / "engram.db")
    query = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)

    hits = store.search_knn(query, Scope("portfolio", None), corpus=None, k=5)

    assert hits == []


def test_search_knn_ranks_nearest_vector_first(tmp_path):
    store = open_store(tmp_path / "engram.db")
    items = [
        ChunkWithVector(
            chunk=_chunk(content_hash="h1", path="a.md"),
            vector=Vector([1.0, 0.0, 0.0, 0.0], "m1", 4),
        ),
        ChunkWithVector(
            chunk=_chunk(content_hash="h2", path="b.md"),
            vector=Vector([0.0, 1.0, 0.0, 0.0], "m1", 4),
        ),
        ChunkWithVector(
            chunk=_chunk(content_hash="h3", path="c.md"),
            vector=Vector([0.0, 0.0, 1.0, 0.0], "m1", 4),
        ),
    ]
    store.upsert_chunks(items)

    query = Vector([0.0, 0.9, 0.0, 0.0], "m1", 4)
    hits = store.search_knn(query, Scope("portfolio", None), corpus=None, k=3)

    assert hits[0].chunk.path == "b.md"


def test_search_knn_rejects_query_vector_with_mismatched_dimension(tmp_path):
    store = open_store(tmp_path / "engram.db")
    store.upsert_chunks(
        [
            ChunkWithVector(
                chunk=_chunk(content_hash="h1"),
                vector=Vector([0.1, 0.2, 0.3, 0.4], "m1", 4),
            )
        ]
    )

    bad_query = Vector([0.1, 0.2, 0.3, 0.4, 0.5], "m1", 5)

    with pytest.raises(StoreModelMismatchError):
        store.search_knn(bad_query, Scope("portfolio", None), corpus=None, k=5)


# --- scope filtering ---


def test_search_bm25_scope_repo_filters_to_single_repo(tmp_path):
    store = open_store(tmp_path / "engram.db")
    chunk_a = _chunk(repo="repoA", content_hash="ha", path="a.md", body="alpha-unique-token")
    chunk_b = _chunk(repo="repoB", content_hash="hb", path="b.md", body="beta-unique-token")
    vec = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=chunk_a, vector=vec),
            ChunkWithVector(chunk=chunk_b, vector=vec),
        ]
    )

    hits_a = store.search_bm25("unique-token", Scope("repo", "repoA"), corpus=None, k=10)
    assert [h.chunk.repo for h in hits_a] == ["repoA"]

    hits_all = store.search_bm25("unique-token", Scope("portfolio", None), corpus=None, k=10)
    assert {h.chunk.repo for h in hits_all} == {"repoA", "repoB"}


def test_search_knn_scope_repo_filters_to_single_repo(tmp_path):
    store = open_store(tmp_path / "engram.db")
    chunk_a = _chunk(repo="repoA", content_hash="ha", path="a.md")
    chunk_b = _chunk(repo="repoB", content_hash="hb", path="b.md")
    vec = Vector([1.0, 0.0, 0.0, 0.0], "m1", 4)
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=chunk_a, vector=vec),
            ChunkWithVector(chunk=chunk_b, vector=vec),
        ]
    )

    query = Vector([1.0, 0.0, 0.0, 0.0], "m1", 4)
    hits_a = store.search_knn(query, Scope("repo", "repoA"), corpus=None, k=10)
    assert [h.chunk.repo for h in hits_a] == ["repoA"]

    hits_all = store.search_knn(query, Scope("portfolio", None), corpus=None, k=10)
    assert {h.chunk.repo for h in hits_all} == {"repoA", "repoB"}


# --- prune ---


def test_prune_deletes_only_matching_scope_and_corpus(tmp_path):
    store = open_store(tmp_path / "engram.db")
    vec = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    chunk_a = _chunk(corpus="docs", repo="repoA", content_hash="ha", path="a.md", body="alpha-marker")
    chunk_b = _chunk(corpus="docs", repo="repoB", content_hash="hb", path="b.md", body="beta-marker")
    chunk_c = _chunk(corpus="adr", repo="repoA", content_hash="hc", path="c.md", body="gamma-marker")
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=chunk_a, vector=vec),
            ChunkWithVector(chunk=chunk_b, vector=vec),
            ChunkWithVector(chunk=chunk_c, vector=vec),
        ]
    )

    deleted = store.prune(Scope("repo", "repoA"), corpus="docs", active_sources=set())

    assert deleted == 1
    scope_all = Scope("portfolio", None)
    assert store.search_bm25("alpha-marker", scope_all, corpus=None, k=10) == []
    assert len(store.search_bm25("beta-marker", scope_all, corpus=None, k=10)) == 1
    assert len(store.search_bm25("gamma-marker", scope_all, corpus=None, k=10)) == 1


def test_prune_with_all_active_sources_deletes_nothing(tmp_path):
    store = open_store(tmp_path / "engram.db")
    chunk = _chunk(repo="repoA", content_hash="h1")
    store.upsert_chunks(
        [ChunkWithVector(chunk=chunk, vector=Vector([0.1, 0.2, 0.3, 0.4], "m1", 4))]
    )

    active_sources = {(chunk.repo, chunk.path, chunk.content_hash)}
    deleted = store.prune(Scope("repo", "repoA"), corpus="docs", active_sources=active_sources)

    assert deleted == 0


# --- status ---


def test_status_reports_row_count_per_corpus(tmp_path):
    store = open_store(tmp_path / "engram.db")
    vec = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=_chunk(corpus="docs", content_hash="h1", path="a.md"), vector=vec),
            ChunkWithVector(chunk=_chunk(corpus="docs", content_hash="h2", path="b.md"), vector=vec),
            ChunkWithVector(chunk=_chunk(corpus="adr", content_hash="h3", path="c.md"), vector=vec),
        ]
    )

    report = store.status(Scope("portfolio", None))

    assert report.per_corpus["docs"].row_count == 2
    assert report.per_corpus["adr"].row_count == 1


def test_status_flags_stale_file_when_source_is_newer_than_indexed_hash(tmp_path):
    store = open_store(tmp_path / "engram.db")
    source = tmp_path / "notes.md"
    source.write_text("original content")

    chunk = _chunk(corpus="docs", path=str(source), content_hash="original-hash")
    store.upsert_chunks(
        [ChunkWithVector(chunk=chunk, vector=Vector([0.1, 0.2, 0.3, 0.4], "m1", 4))]
    )

    source.write_text("modified content")
    future = time.time() + 5
    os.utime(source, (future, future))

    report = store.status(Scope("portfolio", None))

    assert str(source) in report.per_corpus["docs"].stale_files


def test_status_counts_dead_row_when_source_file_no_longer_exists(tmp_path):
    store = open_store(tmp_path / "engram.db")
    source = tmp_path / "gone.md"
    source.write_text("temporary content")

    chunk = _chunk(corpus="docs", path=str(source), content_hash="h1")
    store.upsert_chunks(
        [ChunkWithVector(chunk=chunk, vector=Vector([0.1, 0.2, 0.3, 0.4], "m1", 4))]
    )

    source.unlink()

    report = store.status(Scope("portfolio", None))

    assert report.per_corpus["docs"].dead_rows == 1


# --- search_bm25 multi-word query recall ---


def test_search_bm25_matches_reordered_non_adjacent_query_tokens(tmp_path):
    store = open_store(tmp_path / "engram.db")
    chunk = _chunk(body="alpha beta gamma", content_hash="h1")
    vector = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    store.upsert_chunks([ChunkWithVector(chunk=chunk, vector=vector)])

    hits = store.search_bm25("gamma alpha", Scope("portfolio", None), corpus=None, k=10)

    assert len(hits) == 1
    assert hits[0].chunk == chunk


# --- Scope invariant ---


def test_scope_repo_kind_requires_repo():
    with pytest.raises(ValueError):
        Scope(kind="repo", repo=None)


# --- multi-chunk-per-file ---


def test_upsert_multiple_chunks_from_same_file_land_without_unique_violation(tmp_path):
    store = open_store(tmp_path / "engram.db")
    chunk0 = _chunk(
        content_hash="same-hash",
        chunk_ordinal=0,
        heading="First Heading",
        body="alpha-chunk-token",
    )
    chunk1 = _chunk(
        content_hash="same-hash",
        chunk_ordinal=1,
        heading="Second Heading",
        body="beta-chunk-token",
    )
    vector = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)

    store.upsert_chunks(
        [
            ChunkWithVector(chunk=chunk0, vector=vector),
            ChunkWithVector(chunk=chunk1, vector=vector),
        ]
    )

    assert store.status(Scope("portfolio", None)).per_corpus["docs"].row_count == 2
