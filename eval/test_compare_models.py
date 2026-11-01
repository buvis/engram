"""Tests for the isolated model comparison, without model downloads."""

import pytest

from eval.compare_models import format_input, metrics, select_snapshot


@pytest.mark.parametrize(
    ("style", "query", "corpus", "expected"),
    [
        ("qwen", True, "code", "Instruct: Given a question, retrieve passages that can help answer the question.\nQuery: hello"),
        ("f2", False, "code", "hello<|im_end|>"),
        ("jina", True, "prd", "Query: hello"),
        ("jina", False, "prd", "Document: hello"),
        ("gemma", True, "code", "task: code retrieval | query: hello"),
        ("gemma", False, "prd", "title: title | text: hello"),
        ("raw", True, "prd", "hello"),
    ],
)
def test_model_input_rules(style, query, corpus, expected):
    assert format_input(style, "hello", query=query, corpus=corpus, title="title") == expected


def test_metrics_distinguish_file_from_exact_passage():
    gold = {"path": "a", "acceptable_starts": [20]}
    ranked = [
        {"path": "a", "line_start": 10},
        {"path": "b", "line_start": 20},
        {"path": "a", "line_start": 20},
    ]
    result = metrics(ranked, gold)
    assert result == {"file_hit5": 1, "file_rr": 1.0, "passage_hit5": 1, "passage_rr": 1 / 3}


def test_wrong_passage_in_correct_file_does_not_pass():
    result = metrics([{"path": "a", "line_start": 10}], {"path": "a", "acceptable_starts": [20]})
    assert result["file_hit5"] == 1
    assert result["passage_hit5"] == 0


def test_snapshot_keeps_targets_and_same_distractors_in_stable_order():
    rows = [{"id": i, "path": str(i), "corpus": "code"} for i in range(30)]
    gold = [{"path": "29", "corpus": "code"}]
    selected = select_snapshot(rows, gold, {12}, random_per_corpus=2)
    assert {12, 29} <= {row["id"] for row in selected}
    assert selected == select_snapshot(rows, gold, {12}, random_per_corpus=2)
    assert len(selected) <= 4
