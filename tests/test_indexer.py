import engram.corpora as corpora_module
import pytest

from engram.client import EmbeddingEntry, EngramConfig, Vector
from engram.corpora import CorpusFile
from engram.indexer import IndexReport, index
from engram.store import Chunk, ChunkWithVector, Scope, open_store


@pytest.fixture(autouse=True)
def _reset_missing_dirs():
    # enumerate_corpora is patched per-test, so the real populator never runs;
    # reset the shared module-level list so tests don't leak state into each other.
    corpora_module.missing_dirs.clear()
    yield
    corpora_module.missing_dirs.clear()


def _entry(model_id="test-model"):
    return EmbeddingEntry(id=model_id, endpoint="http://127.0.0.1:8081/v1")


def _config(tmp_path, model_id="test-model"):
    return EngramConfig(
        embeddings=[_entry(model_id)], pinned_id=None, config_path=tmp_path / "config.toml"
    )


def fake_embed(texts, entry):
    return [Vector([1.0, 0.0, 0.0, 0.0], entry.id, 4) for _ in texts]


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
