import hashlib
from pathlib import Path

import pytest

from engram import findings
from engram.cli import main
from engram.client import EmbeddingEntry, EngramConfig, Vector
from engram.findings import FINDINGS_CORPUS, Record
from engram.indexer import IndexReport
from engram.store import Chunk, ChunkWithVector, Scope, StoreModelMismatchError, open_store


def _chunk(
    *,
    corpus="findings",
    repo="repoA",
    doc_type="finding",
    path="review.md",
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


def _config(tmp_path, model_id="m1"):
    return EngramConfig(
        embeddings=[EmbeddingEntry(id=model_id, endpoint="http://127.0.0.1:8081")],
        pinned_id=model_id,
        config_path=tmp_path / "config.toml",
    )


def _make_embed(dim=4, value=0.5):
    def _embed(texts, entry):
        return [Vector([value] * dim, entry.id, dim) for _ in texts]

    return _embed


# --- Chunk.text_for_embedding ---


def test_text_for_embedding_with_heading_joins_heading_and_body_with_newline():
    chunk = _chunk(heading="Distinctive Heading", body="Distinctive body text")

    assert chunk.text_for_embedding == "Distinctive Heading\nDistinctive body text"


def test_text_for_embedding_with_no_heading_is_body_alone():
    chunk = _chunk(heading="", body="Distinctive body text")

    assert chunk.text_for_embedding == "Distinctive body text"


# --- replace_chunks_for_source: atomic replace, retrievable like upsert_chunks ---


def test_replace_chunks_for_source_on_fresh_store_is_searchable_via_bm25_and_knn(tmp_path):
    store = open_store(tmp_path / "engram.db")
    chunk = _chunk(body="the quick zebra jumps over the lazy dog", content_hash="h1")
    vector = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)

    store.replace_chunks_for_source(
        "findings", "review.md", [ChunkWithVector(chunk=chunk, vector=vector)]
    )

    bm25_hits = store.search_bm25("zebra", Scope("portfolio", None), corpus=None, k=10)
    knn_hits = store.search_knn(vector, Scope("portfolio", None), corpus=None, k=10)
    assert len(bm25_hits) == 1
    assert bm25_hits[0].chunk == chunk
    assert len(knn_hits) == 1
    assert knn_hits[0].chunk == chunk


def test_replace_chunks_for_source_replaces_all_prior_rows_for_same_corpus_and_path(tmp_path):
    store = open_store(tmp_path / "engram.db")
    vector = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    old_chunk = _chunk(body="stale-marker-token", content_hash="old", chunk_ordinal=0)
    store.replace_chunks_for_source(
        "findings", "review.md", [ChunkWithVector(chunk=old_chunk, vector=vector)]
    )

    new_chunk = _chunk(body="fresh-marker-token", content_hash="new", chunk_ordinal=0)
    store.replace_chunks_for_source(
        "findings", "review.md", [ChunkWithVector(chunk=new_chunk, vector=vector)]
    )

    assert store.search_bm25("stale-marker-token", Scope("portfolio", None), corpus=None, k=10) == []
    hits = store.search_bm25("fresh-marker-token", Scope("portfolio", None), corpus=None, k=10)
    assert len(hits) == 1


def test_replace_chunks_for_source_dedup_identity_ignores_chunk_repo_field(tmp_path):
    store = open_store(tmp_path / "engram.db")
    vector = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    old_chunk = _chunk(repo="old-repo", body="rename-marker-token-old", content_hash="old")
    store.replace_chunks_for_source(
        "findings", "review.md", [ChunkWithVector(chunk=old_chunk, vector=vector)]
    )

    new_chunk = _chunk(repo="new-repo", body="rename-marker-token-new", content_hash="new")
    store.replace_chunks_for_source(
        "findings", "review.md", [ChunkWithVector(chunk=new_chunk, vector=vector)]
    )

    chunks = store.chunks_for_corpus("findings")
    assert len(chunks) == 1
    assert chunks[0].repo == "new-repo"


def test_replace_chunks_for_source_with_empty_items_deletes_without_raising(tmp_path):
    store = open_store(tmp_path / "engram.db")
    vector = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    chunk = _chunk(body="to-be-cleared-token", content_hash="h1")
    store.replace_chunks_for_source(
        "findings", "review.md", [ChunkWithVector(chunk=chunk, vector=vector)]
    )

    store.replace_chunks_for_source("findings", "review.md", [])

    assert store.chunks_for_corpus("findings") == []


def test_replace_chunks_for_source_rejects_mismatched_model_and_leaves_prior_rows_intact(tmp_path):
    store = open_store(tmp_path / "engram.db")
    chunk1 = _chunk(content_hash="h1", body="prior-content-token")
    vector1 = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    store.replace_chunks_for_source(
        "findings", "review.md", [ChunkWithVector(chunk=chunk1, vector=vector1)]
    )

    chunk2 = _chunk(content_hash="h2", body="mismatched-content-token")
    vector2 = Vector([0.5, 0.6, 0.7, 0.8], "m2", 4)

    with pytest.raises(StoreModelMismatchError):
        store.replace_chunks_for_source(
            "findings", "review.md", [ChunkWithVector(chunk=chunk2, vector=vector2)]
        )

    chunks = store.chunks_for_corpus("findings")
    assert len(chunks) == 1
    assert chunks[0].body == "prior-content-token"
    assert store.search_bm25(
        "mismatched-content-token", Scope("portfolio", None), corpus=None, k=10
    ) == []


# --- chunks_for_corpus ---


def test_chunks_for_corpus_returns_empty_list_for_corpus_with_no_rows(tmp_path):
    store = open_store(tmp_path / "engram.db")

    assert store.chunks_for_corpus("findings") == []


def test_chunks_for_corpus_returns_rows_across_all_repos_in_insertion_order(tmp_path):
    store = open_store(tmp_path / "engram.db")
    vector = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    chunk_a = _chunk(repo="repoA", path="a.md", content_hash="ha", body="alpha")
    chunk_b = _chunk(repo="repoB", path="b.md", content_hash="hb", body="beta")
    other_corpus_chunk = _chunk(corpus="docs", repo="repoA", path="c.md", content_hash="hc", body="gamma")
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=chunk_a, vector=vector),
            ChunkWithVector(chunk=chunk_b, vector=vector),
            ChunkWithVector(chunk=other_corpus_chunk, vector=vector),
        ]
    )

    chunks = store.chunks_for_corpus("findings")

    assert chunks == [chunk_a, chunk_b]


# --- prune: findings exemption (regression guard for ordinary corpora) ---


def test_prune_never_deletes_findings_rows_even_when_absent_from_active_sources(tmp_path):
    store = open_store(tmp_path / "engram.db")
    vector = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    finding_chunk = _chunk(corpus="findings", content_hash="hf", body="finding-marker-token")
    store.upsert_chunks([ChunkWithVector(chunk=finding_chunk, vector=vector)])

    deleted = store.prune(Scope("portfolio", None), corpus="findings", active_sources=set())

    assert deleted == 0
    assert (
        len(store.search_bm25("finding-marker-token", Scope("portfolio", None), corpus=None, k=10))
        == 1
    )


def test_prune_across_all_corpora_deletes_ordinary_rows_but_exempts_findings(tmp_path):
    store = open_store(tmp_path / "engram.db")
    vector = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    doc_chunk = _chunk(
        corpus="docs", doc_type="markdown", repo="repoA", path="a.md",
        content_hash="hd", body="docs-marker-token",
    )
    finding_chunk = _chunk(
        corpus="findings", repo="repoA", path="review.md",
        content_hash="hf", body="finding-marker-token",
    )
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=doc_chunk, vector=vector),
            ChunkWithVector(chunk=finding_chunk, vector=vector),
        ]
    )

    deleted = store.prune(Scope("portfolio", None), corpus=None, active_sources=set())

    assert deleted == 1
    assert store.search_bm25("docs-marker-token", Scope("portfolio", None), corpus=None, k=10) == []
    assert (
        len(store.search_bm25("finding-marker-token", Scope("portfolio", None), corpus=None, k=10))
        == 1
    )


# --- status: findings exemption (regression guard for ordinary corpora) ---


def test_status_never_counts_findings_rows_as_dead_even_when_source_file_is_missing(tmp_path):
    store = open_store(tmp_path / "engram.db")
    vector = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    missing_path = tmp_path / "reviews" / "gone.md"
    finding_chunk = _chunk(
        corpus="findings", repo="repoA", path=str(missing_path),
        content_hash="hf", body="finding-marker-token",
    )
    store.upsert_chunks([ChunkWithVector(chunk=finding_chunk, vector=vector)])

    report = store.status(Scope("portfolio", None))

    assert report.per_corpus["findings"].dead_rows == 0


def test_status_never_reports_findings_rows_as_stale_even_when_content_hash_mismatches_file(
    tmp_path,
):
    store = open_store(tmp_path / "engram.db")
    vector = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    source_path = tmp_path / "review.md"
    source_path.write_text("some review markdown content, unrelated to the record body")
    body_hash = hashlib.sha1(b"finding-marker-token").hexdigest()
    finding_chunk = _chunk(
        corpus="findings", repo="repoA", path=str(source_path),
        content_hash=body_hash, body="finding-marker-token",
    )
    store.upsert_chunks([ChunkWithVector(chunk=finding_chunk, vector=vector)])

    report = store.status(Scope("portfolio", None))

    assert report.per_corpus["findings"].stale_files == []


def test_status_still_counts_findings_rows_in_row_count_despite_staleness_exemption(tmp_path):
    store = open_store(tmp_path / "engram.db")
    vector = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    finding_a = _chunk(
        corpus="findings", repo="repoA", path=str(tmp_path / "gone-a.md"),
        content_hash="ha", body="finding-a-token", chunk_ordinal=0,
    )
    finding_b = _chunk(
        corpus="findings", repo="repoA", path=str(tmp_path / "gone-b.md"),
        content_hash="hb", body="finding-b-token", chunk_ordinal=1,
    )
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=finding_a, vector=vector),
            ChunkWithVector(chunk=finding_b, vector=vector),
        ]
    )

    report = store.status(Scope("portfolio", None))

    assert report.per_corpus["findings"].row_count == 2


def test_status_across_all_corpora_reports_dead_rows_and_stale_files_for_ordinary_corpus_but_exempts_findings(
    tmp_path,
):
    store = open_store(tmp_path / "engram.db")
    vector = Vector([0.1, 0.2, 0.3, 0.4], "m1", 4)
    missing_docs_path = tmp_path / "gone-doc.md"
    stale_docs_path = tmp_path / "changed-doc.md"
    stale_docs_path.write_text("current on-disk content")
    missing_finding_path = tmp_path / "gone-review.md"

    dead_doc_chunk = _chunk(
        corpus="docs", doc_type="markdown", repo="repoA", path=str(missing_docs_path),
        content_hash="hd-dead", body="dead-doc-token",
    )
    stale_doc_chunk = _chunk(
        corpus="docs", doc_type="markdown", repo="repoA", path=str(stale_docs_path),
        content_hash="hd-stale-old", body="stale-doc-token",
    )
    finding_chunk = _chunk(
        corpus="findings", repo="repoA", path=str(missing_finding_path),
        content_hash="hf", body="finding-marker-token",
    )
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=dead_doc_chunk, vector=vector),
            ChunkWithVector(chunk=stale_doc_chunk, vector=vector),
            ChunkWithVector(chunk=finding_chunk, vector=vector),
        ]
    )

    report = store.status(Scope("portfolio", None))

    assert report.per_corpus["docs"].dead_rows == 1
    assert report.per_corpus["docs"].stale_files == [str(stale_docs_path)]
    assert report.per_corpus["findings"].dead_rows == 0


# --- findings.upsert: field mapping, embed text convention, return value ---


def test_findings_upsert_stores_chunks_with_mapped_fields_and_returns_record_count(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    records = [
        Record(heading="Issue One", body="body one text", line_start=5, line_end=6, structured=True),
        Record(heading="", body="body two text", line_start=8, line_end=8, structured=False),
    ]
    path = Path("reviews/2026-01-01.md")

    result = findings.upsert(store, config, "repoA", path, records)

    assert result == 2
    chunks = store.chunks_for_corpus(FINDINGS_CORPUS)
    assert len(chunks) == 2
    c0, c1 = chunks
    assert c0.corpus == FINDINGS_CORPUS
    assert c0.repo == "repoA"
    assert c0.doc_type == "finding"
    assert c0.path == str(path)
    assert c0.heading == "Issue One"
    assert c0.body == "body one text"
    assert c0.line_start == 5
    assert c0.line_end == 6
    assert c0.content_hash == hashlib.sha1(b"body one text").hexdigest()
    assert c0.chunk_ordinal == 0
    assert c1.heading == ""
    assert c1.body == "body two text"
    assert c1.content_hash == hashlib.sha1(b"body two text").hexdigest()
    assert c1.chunk_ordinal == 1


def test_findings_upsert_embed_text_joins_heading_and_body_when_heading_present(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    captured_texts = []

    def fake_embed(texts, entry):
        captured_texts.extend(texts)
        return [Vector([0.1, 0.2, 0.3, 0.4], entry.id, 4) for _ in texts]

    monkeypatch.setattr("engram.findings.embed", fake_embed)
    records = [
        Record(heading="Heading A", body="Body A", line_start=1, line_end=2, structured=True),
        Record(heading="", body="Body B only", line_start=3, line_end=3, structured=False),
    ]

    findings.upsert(store, config, "repoA", Path("review.md"), records)

    assert captured_texts == ["Heading A\nBody A", "Body B only"]


# --- findings.upsert: atomicity against embed failure ---


def test_findings_upsert_embed_failure_leaves_prior_records_fully_intact(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    path = Path("review.md")
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    original_records = [Record("H1", "original-body-token", 1, 1, False)]
    findings.upsert(store, config, "repoA", path, original_records)

    def failing_embed(texts, entry):
        raise RuntimeError("embedding server unreachable")

    monkeypatch.setattr("engram.findings.embed", failing_embed)

    with pytest.raises(RuntimeError):
        findings.upsert(store, config, "repoA", path, [Record("H2", "new-body-token", 2, 2, False)])

    chunks = store.chunks_for_corpus(FINDINGS_CORPUS)
    assert len(chunks) == 1
    assert chunks[0].heading == "H1"
    assert chunks[0].body == "original-body-token"


# --- findings.upsert: re-harvest semantics (dedup, replace, repo rename, empty) ---


def test_findings_upsert_reharvest_dedup_and_replace_yields_one_record_set(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    path = Path("review.md")
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    records = [Record("H1", "same-body-token", 1, 1, False)]

    findings.upsert(store, config, "repoA", path, records)
    findings.upsert(store, config, "repoA", path, records)

    chunks = store.chunks_for_corpus(FINDINGS_CORPUS)
    assert len(chunks) == 1

    amended_records = [Record("H1-amended", "amended-body-token", 1, 2, False)]
    findings.upsert(store, config, "repoA", path, amended_records)

    chunks = store.chunks_for_corpus(FINDINGS_CORPUS)
    assert len(chunks) == 1
    assert chunks[0].heading == "H1-amended"
    assert chunks[0].body == "amended-body-token"


def test_findings_upsert_with_empty_records_deletes_prior_and_returns_zero(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    path = Path("review.md")
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    findings.upsert(store, config, "repoA", path, [Record("H1", "body-token", 1, 1, False)])

    result = findings.upsert(store, config, "repoA", path, [])

    assert result == 0
    assert store.chunks_for_corpus(FINDINGS_CORPUS) == []


def test_findings_upsert_with_empty_records_does_not_call_embed(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    path = Path("review.md")
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    findings.upsert(store, config, "repoA", path, [Record("H1", "body-token", 1, 1, False)])

    def failing_embed(texts, entry):
        raise AssertionError("embed must not be called for an empty record set")

    monkeypatch.setattr("engram.findings.embed", failing_embed)

    result = findings.upsert(store, config, "repoA", path, [])

    assert result == 0
    assert store.chunks_for_corpus(FINDINGS_CORPUS) == []


def test_findings_upsert_repo_rename_yields_one_record_set_no_orphan_under_old_name(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    path = Path("review.md")
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    records = [Record("H1", "rename-body-token", 1, 1, False)]

    findings.upsert(store, config, "old-repo-name", path, records)
    findings.upsert(store, config, "new-repo-name", path, records)

    chunks = store.chunks_for_corpus(FINDINGS_CORPUS)
    assert len(chunks) == 1
    assert chunks[0].repo == "new-repo-name"


# --- findings.upsert: queryable via standard hybrid scoped query ---


def test_findings_upsert_records_queryable_via_search_bm25_in_repo_and_portfolio_scope(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    records = [Record("H", "distinctive-findings-token", 1, 1, False)]

    findings.upsert(store, config, "repoA", Path("review.md"), records)

    hits_repo = store.search_bm25(
        "distinctive-findings-token", Scope("repo", "repoA"), corpus=FINDINGS_CORPUS, k=10
    )
    hits_portfolio = store.search_bm25(
        "distinctive-findings-token", Scope("portfolio", None), corpus=FINDINGS_CORPUS, k=10
    )

    assert len(hits_repo) == 1
    assert len(hits_portfolio) == 1


# --- engram index --rebuild: findings preservation ---


def test_index_rebuild_preserves_findings_with_freshly_embedded_vectors(tmp_path, monkeypatch):
    fake_db_path = tmp_path / "engram.db"
    seed_store = open_store(fake_db_path)
    old_vector = Vector([0.1, 0.2, 0.3, 0.4], "old-model", 4)
    finding_a = _chunk(
        corpus="findings", repo="repoA", path="reviews/a.md",
        heading="Finding A", body="finding-a-body", content_hash="ha", chunk_ordinal=0,
    )
    finding_b = _chunk(
        corpus="findings", repo="repoA", path="reviews/a.md",
        heading="Finding B", body="finding-b-body", content_hash="ha", chunk_ordinal=1,
    )
    seed_store.upsert_chunks(
        [
            ChunkWithVector(chunk=finding_a, vector=old_vector),
            ChunkWithVector(chunk=finding_b, vector=old_vector),
        ]
    )
    seed_store.conn.close()

    config = EngramConfig(
        embeddings=[EmbeddingEntry(id="new-model", endpoint="http://127.0.0.1:8081")],
        pinned_id="new-model",
        config_path=tmp_path / "config.toml",
    )
    fresh_vector_values = [9.0, 9.0, 9.0, 9.0]

    def fake_embed(texts, entry):
        return [Vector(fresh_vector_values, entry.id, 4) for _ in texts]

    monkeypatch.setattr("engram.cli.DEFAULT_DB_PATH", fake_db_path)
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: config)
    monkeypatch.setattr("engram.cli.embed", fake_embed)
    monkeypatch.setattr(
        "engram.cli.index",
        lambda *a, **k: IndexReport(
            files_scanned=0, chunks_added=0, chunks_updated=0, chunks_pruned=0, corpora_missing=[],
        ),
    )

    exit_code = main(["index", "--rebuild"])

    assert exit_code == 0
    result_store = open_store(fake_db_path)
    chunks = result_store.chunks_for_corpus("findings")
    assert {(c.heading, c.body, c.chunk_ordinal) for c in chunks} == {
        ("Finding A", "finding-a-body", 0),
        ("Finding B", "finding-b-body", 1),
    }
    fresh_hits = result_store.search_knn(
        Vector(fresh_vector_values, "new-model", 4), Scope("portfolio", None), corpus="findings", k=10
    )
    assert len(fresh_hits) == 2


def test_index_rebuild_succeeds_with_zero_findings_when_no_existing_database(tmp_path, monkeypatch):
    fake_db_path = tmp_path / "engram.db"
    assert not fake_db_path.exists()

    config = EngramConfig(
        embeddings=[EmbeddingEntry(id="new-model", endpoint="http://127.0.0.1:8081")],
        pinned_id="new-model",
        config_path=tmp_path / "config.toml",
    )

    def fake_embed(texts, entry):
        return [Vector([9.0, 9.0, 9.0, 9.0], entry.id, 4) for _ in texts]

    monkeypatch.setattr("engram.cli.DEFAULT_DB_PATH", fake_db_path)
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: config)
    monkeypatch.setattr("engram.cli.embed", fake_embed)
    monkeypatch.setattr(
        "engram.cli.index",
        lambda *a, **k: IndexReport(
            files_scanned=0, chunks_added=0, chunks_updated=0, chunks_pruned=0, corpora_missing=[],
        ),
    )

    exit_code = main(["index", "--rebuild"])

    assert exit_code == 0
    result_store = open_store(fake_db_path)
    assert result_store.chunks_for_corpus("findings") == []


# --- engram index --rebuild: findings-preservation failure is handled, not raised ---


def test_index_rebuild_reports_failure_when_findings_preservation_fails(
    tmp_path, monkeypatch, capsys
):
    fake_db_path = tmp_path / "engram.db"
    seed_store = open_store(fake_db_path)
    old_vector = Vector([0.1, 0.2, 0.3, 0.4], "old-model", 4)
    finding = _chunk(
        corpus="findings", repo="repoA", path="reviews/a.md",
        heading="Finding A", body="finding-a-body", content_hash="ha", chunk_ordinal=0,
    )
    seed_store.upsert_chunks([ChunkWithVector(chunk=finding, vector=old_vector)])
    seed_store.conn.close()

    config = _config(tmp_path, model_id="new-model")

    def failing_embed(texts, entry):
        raise RuntimeError("embedding server unreachable")

    monkeypatch.setattr("engram.cli.DEFAULT_DB_PATH", fake_db_path)
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: config)
    monkeypatch.setattr("engram.cli.embed", failing_embed)
    monkeypatch.setattr(
        "engram.cli.index",
        lambda *a, **k: IndexReport(
            files_scanned=0, chunks_added=0, chunks_updated=0, chunks_pruned=0, corpora_missing=[],
        ),
    )

    exit_code = main(["index", "--rebuild"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.startswith("rebuild failed: ")


def test_index_rebuild_failure_leaves_existing_database_untouched(tmp_path, monkeypatch):
    fake_db_path = tmp_path / "engram.db"
    seed_store = open_store(fake_db_path)
    old_vector = Vector([0.1, 0.2, 0.3, 0.4], "old-model", 4)
    finding = _chunk(
        corpus="findings", repo="repoA", path="reviews/a.md",
        heading="Finding A", body="finding-a-body", content_hash="ha", chunk_ordinal=0,
    )
    seed_store.upsert_chunks([ChunkWithVector(chunk=finding, vector=old_vector)])
    seed_store.conn.close()

    config = _config(tmp_path, model_id="new-model")

    def failing_embed(texts, entry):
        raise RuntimeError("embedding server unreachable")

    monkeypatch.setattr("engram.cli.DEFAULT_DB_PATH", fake_db_path)
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: config)
    monkeypatch.setattr("engram.cli.embed", failing_embed)
    monkeypatch.setattr(
        "engram.cli.index",
        lambda *a, **k: IndexReport(
            files_scanned=0, chunks_added=0, chunks_updated=0, chunks_pruned=0, corpora_missing=[],
        ),
    )

    main(["index", "--rebuild"])

    result_store = open_store(fake_db_path)
    chunks = result_store.chunks_for_corpus("findings")
    assert {(c.heading, c.body, c.chunk_ordinal) for c in chunks} == {
        ("Finding A", "finding-a-body", 0),
    }
    old_hits = result_store.search_knn(
        old_vector, Scope("portfolio", None), corpus="findings", k=10
    )
    assert len(old_hits) == 1


def test_index_rebuild_failure_removes_temporary_rebuild_database(tmp_path, monkeypatch):
    fake_db_path = tmp_path / "engram.db"
    seed_store = open_store(fake_db_path)
    old_vector = Vector([0.1, 0.2, 0.3, 0.4], "old-model", 4)
    finding = _chunk(
        corpus="findings", repo="repoA", path="reviews/a.md",
        heading="Finding A", body="finding-a-body", content_hash="ha", chunk_ordinal=0,
    )
    seed_store.upsert_chunks([ChunkWithVector(chunk=finding, vector=old_vector)])
    seed_store.conn.close()

    config = _config(tmp_path, model_id="new-model")

    def failing_embed(texts, entry):
        raise RuntimeError("embedding server unreachable")

    monkeypatch.setattr("engram.cli.DEFAULT_DB_PATH", fake_db_path)
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: config)
    monkeypatch.setattr("engram.cli.embed", failing_embed)
    monkeypatch.setattr(
        "engram.cli.index",
        lambda *a, **k: IndexReport(
            files_scanned=0, chunks_added=0, chunks_updated=0, chunks_pruned=0, corpora_missing=[],
        ),
    )

    main(["index", "--rebuild"])

    rebuild_tmp_path = Path(str(fake_db_path) + ".rebuild-tmp")
    assert not rebuild_tmp_path.exists()
