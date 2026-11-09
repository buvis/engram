from pathlib import Path

import pytest

from engram import corpora, symbols
from engram.client import EmbeddingEntry, EngramConfig, Vector
from engram.corpora import CorpusFile
from engram.indexer import index
from engram.store import Scope, open_store


@pytest.mark.parametrize("failure", ["read", "parse"])
def test_transient_symbol_failure_is_retried_without_changing_file(
    tmp_path, monkeypatch, failure
) -> None:
    source = tmp_path / "sample.py"
    source.write_text("def recovered():\n    return 1\n")
    entry = EmbeddingEntry(id="test", endpoint="http://127.0.0.1:8081/v1")
    config = EngramConfig([entry], None, tmp_path / "config.toml")
    scope = Scope("portfolio", None)
    monkeypatch.setattr(corpora, "missing_dirs", [])
    monkeypatch.setattr("engram.indexer.enumerate_corpora", lambda: iter(()))
    monkeypatch.setattr("engram.indexer.transcripts.enumerate", lambda: iter(()))
    monkeypatch.setattr(
        symbols, "enumerate", lambda **kwargs: iter([CorpusFile("code", "repo", source)])
    )
    monkeypatch.setattr(
        "engram.indexer.embed",
        lambda texts, entry: [Vector([1.0, 0.0], entry.id, 2) for _ in texts],
    )
    target, name = (Path, "read_text") if failure == "read" else (symbols, "process")
    original = getattr(target, name)

    def fail_once(*args, **kwargs):
        monkeypatch.setattr(target, name, original)
        raise OSError("temporary failure")

    monkeypatch.setattr(target, name, fail_once)
    store = open_store(tmp_path / "index.db")
    try:
        first = index(store, config, scope)
        assert first.files_skipped == 1
        assert not store.known_empty_sources_by_corpus(scope, None)
        second = index(store, config, scope)
        assert second.chunks_added == 1
        assert store.search_bm25("recovered", scope, None, 5)
    finally:
        store.conn.close()


def test_open_store_invalidates_legacy_empty_code_records_once(tmp_path) -> None:
    path = tmp_path / "index.db"
    scope = Scope("portfolio", None)
    store = open_store(path)
    store.mark_empty_source("code", "repo", "failed.py", "h1")
    store.mark_empty_source("transcripts", "cellar", "empty.jsonl", "h2")
    store.conn.execute("DELETE FROM meta WHERE key = 'empty_code_cache_version'")
    store.conn.close()

    store = open_store(path)
    try:
        assert store.known_empty_sources_by_corpus(scope, "code") == set()
        assert store.known_empty_sources_by_corpus(scope, "transcripts")
        store.mark_empty_source("code", "repo", "empty.py", "h3")
    finally:
        store.conn.close()

    store = open_store(path)
    try:
        assert store.known_empty_sources_by_corpus(scope, "code") == {
            ("code", "repo", "empty.py", "h3")
        }
    finally:
        store.conn.close()


def test_failed_code_enumeration_preserves_empty_markers(tmp_path, monkeypatch) -> None:
    entry = EmbeddingEntry(id="test", endpoint="http://127.0.0.1:8081/v1")
    config = EngramConfig([entry], None, tmp_path / "config.toml")
    scope = Scope("portfolio", None)
    monkeypatch.setattr(corpora, "missing_dirs", ["code:repo"])
    monkeypatch.setattr("engram.indexer.enumerate_corpora", lambda: iter(()))
    monkeypatch.setattr("engram.indexer.transcripts.enumerate", lambda: iter(()))
    monkeypatch.setattr(symbols, "enumerate", lambda **kwargs: iter(()))
    store = open_store(tmp_path / "index.db")
    try:
        store.mark_empty_source("code", "repo", "empty.bin", "h1")
        index(store, config, scope)
        assert store.known_empty_sources_by_corpus(scope, "code") == {
            ("code", "repo", "empty.bin", "h1")
        }
    finally:
        store.conn.close()
