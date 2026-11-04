"""Measurement guards for the fixed-fusion reranker probe."""

import sqlite3
from pathlib import Path

import pytest

from eval.probe_rerank_fixed import (
    assert_baseline,
    open_readonly,
    rerank_documents,
    score_ranking,
)


def test_reranker_framing_budget_includes_heading_and_full_path() -> None:
    documents = rerank_documents(
        [{"heading": "Heading", "path": "/full/path", "body": "x" * 9000}], 8000
    )
    assert documents == ["Heading\n/full/path\n" + "x" * 7981]


def test_passage_metrics_and_total_latency_use_the_original_query() -> None:
    result = score_ranking(
        [{"path": "target", "line_start": 10}, {"path": "target", "line_start": 20}],
        {"path": "target", "acceptable_starts": [20], "corpus": "code"},
        7,
        0.2,
        0.5,
    )
    assert result["metrics"]["file_rr"] == 1
    assert result["metrics"]["passage_rr"] == 0.5
    assert result["seconds"] == 0.7
    assert result["query_id"] == 7


def test_baseline_gate_checks_corpora_even_when_overall_matches() -> None:
    with pytest.raises(ValueError, match="code.file_rr"):
        assert_baseline(
            {"all": {"file_rr": 0.9}, "code": {"file_rr": 0.8}},
            {"all": {"file_rr": 0.9}, "code": {"file_rr": 0.7}},
        )


def test_baseline_gate_accepts_rounding_only() -> None:
    assert_baseline({"all": {"file_rr": 0.979}}, {"all": {"file_rr": 0.97879}})


def test_probe_database_connection_refuses_writes(tmp_path: Path) -> None:
    database = tmp_path / "index.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE guard (value INTEGER)")
    with open_readonly(database) as store:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            store.conn.execute("INSERT INTO guard VALUES (1)")


def test_reranking_scores_each_candidate_and_keeps_private_text_out_of_report(
    tmp_path: Path,
) -> None:
    from unittest.mock import create_autospec

    from eval.benchmark_runtime import Server
    from eval.probe_rerank_fixed import measure_reranking

    server = create_autospec(Server, instance=True)
    server.rerank.return_value = [0.1, 0.9]
    result = measure_reranking(
        server,
        [
            {
                "query_id": 0,
                "seconds": 0.2,
                "ranked": [
                    {
                        "path": "wrong",
                        "heading": "bad",
                        "body": "noise",
                        "line_start": 1,
                    },
                    {
                        "path": "target",
                        "heading": "good",
                        "body": "answer",
                        "line_start": 20,
                    },
                ],
            }
        ],
        [
            {
                "query": "question",
                "path": "target",
                "corpus": "code",
                "acceptable_starts": [20],
            }
        ],
        8000,
        "test",
        tmp_path / "private.jsonl",
    )
    server.rerank.assert_called_once_with(
        "question", ["bad\nwrong\nnoise", "good\ntarget\nanswer"]
    )
    assert result["summary"]["code"]["passage_rr"] == 1
    assert "ranked" not in result["results"][0]
    assert result["results"][0]["seconds"] >= 0.2
    assert '"ranked"' in (tmp_path / "private.jsonl").read_text()


def test_summary_does_not_count_unlabelled_transcripts_as_passage_failures() -> None:
    from eval.probe_rerank_fixed import summarize

    result = summarize(
        [
            score_ranking(
                [{"path": "a", "line_start": 1}],
                {"path": "a", "acceptable_starts": [1], "corpus": "code"},
                0,
                0.1,
            ),
            score_ranking([], {"path": "b", "corpus": "transcripts"}, 1, 0.1),
        ]
    )
    assert result["summary"]["all"]["passage_hit5"] == 1
    assert result["counts"]["transcripts"]["passage_labels"] == 0
    assert "passage_rr" not in result["summary"]["transcripts"]
