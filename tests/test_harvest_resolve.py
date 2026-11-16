import subprocess
from pathlib import Path

import pytest
from _harvest_helpers import _init_git_repo, _write_repos_csv
from engram.harvest import _resolve_repo_for_path

# --- _resolve_repo_for_path: repo resolution from git toplevel + gita registry ---


def test_resolve_repo_for_path_returns_registered_name_for_git_toplevel(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    file_path = toplevel / "review.md"
    file_path.write_text("content")
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(toplevel, "my-repo")])

    result = _resolve_repo_for_path(file_path, repos_csv=repos_csv)

    assert result == "my-repo"


@pytest.mark.parametrize("csv_state", ["missing", "not_registered"])
def test_resolve_repo_for_path_returns_none_when_repo_not_registered(
    tmp_path,
    csv_state,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    file_path = toplevel / "review.md"
    file_path.write_text("content")
    repos_csv = tmp_path / "repos.csv"
    if csv_state == "not_registered":
        _write_repos_csv(repos_csv, [(tmp_path / "some-other-repo", "other-repo")])
    # else "missing": repos_csv is never created

    result = _resolve_repo_for_path(file_path, repos_csv=repos_csv)

    assert result is None


@pytest.mark.parametrize("under_claude_home", [True, False])
def test_resolve_repo_for_path_outside_git_returns_claude_home_sentinel_only_under_claude_home(
    tmp_path,
    monkeypatch,
    under_claude_home,
):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
    target_dir = (
        (fake_home / ".claude") if under_claude_home else (tmp_path / "elsewhere")
    )
    target_dir.mkdir(parents=True)
    file_path = target_dir / "review.md"
    file_path.write_text("content")
    repos_csv = tmp_path / "repos.csv"

    result = _resolve_repo_for_path(file_path, repos_csv=repos_csv)

    assert result == ("claude-home" if under_claude_home else None)


def test_resolve_repo_for_path_maps_claude_project_management_to_claude_home(
    tmp_path,
    monkeypatch,
):
    fake_home = tmp_path / "home"
    target = fake_home / ".claude" / "docs" / "dev" / "project-management"
    target.mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
    file_path = target / "reviews" / "00042-foo-review-1.md"
    file_path.parent.mkdir()
    file_path.write_text("content")
    repos_csv = tmp_path / "repos.csv"

    result = _resolve_repo_for_path(file_path, repos_csv=repos_csv)

    assert result == "claude-home"


def _make_symlinked_repo_layout(tmp_path):
    (tmp_path / "repo").mkdir()
    toplevel = _init_git_repo(tmp_path / "repo")
    sibling = tmp_path / "repo-sibling"
    sibling.mkdir()
    same_name_decoy = tmp_path / "decoy" / "repo"
    same_name_decoy.mkdir(parents=True)
    link = tmp_path / "links" / "repo"
    link.parent.mkdir()
    link.symlink_to(toplevel, target_is_directory=True)
    sibling_link = tmp_path / "links" / "repo-sibling"
    sibling_link.symlink_to(sibling, target_is_directory=True)
    file_path = toplevel / "docs" / "reviews" / "review.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("content")
    near_misses_before = [
        (same_name_decoy, "decoy-repo"),
        (sibling_link, "sibling-repo"),
        (file_path.parent, "subdir-repo"),
    ]
    near_misses_after = [(link.parent, "links-repo")]
    wrong_path_rows = [
        *near_misses_before,
        (sibling_link, "linked-repo"),
        (same_name_decoy, "real-repo"),
        *near_misses_after,
    ]
    return (
        toplevel,
        link,
        file_path,
        near_misses_before,
        near_misses_after,
        wrong_path_rows,
    )


@pytest.mark.parametrize(
    "symlinked_side,registered,expected",
    [
        ("registry", "target", "linked-repo"),
        ("toplevel", "target", "real-repo"),
        ("registry", "near_miss", None),
        ("registry", "name_on_wrong_path", None),
        ("registry", "empty", None),
    ],
)
def test_resolve_repo_for_path_matches_symlinked_registry_path(
    tmp_path,
    monkeypatch,
    symlinked_side,
    registered,
    expected,
):
    toplevel, link, file_path, before, after, wrong_path_rows = (
        _make_symlinked_repo_layout(tmp_path)
    )
    target = link if symlinked_side == "registry" else toplevel
    rows = {
        "target": [*before, (target, expected), *after],
        "near_miss": [*before, *after],
        "name_on_wrong_path": wrong_path_rows,
        "empty": [],
    }[registered]
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    repos_csv = registry_dir / "repos.csv"
    _write_repos_csv(repos_csv, rows)
    _write_repos_csv(
        tmp_path / "repos.csv",
        [(toplevel, "decoy-csv-repo"), (link, "decoy-csv-repo")],
    )
    git_cwds = []
    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        git_cwds.append(Path(kwargs["cwd"]).resolve())
        if symlinked_side == "toplevel" and "--show-toplevel" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=f"{link}\n", stderr="")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("engram.harvest.subprocess.run", fake_run)

    result = _resolve_repo_for_path(file_path, repos_csv=repos_csv)

    assert result == expected
    if expected is not None:
        assert file_path.parent.resolve() in git_cwds


@pytest.mark.parametrize(
    "suffix,registered_name,expected",
    [
        ("/", "slash-repo", "slash-repo"),
        ("//", "double-slash-repo", "double-slash-repo"),
        ("-other/", "near-miss-repo", None),
        ("-other/", "slash-repo", None),
    ],
)
def test_resolve_repo_for_path_matches_trailing_slash_registry_path(
    tmp_path,
    suffix,
    registered_name,
    expected,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    file_path = toplevel / "docs" / "reviews" / "review.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("content")
    same_name_decoy = tmp_path / "decoy" / "repo"
    same_name_decoy.mkdir(parents=True)
    rows = [
        (f"{same_name_decoy}/", "decoy-repo"),
        (f"{file_path.parent}/", "subdir-repo"),
        (f"{toplevel.parent}/", "parent-repo"),
        (f"{toplevel}{suffix}", registered_name),
        (f"{toplevel}-sibling/", "sibling-repo"),
    ]
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    repos_csv = registry_dir / "repos.csv"
    _write_repos_csv(repos_csv, rows)
    _write_repos_csv(tmp_path / "repos.csv", [(toplevel, "decoy-csv-repo")])

    result = _resolve_repo_for_path(file_path, repos_csv=repos_csv)

    assert result == expected
