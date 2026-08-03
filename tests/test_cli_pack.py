import subprocess
from pathlib import Path

import pytest

from engram.cli import main
from engram.indexer import IndexReport
from engram.pack import PackReport
from engram.store import StoreModelMismatchError

from _cli_helpers import _init_git_repo, _refuse, _stub_symbols_count_skipped


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
            chunks_updated=0,
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
        out_dir=Path("dev/local/tmp"),
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


def _stage_diff(toplevel, cycle_id="cyc1"):
    diff_path = toplevel / "dev" / "local" / "tmp" / f"review-diff-{cycle_id}.diff"
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text("diff --git a/foo b/foo\n+added line\n")
    return diff_path


# --- pack: --cycle/--diff mutual exclusivity ---


def test_pack_rejects_both_cycle_and_diff_flags(monkeypatch):
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.build", _refuse)

    with pytest.raises(SystemExit) as exc_info:
        main(["pack", "--cycle", "cyc1", "--diff", "abc123..def456"])

    assert exc_info.value.code == 2


def test_pack_rejects_neither_cycle_nor_diff_flag(monkeypatch):
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.build", _refuse)

    with pytest.raises(SystemExit) as exc_info:
        main(["pack"])

    assert exc_info.value.code == 2


# --- pack: repo_root resolution ---


def test_pack_resolves_repo_root_to_git_toplevel_when_run_from_a_subdirectory(
    monkeypatch,
    tmp_path,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    _stage_diff(toplevel)

    subdir = toplevel / "sub"
    subdir.mkdir()
    monkeypatch.chdir(subdir)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    calls = []
    report = _make_pack_report(toplevel / "dev/local/tmp/engram-pack-cyc1.md")
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--cycle", "cyc1"])

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["repo_root"].resolve() == toplevel.resolve()


def test_pack_fails_loud_when_cwd_is_not_a_git_worktree_despite_a_resolved_scope(
    monkeypatch,
    tmp_path,
    capsys,
):
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    monkeypatch.chdir(not_a_repo)

    monkeypatch.setattr("engram.cli._resolve_repo_name", lambda: "claude-home")
    monkeypatch.setattr("engram.cli.load_config", _refuse)
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.build", _refuse)

    exit_code = main(["pack", "--cycle", "cyc1"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err != ""


# --- pack: diff_path/out_dir anchored to repo_root, not invocation cwd ---


def test_pack_cycle_reads_staged_diff_from_repo_root_when_invoked_from_a_subdirectory(
    monkeypatch,
    tmp_path,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)

    subdir = toplevel / "sub"
    subdir.mkdir()

    root_tmp_dir = toplevel / "dev" / "local" / "tmp"
    root_tmp_dir.mkdir(parents=True)
    staged_diff = root_tmp_dir / "review-diff-cyc1.diff"
    staged_diff.write_text("real staged diff\n")

    monkeypatch.chdir(subdir)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    read_contents = []

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
        out_dir=Path("dev/local/tmp"),
    ):
        read_contents.append(Path(diff_path).read_text())
        return _make_pack_report(toplevel / "dev/local/tmp/engram-pack-cyc1.md")

    monkeypatch.setattr("engram.cli.build", fake_build)

    exit_code = main(["pack", "--cycle", "cyc1"])

    assert exit_code == 0
    assert read_contents == ["real staged diff\n"]


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
        toplevel / "dev/local/tmp/engram-pack-abc123--def456.md",
    )
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--diff", "abc123..def456"])

    assert exit_code == 0
    assert len(diff_calls) == 1
    assert len(calls) == 1
    written_at_repo_root = (
        toplevel / "dev/local/tmp/engram-pack-diff-abc123--def456.diff"
    )
    assert written_at_repo_root.read_text() == fake_stdout
    assert not (subdir / "dev/local/tmp/engram-pack-diff-abc123--def456.diff").exists()


def test_pack_out_dir_default_anchors_to_repo_root_when_invoked_from_a_subdirectory(
    monkeypatch,
    tmp_path,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    _stage_diff(toplevel)

    subdir = toplevel / "sub"
    subdir.mkdir()
    monkeypatch.chdir(subdir)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    calls = []
    report = _make_pack_report(toplevel / "dev/local/tmp/engram-pack-cyc1.md")
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--cycle", "cyc1"])

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["out_dir"].resolve() == (toplevel / "dev/local/tmp").resolve()


# --- pack: --cycle missing staged diff file fails loud before reindex ---


def test_pack_cycle_missing_staged_diff_fails_loud_before_reindex(
    monkeypatch,
    tmp_path,
    capsys,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)

    # No dev/local/tmp/review-diff-cyc1.diff is staged.
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.build", _refuse)

    exit_code = main(["pack", "--cycle", "cyc1"])

    captured = capsys.readouterr()
    expected_diff_path = toplevel / "dev" / "local" / "tmp" / "review-diff-cyc1.diff"
    assert exit_code == 1
    assert str(expected_diff_path) in captured.err
    assert not (toplevel / "dev/local/tmp/engram-pack-cyc1.md").exists()


# --- pack: --cycle derives diff_path/id_/source_ref and prints summary ---


def test_pack_cycle_success_passes_expected_build_args_and_prints_summary_to_stdout(
    monkeypatch,
    tmp_path,
    capsys,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)
    _stage_diff(toplevel)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    explicit_prd = tmp_path / "custom-prd.md"
    explicit_prd.write_text("# PRD\n")
    explicit_capsule = tmp_path / "custom-capsule.md"
    explicit_capsule.write_text("# Capsule\n")

    calls = []
    pack_path = toplevel / "dev" / "local" / "tmp" / "engram-pack-cyc1.md"
    report = _make_pack_report(
        pack_path,
        total_tokens=4242,
        files_scanned=314159,
        chunks_added=271828,
    )
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(
        [
            "pack",
            "--cycle",
            "cyc1",
            "--prd",
            str(explicit_prd),
            "--capsule",
            str(explicit_capsule),
        ],
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["id_"] == "cyc1"
    assert (
        call["diff_path"].resolve()
        == (toplevel / "dev/local/tmp/review-diff-cyc1.diff").resolve()
    )
    assert call["source_ref"] is None
    assert call["prd_path"].resolve() == explicit_prd.resolve()
    assert call["capsule_path"].resolve() == explicit_capsule.resolve()
    assert str(pack_path) in captured.out
    # Distinctive multi-digit values: they cannot collide with digits that
    # show up in the tmp_path-derived pack path (e.g. ".../test_pack..._0")
    # or with each other, so a printout that shows only the path and token
    # total (and never the reindex stats) cannot satisfy these by accident.
    assert "4242" in captured.out
    assert "314159" in captured.out
    assert "271828" in captured.out


# --- pack: --diff materializes git diff and derives slug/source_ref ---


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
        toplevel / "dev/local/tmp/engram-pack-abc123--def456.md",
    )
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--diff", "abc123..def456"])

    assert exit_code == 0
    assert len(diff_calls) == 1
    assert len(calls) == 1
    call = calls[0]
    assert call["id_"] == "abc123--def456"
    assert call["source_ref"] == "def456"
    assert (
        call["diff_path"].resolve()
        == (toplevel / "dev/local/tmp/engram-pack-diff-abc123--def456.diff").resolve()
    )
    written = (
        toplevel / "dev/local/tmp/engram-pack-diff-abc123--def456.diff"
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
        toplevel / "dev/local/tmp/engram-pack-feature-foo--bugfix-bar.md",
    )
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--diff", "feature/foo..bugfix/bar"])

    assert exit_code == 0
    assert len(diff_calls) == 1
    assert len(calls) == 1
    call = calls[0]
    assert call["id_"] == "feature-foo--bugfix-bar"
    assert call["source_ref"] == "bugfix/bar"


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


# --- pack: --prd default resolution ---


def test_pack_prd_omitted_defaults_to_none_when_wip_dir_has_zero_prds(
    monkeypatch,
    tmp_path,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)
    _stage_diff(toplevel)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    calls = []
    report = _make_pack_report(toplevel / "dev/local/tmp/engram-pack-cyc1.md")
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--cycle", "cyc1"])

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["prd_path"] is None


def test_pack_prd_omitted_defaults_to_single_wip_prd_when_exactly_one_exists(
    monkeypatch,
    tmp_path,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)
    _stage_diff(toplevel)

    wip_dir = toplevel / "dev" / "local" / "prds" / "wip"
    wip_dir.mkdir(parents=True)
    prd_file = wip_dir / "00042-example.md"
    prd_file.write_text("# Example PRD\n")

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    calls = []
    report = _make_pack_report(toplevel / "dev/local/tmp/engram-pack-cyc1.md")
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--cycle", "cyc1"])

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["prd_path"].resolve() == prd_file.resolve()


def test_pack_prd_omitted_defaults_to_none_when_wip_dir_has_two_prds(
    monkeypatch,
    tmp_path,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)
    _stage_diff(toplevel)

    wip_dir = toplevel / "dev" / "local" / "prds" / "wip"
    wip_dir.mkdir(parents=True)
    (wip_dir / "00042-first.md").write_text("# First PRD\n")
    (wip_dir / "00043-second.md").write_text("# Second PRD\n")

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    calls = []
    report = _make_pack_report(toplevel / "dev/local/tmp/engram-pack-cyc1.md")
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--cycle", "cyc1"])

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["prd_path"] is None


# --- pack: --capsule default resolution ---


def test_pack_capsule_omitted_defaults_to_none_when_capsule_file_missing(
    monkeypatch,
    tmp_path,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)
    _stage_diff(toplevel)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    calls = []
    report = _make_pack_report(toplevel / "dev/local/tmp/engram-pack-cyc1.md")
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--cycle", "cyc1"])

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["capsule_path"] is None


def test_pack_capsule_omitted_defaults_to_repo_root_capsule_when_file_exists(
    monkeypatch,
    tmp_path,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)

    capsule_dir = toplevel / "dev" / "local"
    capsule_dir.mkdir(parents=True)
    capsule_file = capsule_dir / "project-capsule.md"
    capsule_file.write_text("# Capsule\n")
    _stage_diff(toplevel)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    calls = []
    report = _make_pack_report(toplevel / "dev/local/tmp/engram-pack-cyc1.md")
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--cycle", "cyc1"])

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["capsule_path"].resolve() == capsule_file.resolve()


# --- pack: repo scope resolution failure ---


def test_pack_repo_scope_unresolved_returns_1_and_does_not_call_build(
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
    monkeypatch.setattr("engram.cli.build", _refuse)

    exit_code = main(["pack", "--cycle", "cyc1"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err != ""


def test_pack_unregistered_repo_error_omits_scope_flag_and_names_repos_csv_path(
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
    monkeypatch.setattr("engram.cli.build", _refuse)

    exit_code = main(["pack", "--cycle", "cyc1"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "--scope" not in captured.err
    assert str(repos_csv) in captured.err


# --- pack: StoreModelMismatchError handling ---


def test_pack_store_model_mismatch_returns_nonzero_and_mentions_rebuild(
    monkeypatch,
    tmp_path,
    capsys,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)
    _stage_diff(toplevel)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    def fake_build(*args, **kwargs):
        raise StoreModelMismatchError("embedding model mismatch")

    monkeypatch.setattr("engram.cli.build", fake_build)

    exit_code = main(["pack", "--cycle", "cyc1"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "--rebuild" in captured.err
