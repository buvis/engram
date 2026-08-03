from pathlib import Path

import pytest

from engram.cli import _resolve_repo_name, main
from engram.findings import FINDINGS_CORPUS
from engram.harvest import FileHarvestResult, HarvestReport
from engram.query import Pointer

from _cli_helpers import _init_git_repo, _refuse


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
    monkeypatch,
    capsys,
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
        "broken.md\tparse_failed\t0\tmissing Tests: line",
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


# --- _resolve_repo_name: consolidated repo resolution (claude-home sentinel) ---


def test_resolve_repo_name_from_inside_claude_home_returns_claude_home_sentinel(
    tmp_path,
    monkeypatch,
):
    fake_home = tmp_path / "home"
    claude_dir = fake_home / ".claude"
    claude_dir.mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", tmp_path / "repos.csv")
    monkeypatch.chdir(claude_dir)

    result = _resolve_repo_name()

    assert result == "claude-home"


def test_resolve_repo_name_from_inside_registered_git_repo_returns_registered_name(
    tmp_path,
    monkeypatch,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text(f"{toplevel},repoA\n")
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", repos_csv)
    monkeypatch.chdir(toplevel)

    result = _resolve_repo_name()

    assert result == "repoA"


def test_resolve_repo_name_from_inside_unregistered_git_repo_returns_none(
    tmp_path,
    monkeypatch,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text(f"{tmp_path / 'some-other-repo'},other-repo\n")
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", repos_csv)
    monkeypatch.chdir(toplevel)

    result = _resolve_repo_name()

    assert result is None
