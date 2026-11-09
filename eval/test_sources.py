"""Source retention must survive churn without replacing labels or evidence."""

import json
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

from engram.harness import load_goldset
from engram.store import open_store
from eval import compare_models
from eval.sources import capture, load_sources, restore

Evidence = tuple[Path, Path, Path, Path]


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _gold(tmp_path: Path, source: Path, corpus: str = "prd") -> Path:
    path = tmp_path / "goldset.yaml"
    path.write_text(
        yaml.safe_dump(
            [
                {
                    "query": f"question {i}",
                    "corpus": corpus,
                    "expected_path": str(source),
                }
                for i in range(30)
            ]
        )
    )
    return path


@pytest.fixture
def evidence(tmp_path: Path) -> Evidence:
    source = tmp_path / "evidence.md"
    source.write_text("# Private evidence\noriginal body\n")
    return (
        source,
        _gold(tmp_path, source),
        tmp_path / "sources.json",
        tmp_path / "private",
    )


def test_capture_is_private_and_keeps_labels_after_source_deletion(
    evidence: Evidence,
) -> None:
    source, gold, manifest, storage = evidence
    original = source.read_bytes()
    capture(gold, manifest, storage)
    source.unlink()

    files = load_sources(gold, manifest, storage)
    entries = load_goldset(gold, source_paths=files)
    assert len(entries) == 30
    assert {e.expected_path for e in entries} == {str(source)}
    assert files[str(source)].path.read_bytes() == original
    assert stat.S_IMODE(files[str(source)].path.stat().st_mode) == 0o600
    assert stat.S_IMODE(storage.stat().st_mode) == 0o700
    assert "original body" not in manifest.read_text()


def test_capture_never_overwrites_a_freeze(evidence: Evidence) -> None:
    source, gold, manifest, storage = evidence
    capture(gold, manifest, storage)
    before = manifest.read_bytes()
    source.write_text("replacement")
    with pytest.raises(FileExistsError):
        capture(gold, manifest, storage)
    assert manifest.read_bytes() == before
    assert (
        load_sources(gold, manifest, storage)[str(source)]
        .path.read_text()
        .startswith("# Private")
    )


def test_retained_identity_survives_retargeted_and_deleted_symlinks(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.md"
    source.write_text("Original evidence")
    link = tmp_path / "label.md"
    link.symlink_to(source)
    gold = _gold(tmp_path, link)
    manifest, storage = tmp_path / "sources.json", tmp_path / "private"
    capture(gold, manifest, storage)
    link.unlink()
    replacement = tmp_path / "replacement.md"
    replacement.write_text("Different evidence")
    link.symlink_to(replacement)
    sources = load_sources(gold, manifest, storage)
    assert {e.expected_path for e in load_goldset(gold, source_paths=sources)} == {
        str(source)
    }
    assert sources[str(link)].path.read_text() == "Original evidence"
    link.unlink()
    assert load_sources(gold, manifest, storage) == sources
    sources[str(link)].path.unlink()
    restore(gold, manifest, storage)
    assert load_sources(gold, manifest, storage) == sources


def test_private_source_storage_cannot_be_inside_a_git_checkout(
    evidence: Evidence,
) -> None:
    source, gold, manifest, storage = evidence
    (storage.parent / ".git").mkdir()
    with pytest.raises(ValueError, match="outside Git"):
        capture(gold, manifest, storage)
    assert not storage.exists()


@pytest.mark.parametrize("change", ["query", "path", "corpus", "remove"])
def test_label_changes_require_a_new_explicit_freeze(
    evidence: Evidence, change: str
) -> None:
    source, gold, manifest, storage = evidence
    capture(gold, manifest, storage)
    labels = yaml.safe_load(gold.read_text())
    if change == "remove":
        labels.pop()
    else:
        labels[0][{"path": "expected_path"}.get(change, change)] = "changed"
    gold.write_text(yaml.safe_dump(labels))
    with pytest.raises(ValueError, match="goldset fingerprint"):
        load_sources(gold, manifest, storage)


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_missing_or_corrupt_archive_fails_even_when_live_source_exists(
    evidence: Evidence, damage: str
) -> None:
    source, gold, manifest, storage = evidence
    capture(gold, manifest, storage)
    retained = load_sources(gold, manifest, storage)[str(source)].path
    if damage == "missing":
        retained.unlink()
    else:
        retained.write_text("corrupted")
    with pytest.raises(ValueError, match="retained source"):
        load_sources(gold, manifest, storage)


def test_restore_requires_original_bytes_for_unversioned_sources(
    evidence: Evidence,
) -> None:
    source, gold, manifest, storage = evidence
    capture(gold, manifest, storage)
    retained = load_sources(gold, manifest, storage)[str(source)].path
    original = source.read_bytes()
    retained.unlink()
    source.write_text("changed")
    with pytest.raises(ValueError, match="cannot restore exact source"):
        restore(gold, manifest, storage)
    assert not retained.exists()
    source.write_bytes(original)
    restore(gold, manifest, storage)
    assert retained.read_bytes() == original


def test_recover_committed_deletion_and_restore_pinned_git_bytes(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "cellar"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    source = repo / "session.jsonl"
    original = b'{"type":"user","message":{"content":"Original question"}}\n'
    source.write_bytes(original)
    _git(repo, "add", "session.jsonl")
    _git(repo, "commit", "-qm", "retain evidence")
    revision = _git(repo, "rev-parse", "HEAD")
    source.unlink()
    _git(repo, "add", "-u")
    _git(repo, "commit", "-qm", "prune evidence")
    gold = _gold(tmp_path, source, "transcripts")
    manifest, storage = tmp_path / "sources.json", tmp_path / "private"
    capture(gold, manifest, storage, git_repos=[repo])

    assert not source.exists()
    assert _git(repo, "status", "--porcelain") == ""
    record = json.loads(manifest.read_text())["sources"][str(source)]
    assert record["git"]["commit"] == revision
    retained = load_sources(gold, manifest, storage)[str(source)].path
    assert retained.read_bytes() == original
    retained.unlink()
    source.write_text("new unrelated worktree content")
    restore(gold, manifest, storage)
    assert retained.read_bytes() == original
    assert source.read_text() == "new unrelated worktree content"


def test_capture_failure_does_not_publish_manifest(evidence: Evidence) -> None:
    source, gold, manifest, storage = evidence
    source.unlink()
    with pytest.raises(ValueError, match="cannot retain source"):
        capture(gold, manifest, storage)
    assert not manifest.exists()


@pytest.mark.parametrize("damage", ["missing", "extra", "hash"])
def test_manifest_requires_exact_target_coverage_and_safe_hashes(
    evidence: Evidence, damage: str
) -> None:
    source, gold, manifest, storage = evidence
    capture(gold, manifest, storage)
    raw = json.loads(manifest.read_text())
    if damage == "missing":
        raw["sources"].pop(str(source))
    elif damage == "extra":
        raw["sources"]["/extra"] = raw["sources"][str(source)]
    else:
        raw["sources"][str(source)]["sha256"] = "../../escape"
    manifest.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="manifest"):
        load_sources(gold, manifest, storage)


def test_snapshot_preparation_reads_retained_bytes_but_scores_original_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "demo" / "target.py"
    source.parent.mkdir()
    source.write_text("def answer():\n    return 42\n")
    gold = _gold(tmp_path, source, "code")
    manifest, storage = tmp_path / "sources.json", tmp_path / "private"
    capture(gold, manifest, storage)
    source.unlink()
    (tmp_path / "passage_labels.yaml").write_text("0: [1]\n")
    db = tmp_path / "portfolio.db"
    open_store(db).conn.close()
    original_db = db.read_bytes()
    monkeypatch.setattr(compare_models, "ROOT", tmp_path)
    monkeypatch.setattr(compare_models, "SOURCE", db)
    monkeypatch.setattr(compare_models, "CACHE", tmp_path / "campaigns")

    directory = compare_models.prepare(source_storage=storage)

    snapshot = json.loads((directory / "snapshot.json").read_text())
    assert {g["path"] for g in snapshot["gold"]} == {str(source)}
    assert {r["path"] for r in snapshot["rows"]} == {str(source)}
    assert snapshot["rows"][0]["body"] == "def answer():\n    return 42"
    assert snapshot["gold"][0]["acceptable_starts"] == [1]
    assert (
        str(storage)
        not in compare_models._chunk(snapshot["rows"][0]).text_for_embedding
    )
    assert len(snapshot["gold_sources_sha256"]) == 64
    assert db.read_bytes() == original_db
    assert not source.exists()
