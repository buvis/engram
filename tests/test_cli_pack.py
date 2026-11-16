import re
import subprocess
from pathlib import Path

import pytest
from _cli_helpers import _init_git_repo, _refuse
from engram.cli import main
from engram.harvest import registry_root
from engram.indexer import IndexReport
from engram.pack import PackReport
from engram.store import StoreModelMismatchError

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
                "index_root": index_root,
            },
        )
        return report

    return fake_build


def _fake_build_recording_ids_and_diffs(ids_seen, read_contents, toplevel):
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
        ids_seen.append(id_)
        read_contents.append(Path(diff_path).read_text())
        return _make_pack_report(toplevel / "docs/dev/tmp" / f"engram-pack-{id_}.md")

    return fake_build


def _stage_diff(toplevel, cycle_id="cyc1"):
    diff_path = toplevel / "docs" / "dev" / "tmp" / f"review-diff-{cycle_id}.diff"
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
    report = _make_pack_report(toplevel / "docs/dev/tmp/engram-pack-cyc1.md")
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

    root_tmp_dir = toplevel / "docs" / "dev" / "tmp"
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
        out_dir=Path("docs/dev/tmp"),
        index_root=None,
    ):
        read_contents.append(Path(diff_path).read_text())
        return _make_pack_report(toplevel / "docs/dev/tmp/engram-pack-cyc1.md")

    monkeypatch.setattr("engram.cli.build", fake_build)

    exit_code = main(["pack", "--cycle", "cyc1"])

    assert exit_code == 0
    assert read_contents == ["real staged diff\n"]


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
    report = _make_pack_report(toplevel / "docs/dev/tmp/engram-pack-cyc1.md")
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--cycle", "cyc1"])

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["out_dir"].resolve() == (toplevel / "docs/dev/tmp").resolve()


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

    # No docs/dev/tmp/review-diff-cyc1.diff is staged.
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.build", _refuse)

    exit_code = main(["pack", "--cycle", "cyc1"])

    captured = capsys.readouterr()
    expected_diff_path = toplevel / "docs" / "dev" / "tmp" / "review-diff-cyc1.diff"
    assert exit_code == 1
    assert str(expected_diff_path) in captured.err
    assert not (toplevel / "docs/dev/tmp/engram-pack-cyc1.md").exists()


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
    pack_path = toplevel / "docs" / "dev" / "tmp" / "engram-pack-cyc1.md"
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
        == (toplevel / "docs/dev/tmp/review-diff-cyc1.diff").resolve()
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


# --- pack: --cycle id is slugged, same rule as --diff's derived id ---


def test_pack_cycle_traversal_attempt_is_slugged_and_stays_under_repo_tmp_dir(
    monkeypatch,
    tmp_path,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)

    raw_cycle_id = "../../x"
    # Same filename-safe rule the --diff branch already applies to its
    # derived id (see test_pack_diff_keeps_raw_source_ref_while_slugging...
    # in tests/test_cli_pack_diff.py).
    slug = re.sub(r"[^A-Za-z0-9_-]", "-", raw_cycle_id)
    _stage_diff(toplevel, cycle_id=slug)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    ids_seen = []
    read_contents = []
    monkeypatch.setattr(
        "engram.cli.build",
        _fake_build_recording_ids_and_diffs(ids_seen, read_contents, toplevel),
    )

    exit_code = main(["pack", "--cycle", raw_cycle_id])

    assert exit_code == 0
    # The id handed to build (and therefore used to name the pack output)
    # is the slug, never the raw traversal string.
    assert ids_seen == [slug]
    # The diff actually read is the one staged under the sanitized name,
    # under docs/dev/tmp -- proving the read never escaped via "..".
    assert read_contents == ["diff --git a/foo b/foo\n+added line\n"]
    # Nothing escaped to a sibling of docs/dev/tmp.
    docs_dev_entries = {p.name for p in (toplevel / "docs" / "dev").iterdir()}
    assert docs_dev_entries == {"tmp"}


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
    report = _make_pack_report(toplevel / "docs/dev/tmp/engram-pack-cyc1.md")
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

    wip_dir = toplevel / "docs" / "dev" / "project-management" / "prds" / "wip"
    wip_dir.mkdir(parents=True)
    prd_file = wip_dir / "00042-example.md"
    prd_file.write_text("# Example PRD\n")

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    calls = []
    report = _make_pack_report(toplevel / "docs/dev/tmp/engram-pack-cyc1.md")
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

    wip_dir = toplevel / "docs" / "dev" / "project-management" / "prds" / "wip"
    wip_dir.mkdir(parents=True)
    (wip_dir / "00042-first.md").write_text("# First PRD\n")
    (wip_dir / "00043-second.md").write_text("# Second PRD\n")

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    calls = []
    report = _make_pack_report(toplevel / "docs/dev/tmp/engram-pack-cyc1.md")
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
    report = _make_pack_report(toplevel / "docs/dev/tmp/engram-pack-cyc1.md")
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))

    exit_code = main(["pack", "--cycle", "cyc1"])

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["capsule_path"] is None


def test_pack_capsule_omitted_defaults_to_project_management_meta_capsule_when_file_exists(
    monkeypatch,
    tmp_path,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    _register_repo(monkeypatch, tmp_path, toplevel)
    monkeypatch.chdir(toplevel)

    capsule_dir = toplevel / "docs" / "dev" / "project-management" / "meta"
    capsule_dir.mkdir(parents=True)
    capsule_file = capsule_dir / "project-capsule.md"
    capsule_file.write_text("# Capsule\n")
    _stage_diff(toplevel)

    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())

    calls = []
    report = _make_pack_report(toplevel / "docs/dev/tmp/engram-pack-cyc1.md")
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


# --- pack: linked worktree passes the registry root as index_root ---


_GIT = [
    "git",
    "-c",
    "user.name=engram-test",
    "-c",
    "user.email=engram-test@example.invalid",
    "-c",
    "commit.gpgsign=false",
]


def _git_stdout(cwd, *args):
    result = subprocess.run(
        [*_GIT, *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _main_checkout_with_linked_worktree(tmp_path, name):
    main_dir = tmp_path / "checkouts" / name
    main_dir.mkdir(parents=True)
    main_root = _init_git_repo(main_dir)
    _git_stdout(main_root, "commit", "-q", "--allow-empty", "-m", "init")
    # Not under the main checkout's path and named unlike the repo, so
    # neither a path-prefix match nor the directory name can stand in for
    # real worktree resolution.
    worktree_dir = tmp_path / "worktrees" / "wt-xyz"
    _git_stdout(main_root, "worktree", "add", "-q", str(worktree_dir))
    return main_root, Path(_git_stdout(worktree_dir, "rev-parse", "--show-toplevel"))


def _commit_range(root):
    base = _git_stdout(root, "rev-parse", "HEAD")
    (root / "added.txt").write_text("added line\n")
    _git_stdout(root, "add", "added.txt")
    _git_stdout(root, "commit", "-q", "-m", "add")
    return f"{base}..{_git_stdout(root, 'rev-parse', 'HEAD')}"


def _run_pack_capturing_build(monkeypatch, worktree_root, mode="cycle"):
    if mode == "cycle":
        _stage_diff(worktree_root)
        argv = ["pack", "--cycle", "cyc1"]
    else:
        argv = ["pack", "--diff", _commit_range(worktree_root)]
    monkeypatch.chdir(worktree_root)
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: object())
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: object())
    calls = []
    report = _make_pack_report(worktree_root / "docs/dev/tmp/engram-pack-cyc1.md")
    monkeypatch.setattr("engram.cli.build", _capturing_pack_build(calls, report))
    exit_code = main(argv)
    return exit_code, calls


def _registry_rows(decoy, repo_name, real_root):
    # Before the real row: an unrelated repo, a name ending in repo_name, a
    # proper suffix of repo_name, and a name starting with repo_name. After
    # it: a same-name duplicate (first match must win) and an unrelated row
    # (so the real row is not last).
    return (
        "/some/other/repo,other-repo\n"
        f"{decoy / 'x'},x-{repo_name}\n"
        f"{decoy / 'suffix'},{repo_name[1:]}\n"
        f"{decoy / 'fork'},{repo_name}-fork\n"
        f"{real_root},{repo_name}\n"
        f"{decoy / 'dup'},{repo_name}\n"
        "/yet/another/repo,zzz-last\n"
    )


@pytest.mark.parametrize("mode", ["cycle", "diff"])
@pytest.mark.parametrize("repo_name", ["repoA", "beta-tools"])
def test_cli_pack_succeeds_in_linked_worktree(monkeypatch, tmp_path, repo_name, mode):
    main_root, worktree_root = _main_checkout_with_linked_worktree(
        tmp_path,
        repo_name,
    )
    decoy = tmp_path / "decoy"
    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text(_registry_rows(decoy, repo_name, main_root))
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", repos_csv)

    exit_code, calls = _run_pack_capturing_build(monkeypatch, worktree_root, mode)

    assert exit_code == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["repo"] == repo_name
    assert call["repo_root"].resolve() == worktree_root.resolve()
    assert isinstance(call["index_root"], Path)
    assert call["index_root"].resolve() == main_root.resolve()
    assert call["index_root"].resolve() != worktree_root.resolve()
    assert not call["index_root"].resolve().is_relative_to(decoy.resolve())


def test_cli_pack_linked_worktree_index_root_is_registry_path_not_git_layout(
    monkeypatch,
    tmp_path,
):
    _, worktree_root = _main_checkout_with_linked_worktree(tmp_path, "beta-tools")
    # Registered at a directory that is NOT the git common-dir's parent, so
    # index_root must come from the registry row, not from git's own layout.
    registered_root = tmp_path / "registered" / "beta-tools"
    registered_root.mkdir(parents=True)
    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text(
        _registry_rows(tmp_path / "decoy", "beta-tools", registered_root),
    )
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", repos_csv)
    monkeypatch.setattr("engram.cli._resolve_repo_name", lambda: "beta-tools")

    exit_code, calls = _run_pack_capturing_build(monkeypatch, worktree_root)

    assert exit_code == 0
    assert len(calls) == 1
    assert isinstance(calls[0]["index_root"], Path)
    assert calls[0]["index_root"].resolve() == registered_root.resolve()


def test_cli_pack_linked_worktree_of_unregistered_checkout_passes_registry_lookup_result(
    monkeypatch,
    tmp_path,
):
    _, worktree_root = _main_checkout_with_linked_worktree(tmp_path, "ghost-repo")
    decoy = tmp_path / "decoy"
    repos_csv = tmp_path / "repos.csv"
    # The main checkout is absent; only loose-match decoys with other paths:
    # a name ending in it, a proper suffix of it, a name starting with it.
    repos_csv.write_text(
        "/some/other/repo,other-repo\n"
        f"{decoy / 'x'},x-ghost-repo\n"
        f"{decoy / 'suffix'},repo\n"
        f"{decoy / 'fork'},ghost-repo-fork\n",
    )
    monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", repos_csv)
    monkeypatch.setattr("engram.cli._resolve_repo_name", lambda: "ghost-repo")

    exit_code, calls = _run_pack_capturing_build(monkeypatch, worktree_root)

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["repo"] == "ghost-repo"
    assert calls[0]["repo_root"].resolve() == worktree_root.resolve()
    assert calls[0]["index_root"] == registry_root("ghost-repo", repos_csv)
    assert calls[0]["index_root"] is None
