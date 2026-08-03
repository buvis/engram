import subprocess
from pathlib import Path

from engram import corpora
from engram.corpora import enumerate_corpora, hash_source


def _write_repos_csv(csv_path: Path, rows: list[tuple[str, str]]) -> None:
    lines = [f"{repo_path},{name},,\n" for repo_path, name in rows]
    csv_path.write_text("".join(lines))


# --- full enumeration: prd (recursive), decision, discovery ---


def test_enumerate_corpora_yields_prd_decision_and_discovery_files_for_repo(tmp_path):
    repo_root = tmp_path / "repos" / "widget"
    prds_dir = repo_root / "dev" / "local" / "prds"
    nested_prd_dir = prds_dir / "backlog"
    nested_prd_dir.mkdir(parents=True)
    prd_top = prds_dir / "00001-top.md"
    prd_top.write_text("top level prd")
    prd_nested = nested_prd_dir / "00002-nested.md"
    prd_nested.write_text("nested prd")

    decisions_file = repo_root / "dev" / "local" / "decisions.md"
    decisions_file.write_text("decisions log")

    discovery_dir = repo_root / "dev" / "local" / "discovery"
    discovery_dir.mkdir(parents=True)
    discovery_file = discovery_dir / "notes.md"
    discovery_file.write_text("discovery notes")

    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(str(repo_root), "widget")])

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    results = {
        (cf.corpus, cf.repo, cf.path)
        for cf in enumerate_corpora(repos_csv=repos_csv, projects_dir=projects_dir)
    }

    expected = {
        ("prd", "widget", prd_top),
        ("prd", "widget", prd_nested),
        ("decision", "widget", decisions_file),
        ("discovery", "widget", discovery_file),
    }
    assert results == expected


# --- memory corpus: repo resolution via slug ---


def test_memory_dir_matching_repos_csv_slug_resolves_to_repo_name(tmp_path):
    repo_root = tmp_path / "repos" / "gadget"
    slug = str(repo_root).replace("/", "-")

    projects_dir = tmp_path / "projects"
    memory_dir = projects_dir / slug / "memory"
    memory_dir.mkdir(parents=True)
    memory_file = memory_dir / "notes.md"
    memory_file.write_text("memory content")

    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(str(repo_root), "gadget")])

    results = {
        (cf.corpus, cf.repo, cf.path)
        for cf in enumerate_corpora(repos_csv=repos_csv, projects_dir=projects_dir)
        if cf.corpus == "memory"
    }

    assert results == {("memory", "gadget", memory_file)}


def test_memory_corpus_paths_are_symlink_resolved_when_projects_dir_is_a_symlink(tmp_path):
    repo_root = tmp_path / "repos" / "gadget"
    slug = str(repo_root).replace("/", "-")

    real_projects_dir = tmp_path / "real_projects"
    memory_dir = real_projects_dir / slug / "memory"
    memory_dir.mkdir(parents=True)
    memory_file = memory_dir / "notes.md"
    memory_file.write_text("memory content")

    projects_dir = tmp_path / "projects_link"
    projects_dir.symlink_to(real_projects_dir)

    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(str(repo_root), "gadget")])

    results = {
        (cf.corpus, cf.repo, cf.path)
        for cf in enumerate_corpora(repos_csv=repos_csv, projects_dir=projects_dir)
        if cf.corpus == "memory"
    }

    assert results == {("memory", "gadget", memory_file.resolve())}


def test_memory_dir_matching_no_repos_csv_row_resolves_to_unmapped(tmp_path):
    projects_dir = tmp_path / "projects"
    memory_dir = projects_dir / "-unknown-project" / "memory"
    memory_dir.mkdir(parents=True)
    memory_file = memory_dir / "notes.md"
    memory_file.write_text("memory content")

    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(str(tmp_path / "repos" / "other"), "other")])

    results = {
        (cf.corpus, cf.repo, cf.path)
        for cf in enumerate_corpora(repos_csv=repos_csv, projects_dir=projects_dir)
        if cf.corpus == "memory"
    }

    assert results == {("memory", "_unmapped", memory_file)}


def test_memory_dir_for_hyphenated_repo_name_resolves_to_full_name_not_last_segment(tmp_path):
    projects_dir = tmp_path / "projects"
    memory_dir = projects_dir / "-some-base-audit-tools" / "memory"
    memory_dir.mkdir(parents=True)
    memory_file = memory_dir / "notes.md"
    memory_file.write_text("memory content")

    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [("/some/base/audit-tools", "audit-tools")])

    results = {
        (cf.corpus, cf.repo, cf.path)
        for cf in enumerate_corpora(repos_csv=repos_csv, projects_dir=projects_dir)
        if cf.corpus == "memory"
    }

    assert results == {("memory", "audit-tools", memory_file)}


# --- missing per-repo sources are skipped and counted, never raised ---


def test_missing_prds_dir_appends_prd_entry_to_missing_dirs_without_raising(tmp_path):
    repo_root = tmp_path / "repos" / "acme"
    decisions_file = repo_root / "dev" / "local" / "decisions.md"
    decisions_file.parent.mkdir(parents=True)
    decisions_file.write_text("decisions")
    discovery_dir = repo_root / "dev" / "local" / "discovery"
    discovery_dir.mkdir()

    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(str(repo_root), "acme")])
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    results = list(enumerate_corpora(repos_csv=repos_csv, projects_dir=projects_dir))

    assert "prd:acme" in corpora.missing_dirs
    assert not any(cf.corpus == "prd" for cf in results)


def test_missing_decisions_file_appends_decision_entry_to_missing_dirs(tmp_path):
    repo_root = tmp_path / "repos" / "acme"
    prds_dir = repo_root / "dev" / "local" / "prds"
    prds_dir.mkdir(parents=True)
    discovery_dir = repo_root / "dev" / "local" / "discovery"
    discovery_dir.mkdir()

    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(str(repo_root), "acme")])
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    results = list(enumerate_corpora(repos_csv=repos_csv, projects_dir=projects_dir))

    assert "decision:acme" in corpora.missing_dirs
    assert not any(cf.corpus == "decision" for cf in results)


def test_missing_discovery_dir_appends_discovery_entry_to_missing_dirs(tmp_path):
    repo_root = tmp_path / "repos" / "acme"
    prds_dir = repo_root / "dev" / "local" / "prds"
    prds_dir.mkdir(parents=True)
    decisions_file = repo_root / "dev" / "local" / "decisions.md"
    decisions_file.write_text("decisions")

    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(str(repo_root), "acme")])
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    results = list(enumerate_corpora(repos_csv=repos_csv, projects_dir=projects_dir))

    assert "discovery:acme" in corpora.missing_dirs
    assert not any(cf.corpus == "discovery" for cf in results)


# --- missing_dirs lifecycle ---


def test_missing_dirs_resets_to_empty_on_each_call(tmp_path):
    empty_repo_root = tmp_path / "repos" / "empty"
    empty_repo_root.mkdir(parents=True)
    repos_csv_missing = tmp_path / "repos_missing.csv"
    _write_repos_csv(repos_csv_missing, [(str(empty_repo_root), "empty")])
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    list(enumerate_corpora(repos_csv=repos_csv_missing, projects_dir=projects_dir))
    assert corpora.missing_dirs  # sanity: first call populated missing entries

    full_repo_root = tmp_path / "repos" / "full"
    (full_repo_root / "dev" / "local" / "prds").mkdir(parents=True)
    (full_repo_root / "dev" / "local" / "decisions.md").write_text("decisions")
    (full_repo_root / "dev" / "local" / "discovery").mkdir()
    repos_csv_full = tmp_path / "repos_full.csv"
    _write_repos_csv(repos_csv_full, [(str(full_repo_root), "full")])

    list(enumerate_corpora(repos_csv=repos_csv_full, projects_dir=projects_dir))

    assert corpora.missing_dirs == []


# --- discovery corpus is non-recursive ---


def test_discovery_corpus_ignores_files_in_nested_subdirectories(tmp_path):
    repo_root = tmp_path / "repos" / "widget"
    discovery_dir = repo_root / "dev" / "local" / "discovery"
    nested_dir = discovery_dir / "archive"
    nested_dir.mkdir(parents=True)
    top_file = discovery_dir / "top.md"
    top_file.write_text("top level discovery note")
    nested_file = nested_dir / "nested.md"
    nested_file.write_text("nested discovery note")

    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(str(repo_root), "widget")])
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    results = {
        cf.path
        for cf in enumerate_corpora(repos_csv=repos_csv, projects_dir=projects_dir)
        if cf.corpus == "discovery"
    }

    assert results == {top_file}


# --- projects_dir absence is a no-op, not a missing-dirs entry ---


def test_missing_projects_dir_yields_no_memory_files_and_does_not_populate_missing_dirs(
    tmp_path,
):
    projects_dir = tmp_path / "does-not-exist"
    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [])

    results = list(enumerate_corpora(repos_csv=repos_csv, projects_dir=projects_dir))

    assert results == []
    assert corpora.missing_dirs == []


# --- hash_source ---


def test_hash_source_matches_git_hash_object_for_non_ascii_content(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text("Café — naïve résumé 日本語", encoding="utf-8")

    result = subprocess.run(
        ["git", "hash-object", str(source)],
        capture_output=True,
        text=True,
        check=True,
    )
    expected_hash = result.stdout.strip()

    assert hash_source(source) == expected_hash


# --- robustness: malformed repos.csv rows ---


def test_blank_line_in_repos_csv_is_skipped_without_raising(tmp_path):
    repo_root = tmp_path / "repos" / "widget"
    (repo_root / "dev" / "local" / "prds").mkdir(parents=True)
    decisions_file = repo_root / "dev" / "local" / "decisions.md"
    decisions_file.write_text("decisions")
    (repo_root / "dev" / "local" / "discovery").mkdir()

    repos_csv = tmp_path / "repos.csv"
    # stray blank lines are plausible in a hand-edited gita csv; they must be
    # skipped, not crash enumeration
    repos_csv.write_text(f"\n{repo_root},widget,,\n\n")
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    results = {
        (cf.corpus, cf.repo, cf.path)
        for cf in enumerate_corpora(repos_csv=repos_csv, projects_dir=projects_dir)
    }

    assert ("decision", "widget", decisions_file) in results


# --- missing_dirs identity: a direct name-import must see updates ---


def test_missing_dirs_updates_are_visible_through_a_direct_name_import(tmp_path):
    from engram.corpora import missing_dirs as bound

    repo_root = tmp_path / "repos" / "acme"
    repo_root.mkdir(parents=True)  # no dev/local -> all three sources missing

    repos_csv = tmp_path / "repos.csv"
    _write_repos_csv(repos_csv, [(str(repo_root), "acme")])
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    list(enumerate_corpora(repos_csv=repos_csv, projects_dir=projects_dir))

    assert bound is corpora.missing_dirs
    assert "prd:acme" in bound
