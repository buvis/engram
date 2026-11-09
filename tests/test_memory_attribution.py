from collections.abc import Iterator
from dataclasses import replace
from functools import partial
from pathlib import Path

import pytest

from engram.client import EmbeddingEntry, EngramConfig, Vector
from engram.corpora import CorpusFile, enumerate_corpora
from engram.indexer import index
from engram.query import query
from engram.store import Chunk, ChunkWithVector, Scope, Store, open_store


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    db = open_store(tmp_path / "engram.db")
    yield db
    db.conn.close()


@pytest.fixture
def memory_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[CorpusFile]:
    projects = tmp_path / "projects"
    for slug in (
        "-work-github-com-repoA",
        "-work-github-com-repoB",
        "-unknown",
        "-work-a-b",
    ):
        memory = projects / slug / "memory"
        memory.mkdir(parents=True)
        (memory / "notes.md").write_text("# Recall\nsharedmarker\n")
    (projects / "-work-github-com-repoA" / "memory" / "empty.md").write_text("")
    registry = tmp_path / "repos.csv"
    registry.write_text(
        "/work/github.com/repoA,repoA\n/work/github.com/repoB,repoB\n"
        "/work/a/b,first\n/work/a-b,second\n"
    )
    enumerate_memory = partial(enumerate_corpora, registry, projects)
    monkeypatch.setattr("engram.indexer.enumerate_corpora", enumerate_memory)

    def unrelated_enumeration(**kwargs: object) -> Iterator[CorpusFile]:
        pytest.fail("memory-only indexing must not enumerate code or transcripts")

    monkeypatch.setattr("engram.indexer.symbols.enumerate", unrelated_enumeration)
    monkeypatch.setattr("engram.indexer.transcripts.enumerate", unrelated_enumeration)
    return list(enumerate_memory())


@pytest.fixture
def config(tmp_path: Path) -> EngramConfig:
    return EngramConfig(
        embeddings=[EmbeddingEntry("test-model", "http://127.0.0.1:8081/v1")],
        pinned_id="test-model",
        config_path=tmp_path / "config.toml",
    )


def fake_embed(texts: list[str], entry: EmbeddingEntry) -> list[Vector]:
    return [Vector([1.0, 0.0], entry.id, 2) for _ in texts]


@pytest.mark.parametrize("scope", [Scope("portfolio", None), Scope("repo", "repoA")])
def test_repository_recall_cannot_cross_memory_boundaries(
    store: Store,
    config: EngramConfig,
    memory_sources: list[CorpusFile],
    monkeypatch: pytest.MonkeyPatch,
    scope: Scope,
) -> None:
    monkeypatch.setattr("engram.indexer.embed", fake_embed)
    index(store, config, scope, corpus="memory")
    vector = Vector([1.0, 0.0], "test-model", 2)
    expected_path = str(
        next(
            f.path
            for f in memory_sources
            if f.path.parent.parent.name == "-work-github-com-repoA"
            and f.path.name == "notes.md"
        )
    )

    for hits in (
        store.search_bm25("sharedmarker", Scope("repo", "repoA"), "memory", 10),
        store.search_knn(vector, Scope("repo", "repoA"), "memory", 10),
    ):
        assert [(h.chunk.repo, h.chunk.path) for h in hits] == [
            ("repoA", expected_path)
        ]
    results = query(
        store, config, "sharedmarker", Scope("repo", "repoA"), "memory", vector=vector
    )
    assert [(p.repo, p.path) for p in results] == [("repoA", expected_path)]
    assert (
        query(
            store,
            config,
            "sharedmarker",
            Scope("repo", "first"),
            "memory",
            vector=vector,
        )
        == []
    )
    assert (
        query(
            store,
            config,
            "sharedmarker",
            Scope("repo", "second"),
            "memory",
            vector=vector,
        )
        == []
    )


def test_memory_only_pass_migrates_old_attribution_and_preserves_other_corpora(
    store: Store,
    config: EngramConfig,
    memory_sources: list[CorpusFile],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("engram.indexer.embed", fake_embed)
    with monkeypatch.context() as legacy:
        legacy.setattr(
            "engram.indexer.enumerate_corpora",
            lambda: (replace(f, repo="_unmapped") for f in memory_sources),
        )
        index(store, config, Scope("portfolio", None), corpus="memory")
    assert len(store.known_sources(Scope("repo", "_unmapped"), "memory")) == 4

    unrelated = Chunk(
        "prd", "repoA", "markdown", "/absent/prd.md", "Keep", "keep", 1, 2, "old", 0
    )
    store.upsert_chunks(
        [ChunkWithVector(unrelated, Vector([0.0, 1.0], "test-model", 2))]
    )
    store.mark_empty_source("code", "repoA", "/absent/code.py", "old")
    original_rows = store.conn.execute(
        "SELECT * FROM chunks WHERE corpus != 'memory'"
    ).fetchall()
    original_vectors = store.conn.execute(
        "SELECT * FROM chunks_vec WHERE corpus != 'memory'"
    ).fetchall()
    original_empty = store.known_empty_sources_by_corpus(
        Scope("portfolio", None), "code"
    )

    report = index(store, config, Scope("portfolio", None), corpus="memory")

    assert report.chunks_added == 2
    assert report.chunks_pruned == 2
    assert sorted(c.repo for c in store.chunks_for_corpus("memory")) == [
        "_unmapped",
        "_unmapped",
        "repoA",
        "repoB",
    ]
    assert {
        key[1]
        for key in store.known_empty_sources_by_corpus(
            Scope("portfolio", None), "memory"
        )
    } == {"repoA"}
    assert (
        store.conn.execute("SELECT * FROM chunks WHERE corpus != 'memory'").fetchall()
        == original_rows
    )
    assert (
        store.conn.execute(
            "SELECT * FROM chunks_vec WHERE corpus != 'memory'"
        ).fetchall()
        == original_vectors
    )
    assert (
        store.known_empty_sources_by_corpus(Scope("portfolio", None), "code")
        == original_empty
    )

    def unexpected_embed(texts: list[str], entry: EmbeddingEntry) -> list[Vector]:
        pytest.fail("unchanged memory migration must be idempotent")

    monkeypatch.setattr("engram.indexer.embed", unexpected_embed)
    repeated = index(store, config, Scope("portfolio", None), corpus="memory")
    assert repeated.chunks_added == repeated.chunks_pruned == 0
