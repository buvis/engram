import pytest

from engram import corpora
from engram.cli import main
from engram.indexer import IndexReport
from engram.query import Pointer
from engram.store import CorpusStatus, DEFAULT_DB_PATH, StatusReport, StoreModelMismatchError


def _refuse(*args, **kwargs):
    raise AssertionError("should not be called")


class _FakeStoreForStatus:
    def __init__(self, report):
        self._report = report

    def status(self, scope):
        return self._report


# --- query requires --scope ---


def test_query_without_scope_exits_nonzero_before_opening_store(monkeypatch):
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.query", _refuse)

    with pytest.raises(SystemExit) as exc_info:
        main(["query", "some text"])

    assert exc_info.value.code != 0


# --- query rejects non-positive -k ---


@pytest.mark.parametrize("k", ["-3", "0"])
def test_query_rejects_non_positive_k(monkeypatch, capsys, k):
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.query", _refuse)

    with pytest.raises(SystemExit) as exc_info:
        main(["query", "--scope", "portfolio", "-k", k, "some text"])

    captured = capsys.readouterr()
    assert exc_info.value.code != 0
    assert captured.err != ""


# --- query output format ---


def test_query_scope_portfolio_prints_tab_separated_pointer_lines(monkeypatch, capsys):
    pointers = [
        Pointer(
            rank=1,
            score=0.987,
            path="notes/file.md",
            line_start=10,
            line_end=14,
            heading="Section One",
            corpus="docs",
            repo="repoA",
        ),
        Pointer(
            rank=2,
            score=0.5,
            path="other.md",
            line_start=1,
            line_end=3,
            heading="Section Two",
            corpus="docs",
            repo="repoB",
        ),
    ]
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.query", lambda *a, **k: pointers)

    exit_code = main(["query", "--scope", "portfolio", "some text"])

    captured = capsys.readouterr()
    expected = [
        f"{p.rank}\t{p.score:.4f}\t{p.path}:{p.line_start}-{p.line_end}\t{p.heading}"
        for p in pointers
    ]
    assert captured.out.splitlines() == expected
    assert exit_code == 0


def test_query_prints_pointer_score_at_fixed_precision(monkeypatch, capsys):
    pointers = [
        Pointer(
            rank=1,
            score=0.5,
            path="notes/file.md",
            line_start=10,
            line_end=14,
            heading="Section One",
            corpus="docs",
            repo="repoA",
        ),
    ]
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.query", lambda *a, **k: pointers)

    exit_code = main(["query", "--scope", "portfolio", "some text"])

    captured = capsys.readouterr()
    assert captured.out.splitlines() == ["1\t0.5000\tnotes/file.md:10-14\tSection One"]
    assert exit_code == 0


# --- status output format ---


def test_status_scope_portfolio_prints_tab_separated_corpus_lines(monkeypatch, capsys):
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(row_count=42, stale_files=["a.md", "b.md"], dead_rows=3),
            "adr": CorpusStatus(row_count=7, stale_files=[], dead_rows=0),
        }
    )
    monkeypatch.setattr(corpora, "missing_dirs", [])
    monkeypatch.setattr("engram.cli.enumerate_corpora", lambda *a, **k: iter([]), raising=False)
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: _FakeStoreForStatus(report))

    exit_code = main(["status", "--scope", "portfolio"])

    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "docs\t42\tstale=2\tdead=3",
        "adr\t7\tstale=0\tdead=0",
    ]
    # this report has stale files and dead rows, so status must fail loud
    assert exit_code != 0


# --- status fails loud on staleness ---


def test_status_exits_nonzero_when_a_corpus_has_stale_files(monkeypatch):
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(row_count=42, stale_files=["a.md"], dead_rows=0),
        }
    )
    monkeypatch.setattr(corpora, "missing_dirs", [])
    monkeypatch.setattr("engram.cli.enumerate_corpora", lambda *a, **k: iter([]), raising=False)
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: _FakeStoreForStatus(report))

    exit_code = main(["status", "--scope", "portfolio"])

    assert exit_code != 0


def test_status_exits_nonzero_when_a_corpus_has_dead_rows(monkeypatch):
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(row_count=42, stale_files=[], dead_rows=1),
        }
    )
    monkeypatch.setattr(corpora, "missing_dirs", [])
    monkeypatch.setattr("engram.cli.enumerate_corpora", lambda *a, **k: iter([]), raising=False)
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: _FakeStoreForStatus(report))

    exit_code = main(["status", "--scope", "portfolio"])

    assert exit_code != 0


def test_status_exits_zero_when_no_corpus_has_staleness_or_dead_rows(monkeypatch):
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(row_count=42, stale_files=[], dead_rows=0),
            "adr": CorpusStatus(row_count=7, stale_files=[], dead_rows=0),
        }
    )
    monkeypatch.setattr(corpora, "missing_dirs", [])
    monkeypatch.setattr("engram.cli.enumerate_corpora", lambda *a, **k: iter([]), raising=False)
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: _FakeStoreForStatus(report))

    exit_code = main(["status", "--scope", "portfolio"])

    assert exit_code == 0


# --- status surfaces missing corpus dirs ---


def test_status_reports_missing_corpus_dirs_without_forcing_nonzero_exit(monkeypatch, capsys):
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(row_count=42, stale_files=[], dead_rows=0),
        }
    )
    monkeypatch.setattr(corpora, "missing_dirs", [])

    def fake_enumerate_corpora(*args, **kwargs):
        corpora.missing_dirs[:] = ["decision:repoA", "discovery:repoA"]
        return iter([])

    monkeypatch.setattr("engram.cli.enumerate_corpora", fake_enumerate_corpora, raising=False)
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: _FakeStoreForStatus(report))

    exit_code = main(["status", "--scope", "portfolio"])

    captured = capsys.readouterr()
    assert "decision:repoA" in captured.out
    assert "discovery:repoA" in captured.out
    # missing dirs alone (no staleness/dead rows) must not force a nonzero exit
    assert exit_code == 0


# --- index --scope + --corpus combine legally without --rebuild ---


def test_index_scope_and_corpus_without_rebuild_is_accepted(monkeypatch):
    calls = []

    def fake_index(store, config, scope, corpus=None):
        calls.append((scope, corpus))
        return IndexReport(
            files_scanned=0,
            chunks_added=0,
            chunks_updated=0,
            chunks_pruned=0,
            corpora_missing=[],
        )

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.index", fake_index)

    exit_code = main(["index", "--scope", "portfolio", "--corpus", "prd"])

    assert exit_code == 0
    assert len(calls) == 1
    scope, corpus = calls[0]
    assert scope.kind == "portfolio"
    assert corpus == "prd"


# --- index surfaces IndexReport.corpora_missing ---


def test_index_prints_missing_corpora_from_report(monkeypatch, capsys):
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr(
        "engram.cli.index",
        lambda *a, **k: IndexReport(
            files_scanned=1,
            chunks_added=1,
            chunks_updated=0,
            chunks_pruned=0,
            corpora_missing=["prd:repoB"],
        ),
    )

    exit_code = main(["index", "--scope", "portfolio"])

    captured = capsys.readouterr()
    assert "prd:repoB" in captured.out
    assert exit_code == 0


# --- index --rebuild is mutually exclusive with --scope and --corpus ---


def test_index_rebuild_with_scope_is_rejected(monkeypatch):
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.index", _refuse)

    with pytest.raises(SystemExit) as exc_info:
        main(["index", "--scope", "portfolio", "--rebuild"])

    assert exc_info.value.code == 2


def test_index_rebuild_with_corpus_is_rejected(monkeypatch):
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.index", _refuse)

    with pytest.raises(SystemExit) as exc_info:
        main(["index", "--corpus", "prd", "--rebuild"])

    assert exc_info.value.code == 2


# --- StoreModelMismatchError fails loud with --rebuild guidance ---


def test_query_store_model_mismatch_returns_nonzero_and_mentions_rebuild(monkeypatch, capsys):
    def fake_query(*args, **kwargs):
        raise StoreModelMismatchError("embedding model mismatch")

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.query", fake_query)

    exit_code = main(["query", "--scope", "portfolio", "some text"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "--rebuild" in captured.err


# --- index --rebuild atomicity ---


def test_index_rebuild_swaps_live_db_only_after_successful_build(monkeypatch):
    replace_calls = []

    def fake_replace(src, dst):
        replace_calls.append((str(src), str(dst)))

    monkeypatch.setattr("engram.cli.os.replace", fake_replace)
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr(
        "engram.cli.index",
        lambda *a, **k: IndexReport(
            files_scanned=1,
            chunks_added=1,
            chunks_updated=0,
            chunks_pruned=0,
            corpora_missing=[],
        ),
    )

    exit_code = main(["index", "--rebuild"])

    assert replace_calls == [(str(DEFAULT_DB_PATH) + ".rebuild-tmp", str(DEFAULT_DB_PATH))]
    assert exit_code == 0


def test_index_rebuild_failure_leaves_live_db_untouched(monkeypatch):
    replace_calls = []

    def fake_replace(src, dst):
        replace_calls.append((str(src), str(dst)))

    def fake_index(*args, **kwargs):
        raise RuntimeError("embedding failed")

    monkeypatch.setattr("engram.cli.os.replace", fake_replace)
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.index", fake_index)

    exit_code = main(["index", "--rebuild"])

    assert replace_calls == []
    assert exit_code != 0


def test_index_rebuild_removes_leftover_tmp_db_before_building(monkeypatch, tmp_path):
    fake_db_path = tmp_path / "engram.db"
    leftover_tmp = tmp_path / "engram.db.rebuild-tmp"
    leftover_tmp.write_text("stale leftover data")

    monkeypatch.setattr("engram.cli.DEFAULT_DB_PATH", fake_db_path)
    monkeypatch.setattr("engram.cli.os.replace", lambda src, dst: None)
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr(
        "engram.cli.index",
        lambda *a, **k: IndexReport(
            files_scanned=1,
            chunks_added=1,
            chunks_updated=0,
            chunks_pruned=0,
            corpora_missing=[],
        ),
    )

    exit_code = main(["index", "--rebuild"])

    assert not leftover_tmp.exists()
    assert exit_code == 0
