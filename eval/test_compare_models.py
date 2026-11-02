"""Tests for the isolated model comparison, without model downloads."""

import json
from pathlib import Path

import pytest

from engram.store import open_store
from eval.benchmark_runtime import Server
from eval.compare_models import _embed_documents, format_input, metrics, select_snapshot
from eval.compare_rerankers import rerank


@pytest.mark.parametrize(
    ("style", "query", "corpus", "expected"),
    [
        (
            "qwen",
            True,
            "code",
            "Instruct: Given a question, retrieve passages that can help answer the question.\nQuery: hello",
        ),
        ("f2", False, "code", "hello<|im_end|>"),
        ("jina", True, "prd", "Query: hello"),
        ("jina", False, "prd", "Document: hello"),
        ("gemma", True, "code", "task: code retrieval | query: hello"),
        ("gemma", False, "prd", "title: title | text: hello"),
        ("raw", True, "prd", "hello"),
    ],
)
def test_model_input_rules(style: str, query: bool, corpus: str, expected: str) -> None:
    assert (
        format_input(style, "hello", query=query, corpus=corpus, title="title")
        == expected
    )


def test_metrics_distinguish_file_from_exact_passage() -> None:
    gold = {"path": "a", "acceptable_starts": [20]}
    ranked = [
        {"path": "a", "line_start": 10},
        {"path": "b", "line_start": 20},
        {"path": "a", "line_start": 20},
    ]
    result = metrics(ranked, gold)
    assert result == {
        "file_hit5": 1,
        "file_rr": 1.0,
        "passage_hit5": 1,
        "passage_rr": 1 / 3,
    }


def test_wrong_passage_in_correct_file_does_not_pass() -> None:
    result = metrics(
        [{"path": "a", "line_start": 10}], {"path": "a", "acceptable_starts": [20]}
    )
    assert result["file_hit5"] == 1
    assert result["passage_hit5"] == 0


def test_five_chunks_from_one_file_do_not_expand_top_five() -> None:
    ranked = [{"path": "other", "line_start": n} for n in range(5)]
    ranked.append({"path": "target", "line_start": 20})
    assert metrics(ranked, {"path": "target"})["file_hit5"] == 0


@pytest.mark.parametrize("values", [[None], [float("nan")], [0.0, 0.0]])
def test_invalid_embeddings_fail_instead_of_entering_an_index(
    values: list, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "eval.benchmark_runtime.request",
        lambda *args: {"data": [{"index": 0, "embedding": values}]},
    )
    server = Server({"name": "test"}, tmp_path)
    with pytest.raises(ValueError):
        server.embed(["hello"])


def test_interrupted_document_index_resumes_without_reembedding_saved_chunks(
    tmp_path: Path,
) -> None:
    class TestServer:
        def __init__(self) -> None:
            self.inputs = []

        def embed(self, texts: list[str]) -> list[list[float]]:
            self.inputs.extend(texts)
            return [[1.0, 0.0] for _ in texts]

    row = {
        "id": 1,
        "corpus": "code",
        "repo": "demo",
        "doc_type": "symbol",
        "path": "/demo/a.py",
        "heading": "f",
        "body": "return 1",
        "line_start": 1,
        "line_end": 2,
        "content_hash": "abc",
        "chunk_ordinal": 0,
    }
    store = open_store(tmp_path / "candidate.db")
    server = TestServer()
    try:
        _embed_documents(
            server, {"style": "raw", "id": "test", "name": "test"}, [row], store
        )
        second = _embed_documents(
            server, {"style": "raw", "id": "test", "name": "test"}, [row], store
        )
        assert len(server.inputs) == 1
        assert second["new_chunks"] == 0
    finally:
        store.conn.close()


def test_snapshot_keeps_targets_and_same_distractors_in_stable_order() -> None:
    rows = [{"id": i, "path": str(i), "corpus": "code"} for i in range(30)]
    gold = [{"path": "29", "corpus": "code"}]
    selected = select_snapshot(rows, gold, {12}, random_per_corpus=2)
    assert {12, 29} <= {row["id"] for row in selected}
    assert selected == select_snapshot(rows, gold, {12}, random_per_corpus=2)
    assert len(selected) <= 4


def test_reranking_records_new_rank_and_preserves_retrieval_rank(
    tmp_path: Path,
) -> None:
    class FakeReranker:
        peak_rss_kib = None
        memory_sampling_error = None

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "FakeReranker":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def rerank(self, query: str, documents: list[str]) -> list[float]:
            return [0.1, 0.9]

        def allocation_lines(self) -> list[str]:
            return []

    pointers = [
        {"path": "wrong", "body": "wrong", "heading": "", "line_start": 1, "rank": 1},
        {"path": "target", "body": "answer", "heading": "", "line_start": 2, "rank": 2},
    ]
    original = tmp_path / "embedding.json"
    original.write_text(
        json.dumps(
            {
                "spec": {"name": "embedding"},
                "results": [{"query_id": 0, "ranked": pointers, "seconds": 0.1}],
            }
        )
    )
    snapshot = {
        "max_chars": 4000,
        "gold": [{"query": "question", "path": "target", "corpus": "code"}],
    }
    rerank({"name": "reranker"}, original, tmp_path, snapshot, server_type=FakeReranker)
    report = json.loads(next(tmp_path.glob("*/result.json")).read_text())
    winner = report["results"][0]["ranked"][0]
    assert winner["path"] == "target"
    assert winner["rank"] == 1
    assert winner["retrieval_rank"] == 2
    assert winner["rerank_score"] == 0.9
    assert report["summary"]["all"]["file_rr"] == 1
