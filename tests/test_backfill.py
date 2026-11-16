import pytest

from engram.client import Vector
from engram.store import Chunk, ChunkWithVector, Scope, open_store


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


@pytest.mark.parametrize(
    ("model_id", "values"),
    [
        ("model-a", [[0.5, -1.0, 2.0], [0.25, 4.0, -0.125], [-8.0, 0.75, 1.5]]),
        (
            "model-b",
            [[1.0, 2.0, 3.0, 4.0], [-0.5, 0.0, 0.5, 16.0], [3.0, -2.0, 1.0, 0.0]],
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
        _item(
            _chunk(path=path, heading=f"function f{ordinal}", chunk_ordinal=ordinal),
            values[ordinal],
            model_id,
            dim,
        )
        for ordinal in (2, 0, 1)
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

    assert [item.chunk.chunk_ordinal for item in result] == [0, 1, 2]
    assert [item.chunk.heading for item in result] == [
        "function f0",
        "function f1",
        "function f2",
    ]
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

    assert store.code_chunks_with_vectors("/src/repoA/mod") == []
    assert store.code_chunks_with_vectors("/src/repoA/other.py") == []


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

    store.unmark_empty_source("docs", "repoB", "/src/b.md")

    assert store.known_empty_sources_by_corpus(Scope("portfolio", None), None) == {
        ("code", "repoA", "/src/a.py", "h1"),
    }


def test_unmark_empty_source_is_noop_when_no_row_matches(tmp_path):
    store = open_store(tmp_path / "engram.db")
    store.mark_empty_source("code", "repoA", "/src/a.py", "h1")

    store.unmark_empty_source("code", "repoA", "/src/missing.py")
    store.unmark_empty_source("docs", "repoA", "/src/a.py")

    assert store.known_empty_sources_by_corpus(Scope("portfolio", None), None) == {
        ("code", "repoA", "/src/a.py", "h1"),
    }
