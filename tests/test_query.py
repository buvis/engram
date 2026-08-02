import pytest

from engram.client import EmbeddingEntry, EngramConfig, Vector
from engram.query import Pointer, query
from engram.store import Chunk, ChunkWithVector, Scope, StoreModelMismatchError, open_store


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


def _entry(id_="m1"):
    return EmbeddingEntry(id=id_, endpoint="http://127.0.0.1:8081/v1")


def _config(tmp_path, entry):
    return EngramConfig(embeddings=[entry], pinned_id=None, config_path=tmp_path / "config.toml")


# --- BM25 leg contributes ---


def test_exact_token_query_returns_lexically_matching_doc(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    lexical_chunk = _chunk(
        path="lexical.md",
        heading="Lexical Heading",
        body="distinctive-lexical-marker appears here",
        content_hash="h-lex",
    )
    semantic_chunk = _chunk(
        path="semantic.md",
        heading="Semantic Heading",
        body="unrelated vocabulary entirely",
        content_hash="h-sem",
    )
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=lexical_chunk, vector=Vector([1.0, 0.0, 0.0, 0.0], "m1", 4)),
            ChunkWithVector(chunk=semantic_chunk, vector=Vector([0.0, 1.0, 0.0, 0.0], "m1", 4)),
        ]
    )
    config = _config(tmp_path, _entry())

    # steer the query vector toward the semantic doc's stored vector, away from the
    # lexical doc, so the lexical doc can only win overall via the BM25 leg.
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [Vector([0.0, 1.0, 0.0, 0.0], "m1", 4)],
    )

    results = query(store, config, "distinctive-lexical-marker", Scope("portfolio", None))

    assert results[0].path == "lexical.md"
    assert results[0].heading == "Lexical Heading"


# --- KNN leg contributes ---


def test_synonym_query_with_no_lexical_overlap_returns_semantic_match(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    lexical_chunk = _chunk(
        path="lexical.md",
        heading="Lexical Heading",
        body="distinctive-lexical-marker appears here",
        content_hash="h-lex",
    )
    semantic_chunk = _chunk(
        path="semantic.md",
        heading="Semantic Heading",
        body="unrelated vocabulary entirely",
        content_hash="h-sem",
    )
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=lexical_chunk, vector=Vector([1.0, 0.0, 0.0, 0.0], "m1", 4)),
            ChunkWithVector(chunk=semantic_chunk, vector=Vector([0.0, 1.0, 0.0, 0.0], "m1", 4)),
        ]
    )
    config = _config(tmp_path, _entry())

    # query text shares no tokens with either stored body, so the BM25 leg contributes
    # nothing; steer the fake embedding onto the semantic doc's stored vector so it can
    # only be found via the KNN leg.
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [Vector([0.0, 1.0, 0.0, 0.0], "m1", 4)],
    )

    results = query(store, config, "totally different synonym phrase", Scope("portfolio", None))

    assert results[0].path == "semantic.md"
    assert results[0].heading == "Semantic Heading"


# --- RRF fusion property ---


def test_doc_ranked_in_both_legs_outranks_doc_ranked_in_only_one_leg(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    both_legs_chunk = _chunk(
        path="both.md",
        heading="Both Legs",
        body="walrus-marker appears in this passage",
        content_hash="h-both",
    )
    knn_only_chunk = _chunk(
        path="knn-only.md",
        heading="KNN Only",
        body="giraffe savanna unrelated text",
        content_hash="h-knn",
    )
    query_vector = [1.0, 0.0, 0.0, 0.0]
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=both_legs_chunk, vector=Vector(query_vector, "m1", 4)),
            ChunkWithVector(
                chunk=knn_only_chunk, vector=Vector([0.0, 1.0, 0.0, 0.0], "m1", 4)
            ),
        ]
    )
    config = _config(tmp_path, _entry())

    # both_legs_chunk's stored vector equals the query vector exactly (KNN rank 1) and
    # it lexically matches the query (BM25 rank 1). knn_only_chunk has no lexical
    # overlap at all, so it is excluded from the BM25 leg entirely and only ranks via
    # KNN (rank 2, since it is farther from the query vector).
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [Vector(query_vector, "m1", 4)],
    )

    results = query(store, config, "walrus-marker", Scope("portfolio", None))

    by_path = {p.path: p for p in results}
    assert by_path["both.md"].rank < by_path["knn-only.md"].rank
    assert by_path["both.md"].score > by_path["knn-only.md"].score


# --- Pointer contract ---


def test_pointer_carries_winning_chunk_fields_with_one_indexed_rank(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    # chunk_one repeats the query token for a stronger BM25 match, and its stored
    # vector equals the fake query vector exactly, so it is unambiguously rank 1 in
    # both legs; chunk_two is unambiguously rank 2 in both legs.
    chunk_one = _chunk(
        corpus="docs",
        repo="repoA",
        path="notes/file.md",
        heading="Section One",
        body="pointer-field-marker pointer-field-marker repeated body text",
        line_start=10,
        line_end=14,
        content_hash="h-ptr-1",
    )
    chunk_two = _chunk(
        corpus="docs",
        repo="repoA",
        path="notes/other.md",
        heading="Section Two",
        body="pointer-field-marker other text",
        line_start=20,
        line_end=24,
        content_hash="h-ptr-2",
    )
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=chunk_one, vector=Vector([1.0, 0.0, 0.0, 0.0], "m1", 4)),
            ChunkWithVector(chunk=chunk_two, vector=Vector([0.0, 1.0, 0.0, 0.0], "m1", 4)),
        ]
    )
    config = _config(tmp_path, _entry())

    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [Vector([1.0, 0.0, 0.0, 0.0], "m1", 4)],
    )

    results = query(store, config, "pointer-field-marker", Scope("portfolio", None))

    assert [p.rank for p in results] == [1, 2]
    top = results[0]
    assert isinstance(top, Pointer)
    assert top.path == "notes/file.md"
    assert top.line_start == 10
    assert top.line_end == 14
    assert top.heading == "Section One"
    assert top.corpus == "docs"
    assert top.repo == "repoA"


# --- k bounds result count ---


def test_k_bounds_number_of_returned_pointers(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    vectors = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
        [0.7, 0.7, 0.0, 0.0],
    ]
    items = [
        ChunkWithVector(
            chunk=_chunk(
                path=f"doc{i}.md",
                heading=f"Heading {i}",
                body="k-bound-marker shared across every doc",
                content_hash=f"h-k-{i}",
            ),
            vector=Vector(vec, "m1", 4),
        )
        for i, vec in enumerate(vectors)
    ]
    store.upsert_chunks(items)
    config = _config(tmp_path, _entry())

    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [Vector([1.0, 0.0, 0.0, 0.0], "m1", 4)],
    )

    results = query(store, config, "k-bound-marker", Scope("portfolio", None), k=2)

    assert len(results) == 2
    assert [p.rank for p in results] == [1, 2]


# --- StoreModelMismatchError propagation ---


def test_store_model_mismatch_from_knn_leg_propagates(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    chunk = _chunk(body="mismatch-marker body text", content_hash="h-mismatch")
    store.upsert_chunks(
        [ChunkWithVector(chunk=chunk, vector=Vector([0.1, 0.2, 0.3, 0.4], "m1", 4))]
    )
    config = _config(tmp_path, _entry())

    # wrong dimension relative to the store's recorded model ("m1", dim 4)
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [Vector([0.1, 0.2, 0.3, 0.4, 0.5], "m1", 5)],
    )

    with pytest.raises(StoreModelMismatchError):
        query(store, config, "mismatch-marker", Scope("portfolio", None))


# --- corpus filter ---


def test_corpus_filter_restricts_results_to_that_corpus(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    docs_chunk = _chunk(
        corpus="docs",
        path="docs.md",
        heading="Docs Heading",
        body="corpus-filter-marker in docs",
        content_hash="h-docs",
    )
    adr_chunk = _chunk(
        corpus="adr",
        path="adr.md",
        heading="ADR Heading",
        body="corpus-filter-marker in adr",
        content_hash="h-adr",
    )
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=docs_chunk, vector=Vector([1.0, 0.0, 0.0, 0.0], "m1", 4)),
            ChunkWithVector(chunk=adr_chunk, vector=Vector([0.0, 1.0, 0.0, 0.0], "m1", 4)),
        ]
    )
    config = _config(tmp_path, _entry())

    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [Vector([1.0, 0.0, 0.0, 0.0], "m1", 4)],
    )

    results = query(
        store, config, "corpus-filter-marker", Scope("portfolio", None), corpus="docs"
    )

    assert [p.path for p in results] == ["docs.md"]
