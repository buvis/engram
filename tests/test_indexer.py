import engram.corpora as corpora_module
import pytest

from engram import symbols
from engram.client import EmbeddingEntry, EngramConfig, Vector
from engram.corpora import CorpusFile, hash_source
from engram.indexer import IndexReport, _chunk_file, index
from engram.store import Chunk, ChunkWithVector, Scope, StoreModelMismatchError, open_store


@pytest.fixture(autouse=True)
def _reset_missing_dirs():
    # enumerate_corpora is patched per-test, so the real populator never runs;
    # reset the shared module-level list so tests don't leak state into each other.
    corpora_module.missing_dirs.clear()
    yield
    corpora_module.missing_dirs.clear()


@pytest.fixture(autouse=True)
def _stub_new_producers(monkeypatch):
    # index() now chains in the transcripts and symbols producers alongside
    # enumerate_corpora; default them to no-ops so existing tests (which only
    # stub enumerate_corpora) don't hit the real filesystem or spawn git.
    monkeypatch.setattr("engram.indexer.transcripts.enumerate", lambda *a, **k: iter(()))
    monkeypatch.setattr("engram.indexer.symbols.enumerate", lambda *a, **k: iter(()))


def _entry(model_id="test-model"):
    return EmbeddingEntry(id=model_id, endpoint="http://127.0.0.1:8081/v1")


def _config(tmp_path, model_id="test-model"):
    return EngramConfig(
        embeddings=[_entry(model_id)], pinned_id=None, config_path=tmp_path / "config.toml"
    )


def fake_embed(texts, entry):
    return [Vector([1.0, 0.0, 0.0, 0.0], entry.id, 4) for _ in texts]


class _EmbedFailure(Exception):
    """Distinct exception used to simulate a killed/crashed embedding step."""


# --- zero-embeds on unchanged reindex (PRD key acceptance) ---


def test_reindexing_unchanged_corpus_embeds_zero_chunks(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    repo_dir = tmp_path / "repoA"
    repo_dir.mkdir()
    file_path = repo_dir / "doc.md"
    file_path.write_text("# Heading\nstable content\n")

    def fake_enum(*a, **k):
        yield CorpusFile("notes", "repoA", file_path)

    embed_calls = []

    def counting_embed(texts, entry):
        embed_calls.append(texts)
        return [Vector([1.0, 0.0, 0.0, 0.0], entry.id, 4) for _ in texts]

    monkeypatch.setattr("engram.indexer.enumerate_corpora", fake_enum)
    monkeypatch.setattr("engram.indexer.embed", counting_embed)

    first_report = index(store, config, Scope("portfolio", None))
    assert first_report.chunks_added > 0
    embed_calls.clear()

    second_report = index(store, config, Scope("portfolio", None))

    assert embed_calls == []
    assert second_report.chunks_added == 0


# --- new file gets chunked, embedded, upserted, and is retrievable ---


def test_new_file_is_chunked_embedded_and_retrievable(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    repo_dir = tmp_path / "repoA"
    repo_dir.mkdir()
    file_path = repo_dir / "doc.md"
    file_path.write_text("# Heading\nfreshly-added-marker-text\n")

    def fake_enum(*a, **k):
        yield CorpusFile("notes", "repoA", file_path)

    monkeypatch.setattr("engram.indexer.enumerate_corpora", fake_enum)
    monkeypatch.setattr("engram.indexer.embed", fake_embed)

    report = index(store, config, Scope("portfolio", None))

    assert report.chunks_added > 0
    hits = store.search_bm25(
        "freshly-added-marker-text", Scope("portfolio", None), corpus=None, k=10
    )
    assert len(hits) == 1


# --- deleted file gets pruned on next index() ---


def test_deleted_file_is_pruned_on_next_index(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    repo_dir = tmp_path / "repoA"
    repo_dir.mkdir()
    file_path = repo_dir / "doc.md"
    file_path.write_text("# Heading\nvanishing-marker-text\n")

    call_state = {"deleted": False}

    def fake_enum(*a, **k):
        if not call_state["deleted"]:
            yield CorpusFile("notes", "repoA", file_path)

    monkeypatch.setattr("engram.indexer.enumerate_corpora", fake_enum)
    monkeypatch.setattr("engram.indexer.embed", fake_embed)

    first_report = index(store, config, Scope("portfolio", None))
    assert first_report.chunks_added > 0

    call_state["deleted"] = True
    second_report = index(store, config, Scope("portfolio", None))

    assert second_report.chunks_pruned > 0
    hits = store.search_bm25(
        "vanishing-marker-text", Scope("portfolio", None), corpus=None, k=10
    )
    assert hits == []


# --- scope isolation ---


def test_scoped_index_never_adds_or_prunes_another_repos_rows(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    # Pre-existing repoB chunk, as if indexed by an earlier run.
    preexisting = Chunk(
        corpus="notes",
        repo="repoB",
        doc_type="md",
        path="repoB/old.md",
        heading="H",
        body="repoB-marker-content",
        line_start=1,
        line_end=1,
        content_hash="old-hash",
        chunk_ordinal=0,
    )
    store.upsert_chunks(
        [ChunkWithVector(chunk=preexisting, vector=Vector([1.0, 0.0, 0.0, 0.0], "test-model", 4))]
    )

    repo_a_dir = tmp_path / "repoA"
    repo_a_dir.mkdir()
    file_a = repo_a_dir / "doc.md"
    file_a.write_text("# Heading\nrepoA-marker-content\n")

    repo_b_dir = tmp_path / "repoB"
    repo_b_dir.mkdir()
    file_b = repo_b_dir / "doc.md"
    file_b.write_text("# Heading\nrepoB-new-content\n")

    def fake_enum(*a, **k):
        yield CorpusFile("notes", "repoA", file_a)
        yield CorpusFile("notes", "repoB", file_b)

    monkeypatch.setattr("engram.indexer.enumerate_corpora", fake_enum)
    monkeypatch.setattr("engram.indexer.embed", fake_embed)

    index(store, config, Scope("repo", "repoA"))

    hits_a = store.search_bm25(
        "repoA-marker-content", Scope("portfolio", None), corpus=None, k=10
    )
    hits_new_b = store.search_bm25(
        "repoB-new-content", Scope("portfolio", None), corpus=None, k=10
    )
    hits_old_b = store.search_bm25(
        "repoB-marker-content", Scope("portfolio", None), corpus=None, k=10
    )

    assert len(hits_a) == 1
    assert hits_new_b == []
    assert len(hits_old_b) == 1


# --- corpora_missing surfaced on report ---


def test_missing_corpus_dirs_are_surfaced_on_report(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    repo_dir = tmp_path / "repoA"
    repo_dir.mkdir()
    file_path = repo_dir / "doc.md"
    file_path.write_text("# Heading\nsome content\n")

    def fake_enum(*a, **k):
        corpora_module.missing_dirs.append("prd:repoA")
        corpora_module.missing_dirs.append("decision:repoB")
        yield CorpusFile("notes", "repoA", file_path)

    monkeypatch.setattr("engram.indexer.enumerate_corpora", fake_enum)
    monkeypatch.setattr("engram.indexer.embed", fake_embed)

    report = index(store, config, Scope("portfolio", None))

    assert report.corpora_missing == ["prd:repoA", "decision:repoB"]


# --- empty enumeration ---


def test_empty_enumeration_yields_all_zero_report(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    def fake_enum(*a, **k):
        return iter(())

    monkeypatch.setattr("engram.indexer.enumerate_corpora", fake_enum)
    monkeypatch.setattr("engram.indexer.embed", fake_embed)

    report = index(store, config, Scope("portfolio", None))

    assert report == IndexReport(
        files_scanned=0,
        chunks_added=0,
        chunks_updated=0,
        chunks_pruned=0,
        corpora_missing=[],
    )


# --- mismatched configured model fails loud even when unchanged (PRD success metric) ---


def test_reindex_unchanged_with_mismatched_model_fails_loud(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")

    repo_dir = tmp_path / "repoA"
    repo_dir.mkdir()
    file_path = repo_dir / "doc.md"
    file_path.write_text("# Heading\nstable content\n")

    def fake_enum(*a, **k):
        yield CorpusFile("notes", "repoA", file_path)

    def counting_embed(texts, entry):
        return [Vector([1.0, 0.0, 0.0, 0.0], entry.id, 4) for _ in texts]

    monkeypatch.setattr("engram.indexer.enumerate_corpora", fake_enum)
    monkeypatch.setattr("engram.indexer.embed", counting_embed)

    first_report = index(store, _config(tmp_path, model_id="model-A"), Scope("portfolio", None))
    assert first_report.chunks_added > 0

    with pytest.raises(StoreModelMismatchError):
        index(store, _config(tmp_path, model_id="model-B"), Scope("portfolio", None))


# --- heading text is embedded together with the body ---


def test_index_embeds_heading_with_body(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    repo_dir = tmp_path / "repoA"
    repo_dir.mkdir()
    file_path = repo_dir / "doc.md"
    file_path.write_text("# MyUniqueHeading\nsome body text\n")

    def fake_enum(*a, **k):
        yield CorpusFile("notes", "repoA", file_path)

    embed_calls = []

    def counting_embed(texts, entry):
        embed_calls.append(texts)
        return [Vector([1.0, 0.0, 0.0, 0.0], entry.id, 4) for _ in texts]

    monkeypatch.setattr("engram.indexer.enumerate_corpora", fake_enum)
    monkeypatch.setattr("engram.indexer.embed", counting_embed)

    report = index(store, config, Scope("portfolio", None))

    assert report.chunks_added > 0
    all_texts = [text for call in embed_calls for text in call]
    assert any("MyUniqueHeading" in t and "some body text" in t for t in all_texts)
    assert len(all_texts) == report.chunks_added


# --- re-indexing a changed file prunes stale chunks and adds fresh ones ---


def test_reindexing_a_changed_file_prunes_old_and_adds_new(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    repo_dir = tmp_path / "repoA"
    repo_dir.mkdir()
    file_path = repo_dir / "doc.md"
    file_path.write_text("# Heading\nold-marker-xyz\n")

    def fake_enum(*a, **k):
        yield CorpusFile("notes", "repoA", file_path)

    monkeypatch.setattr("engram.indexer.enumerate_corpora", fake_enum)
    monkeypatch.setattr("engram.indexer.embed", fake_embed)

    first_report = index(store, config, Scope("portfolio", None))
    assert first_report.chunks_added > 0

    file_path.write_text("# Heading\nnew-marker-xyz\n")

    second_report = index(store, config, Scope("portfolio", None))

    assert second_report.chunks_added > 0
    assert second_report.chunks_pruned > 0

    hits_new = store.search_bm25(
        "new-marker-xyz", Scope("portfolio", None), corpus=None, k=10
    )
    assert len(hits_new) == 1

    hits_old = store.search_bm25(
        "old-marker-xyz", Scope("portfolio", None), corpus=None, k=10
    )
    assert hits_old == []


# --- _chunk_file: dispatches by corpus ---


def test_chunk_file_routes_transcripts_corpus_to_transcripts_chunk(tmp_path, monkeypatch):
    file_path = tmp_path / "session.jsonl"
    file_path.write_text("")
    file = CorpusFile("transcripts", "cellar", file_path)

    known_chunk = Chunk(
        corpus="transcripts",
        repo="cellar",
        doc_type="turn",
        path=str(file_path),
        heading="user turn",
        body="body",
        line_start=1,
        line_end=1,
        content_hash="hash123",
        chunk_ordinal=1,
    )

    calls = []

    def fake_transcripts_chunk(path, repo, content_hash):
        calls.append((path, repo, content_hash))
        return [known_chunk]

    def refuse_chunk_markdown(*a, **k):
        raise AssertionError("chunk_markdown should not be used for a transcripts file")

    monkeypatch.setattr("engram.indexer.transcripts.chunk", fake_transcripts_chunk)
    monkeypatch.setattr("engram.indexer.chunk_markdown", refuse_chunk_markdown)

    result = _chunk_file(file, "hash123")

    assert calls == [(file_path, "cellar", "hash123")]
    assert result == [known_chunk]


def test_chunk_file_routes_code_corpus_to_symbols_chunk(tmp_path, monkeypatch):
    file_path = tmp_path / "main.py"
    file_path.write_text("def f():\n    pass\n")
    file = CorpusFile("code", "repoA", file_path)

    known_chunk = Chunk(
        corpus="code",
        repo="repoA",
        doc_type="function",
        path=str(file_path),
        heading="function f",
        body="def f():\n    pass",
        line_start=1,
        line_end=2,
        content_hash="hash456",
        chunk_ordinal=1,
    )

    calls = []

    def fake_symbols_chunk(path, repo, content_hash):
        calls.append((path, repo, content_hash))
        return [known_chunk]

    def refuse_chunk_markdown(*a, **k):
        raise AssertionError("chunk_markdown should not be used for a code file")

    monkeypatch.setattr("engram.indexer.symbols.chunk", fake_symbols_chunk)
    monkeypatch.setattr("engram.indexer.chunk_markdown", refuse_chunk_markdown)

    result = _chunk_file(file, "hash456")

    assert calls == [(file_path, "repoA", "hash456")]
    assert result == [known_chunk]


def test_chunk_file_routes_other_corpora_to_chunk_markdown(tmp_path, monkeypatch):
    file_path = tmp_path / "doc.md"
    file_path.write_text("# H\nbody\n")
    file = CorpusFile("memory", "repoA", file_path)

    known_chunk = Chunk(
        corpus="memory",
        repo="repoA",
        doc_type="md",
        path=str(file_path),
        heading="H",
        body="body",
        line_start=1,
        line_end=2,
        content_hash="hash789",
        chunk_ordinal=0,
    )

    calls = []

    def fake_chunk_markdown(path, corpus, repo, content_hash):
        calls.append((path, corpus, repo, content_hash))
        return [known_chunk]

    monkeypatch.setattr("engram.indexer.chunk_markdown", fake_chunk_markdown)

    result = _chunk_file(file, "hash789")

    assert calls == [(file_path, "memory", "repoA", "hash789")]
    assert result == [known_chunk]


# --- index() enumerates the transcripts producer ---


def test_index_enumerates_transcripts_producer_and_indexes_its_chunks(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text('{"type": "user"}\n')

    def fake_enum_corpora(*a, **k):
        return iter(())

    def fake_transcripts_enum(*a, **k):
        yield CorpusFile("transcripts", "cellar", transcript_path)

    def fake_transcripts_chunk(path, repo, content_hash):
        return [
            Chunk(
                corpus="transcripts",
                repo="cellar",
                doc_type="turn",
                path=str(transcript_path),
                heading="user turn",
                body="freshly-added-transcript-marker",
                line_start=1,
                line_end=1,
                content_hash=content_hash,
                chunk_ordinal=1,
            )
        ]

    monkeypatch.setattr("engram.indexer.enumerate_corpora", fake_enum_corpora)
    monkeypatch.setattr("engram.indexer.transcripts.enumerate", fake_transcripts_enum)
    monkeypatch.setattr("engram.indexer.transcripts.chunk", fake_transcripts_chunk)
    monkeypatch.setattr("engram.indexer.embed", fake_embed)

    report = index(store, config, Scope("portfolio", None))

    assert report.chunks_added > 0
    hits = store.search_bm25(
        "freshly-added-transcript-marker", Scope("portfolio", None), corpus=None, k=10
    )
    assert len(hits) == 1


# --- checkpointing: a killed run keeps the progress it already committed ---


def test_index_preserves_already_committed_chunks_when_embedding_fails_partway(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    repo_dir = tmp_path / "repoA"
    repo_dir.mkdir()
    file_committed = repo_dir / "committed.md"
    file_committed.write_text("# Heading\ncommitted-before-failure-marker\n")
    file_uncommitted = repo_dir / "uncommitted.md"
    file_uncommitted.write_text("# Heading\nnever-embedded-marker\n")

    def fake_enum(*a, **k):
        yield CorpusFile("notes", "repoA", file_committed)
        yield CorpusFile("notes", "repoA", file_uncommitted)

    call_count = {"n": 0}

    def failing_embed(texts, entry):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [Vector([1.0, 0.0, 0.0, 0.0], entry.id, 4) for _ in texts]
        raise _EmbedFailure("embedding server died mid-run")

    monkeypatch.setattr("engram.indexer.enumerate_corpora", fake_enum)
    monkeypatch.setattr("engram.indexer.embed", failing_embed)

    with pytest.raises(_EmbedFailure):
        index(store, config, Scope("portfolio", None))

    hits_committed = store.search_bm25(
        "committed-before-failure-marker", Scope("portfolio", None), corpus=None, k=10
    )
    assert len(hits_committed) == 1

    hits_uncommitted = store.search_bm25(
        "never-embedded-marker", Scope("portfolio", None), corpus=None, k=10
    )
    assert hits_uncommitted == []


# --- checkpointing: re-run after a failure resumes instead of restarting ---


def test_rerun_after_partial_failure_embeds_only_the_uncommitted_file(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    repo_dir = tmp_path / "repoA"
    repo_dir.mkdir()
    file_committed = repo_dir / "committed.md"
    file_committed.write_text("# Heading\nalready-committed-marker\n")
    file_uncommitted = repo_dir / "uncommitted.md"
    file_uncommitted.write_text("# Heading\nresumed-after-failure-marker\n")

    def fake_enum(*a, **k):
        yield CorpusFile("notes", "repoA", file_committed)
        yield CorpusFile("notes", "repoA", file_uncommitted)

    call_count = {"n": 0}

    def failing_embed(texts, entry):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [Vector([1.0, 0.0, 0.0, 0.0], entry.id, 4) for _ in texts]
        raise _EmbedFailure("embedding server died mid-run")

    monkeypatch.setattr("engram.indexer.enumerate_corpora", fake_enum)
    monkeypatch.setattr("engram.indexer.embed", failing_embed)

    with pytest.raises(_EmbedFailure):
        index(store, config, Scope("portfolio", None))

    embed_calls = []

    def counting_embed(texts, entry):
        embed_calls.append(texts)
        return [Vector([1.0, 0.0, 0.0, 0.0], entry.id, 4) for _ in texts]

    monkeypatch.setattr("engram.indexer.embed", counting_embed)

    second_report = index(store, config, Scope("portfolio", None))

    assert len(embed_calls) == 1
    all_texts = [t for call in embed_calls for t in call]
    assert not any("already-committed-marker" in t for t in all_texts)
    assert any("resumed-after-failure-marker" in t for t in all_texts)
    assert second_report.chunks_added > 0

    hits_resumed = store.search_bm25(
        "resumed-after-failure-marker", Scope("portfolio", None), corpus=None, k=10
    )
    assert len(hits_resumed) == 1


# --- checkpointing: a killed run never prunes rows of files it never reached ---


def test_partial_failure_never_prunes_rows_of_files_it_never_reached(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    repo_dir = tmp_path / "repoA"
    repo_dir.mkdir()

    failing_file = repo_dir / "triggers-failure.md"
    failing_file.write_text("# Heading\nfailing-file-marker\n")

    unreached_file = repo_dir / "never-reached.md"
    unreached_file.write_text("# Heading\nnever-reached-preexisting-marker\n")

    # Simulate rows already committed by an earlier, successful index() run.
    preexisting_chunk = Chunk(
        corpus="notes",
        repo="repoA",
        doc_type="md",
        path=str(unreached_file),
        heading="Heading",
        body="never-reached-preexisting-marker",
        line_start=1,
        line_end=2,
        content_hash=hash_source(unreached_file),
        chunk_ordinal=0,
    )
    store.upsert_chunks(
        [
            ChunkWithVector(
                chunk=preexisting_chunk,
                vector=Vector([1.0, 0.0, 0.0, 0.0], "test-model", 4),
            )
        ]
    )

    def fake_enum(*a, **k):
        yield CorpusFile("notes", "repoA", failing_file)
        yield CorpusFile("notes", "repoA", unreached_file)

    def failing_embed(texts, entry):
        raise _EmbedFailure("embedding server died mid-run")

    monkeypatch.setattr("engram.indexer.enumerate_corpora", fake_enum)
    monkeypatch.setattr("engram.indexer.embed", failing_embed)

    with pytest.raises(_EmbedFailure):
        index(store, config, Scope("portfolio", None))

    hits = store.search_bm25(
        "never-reached-preexisting-marker", Scope("portfolio", None), corpus=None, k=10
    )
    assert len(hits) == 1


# --- Defect A: a repo whose git-ls-files enumeration failed must not have its
# already-indexed chunks pruned; a repo that enumerates fine still prunes normally ---


def test_failed_repo_enumeration_does_not_prune_its_chunks(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    # Rows already indexed for repoA and repoB by an earlier, healthy run.
    preexisting_a = Chunk(
        corpus="code",
        repo="repoA",
        doc_type="function",
        path="repoA/old.py",
        heading="Function repo_a_marker",
        body="def repo_a_marker():\n    pass",
        line_start=1,
        line_end=2,
        content_hash="preexisting-hash-a",
        chunk_ordinal=1,
    )
    preexisting_b = Chunk(
        corpus="code",
        repo="repoB",
        doc_type="function",
        path="repoB/old.py",
        heading="Function repo_b_marker",
        body="def repo_b_marker():\n    pass",
        line_start=1,
        line_end=2,
        content_hash="preexisting-hash-b",
        chunk_ordinal=1,
    )
    store.upsert_chunks(
        [
            ChunkWithVector(
                chunk=preexisting_a, vector=Vector([1.0, 0.0, 0.0, 0.0], "test-model", 4)
            ),
            ChunkWithVector(
                chunk=preexisting_b, vector=Vector([1.0, 0.0, 0.0, 0.0], "test-model", 4)
            ),
        ]
    )

    repo_a_dir = tmp_path / "repoA"
    repo_a_dir.mkdir()
    file_a = repo_a_dir / "new.py"
    file_a.write_text("def repo_a_marker():\n    pass\n")

    def fake_symbols_enum(*a, **k):
        # repoA enumerates fine and reports its one currently-tracked file.
        yield CorpusFile("code", "repoA", file_a)
        # repoB's `git ls-files` failed (dir gone / mid-rebase / unmounted disk):
        # nothing is yielded for it, matching enumerate()'s real failure branch.
        corpora_module.missing_dirs.append("code:repoB")

    monkeypatch.setattr("engram.indexer.enumerate_corpora", lambda *a, **k: iter(()))
    monkeypatch.setattr("engram.indexer.symbols.enumerate", fake_symbols_enum)
    monkeypatch.setattr("engram.indexer.embed", fake_embed)

    index(store, config, Scope("portfolio", None))

    remaining_paths = {c.path for c in store.chunks_for_corpus("code")}
    assert preexisting_b.path in remaining_paths


def test_healthy_repo_still_prunes_genuinely_deleted_files_despite_a_sibling_repos_enumeration_failure(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    preexisting_a_old = Chunk(
        corpus="code",
        repo="repoA",
        doc_type="function",
        path="repoA/old.py",
        heading="Function repo_a_marker",
        body="def repo_a_marker():\n    pass",
        line_start=1,
        line_end=2,
        content_hash="preexisting-hash-a",
        chunk_ordinal=1,
    )
    preexisting_b = Chunk(
        corpus="code",
        repo="repoB",
        doc_type="function",
        path="repoB/old.py",
        heading="Function repo_b_marker",
        body="def repo_b_marker():\n    pass",
        line_start=1,
        line_end=2,
        content_hash="preexisting-hash-b",
        chunk_ordinal=1,
    )
    store.upsert_chunks(
        [
            ChunkWithVector(
                chunk=preexisting_a_old, vector=Vector([1.0, 0.0, 0.0, 0.0], "test-model", 4)
            ),
            ChunkWithVector(
                chunk=preexisting_b, vector=Vector([1.0, 0.0, 0.0, 0.0], "test-model", 4)
            ),
        ]
    )

    # repoA is healthy this run but old.py is genuinely gone; only a different
    # file remains tracked.
    repo_a_dir = tmp_path / "repoA"
    repo_a_dir.mkdir()
    file_a_current = repo_a_dir / "current.py"
    file_a_current.write_text("def repo_a_current():\n    pass\n")

    def fake_symbols_enum(*a, **k):
        yield CorpusFile("code", "repoA", file_a_current)
        corpora_module.missing_dirs.append("code:repoB")

    monkeypatch.setattr("engram.indexer.enumerate_corpora", lambda *a, **k: iter(()))
    monkeypatch.setattr("engram.indexer.symbols.enumerate", fake_symbols_enum)
    monkeypatch.setattr("engram.indexer.embed", fake_embed)

    index(store, config, Scope("portfolio", None))

    remaining_paths = {c.path for c in store.chunks_for_corpus("code")}
    assert preexisting_a_old.path not in remaining_paths
    assert preexisting_b.path in remaining_paths


# --- Defect B: a file that raises while being parsed is skipped, not fatal,
# and the run completes and visibly reports the skip ---


def test_index_skips_file_that_fails_to_parse_completes_and_reports_the_skip(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    repo_dir = tmp_path / "repoA"
    repo_dir.mkdir()
    good_file = repo_dir / "good.py"
    good_file.write_text("def surviving_marker():\n    pass\n")
    bad_file = repo_dir / "bad.py"
    bad_file.write_text("def failing_marker():\n    pass\n")

    def fake_symbols_enum(*a, **k):
        yield CorpusFile("code", "repoA", good_file)
        yield CorpusFile("code", "repoA", bad_file)

    real_process = symbols.process

    def flaky_process(source, process_config):
        if "failing_marker" in source:
            raise RuntimeError("tree-sitter blew up")
        return real_process(source, process_config)

    monkeypatch.setattr("engram.indexer.enumerate_corpora", lambda *a, **k: iter(()))
    monkeypatch.setattr("engram.indexer.symbols.enumerate", fake_symbols_enum)
    monkeypatch.setattr("engram.symbols.process", flaky_process)
    monkeypatch.setattr("engram.indexer.embed", fake_embed)

    report = index(store, config, Scope("portfolio", None))

    assert report.files_skipped >= 1
    hits = store.search_bm25(
        "surviving_marker", Scope("portfolio", None), corpus=None, k=10
    )
    assert len(hits) == 1


# --- Defect A: a non-code corpus file (memory/prd/decision/discovery) that
# fails to decode as UTF-8 goes through chunk_markdown, not symbols.chunk, so
# it must be skipped by index()'s own try/except rather than kill the run ---


def test_index_skips_an_undecodable_markdown_file_and_completes_the_run(
    tmp_path, monkeypatch
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    repo_dir = tmp_path / "repoA"
    repo_dir.mkdir()
    good_file = repo_dir / "good.md"
    good_file.write_text("# Heading\nsurviving-markdown-marker\n")
    bad_file = repo_dir / "bad.md"
    bad_file.write_bytes(b"# Heading\nbroken \xe9 byte marker\n")

    def fake_enum(*a, **k):
        yield CorpusFile("memory", "repoA", good_file)
        yield CorpusFile("memory", "repoA", bad_file)

    monkeypatch.setattr("engram.indexer.enumerate_corpora", fake_enum)
    monkeypatch.setattr("engram.indexer.embed", fake_embed)

    report = index(store, config, Scope("portfolio", None))

    assert report.files_skipped >= 1
    hits = store.search_bm25(
        "surviving-markdown-marker", Scope("portfolio", None), corpus=None, k=10
    )
    assert len(hits) == 1
