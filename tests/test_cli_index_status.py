import pytest
from _cli_helpers import _refuse

from engram import corpora, transcripts
from engram.cli import main
from engram.indexer import IndexReport
from engram.store import CorpusStatus, StatusReport, StoreModelMismatchError


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


def test_status_repos_csv_producer_prints_its_raised_message_verbatim(
    monkeypatch,
    capsys,
):
    # Renamed from ..._file_not_found_error_..._message (originally used a
    # "custom-cellar-marker" literal). enumerate_corpora is the repos.csv
    # producer, not the cellar-path producer, so it cannot exercise the
    # cellar case; this now names and asserts only what it actually covers:
    # that _run_status prints whatever message the repos.csv producer
    # raises, verbatim. See
    # test_status_missing_cellar_path_from_transcripts_producer_fails_loud
    # for the real cellar-path case.
    report = StatusReport(
        per_corpus={
            "docs": CorpusStatus(row_count=42, stale_files=[], dead_rows=0),
        },
    )

    def fake_enumerate_corpora(*args, **kwargs):
        raise FileNotFoundError("custom-repos-csv-marker not found")

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
    assert "custom-repos-csv-marker" in captured.err


# --- status must consult the transcripts producer for the cellar path ---


def test_status_missing_cellar_path_from_transcripts_producer_fails_loud(
    monkeypatch,
    capsys,
):
    # PRD 00002 Test Strategy: "cellar path missing -> loud status failure,
    # not a silent empty corpus". transcripts.enumerate() is the producer
    # that raises FileNotFoundError when the cellar path is absent (see
    # src/engram/transcripts.py). _run_status must consult it and fail loud
    # when it does. This must fail against the current code: _run_status
    # never calls transcripts.enumerate() today, so the stub never fires
    # and status exits 0.
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

    def fake_transcripts_enumerate(*args, **kwargs):
        raise FileNotFoundError("distinctive-cellar-path-missing-marker not found")

    monkeypatch.setattr(transcripts, "enumerate", fake_transcripts_enumerate)

    exit_code = main(["status", "--scope", "portfolio"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "distinctive-cellar-path-missing-marker" in captured.err


def test_status_exits_zero_when_transcripts_producer_is_healthy(
    monkeypatch,
    capsys,
):
    # Guards against an over-eager fix: a healthy transcripts producer must
    # not force status to fail loud. The fix for the case above cannot
    # simply be "always fail" - it must actually check the producer.
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
    monkeypatch.setattr(transcripts, "enumerate", lambda *a, **k: iter([]))

    exit_code = main(["status", "--scope", "portfolio"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""


def test_index_and_status_agree_a_missing_cellar_path_fails_loud_in_both(
    monkeypatch,
    capsys,
):
    # indexer.index() already enumerates transcripts.enumerate() alongside
    # enumerate_corpora and symbols.enumerate(), so `engram index` already
    # fails loud on a missing cellar path. `engram status` must reach the
    # same producer so the two commands agree on which corpora exist,
    # instead of index failing while status silently reports nothing.
    marker = "distinctive-agreement-cellar-marker not found"

    def fake_index(*args, **kwargs):
        raise FileNotFoundError(marker)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.index", fake_index)

    index_exit_code = main(["index", "--scope", "portfolio"])
    index_err = capsys.readouterr().err

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

    def fake_transcripts_enumerate(*args, **kwargs):
        raise FileNotFoundError(marker)

    monkeypatch.setattr(transcripts, "enumerate", fake_transcripts_enumerate)

    status_exit_code = main(["status", "--scope", "portfolio"])
    status_err = capsys.readouterr().err

    assert index_exit_code != 0
    assert marker in index_err
    assert status_exit_code != 0
    assert marker in status_err


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


def test_query_repo_scope_unregistered_repo_error_still_recommends_scope_portfolio(
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
    assert "--scope portfolio" in captured.err
