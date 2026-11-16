import pytest

from engram import corpora, transcripts
from engram.cli import main
from engram.store import CorpusStatus, StatusReport


@pytest.fixture(autouse=True)
def _stub_symbols_count_skipped(monkeypatch):
    monkeypatch.setattr("engram.cli.symbols.count_excluded", lambda: 0)
    # _run_status now prints a "code\tskipped=N" line driven by
    # symbols.count_skipped(); default it to 0 (no line printed) so existing
    # tests (written before this producer existed) are unaffected.
    monkeypatch.setattr(
        "engram.cli.symbols.count_skipped",
        lambda *a, **k: 0,
        raising=False,
    )
    # Status consults the Cellar transcript producer; never read the
    # developer's real Cellar checkout. Cellar-failure tests override this.
    monkeypatch.setattr(transcripts, "enumerate", lambda *a, **k: iter([]))
    monkeypatch.setattr(corpora, "repo_memory_dirs", [])
    monkeypatch.setattr(corpora, "legacy_shadowed", [])


class _FakeStoreForStatus:
    def __init__(self, report):
        self._report = report

    def status(self, scope):
        return self._report


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


# --- default scope (no --scope flag) distinguishes missing repos.csv from unregistered repo ---


def test_status_default_scope_fails_loud_with_repos_csv_message_when_registry_missing(
    monkeypatch,
    tmp_path,
    capsys,
):
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", tmp_path / "nonexistent-repos.csv")

    def _refuse(*args, **kwargs):
        raise AssertionError("should not be called")

    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.enumerate_corpora", _refuse, raising=False)

    exit_code = main(["status"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "not found" in captured.err
    assert "repos.csv" in captured.err
    assert "not inside a registered repo" not in captured.err


def test_status_default_scope_reports_not_in_registered_repo_when_repos_csv_present_but_repo_unregistered(
    monkeypatch,
    tmp_path,
    capsys,
):
    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text("/some/other/repo,other-repo\n")
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", repos_csv)
    monkeypatch.setattr("engram.cli._resolve_repo_name", lambda: None)

    def _refuse(*args, **kwargs):
        raise AssertionError("should not be called")

    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.enumerate_corpora", _refuse, raising=False)

    exit_code = main(["status"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "not inside a registered repo" in captured.err
    assert "not found" not in captured.err
