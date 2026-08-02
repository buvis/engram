from pathlib import Path

import pytest
from engram.harvest import FileHarvestResult, HarvestReport

from engram import corpora
from engram.cli import main
from engram.findings import FINDINGS_CORPUS
from engram.indexer import IndexReport
from engram.query import Pointer
from engram.store import CorpusStatus, StatusReport, StoreModelMismatchError


def _refuse(*args, **kwargs):
    raise AssertionError("should not be called")


@pytest.fixture(autouse=True)
def _stub_symbols_count_skipped(monkeypatch):
    # _run_status now prints a "code\tskipped=N" line driven by
    # symbols.count_skipped(); default it to 0 (no line printed) so existing
    # tests (written before this producer existed) are unaffected.
    monkeypatch.setattr(
        "engram.cli.symbols.count_skipped",
        lambda *a, **k: 0,
        raising=False,
    )


class _FakeStoreForStatus:
    def __init__(self, report):
        self._report = report

    def status(self, scope):
        return self._report


class _RecordingConn:
    def __init__(self, events):
        self._events = events

    def close(self):
        self._events.append("close")


class _FakeRebuildStore:
    def __init__(self, events):
        self.conn = _RecordingConn(events)


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

    exit_code = main(["query", "--scope", "portfolio", "-k", k, "some text"])

    captured = capsys.readouterr()
    assert exit_code != 0
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


# --- findings corpus hits print body line after summary line ---


def test_findings_hit_prints_body_line_after_summary_line(monkeypatch, capsys):
    pointer = Pointer(
        rank=1,
        score=0.987,
        path="findings/finding-1.md",
        line_start=1,
        line_end=5,
        heading="Finding Heading",
        corpus=FINDINGS_CORPUS,
        repo="repoA",
        body="stored finding record text",
    )
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.query", lambda *a, **k: [pointer])

    exit_code = main(["query", "--scope", "portfolio", "some text"])

    captured = capsys.readouterr()
    expected_summary = (
        f"{pointer.rank}\t{pointer.score:.4f}\t"
        f"{pointer.path}:{pointer.line_start}-{pointer.line_end}\t{pointer.heading}"
    )
    assert captured.out.splitlines() == [expected_summary, pointer.body]
    assert exit_code == 0


def test_non_findings_hit_prints_only_summary_line(monkeypatch, capsys):
    pointer = Pointer(
        rank=1,
        score=0.5,
        path="docs.md",
        line_start=1,
        line_end=3,
        heading="Docs Heading",
        corpus="docs",
        repo="repoA",
    )
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.query", lambda *a, **k: [pointer])

    exit_code = main(["query", "--scope", "portfolio", "some text"])

    captured = capsys.readouterr()
    expected_summary = (
        f"{pointer.rank}\t{pointer.score:.4f}\t"
        f"{pointer.path}:{pointer.line_start}-{pointer.line_end}\t{pointer.heading}"
    )
    assert captured.out.splitlines() == [expected_summary]
    assert exit_code == 0


def test_mixed_results_interleave_body_lines_only_for_findings_hits(
    monkeypatch, capsys
):
    findings_pointer = Pointer(
        rank=1,
        score=0.9,
        path="findings/finding-2.md",
        line_start=1,
        line_end=2,
        heading="Finding Two",
        corpus=FINDINGS_CORPUS,
        repo="repoA",
        body="second stored finding text",
    )
    docs_pointer = Pointer(
        rank=2,
        score=0.4,
        path="other.md",
        line_start=1,
        line_end=3,
        heading="Section Two",
        corpus="docs",
        repo="repoB",
    )
    pointers = [findings_pointer, docs_pointer]
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.query", lambda *a, **k: pointers)

    exit_code = main(["query", "--scope", "portfolio", "some text"])

    captured = capsys.readouterr()
    findings_summary = (
        f"{findings_pointer.rank}\t{findings_pointer.score:.4f}\t"
        f"{findings_pointer.path}:{findings_pointer.line_start}-{findings_pointer.line_end}"
        f"\t{findings_pointer.heading}"
    )
    docs_summary = (
        f"{docs_pointer.rank}\t{docs_pointer.score:.4f}\t"
        f"{docs_pointer.path}:{docs_pointer.line_start}-{docs_pointer.line_end}"
        f"\t{docs_pointer.heading}"
    )
    assert captured.out.splitlines() == [
        findings_summary,
        findings_pointer.body,
        docs_summary,
    ]
    assert exit_code == 0


# --- status output format ---


def test_status_scope_portfolio_prints_tab_separated_corpus_lines(monkeypatch, capsys):
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(
                row_count=42,
                stale_files=["a.md", "b.md"],
                dead_rows=3,
            ),
            "adr": CorpusStatus(row_count=7, stale_files=[], dead_rows=0),
        },
    )
    monkeypatch.setattr(corpora, "missing_dirs", [])
    monkeypatch.setattr(
        "engram.cli.enumerate_corpora",
        lambda *a, **k: iter([]),
        raising=False,
    )
    monkeypatch.setattr(
        "engram.cli.open_store",
        lambda *a, **k: _FakeStoreForStatus(report),
    )

    exit_code = main(["status", "--scope", "portfolio"])

    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "docs\t42\tstale=2\tdead=3",
        "adr\t7\tstale=0\tdead=0",
    ]
    # this report has stale files and dead rows, so status must fail loud
    assert exit_code != 0


# --- status surfaces symbols.count_skipped() ---


def test_status_prints_skipped_line_when_symbols_have_skipped_files(
    monkeypatch,
    capsys,
):
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(row_count=42, stale_files=[], dead_rows=0),
        },
    )
    monkeypatch.setattr(corpora, "missing_dirs", [])
    monkeypatch.setattr(
        "engram.cli.enumerate_corpora",
        lambda *a, **k: iter([]),
        raising=False,
    )
    monkeypatch.setattr(
        "engram.cli.open_store",
        lambda *a, **k: _FakeStoreForStatus(report),
    )
    monkeypatch.setattr(
        "engram.cli.symbols.count_skipped",
        lambda *a, **k: 3,
        raising=False,
    )

    exit_code = main(["status", "--scope", "portfolio"])

    captured = capsys.readouterr()
    assert any("skipped=3" in line for line in captured.out.splitlines())
    assert exit_code == 0


def test_status_prints_no_skipped_line_when_no_files_were_skipped(monkeypatch, capsys):
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(row_count=42, stale_files=[], dead_rows=0),
        },
    )
    monkeypatch.setattr(corpora, "missing_dirs", [])
    monkeypatch.setattr(
        "engram.cli.enumerate_corpora",
        lambda *a, **k: iter([]),
        raising=False,
    )
    monkeypatch.setattr(
        "engram.cli.open_store",
        lambda *a, **k: _FakeStoreForStatus(report),
    )

    exit_code = main(["status", "--scope", "portfolio"])

    captured = capsys.readouterr()
    assert "skipped=" not in captured.out
    assert exit_code == 0


# --- status fails loud on staleness ---


def test_status_exits_nonzero_when_a_corpus_has_stale_files(monkeypatch):
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(row_count=42, stale_files=["a.md"], dead_rows=0),
        },
    )
    monkeypatch.setattr(corpora, "missing_dirs", [])
    monkeypatch.setattr(
        "engram.cli.enumerate_corpora",
        lambda *a, **k: iter([]),
        raising=False,
    )
    monkeypatch.setattr(
        "engram.cli.open_store",
        lambda *a, **k: _FakeStoreForStatus(report),
    )

    exit_code = main(["status", "--scope", "portfolio"])

    assert exit_code != 0


def test_status_exits_nonzero_when_a_corpus_has_dead_rows(monkeypatch):
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(row_count=42, stale_files=[], dead_rows=1),
        },
    )
    monkeypatch.setattr(corpora, "missing_dirs", [])
    monkeypatch.setattr(
        "engram.cli.enumerate_corpora",
        lambda *a, **k: iter([]),
        raising=False,
    )
    monkeypatch.setattr(
        "engram.cli.open_store",
        lambda *a, **k: _FakeStoreForStatus(report),
    )

    exit_code = main(["status", "--scope", "portfolio"])

    assert exit_code != 0


def test_status_exits_zero_when_no_corpus_has_staleness_or_dead_rows(monkeypatch):
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(row_count=42, stale_files=[], dead_rows=0),
            "adr": CorpusStatus(row_count=7, stale_files=[], dead_rows=0),
        },
    )
    monkeypatch.setattr(corpora, "missing_dirs", [])
    monkeypatch.setattr(
        "engram.cli.enumerate_corpora",
        lambda *a, **k: iter([]),
        raising=False,
    )
    monkeypatch.setattr(
        "engram.cli.open_store",
        lambda *a, **k: _FakeStoreForStatus(report),
    )

    exit_code = main(["status", "--scope", "portfolio"])

    assert exit_code == 0


# --- status surfaces missing corpus dirs ---


def test_status_reports_missing_corpus_dirs_without_forcing_nonzero_exit(
    monkeypatch,
    capsys,
):
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(row_count=42, stale_files=[], dead_rows=0),
        },
    )
    monkeypatch.setattr(corpora, "missing_dirs", [])

    def fake_enumerate_corpora(*args, **kwargs):
        corpora.missing_dirs[:] = ["decision:repoA", "discovery:repoA"]
        return iter([])

    monkeypatch.setattr(
        "engram.cli.enumerate_corpora",
        fake_enumerate_corpora,
        raising=False,
    )
    monkeypatch.setattr(
        "engram.cli.open_store",
        lambda *a, **k: _FakeStoreForStatus(report),
    )

    exit_code = main(["status", "--scope", "portfolio"])

    captured = capsys.readouterr()
    assert "decision:repoA" in captured.out
    assert "discovery:repoA" in captured.out
    # missing dirs alone (no staleness/dead rows) must not force a nonzero exit
    assert exit_code == 0


# --- status fails loud on a missing repos.csv ---


def test_status_fails_loud_when_repos_csv_missing(monkeypatch, capsys):
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(row_count=42, stale_files=[], dead_rows=0),
        },
    )

    def fake_enumerate_corpora(*args, **kwargs):
        raise FileNotFoundError("repos.csv not found")

    monkeypatch.setattr(
        "engram.cli.enumerate_corpora",
        fake_enumerate_corpora,
        raising=False,
    )
    monkeypatch.setattr(
        "engram.cli.open_store",
        lambda *a, **k: _FakeStoreForStatus(report),
    )

    exit_code = main(["status", "--scope", "portfolio"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "repos.csv" in captured.err


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


def test_index_corpus_scopes_missing_dir_warnings_to_that_corpus(monkeypatch, capsys):
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr(
        "engram.cli.index",
        lambda *a, **k: IndexReport(
            files_scanned=1,
            chunks_added=1,
            chunks_updated=0,
            chunks_pruned=0,
            corpora_missing=["prd:repoB", "decision:repoB", "discovery:repoB"],
        ),
    )

    exit_code = main(["index", "--scope", "portfolio", "--corpus", "prd"])

    captured = capsys.readouterr()
    assert "prd:repoB" in captured.out
    assert "decision:repoB" not in captured.out
    assert "discovery:repoB" not in captured.out
    assert exit_code == 0


# --- index fails loud on a missing repos.csv ---


def test_index_fails_loud_when_repos_csv_missing(monkeypatch, capsys):
    def fake_index(*args, **kwargs):
        raise FileNotFoundError("repos.csv not found")

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.index", fake_index)

    exit_code = main(["index", "--scope", "portfolio"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "repos.csv" in captured.err


# --- index/status print the raised FileNotFoundError's own message ---


def test_index_file_not_found_error_prints_the_producer_supplied_message(
    monkeypatch,
    capsys,
):
    def fake_index(*args, **kwargs):
        raise FileNotFoundError("custom-cellar-marker not found")

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.index", fake_index)

    exit_code = main(["index", "--scope", "portfolio"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "custom-cellar-marker" in captured.err


def test_status_file_not_found_error_prints_the_producer_supplied_message(
    monkeypatch,
    capsys,
):
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(row_count=42, stale_files=[], dead_rows=0),
        },
    )

    def fake_enumerate_corpora(*args, **kwargs):
        raise FileNotFoundError("custom-cellar-marker not found")

    monkeypatch.setattr(
        "engram.cli.enumerate_corpora",
        fake_enumerate_corpora,
        raising=False,
    )
    monkeypatch.setattr(
        "engram.cli.open_store",
        lambda *a, **k: _FakeStoreForStatus(report),
    )

    exit_code = main(["status", "--scope", "portfolio"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "custom-cellar-marker" in captured.err


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


def test_query_store_model_mismatch_returns_nonzero_and_mentions_rebuild(
    monkeypatch,
    capsys,
):
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


def test_index_rebuild_swaps_live_db_only_after_successful_build(monkeypatch, tmp_path):
    fake_db_path = tmp_path / "engram.db"
    replace_calls = []

    def fake_replace(src, dst):
        replace_calls.append((str(src), str(dst)))

    monkeypatch.setattr("engram.cli.DEFAULT_DB_PATH", fake_db_path)
    monkeypatch.setattr("engram.cli.os.replace", fake_replace)
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: _FakeRebuildStore([]))
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

    assert replace_calls == [(str(fake_db_path) + ".rebuild-tmp", str(fake_db_path))]
    assert exit_code == 0


def test_index_rebuild_closes_temp_store_connection_before_os_replace(
    monkeypatch,
    tmp_path,
):
    events = []

    def fake_replace(src, dst):
        events.append("replace")

    monkeypatch.setattr("engram.cli.DEFAULT_DB_PATH", tmp_path / "engram.db")
    monkeypatch.setattr("engram.cli.os.replace", fake_replace)
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr(
        "engram.cli.open_store",
        lambda *a, **k: _FakeRebuildStore(events),
    )
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

    assert events == ["close", "replace"]
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
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: _FakeRebuildStore([]))
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


# --- default scope (no --scope flag) distinguishes missing repos.csv from unregistered repo ---


def test_index_default_scope_fails_loud_with_repos_csv_message_when_registry_missing(
    monkeypatch,
    tmp_path,
    capsys,
):
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", tmp_path / "nonexistent-repos.csv")
    monkeypatch.setattr("engram.cli.load_config", _refuse)
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.index", _refuse)

    exit_code = main(["index"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "not found" in captured.err
    assert "repos.csv" in captured.err
    assert "not inside a registered repo" not in captured.err


def test_status_default_scope_fails_loud_with_repos_csv_message_when_registry_missing(
    monkeypatch,
    tmp_path,
    capsys,
):
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", tmp_path / "nonexistent-repos.csv")
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.enumerate_corpora", _refuse, raising=False)

    exit_code = main(["status"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "not found" in captured.err
    assert "repos.csv" in captured.err
    assert "not inside a registered repo" not in captured.err


def test_index_default_scope_reports_not_in_registered_repo_when_repos_csv_present_but_repo_unregistered(
    monkeypatch,
    tmp_path,
    capsys,
):
    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text("/some/other/repo,other-repo\n")
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", repos_csv)
    monkeypatch.setattr("engram.cli._resolve_repo_name", lambda: None)
    monkeypatch.setattr("engram.cli.load_config", _refuse)
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.index", _refuse)

    exit_code = main(["index"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "not inside a registered repo" in captured.err
    assert "not found" not in captured.err


def test_status_default_scope_reports_not_in_registered_repo_when_repos_csv_present_but_repo_unregistered(
    monkeypatch,
    tmp_path,
    capsys,
):
    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text("/some/other/repo,other-repo\n")
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", repos_csv)
    monkeypatch.setattr("engram.cli._resolve_repo_name", lambda: None)
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.enumerate_corpora", _refuse, raising=False)

    exit_code = main(["status"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "not inside a registered repo" in captured.err
    assert "not found" not in captured.err


# --- query --scope repo distinguishes missing repos.csv from unregistered repo ---


def test_query_repo_scope_fails_loud_with_repos_csv_message_when_registry_missing(
    monkeypatch,
    tmp_path,
    capsys,
):
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", tmp_path / "nonexistent-repos.csv")
    monkeypatch.setattr("engram.cli.load_config", _refuse)
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.query", _refuse)

    exit_code = main(["query", "--scope", "repo", "some text"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "not found" in captured.err
    assert "repos.csv" in captured.err
    assert "not inside a registered repo" not in captured.err


def test_query_repo_scope_reports_not_in_registered_repo_when_repos_csv_present_but_repo_unregistered(
    monkeypatch,
    tmp_path,
    capsys,
):
    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text("/some/other/repo,other-repo\n")
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", repos_csv)
    monkeypatch.setattr("engram.cli._resolve_repo_name", lambda: None)
    monkeypatch.setattr("engram.cli.load_config", _refuse)
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.query", _refuse)

    exit_code = main(["query", "--scope", "repo", "some text"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "not inside a registered repo" in captured.err
    assert "not found" not in captured.err


# --- harvest: CLI dispatch and output ---


def test_harvest_dispatches_through_main_and_calls_harvest_entry_point_with_paths(
    monkeypatch,
):
    calls = []
    sentinel_config = object()
    sentinel_store = object()

    def fake_harvest(store, config, paths):
        calls.append((store, config, paths))
        return HarvestReport(results=[])

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: sentinel_config)
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: sentinel_store)
    monkeypatch.setattr("engram.cli.harvest", fake_harvest)

    exit_code = main(["harvest", "a.md", "b.md"])

    assert len(calls) == 1
    store_arg, config_arg, paths_arg = calls[0]
    assert store_arg is sentinel_store
    assert config_arg is sentinel_config
    assert paths_arg == [Path("a.md"), Path("b.md")]
    assert exit_code == 0


def test_harvest_prints_tab_separated_line_per_result(monkeypatch, capsys):
    results = [
        FileHarvestResult(path=Path("a.md"), outcome="upserted", records_count=3),
        FileHarvestResult(path=Path("b.md"), outcome="no_repo", records_count=0),
    ]
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr(
        "engram.cli.harvest",
        lambda *a, **k: HarvestReport(results=results),
    )

    exit_code = main(["harvest", "a.md", "b.md"])

    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "a.md\tupserted\t3",
        "b.md\tno_repo\t0",
    ]
    assert exit_code != 0


def test_harvest_appends_error_suffix_when_result_has_error(monkeypatch, capsys):
    results = [
        FileHarvestResult(
            path=Path("broken.md"),
            outcome="parse_failed",
            records_count=0,
            error="missing Tests: line",
        ),
    ]
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr(
        "engram.cli.harvest",
        lambda *a, **k: HarvestReport(results=results),
    )

    exit_code = main(["harvest", "broken.md"])

    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "broken.md\tparse_failed\t0\tmissing Tests: line"
    ]
    assert exit_code != 0


@pytest.mark.parametrize(
    "outcome,expected_exit_code",
    [("upserted", 0), ("parse_failed", 1)],
)
def test_harvest_exit_code_reflects_report_any_failed(
    monkeypatch,
    outcome,
    expected_exit_code,
):
    results = [FileHarvestResult(path=Path("a.md"), outcome=outcome, records_count=0)]
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr(
        "engram.cli.harvest",
        lambda *a, **k: HarvestReport(results=results),
    )

    exit_code = main(["harvest", "a.md"])

    assert exit_code == expected_exit_code


def test_harvest_without_any_path_argument_exits_with_usage_error(monkeypatch):
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.harvest", _refuse)

    with pytest.raises(SystemExit) as exc_info:
        main(["harvest"])

    assert exc_info.value.code == 2
