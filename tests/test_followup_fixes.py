"""Regressions for the 2026-11-01 follow-up defects (transcript results, failed sources,
absent cellar, code embedding paths)."""

import json
from pathlib import Path

import engram.corpora as corpora_module
import pytest

from engram import transcripts
from engram.client import EmbeddingEntry, EngramConfig, Vector
from engram.corpora import CorpusFile
from engram.indexer import index
from engram.store import Chunk, Scope, open_store


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    corpora_module.missing_dirs.clear()
    monkeypatch.setattr("engram.indexer.transcripts.enumerate", lambda *a, **k: iter(()))
    monkeypatch.setattr("engram.indexer.symbols.enumerate", lambda *a, **k: iter(()))
    monkeypatch.setattr("engram.indexer.embed", _embed)
    yield
    corpora_module.missing_dirs.clear()


def _embed(texts, entry):
    return [Vector([1.0, 0.0, 0.0, 0.0], entry.id, 4) for _ in texts]


def _config(tmp_path):
    entry = EmbeddingEntry(id="test-model", endpoint="http://127.0.0.1:8081/v1")
    return EngramConfig(embeddings=[entry], pinned_id=None, config_path=tmp_path / "c.toml")


def _chunks(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return transcripts.chunk(
        path, "cellar", "h", error_patterns=transcripts.DEFAULT_ERROR_PATTERNS
    )


# --- 1. transcript tool-result text ---


def test_error_tool_result_text_is_in_the_chunk_body(tmp_path):
    msg = {"role": "user", "content": [{"type": "tool_result", "content": "Traceback (most recent call last):\nKeyError: x"}]}
    chunks = _chunks(tmp_path / "s.jsonl", [{"type": "user", "message": msg}])
    assert len(chunks) == 1
    assert "KeyError: x" in chunks[0].body


def test_list_form_tool_result_is_matched_and_extracted(tmp_path):
    msg = {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "content": [{"type": "text", "text": "pytest: FAIL test_a"}, {"type": "image"}],
            }
        ],
    }
    chunks = _chunks(tmp_path / "s.jsonl", [{"type": "user", "message": msg}])
    assert len(chunks) == 1
    assert "FAIL test_a" in chunks[0].body


def test_non_error_tool_result_is_not_added(tmp_path):
    msg = {"role": "user", "content": [{"type": "tool_result", "content": "all fine"}]}
    assert _chunks(tmp_path / "s.jsonl", [{"type": "user", "message": msg}]) == []


# --- 2. failed sources keep their rows ---


def _doc_index(tmp_path, monkeypatch, name="doc.md"):
    repo_dir = tmp_path / "repoA"
    repo_dir.mkdir(exist_ok=True)
    f = repo_dir / name
    f.write_text("# H\nbody\n")
    monkeypatch.setattr(
        "engram.indexer.enumerate_corpora", lambda *a, **k: iter([CorpusFile("notes", "repoA", f)])
    )
    return f


def test_hash_failure_preserves_rows_and_reports_source(tmp_path, monkeypatch):
    store = open_store(tmp_path / "e.db")
    config = _config(tmp_path)
    f = _doc_index(tmp_path, monkeypatch)
    index(store, config, Scope("portfolio", None))
    before = store.conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
    assert before > 0

    def boom(path):
        raise PermissionError(path)

    monkeypatch.setattr("engram.indexer.hash_source", boom)
    report = index(store, config, Scope("portfolio", None))

    assert store.conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == before
    assert report.chunks_pruned == 0
    assert [str(f)] == [p for p in report.failed_sources]


def test_chunk_failure_on_changed_file_preserves_old_rows(tmp_path, monkeypatch):
    store = open_store(tmp_path / "e.db")
    config = _config(tmp_path)
    f = _doc_index(tmp_path, monkeypatch)
    index(store, config, Scope("portfolio", None))
    before = store.conn.execute("SELECT count(*) FROM chunks").fetchone()[0]

    f.write_text("# H\nchanged\n")

    def boom(*a, **k):
        raise ValueError("parse")

    monkeypatch.setattr("engram.indexer._chunk_file", boom)
    report = index(store, config, Scope("portfolio", None))

    assert store.conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == before
    assert report.failed_sources == [str(f)]


def test_vanished_source_is_still_pruned(tmp_path, monkeypatch):
    store = open_store(tmp_path / "e.db")
    config = _config(tmp_path)
    f = _doc_index(tmp_path, monkeypatch)
    index(store, config, Scope("portfolio", None))
    monkeypatch.setattr("engram.indexer.enumerate_corpora", lambda *a, **k: iter(()))
    report = index(store, config, Scope("portfolio", None))
    assert report.chunks_pruned > 0
    assert report.failed_sources == []


# --- 3. absent cellar ---


def _no_cellar(*a, **k):
    raise FileNotFoundError("/x/cellar not found; cellar transcripts corpus requires this path")
    yield  # pragma: no cover


def test_scoped_corpus_index_works_without_cellar(tmp_path, monkeypatch):
    store = open_store(tmp_path / "e.db")
    _doc_index(tmp_path, monkeypatch)
    monkeypatch.setattr("engram.indexer.transcripts.enumerate", _no_cellar)
    report = index(store, _config(tmp_path), Scope("portfolio", None), corpus="notes")
    assert report.chunks_added > 0


def test_repo_scope_other_than_cellar_works_without_cellar(tmp_path, monkeypatch):
    store = open_store(tmp_path / "e.db")
    _doc_index(tmp_path, monkeypatch)
    monkeypatch.setattr("engram.indexer.transcripts.enumerate", _no_cellar)
    report = index(store, _config(tmp_path), Scope("repo", "repoA"))
    assert report.chunks_added > 0


@pytest.mark.parametrize(
    ("scope", "corpus"),
    [
        (Scope("portfolio", None), "transcripts"),
        (Scope("portfolio", None), None),
        (Scope("repo", "cellar"), None),
    ],
    ids=["transcripts-corpus", "portfolio-all", "cellar-repo"],
)
def test_scope_needing_transcripts_still_fails_clearly(tmp_path, monkeypatch, scope, corpus):
    store = open_store(tmp_path / "e.db")
    _doc_index(tmp_path, monkeypatch)
    monkeypatch.setattr("engram.indexer.transcripts.enumerate", _no_cellar)
    with pytest.raises(FileNotFoundError, match="cellar"):
        index(store, _config(tmp_path), scope, corpus=corpus)


# --- 4. code embedding includes the file path ---


def test_code_embedding_text_includes_repo_relative_path():
    c = Chunk("code", "engram", "function", "/Users/b/git/engram/src/engram/store.py",
              "Function open_store", "def open_store(): ...", 1, 1, "h", 1)
    text = c.text_for_embedding
    assert "engram/src/engram/store.py" in text
    assert "/Users/b" not in text
    assert text.startswith("Function open_store\n")
    assert text.endswith("def open_store(): ...")


def test_non_code_embedding_text_is_unchanged():
    c = Chunk("prd", "r", "section", "/a/b.md", "Head", "body", 1, 1, "h", 1)
    assert c.text_for_embedding == "Head\nbody"


# --- 5. targeted code-vector refresh ---


def test_reembed_code_replaces_vectors_with_path_enriched_text(tmp_path, monkeypatch):
    from engram.indexer import reembed_code
    from engram.store import ChunkWithVector

    store = open_store(tmp_path / "e.db")
    code = Chunk("code", "r", "function", "/h/r/a.py", "Function f", "def f(): ...", 1, 1, "h1", 1)
    prd = Chunk("prd", "r", "section", "/h/r/p.md", "Head", "body", 1, 1, "h2", 1)
    old = Vector([0.0, 1.0, 0.0, 0.0], "test-model", 4)
    store.upsert_chunks([ChunkWithVector(code, old), ChunkWithVector(prd, old)])

    seen = []

    def embed(texts, entry):
        seen.extend(texts)
        return [Vector([1.0, 0.0, 0.0, 0.0], entry.id, 4) for _ in texts]

    monkeypatch.setattr("engram.indexer.embed", embed)
    assert reembed_code(store, _config(tmp_path)) == 1

    assert seen == ["Function f\nr/a.py\ndef f(): ..."]
    rows = store.conn.execute("SELECT corpus, content_hash FROM chunks ORDER BY corpus").fetchall()
    assert rows == [("code", "h1"), ("prd", "h2")]
