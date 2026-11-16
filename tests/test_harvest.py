import inspect
import os
import subprocess
from pathlib import Path

import pytest
from _cli_helpers import _init_git_repo, _write_repos_csv
from engram import corpora, findings
from engram.cli import main as cli_main
from engram.client import (
    EmbeddingEntry,
    EmbeddingServerError,
    EngramConfig,
    Vector,
)
from engram.findings import FINDINGS_CORPUS
from engram.harvest import (
    FileHarvestResult,
    HarvestReport,
    _resolve_repo_for_path,
    harvest,
)
from engram.store import open_store


def _config(tmp_path, model_id="m1"):
    return EngramConfig(
        embeddings=[EmbeddingEntry(id=model_id, endpoint="http://127.0.0.1:8081")],
        pinned_id=model_id,
        config_path=tmp_path / "config.toml",
    )


def _make_embed(dim=4, value=0.5):
    def _embed(texts, entry):
        return [Vector([value] * dim, entry.id, dim) for _ in texts]

    return _embed


def _write_review_file(
    path,
    *,
    reviewers="Reviewer One",
    verdict="APPROVE",
    body_marker="finding body text",
):
    path.write_text(
        "---\n"
        f"reviewers:\n  - {reviewers}\n"
        "---\n\n"
        f"Verdict: {verdict}\n\n"
        "Tests: pass\n\n"
        "## Finding One\n"
        f"{body_marker}\n",
    )


def _write_broken_review_file(
    path,
    *,
    reviewers="Reviewer One",
    verdict="APPROVE",
    body_marker="broken body text",
):
    # missing the required "Tests:" line -> findings.parse() must raise ValueError
    path.write_text(
        "---\n"
        f"reviewers:\n  - {reviewers}\n"
        "---\n\n"
        f"Verdict: {verdict}\n\n"
        "## Finding One\n"
        f"{body_marker}\n",
    )


# --- harvest: idempotent re-harvest and amended-file replace ---


def test_harvest_reharvesting_unchanged_file_twice_yields_one_record_set_no_duplicates(
    tmp_path,
    monkeypatch,
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    review_path = toplevel / "review.md"
    _write_review_file(review_path, body_marker="unchanged-marker-token")
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(toplevel, "repoA")])
    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", repos_csv)
    expected_records = findings.parse(review_path)

    first_report = harvest(store, config, [review_path])
    second_report = harvest(store, config, [review_path])

    assert first_report.results[0].outcome == "upserted"
    assert second_report.results[0].outcome == "upserted"
    assert second_report.results[0].records_count == len(expected_records)
    chunks = store.chunks_for_corpus(FINDINGS_CORPUS)
    assert len(chunks) == len(expected_records)


def test_harvest_of_amended_file_replaces_prior_records(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    review_path = toplevel / "review.md"
    _write_review_file(review_path, body_marker="original-marker-token")
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(toplevel, "repoA")])
    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", repos_csv)
    harvest(store, config, [review_path])

    _write_review_file(review_path, body_marker="amended-marker-token")
    expected_records = findings.parse(review_path)
    report = harvest(store, config, [review_path])

    assert report.results[0].outcome == "upserted"
    chunks = store.chunks_for_corpus(FINDINGS_CORPUS)
    assert len(chunks) == len(expected_records)
    assert all("original-marker-token" not in c.body for c in chunks)
    assert any("amended-marker-token" in c.body for c in chunks)


# --- harvest: parse and upsert failures are loss-proof ---


def test_harvest_parse_failure_leaves_existing_records_untouched(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    review_path = toplevel / "review.md"
    _write_review_file(review_path, body_marker="stable-marker-token")
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(toplevel, "repoA")])
    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", repos_csv)
    harvest(store, config, [review_path])
    prior_chunks = store.chunks_for_corpus(FINDINGS_CORPUS)

    _write_broken_review_file(review_path, body_marker="broken-marker-token")
    report = harvest(store, config, [review_path])

    result = report.results[0]
    assert result.outcome == "parse_failed"
    assert result.records_count == 0
    assert result.error is not None
    assert store.chunks_for_corpus(FINDINGS_CORPUS) == prior_chunks


def test_harvest_embed_failure_leaves_existing_records_untouched(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    review_path = toplevel / "review.md"
    _write_review_file(review_path, body_marker="prior-marker-token")
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(toplevel, "repoA")])
    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", repos_csv)
    harvest(store, config, [review_path])
    prior_chunks = store.chunks_for_corpus(FINDINGS_CORPUS)

    def failing_embed(texts, entry):
        raise EmbeddingServerError("embedding server unreachable")

    monkeypatch.setattr("engram.findings.embed", failing_embed)
    _write_review_file(review_path, body_marker="new-marker-token")
    report = harvest(store, config, [review_path])

    result = report.results[0]
    assert result.outcome == "upsert_failed"
    assert result.records_count == 0
    assert result.error is not None
    assert store.chunks_for_corpus(FINDINGS_CORPUS) == prior_chunks


def test_harvest_embed_programming_error_propagates_instead_of_being_swallowed(
    tmp_path,
    monkeypatch,
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    review_path = toplevel / "review.md"
    _write_review_file(review_path, body_marker="prior-marker-token")
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(toplevel, "repoA")])
    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", repos_csv)
    harvest(store, config, [review_path])

    def broken_embed(texts, entry):
        raise TypeError("programming error")

    monkeypatch.setattr("engram.findings.embed", broken_embed)
    _write_review_file(review_path, body_marker="new-marker-token")

    with pytest.raises(TypeError):
        harvest(store, config, [review_path])


# --- harvest: repo resolution outcomes (no_repo, claude-home) ---


@pytest.mark.parametrize("scenario", ["outside_git_repo", "unregistered_repo"])
def test_harvest_no_repo_outcome_without_crash(tmp_path, monkeypatch, scenario):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
    repos_csv = tmp_path / "repos.csv"

    if scenario == "outside_git_repo":
        review_path = tmp_path / "outside" / "review.md"
        review_path.parent.mkdir()
        _write_review_file(review_path)
    else:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        toplevel = _init_git_repo(repo_dir)
        review_path = toplevel / "review.md"
        _write_review_file(review_path)
        _write_repos_csv(repos_csv, [(tmp_path / "some-other-repo", "other-repo")])
    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", repos_csv)

    report = harvest(store, config, [review_path])

    result = report.results[0]
    assert result.outcome == "no_repo"
    assert result.records_count == 0
    assert store.chunks_for_corpus(FINDINGS_CORPUS) == []


def test_harvest_claude_home_path_upserts_under_claude_home_repo_name(
    tmp_path,
    monkeypatch,
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    fake_home = tmp_path / "home"
    claude_dir = fake_home / ".claude"
    claude_dir.mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
    review_path = claude_dir / "review.md"
    _write_review_file(review_path, body_marker="claude-home-marker-token")
    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", tmp_path / "repos.csv")
    expected_records = findings.parse(review_path)

    report = harvest(store, config, [review_path])

    assert report.results[0].outcome == "upserted"
    chunks = store.chunks_for_corpus(FINDINGS_CORPUS)
    assert len(chunks) == len(expected_records)
    assert {c.repo for c in chunks} == {"claude-home"}


# --- harvest: dedup identity and repo rename ---


def test_harvest_dedups_relative_absolute_and_symlink_spellings_to_one_record_set(
    tmp_path,
    monkeypatch,
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    review_path = toplevel / "review.md"
    _write_review_file(review_path, body_marker="dedup-marker-token")
    symlink_path = toplevel / "review-link.md"
    symlink_path.symlink_to(review_path)
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(toplevel, "repoA")])
    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", repos_csv)
    relative_path = Path(os.path.relpath(review_path, Path.cwd()))
    expected_records = findings.parse(review_path)

    report_relative = harvest(store, config, [relative_path])
    report_absolute = harvest(store, config, [review_path])
    report_symlink = harvest(store, config, [symlink_path])

    for report in (report_relative, report_absolute, report_symlink):
        assert report.results[0].outcome == "upserted"
    chunks = store.chunks_for_corpus(FINDINGS_CORPUS)
    assert len(chunks) == len(expected_records)
    assert any(c.body == "dedup-marker-token" for c in chunks)


def test_harvest_repo_rename_between_harvests_yields_one_set_under_new_name(
    tmp_path,
    monkeypatch,
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    review_path = toplevel / "review.md"
    _write_review_file(review_path, body_marker="rename-marker-token")
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(toplevel, "old-repo-name")])
    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", repos_csv)
    expected_records = findings.parse(review_path)
    harvest(store, config, [review_path])

    _write_repos_csv(repos_csv, [(toplevel, "new-repo-name")])
    report = harvest(store, config, [review_path])

    assert report.results[0].outcome == "upserted"
    chunks = store.chunks_for_corpus(FINDINGS_CORPUS)
    assert len(chunks) == len(expected_records)
    assert {c.repo for c in chunks} == {"new-repo-name"}


# --- harvest: empty input and batch isolation ---


def test_harvest_with_empty_paths_returns_empty_report_with_any_failed_false(tmp_path):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)

    report = harvest(store, config, [])

    assert report.results == []
    assert report.any_failed is False


@pytest.mark.parametrize("resolve_error", [OSError, RuntimeError])
def test_harvest_batch_isolates_failures_so_one_bad_path_does_not_abort_the_rest(
    tmp_path,
    monkeypatch,
    resolve_error,
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    good_path = toplevel / "good.md"
    _write_review_file(good_path, body_marker="good-marker-token")
    broken_path = toplevel / "broken.md"
    _write_broken_review_file(broken_path, body_marker="broken-marker-token")
    unresolvable_path = toplevel / "unresolvable.md"
    unresolvable_path.write_text("irrelevant content")
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(toplevel, "repoA")])
    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", repos_csv)

    original_resolve = Path.resolve

    def flaky_resolve(self, *args, **kwargs):
        if self == unresolvable_path:
            raise resolve_error("simulated symlink loop")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", flaky_resolve)
    expected_records = findings.parse(good_path)

    report = harvest(store, config, [good_path, broken_path, unresolvable_path])

    assert len(report.results) == 3
    good_result, broken_result, unresolvable_result = report.results
    assert good_result.outcome == "upserted"
    assert good_result.records_count > 0
    assert broken_result.outcome == "parse_failed"
    assert broken_result.records_count == 0
    assert broken_result.error is not None
    assert unresolvable_result.outcome == "no_repo"
    assert unresolvable_result.records_count == 0
    assert unresolvable_result.error is not None
    chunks = store.chunks_for_corpus(FINDINGS_CORPUS)
    assert len(chunks) == len(expected_records)
    assert any(c.body == "good-marker-token" for c in chunks)


# --- harvest: OSError escaping repo resolution is isolated per-path ---


def test_harvest_os_error_during_repo_resolution_yields_no_repo_outcome_without_raising(
    tmp_path,
    monkeypatch,
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    broken_dir = tmp_path / "broken"
    broken_dir.mkdir()
    broken_path = broken_dir / "review.md"
    _write_review_file(broken_path)
    repos_csv = tmp_path / "repos.csv"
    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", repos_csv)
    broken_cwd = broken_path.resolve().parent
    original_run = subprocess.run

    def flaky_run(cmd, **kwargs):
        if kwargs.get("cwd") == broken_cwd:
            raise PermissionError("simulated permission error")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("engram.harvest.subprocess.run", flaky_run)

    report = harvest(store, config, [broken_path])

    result = report.results[0]
    assert result.outcome == "no_repo"
    assert result.records_count == 0


# --- harvest: main-checkout lookup failure during repo resolution is isolated ---


@pytest.mark.parametrize(
    "main_checkout_error", [subprocess.CalledProcessError(1, ["git"]), OSError("simulated")]
)
def test_resolve_repo_for_path_returns_none_when_main_checkout_lookup_fails(
    tmp_path,
    monkeypatch,
    main_checkout_error,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    path = toplevel / "file.md"
    path.write_text("irrelevant")
    repos_csv = tmp_path / "repos.csv"
    # a registry entry that does not match the resolved toplevel, so
    # resolution falls through to _resolve_main_checkout
    _write_repos_csv(repos_csv, [(tmp_path / "other-repo", "repoA")])
    original_run = subprocess.run

    def flaky_run(cmd, **kwargs):
        if "--git-common-dir" in cmd:
            raise main_checkout_error
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("engram.harvest.subprocess.run", flaky_run)

    result = _resolve_repo_for_path(path, repos_csv)

    assert result is None


def test_harvest_os_error_during_repo_resolution_on_one_path_does_not_abort_the_batch(
    tmp_path,
    monkeypatch,
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    good_path = toplevel / "good.md"
    _write_review_file(good_path, body_marker="good-marker-token")
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(toplevel, "repoA")])
    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", repos_csv)

    broken_dir = tmp_path / "broken"
    broken_dir.mkdir()
    broken_path = broken_dir / "review.md"
    _write_review_file(broken_path)
    broken_cwd = broken_path.resolve().parent
    original_run = subprocess.run

    def flaky_run(cmd, **kwargs):
        if kwargs.get("cwd") == broken_cwd:
            raise PermissionError("simulated permission error")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("engram.harvest.subprocess.run", flaky_run)

    report = harvest(store, config, [broken_path, good_path])

    broken_result, good_result = report.results
    assert broken_result.outcome == "no_repo"
    assert good_result.outcome == "upserted"
    assert good_result.records_count > 0


@pytest.mark.parametrize("read_error", [PermissionError, OSError])
def test_harvest_unreadable_registry_yields_no_repo_without_aborting_batch(
    tmp_path,
    monkeypatch,
    read_error,
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    paths = []
    for name in ("repoA", "repoB", "repoC"):
        (tmp_path / name).mkdir()
        review_path = _init_git_repo(tmp_path / name) / "review.md"
        _write_review_file(review_path, body_marker=f"{name}-marker-token")
        paths.append(review_path)
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(p.parent, p.parent.name) for p in paths])
    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", repos_csv)
    unreadable_dir = paths[1].parent
    git_cwds = []
    original_run = subprocess.run
    original_read = corpora.read_repos_csv

    def tracking_run(cmd, **kwargs):
        git_cwds.append(Path(kwargs["cwd"]).resolve())
        return original_run(cmd, **kwargs)

    def unreadable_for_repo_b(csv_path):
        if git_cwds and git_cwds[-1] == unreadable_dir:
            raise read_error("simulated unreadable registry")
        return original_read(csv_path)

    monkeypatch.setattr("engram.harvest.subprocess.run", tracking_run)
    monkeypatch.setattr("engram.corpora.read_repos_csv", unreadable_for_repo_b)

    report = harvest(store, config, paths)

    assert [r.outcome for r in report.results] == ["upserted", "no_repo", "upserted"]
    assert report.results[0].records_count > 0
    assert report.results[1].records_count == 0
    assert report.results[2].records_count > 0
    assert report.any_failed is True
    assert unreadable_dir in git_cwds
    chunks = store.chunks_for_corpus(FINDINGS_CORPUS)
    assert {c.repo for c in chunks} == {"repoA", "repoC"}
    assert all("repoB-marker-token" not in c.body for c in chunks)


def test_harvest_unreadable_registry_non_os_error_propagates_instead_of_being_swallowed(
    tmp_path,
    monkeypatch,
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path)
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    (tmp_path / "repo").mkdir()
    review_path = _init_git_repo(tmp_path / "repo") / "review.md"
    _write_review_file(review_path)
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(review_path.parent, "repo")])
    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", repos_csv)

    def broken_read(csv_path):
        raise ValueError("simulated registry programming error")

    monkeypatch.setattr("engram.corpora.read_repos_csv", broken_read)

    with pytest.raises(ValueError, match="simulated registry programming error"):
        harvest(store, config, [review_path])


# --- _resolve_repo_for_path: linked worktrees fall back to the main checkout ---


def _git(cwd, *args):
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=engram-test",
            "-c",
            "user.email=engram-test@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _make_repo_with_worktree(root, name):
    (root / name).mkdir()
    main = _init_git_repo(root / name)
    _git(main, "commit", "--allow-empty", "--no-verify", "-q", "-m", "init")
    worktree = root / f"{name}-wt"
    _git(main, "worktree", "add", "-q", "--detach", str(worktree))
    (worktree / "sub").mkdir()
    file_path = worktree / "sub" / "review.md"
    file_path.write_text("review\n")
    return main, worktree, file_path


def test_resolve_repo_for_path_maps_linked_worktree_to_main_checkout(tmp_path):
    main_one, _, file_one = _make_repo_with_worktree(tmp_path, "proj")
    main_two, _, file_two = _make_repo_with_worktree(tmp_path, "proj-two")
    elsewhere_wt = tmp_path / "elsewhere" / "feature-x"
    nested_wt = main_one / ".worktrees" / "x"
    for worktree in (elsewhere_wt, nested_wt):
        worktree.parent.mkdir(parents=True, exist_ok=True)
        _git(main_one, "worktree", "add", "-q", "--detach", str(worktree))
        (worktree / "review.md").write_text("review\n")
    link_two = tmp_path / "link-two"
    link_two.symlink_to(main_two)
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(
        repos_csv,
        [
            (tmp_path, "ancestor-decoy"),
            (tmp_path / "other" / "proj-wt", "worktree-basename-decoy"),
            (tmp_path / "other" / "proj", "main-basename-decoy"),
            (main_one, "proj-main"),
            (link_two, "proj-two-main"),
        ],
    )

    assert _resolve_repo_for_path(file_one, repos_csv) == "proj-main"
    assert _resolve_repo_for_path(file_two, repos_csv) == "proj-two-main"
    assert _resolve_repo_for_path(elsewhere_wt / "review.md", repos_csv) == "proj-main"
    assert _resolve_repo_for_path(nested_wt / "review.md", repos_csv) == "proj-main"


def test_resolve_repo_for_path_registered_worktree_keeps_its_own_name(tmp_path):
    main, worktree, worktree_file = _make_repo_with_worktree(tmp_path, "proj")
    main_file = main / "review.md"
    main_file.write_text("review\n")
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(main, "proj-main"), (worktree, "proj-wt-own")])

    assert _resolve_repo_for_path(worktree_file, repos_csv) == "proj-wt-own"
    assert _resolve_repo_for_path(main_file, repos_csv) == "proj-main"


def test_resolve_repo_for_path_worktree_of_unregistered_repo_returns_none(tmp_path):
    main, _, worktree_file = _make_repo_with_worktree(tmp_path, "proj")
    bare_dir = tmp_path / "store" / "proj.git"
    _git(tmp_path, "clone", "--bare", "-q", str(main), str(bare_dir))
    bare_worktree = tmp_path / "bare-wt"
    _git(
        bare_dir,
        "-c",
        "safe.bareRepository=all",
        "worktree",
        "add",
        "-q",
        "--detach",
        str(bare_worktree),
    )
    bare_file = bare_worktree / "review.md"
    bare_file.write_text("review\n")
    plain_roots = []
    for name in ("proj", "proj-wt"):
        (tmp_path / "plain" / name).mkdir(parents=True)
        plain_roots.append(_init_git_repo(tmp_path / "plain" / name))
        (plain_roots[-1] / "review.md").write_text("review\n")
    plain_main, plain_wt_named = plain_roots
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("")
    decoy_csv = tmp_path / "repos.csv"
    _write_repos_csv(
        decoy_csv,
        [
            (tmp_path, "ancestor-decoy"),
            (tmp_path / "pro", "prefix-decoy"),
            (tmp_path / "other" / "proj", "main-basename-decoy"),
            (tmp_path / "other" / "proj-wt", "worktree-basename-decoy"),
            (tmp_path / "store", "bare-parent-decoy"),
            (bare_dir, "bare-dir-decoy"),
            (plain_main, "plain-proj"),
        ],
    )

    assert _resolve_repo_for_path(worktree_file, empty_csv) is None
    assert _resolve_repo_for_path(worktree_file, decoy_csv) is None
    assert _resolve_repo_for_path(bare_file, decoy_csv) is None
    assert _resolve_repo_for_path(plain_main / "review.md", decoy_csv) == "plain-proj"
    assert _resolve_repo_for_path(plain_wt_named / "review.md", decoy_csv) is None


def test_registry_root_returns_path_for_name(tmp_path):
    from engram.harvest import registry_root

    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(
        repos_csv,
        [
            (tmp_path / "a" / "proj-main", "proj-main"),
            (tmp_path / "x" / "my-proj", "my-proj"),
            (tmp_path / "u" / "Proj", "Proj"),
            (tmp_path / "b" / "checkout", "proj"),
            (tmp_path / "d" / "proj", "proj"),
        ],
    )
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("")

    proj_root = registry_root("proj", repos_csv)
    assert isinstance(proj_root, Path)
    assert proj_root == tmp_path / "b" / "checkout"
    assert registry_root("my-proj", repos_csv) == tmp_path / "x" / "my-proj"
    assert registry_root("Proj", repos_csv) == tmp_path / "u" / "Proj"
    assert registry_root("PROJ", repos_csv) is None
    assert registry_root("pro", repos_csv) is None
    assert registry_root("proj", empty_csv) is None
    assert registry_root("proj", tmp_path / "missing.csv") is None
    assert registry_root("proj", tmp_path) is None
    default = inspect.signature(registry_root).parameters["repos_csv"].default
    assert default == corpora.GITA_REPOS_CSV


# --- HarvestReport.any_failed ---


@pytest.mark.parametrize(
    "outcomes,expected",
    [
        (["upserted", "upserted"], False),
        (["upserted", "parse_failed"], True),
        (["no_repo"], True),
        (["upsert_failed", "upserted"], True),
    ],
)
def test_harvest_report_any_failed_reflects_whether_any_result_is_not_upserted(
    outcomes,
    expected,
):
    results = [
        FileHarvestResult(path=Path(f"f{i}.md"), outcome=outcome, records_count=0)
        for i, outcome in enumerate(outcomes)
    ]

    report = HarvestReport(results=results)

    assert report.any_failed is expected


# --- end-to-end: CLI harvest -> source deleted -> finding still queryable ---


def test_harvest_via_cli_then_source_deleted_finding_still_queryable_via_cli_query(
    tmp_path,
    monkeypatch,
    capsys,
):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toplevel = _init_git_repo(repo_dir)
    review_path = (
        toplevel
        / "docs"
        / "dev"
        / "project-management"
        / "reviews"
        / "feature-review-1.md"
    )
    review_path.parent.mkdir(parents=True)
    _write_review_file(review_path, body_marker="zeroloss-marker-token")
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(toplevel, "repoA")])
    config = _config(tmp_path)
    db_path = tmp_path / "engram.db"

    monkeypatch.setattr("engram.harvest.GITA_REPOS_CSV", repos_csv)
    monkeypatch.setattr("engram.cli.load_config", lambda *a, **k: config)
    monkeypatch.setattr("engram.cli.open_store", lambda *a, **k: open_store(db_path))
    monkeypatch.setattr("engram.findings.embed", _make_embed())
    monkeypatch.setattr("engram.query.embed", _make_embed())

    harvest_exit_code = cli_main(["harvest", str(review_path)])
    assert harvest_exit_code == 0
    capsys.readouterr()  # discard harvest's own output

    review_path.unlink()

    query_exit_code = cli_main(
        ["query", "--scope", "portfolio", "zeroloss-marker-token"],
    )

    captured = capsys.readouterr()
    assert query_exit_code == 0
    assert "zeroloss-marker-token" in captured.out.splitlines()
