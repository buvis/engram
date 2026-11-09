"""Review-pack correctness at retrieval, Git, budget, and failure boundaries."""

import argparse
import subprocess
from pathlib import Path

import pytest
from _pack_helpers import (
    _chunk,
    _config,
    _small_budget,
    _vec,
    _write_single_function_diff,
)

from engram.cli import _resolve_pack_diff, main
from engram.client import (
    EmbeddingModelIdentityError,
    EmbeddingPreflightError,
    EmbeddingServerError,
    PackBudget,
)
from engram.diffmap import changed_symbols
from engram.indexer import IndexReport
from engram.pack import (
    _SECTION_ORDER,
    _finalize_pack,
    _query_hits_for_symbol,
    _symbol_query_text,
    _task_prose_entries,
    build,
)
from engram.store import ChunkWithVector, Scope, open_store


@pytest.mark.parametrize("hard_cap", [104, 204])
def test_omission_notices_cannot_overflow_hard_cap(
    tmp_path: Path, hard_cap: int
) -> None:
    sections = {label: (["x" * 200], str) for label in _SECTION_ORDER}
    budget = PackBudget(hard_cap, 1, 1, 1, 1)
    report = _finalize_pack(
        sections,
        [],
        5,
        [Path("/" + "long/" * 300 + "prd.md")],
        budget,
        "cap",
        tmp_path,
        IndexReport(0, 0, 0, []),
    )
    content = report.path.read_text()
    assert len(content) // 4 <= budget.hard_cap_tokens
    assert report.total_estimated_tokens == len(content) // 4
    assert "could not be read" in content
    assert "5 changed symbol(s) omitted" in content
    assert all(f"## {label}" in content for label in _SECTION_ORDER)


def test_compact_notices_preserve_content_that_still_fits(tmp_path: Path) -> None:
    sections = {label: (["evidence"], str) for label in _SECTION_ORDER}
    report = _finalize_pack(
        sections,
        [],
        0,
        [Path("/" + "long/" * 300 + "prd.md")],
        PackBudget(104, 1, 1, 1, 1),
        "cap",
        tmp_path,
        IndexReport(0, 0, 0, []),
    )
    assert report.path.read_text().count("evidence") == 4
    assert report.total_estimated_tokens <= 104


@pytest.mark.parametrize("prd_text", [None, "#   \nBody"])
def test_prd_without_usable_title_skips_memory_retrieval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prd_text: str | None,
) -> None:
    prd = tmp_path / "filename-is-not-a-query.md"
    if prd_text is not None:
        prd.write_text(prd_text)

    def refuse_query(*args, **kwargs) -> None:
        pytest.fail("PRD without a usable title triggered retrieval")

    monkeypatch.setattr("engram.pack.query", refuse_query)
    entries, unreadable = _task_prose_entries(None, None, "cycle", prd, None, 200)
    assert entries == ([] if prd_text is None else [prd_text])
    assert unreadable == ([prd] if prd_text is None else [])


def test_memory_bodies_reach_task_prose_with_two_hit_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = open_store(tmp_path / "test.db")
    vector = _vec([1, 0, 0, 0])
    for i in range(3):
        path = f"memory-{i}.md"
        chunk = _chunk(corpus="memory", path=path, body=f"Recall memory body {i}")
        store.upsert_chunks([ChunkWithVector(chunk, vector)])
    monkeypatch.setattr("engram.query.embed", lambda texts, entry: [vector])
    prd = tmp_path / "prd.md"
    prd.write_text("# Recall\nPRD body")
    entries, unreadable = _task_prose_entries(
        store,
        _config(tmp_path, _small_budget()),
        "cycle",
        prd,
        None,
        200,
    )
    assert len(entries) == 3
    assert entries[0].startswith("Recall memory body")
    assert entries[1].startswith("Recall memory body")
    assert entries[0] != entries[1]
    assert entries[2] == prd.read_text()
    assert unreadable == []
    store.conn.close()


def test_reuse_retrieves_foreign_code_beyond_local_candidate_pool(
    tmp_path: Path,
) -> None:
    store = open_store(tmp_path / "test.db")
    vector = _vec([1, 0, 0, 0])
    for i in range(25):
        path = f"local-{i}.py"
        chunk = _chunk(path=path, body="needle")
        store.upsert_chunks([ChunkWithVector(chunk, vector)])
    foreign = _chunk(repo="repoB", path="foreign.py", body="needle foreign evidence")
    store.upsert_chunks(
        [ChunkWithVector(foreign, _vec([0, 1, 0, 0]))],
    )
    similar, reuse, _ = _query_hits_for_symbol(
        store,
        _config(tmp_path, _small_budget()),
        "repoA",
        "needle",
        vector,
    )
    assert len(similar) == 5
    assert {hit.repo for hit in similar} == {"repoA"}
    assert [hit.body for hit in reuse] == ["needle foreign evidence"]
    store.conn.close()


@pytest.mark.parametrize("text", ["", "_No diff available_\n"])
def test_non_diff_input_fails_before_reindex(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
) -> None:
    diff = tmp_path / "invalid.diff"
    diff.write_text(text)

    def refuse_index(*args, **kwargs) -> None:
        pytest.fail("reindex ran for non-diff input")

    monkeypatch.setattr("engram.pack.index", refuse_index)
    with pytest.raises(ValueError, match="no git diff sections"):
        build(None, None, "repoA", tmp_path, "cycle", diff)


@pytest.mark.parametrize(
    "index_report",
    [
        IndexReport(0, 0, 0, [], failed_sources=["unreadable.py"]),
        IndexReport(0, 0, 0, ["code:repoA"]),
    ],
)
def test_failed_index_does_not_publish_pack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    index_report: IndexReport,
) -> None:
    _, diff = _write_single_function_diff(tmp_path)
    monkeypatch.setattr("engram.pack.index", lambda *args: index_report)
    with pytest.raises(ValueError, match="pack reindex failed"):
        build(None, None, "repoA", tmp_path, "cycle", diff, out_dir=tmp_path)
    assert not (tmp_path / "engram-pack-cycle.md").exists()


def test_impossible_cap_does_not_overwrite_previous_pack(tmp_path: Path) -> None:
    target = tmp_path / "engram-pack-cap.md"
    target.write_text("previous pack")
    sections = {label: ([], str) for label in _SECTION_ORDER}
    with pytest.raises(ValueError, match="too small"):
        _finalize_pack(
            sections,
            [],
            0,
            [],
            PackBudget(1, 1, 1, 1, 1),
            "cap",
            tmp_path,
            IndexReport(0, 0, 0, []),
        )
    assert target.read_text() == "previous pack"


@pytest.mark.parametrize("method", ["search_bm25", "search_knn"])
def test_repo_exclusion_precedes_each_search_limit(tmp_path: Path, method: str) -> None:
    store = open_store(tmp_path / "test.db")
    vector = _vec([1, 0, 0, 0])
    for repo in ("repoA", "repoB"):
        chunk = _chunk(repo=repo, path=f"{repo}.py", body="needle")
        store.upsert_chunks([ChunkWithVector(chunk, vector)])
    subject = "needle" if method == "search_bm25" else vector
    hits = getattr(store, method)(
        subject,
        Scope("portfolio", None),
        "code",
        1,
        exclude_repo="repoA",
    )
    assert [hit.chunk.repo for hit in hits] == ["repoB"]
    store.conn.close()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.mark.parametrize("range_str", ["HEAD~1..", "HEAD~1...", "HEAD~1...HEAD"])
def test_diff_ranges_read_head_instead_of_staged_or_worktree_content(
    tmp_path: Path,
    range_str: str,
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.com")
    source = tmp_path / "source.py"
    source.write_text("def base():\n    return 0\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "base")
    source.write_text("def committed_head():\n    return 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "head")
    source.write_text("def staged():\n    return 2\n")
    _git(tmp_path, "add", ".")
    source.write_text("def worktree():\n    return 3\n")
    resolved = _resolve_pack_diff(
        argparse.Namespace(cycle=None, diff=range_str),
        tmp_path,
        tmp_path / "out",
    )
    assert resolved is not None
    diff, _, source_ref = resolved
    symbols = changed_symbols(diff, tmp_path, source_ref)
    assert [symbol.name for symbol in symbols] == ["committed_head"]
    assert "def committed_head()" in _symbol_query_text(
        symbols[0], tmp_path, source_ref
    )


@pytest.mark.parametrize("path", ["../outside.py", "/absolute.py", "link.py"])
def test_diff_rejects_paths_outside_repository(tmp_path: Path, path: str) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("def private():\n    return 'private'\n")
    (repo / "link.py").symlink_to(outside)
    diff = repo / "changes.diff"
    diff.write_text(
        f"diff --git a/x b/x\n--- a/x\n+++ b/{path}\n@@ -0,0 +1 @@\n+added\n",
    )
    with pytest.raises(ValueError, match="outside repository"):
        changed_symbols(diff, repo)


def test_missing_diff_fails_before_reindex(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse_index(*args, **kwargs) -> None:
        pytest.fail("reindex ran before reading the missing diff")

    monkeypatch.setattr("engram.pack.index", refuse_index)
    with pytest.raises(FileNotFoundError, match="missing.diff"):
        build(None, None, "repoA", tmp_path, "cycle", tmp_path / "missing.diff")


@pytest.mark.parametrize(
    ("boundary", "error"),
    [
        ("load_config", ValueError("invalid pack budget")),
        ("build", FileNotFoundError("missing staged diff")),
        ("build", EmbeddingServerError("endpoint unavailable")),
        ("build", EmbeddingPreflightError("preflight failed")),
        ("build", EmbeddingModelIdentityError("wrong model at endpoint")),
        ("_resolve_pack_repo", PermissionError("registry unreadable")),
        ("_resolve_pack_diff", PermissionError("diff directory is not writable")),
    ],
)
def test_pack_reports_expected_failures_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    boundary: str,
    error: Exception,
) -> None:
    monkeypatch.setattr("engram.cli._resolve_pack_repo", lambda: ("repoA", tmp_path))
    monkeypatch.setattr(
        "engram.cli._resolve_pack_diff",
        lambda *args: (tmp_path / "diff", "cycle", None),
    )
    monkeypatch.setattr("engram.cli.load_config", lambda: None)
    monkeypatch.setattr("engram.cli.open_store", lambda: None)

    def fail(*args, **kwargs) -> None:
        raise error

    monkeypatch.setattr(f"engram.cli.{boundary}", fail)
    assert main(["pack", "--cycle", "cycle"]) == 1
    output = capsys.readouterr()
    assert str(error) in output.err
    assert output.out == ""
    assert "Traceback" not in output.err
