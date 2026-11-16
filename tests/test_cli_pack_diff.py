import hashlib
import re
import subprocess
from pathlib import Path

import pytest
from _cli_helpers import _init_git_repo, _refuse
from engram.cli import main
from engram.indexer import IndexReport
from engram.pack import PackReport

# --- pack: shared test helpers ---


def _register_repo(monkeypatch, tmp_path, toplevel, repo_name="repoA"):
    repos_csv = tmp_path / f"pack-repos-{repo_name}.csv"
    repos_csv.write_text(f"{toplevel},{repo_name}\n")
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", repos_csv)
    monkeypatch.setattr("engram.cli._resolve_repo_name", lambda: repo_name)


def _make_pack_report(path, total_tokens=100, files_scanned=1, chunks_added=2):
    return PackReport(
        path=path,
        sections=[],
        total_estimated_tokens=total_tokens,
        trimmed_sections=[],
        symbols_omitted=0,
        index_report=IndexReport(
            files_scanned=files_scanned,
            chunks_added=chunks_added,
            chunks_pruned=0,
            corpora_missing=[],
        ),
    )


def _capturing_pack_build(calls, report):
    def fake_build(
        store,
        config,
        repo,
        repo_root,
        id_,
        diff_path,
        source_ref=None,
        prd_path=None,
        capsule_path=None,
        out_dir=Path("docs/dev/tmp"),
        index_root=None,
    ):
        calls.append(
            {
                "repo": repo,
                "repo_root": repo_root,
                "id_": id_,
                "diff_path": diff_path,
                "source_ref": source_ref,
                "prd_path": prd_path,
                "capsule_path": capsule_path,
                "out_dir": out_dir,
            },
        )
        return report

    return fake_build


def _make_fake_git_diff_run(stdout, returncode=0):
    calls = []
    real_run = subprocess.run

    def fake_run(*args, **kwargs):
        argv = args[0] if args else kwargs.get("args", [])
        flat = argv if isinstance(argv, str) else " ".join(str(a) for a in argv)
        if "diff" in flat:
            calls.append(argv)
            return subprocess.CompletedProcess(
                args=argv,
                returncode=returncode,
                stdout=stdout,
                stderr="",
            )
        return real_run(*args, **kwargs)

    return calls, fake_run


# --- pack: --diff materializes git diff and derives slug/source_ref ---


def test_pack_diff_materializes_diff_under_repo_root_when_invoked_from_a_subdirectory(
    monkeypatch,
    tmp_path,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)

    subdir = toplevel / "sub"
    subdir.mkdir()
    monkeypatch.chdir(subdir)

    fake_stdout = "diff --git a/foo b/foo\n+added line\n"
    diff_calls, fake_run = _make_fake_git_diff_run(fake_stdout, returncode=0)
    monkeypatch.setattr("engram.cli.subprocess.run", fake_run)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    calls = []
    report = _make_pack_report(
        toplevel / "docs/dev/tmp/engram-pack-abc123--def456-14ec8cc4.md",
    )
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--diff", "abc123..def456"])

    assert exit_code == 0
    assert len(diff_calls) == 1
    assert len(calls) == 1
    written_at_repo_root = (
        toplevel / "docs/dev/tmp/engram-pack-diff-abc123--def456-14ec8cc4.diff"
    )
    assert written_at_repo_root.read_text() == fake_stdout
    assert not (
        subdir / "docs/dev/tmp/engram-pack-diff-abc123--def456-14ec8cc4.diff"
    ).exists()


def test_pack_diff_materializes_git_diff_and_slugs_id_per_given_example(
    monkeypatch,
    tmp_path,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)

    fake_stdout = "diff --git a/foo b/foo\n+added line\n"
    diff_calls, fake_run = _make_fake_git_diff_run(fake_stdout, returncode=0)
    monkeypatch.setattr("engram.cli.subprocess.run", fake_run)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    calls = []
    report = _make_pack_report(
        toplevel / "docs/dev/tmp/engram-pack-abc123--def456-14ec8cc4.md",
    )
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--diff", "abc123..def456"])

    assert exit_code == 0
    assert len(diff_calls) == 1
    assert len(calls) == 1
    call = calls[0]
    assert call["id_"] == "abc123--def456-14ec8cc4"
    assert call["source_ref"] == "def456"
    assert (
        call["diff_path"].resolve()
        == (
            toplevel / "docs/dev/tmp/engram-pack-diff-abc123--def456-14ec8cc4.diff"
        ).resolve()
    )
    written = (
        toplevel / "docs/dev/tmp/engram-pack-diff-abc123--def456-14ec8cc4.diff"
    ).read_text()
    assert written == fake_stdout


def test_pack_diff_keeps_raw_source_ref_while_slugging_special_characters_in_id(
    monkeypatch,
    tmp_path,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)

    fake_stdout = "unified diff content for slug test\n"
    diff_calls, fake_run = _make_fake_git_diff_run(fake_stdout, returncode=0)
    monkeypatch.setattr("engram.cli.subprocess.run", fake_run)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    calls = []
    report = _make_pack_report(
        toplevel / "docs/dev/tmp/engram-pack-feature-foo--bugfix-bar-77cd121a.md",
    )
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--diff", "feature/foo..bugfix/bar"])

    assert exit_code == 0
    assert len(diff_calls) == 1
    assert len(calls) == 1
    call = calls[0]
    assert call["id_"] == "feature-foo--bugfix-bar-77cd121a"
    assert call["source_ref"] == "bugfix/bar"


_LONG_RANGE_PREFIX = "release/2026-11-candidate-build..feature/very-long-branch"


@pytest.mark.parametrize(
    ("first_range", "second_range"),
    [
        ("a/b..c", "a-b..c"),
        (f"{_LONG_RANGE_PREFIX}/tail", f"{_LONG_RANGE_PREFIX}-tail"),
        ("main...feature/x", "main...feature-x"),
        ("a~1..c", "a/1..c"),
        ("HEAD^..main", "HEAD/..main"),
        ("a:b..c", "a/b..c"),
        ("a@b..c", "a/b..c"),
    ],
    ids=[
        "slash-vs-dash",
        "long-differs-at-end",
        "three-dot",
        "tilde",
        "caret",
        "colon",
        "at-sign",
    ],
)
def test_pack_diff_ids_differ_for_ranges_that_sanitize_alike(
    monkeypatch,
    tmp_path,
    first_range,
    second_range,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    calls = []
    report = _make_pack_report(toplevel / "docs/dev/tmp/engram-pack-x.md")
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    slug = re.sub(r"[^A-Za-z0-9_-]", "-", first_range)
    assert slug == re.sub(r"[^A-Za-z0-9_-]", "-", second_range)
    tmp_dir = toplevel / "docs/dev/tmp"
    for range_str in (first_range, second_range):
        _, fake_run = _make_fake_git_diff_run(f"diff for {range_str}\n")
        monkeypatch.setattr("engram.cli.subprocess.run", fake_run)
        assert main(["pack", "--diff", range_str]) == 0

    assert len(calls) == 2
    for call, range_str in zip(calls, (first_range, second_range), strict=True):
        expected_id = f"{slug}-{hashlib.sha1(range_str.encode()).hexdigest()[:8]}"
        assert call["id_"] == expected_id
        # Each run keeps its own scratch diff; neither overwrote the other.
        diff_file = tmp_dir / f"engram-pack-diff-{expected_id}.diff"
        assert call["diff_path"].resolve() == diff_file.resolve()
        assert diff_file.read_text() == f"diff for {range_str}\n"
    assert calls[0]["id_"] != calls[1]["id_"]
    assert not (tmp_dir / f"engram-pack-diff-{slug}.diff").exists()


# --- pack: --diff failures never call build ---


def test_pack_diff_nonzero_git_exit_returns_1_and_does_not_call_build(
    monkeypatch,
    tmp_path,
    capsys,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)

    _, fake_run = _make_fake_git_diff_run("", returncode=128)
    monkeypatch.setattr("engram.cli.subprocess.run", fake_run)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.build", _refuse)

    exit_code = main(["pack", "--diff", "abc123..def456"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err != ""


def test_pack_diff_empty_git_output_returns_1_and_does_not_call_build(
    monkeypatch,
    tmp_path,
    capsys,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)

    _, fake_run = _make_fake_git_diff_run("", returncode=0)
    monkeypatch.setattr("engram.cli.subprocess.run", fake_run)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.build", _refuse)

    exit_code = main(["pack", "--diff", "abc123..def456"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err != ""


def test_pack_diff_range_starting_with_dash_is_rejected_before_reaching_git(
    monkeypatch,
    tmp_path,
    capsys,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)

    diff_calls, fake_run = _make_fake_git_diff_run(
        "diff --git a/foo b/foo\n+added line\n",
        returncode=0,
    )
    monkeypatch.setattr("engram.cli.subprocess.run", fake_run)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.build", _refuse)

    malicious_range = "--output=/tmp/pwned..HEAD"
    exit_code = main(["pack", f"--diff={malicious_range}"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err != ""
    assert malicious_range in captured.err
    # git must never have been invoked with the rejected value.
    assert diff_calls == []


def test_pack_diff_range_head_starting_with_dash_is_rejected_before_reaching_git(
    monkeypatch,
    tmp_path,
    capsys,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)

    diff_calls, fake_run = _make_fake_git_diff_run(
        "diff --git a/foo b/foo\n+added line\n",
        returncode=0,
    )
    monkeypatch.setattr("engram.cli.subprocess.run", fake_run)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.build", _refuse)

    malicious_head = "--output=/tmp/pwned"
    exit_code = main(["pack", f"--diff=HEAD..{malicious_head}"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err != ""
    assert malicious_head in captured.err
    # git must never have been invoked with the rejected value.
    assert diff_calls == []
