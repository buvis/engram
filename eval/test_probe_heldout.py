"""Freeze integrity gates must fail before inference starts."""

import json
from pathlib import Path

import pytest

from eval import probe_heldout


@pytest.fixture
def snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(probe_heldout, "CACHE", tmp_path)
    directory = tmp_path / probe_heldout.SNAPSHOT
    directory.mkdir()
    path = directory / "snapshot.json"
    path.write_text(
        json.dumps(
            {
                "gold": [{"path": "development"}],
                "rows": [
                    {
                        "corpus": "code",
                        "path": "development",
                        "body": "x" * 200,
                        "line_start": 1,
                    },
                    {
                        "corpus": "code",
                        "path": "heldout",
                        "body": "y" * 200,
                        "line_start": 42,
                    },
                ],
            }
        )
    )
    return path


def test_freeze_excludes_development_and_preserves_passage(
    snapshot: Path, tmp_path: Path
) -> None:
    labels = tmp_path / "labels.json"
    probe_heldout.freeze(labels)
    data = json.loads(labels.read_text())
    assert [g["path"] for g in data["gold"]] == ["heldout"]
    assert data["gold"][0]["acceptable_starts"] == [42]
    assert data["sources"][0]["body"] == "y" * 200
    assert data["snapshot_sha256"] == probe_heldout.digest(snapshot)


def test_freeze_refuses_overwrite(snapshot: Path, tmp_path: Path) -> None:
    labels = tmp_path / "labels.json"
    labels.write_text("preserve existing labels")
    with pytest.raises(FileExistsError):
        probe_heldout.freeze(labels)
    assert labels.read_text() == "preserve existing labels"


def test_changed_snapshot_rejected_before_inference(
    snapshot: Path, tmp_path: Path
) -> None:
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"snapshot_sha256": "changed"}))
    with pytest.raises(ValueError, match="snapshot changed"):
        probe_heldout.run(labels, tmp_path / "results.json")
    assert not (tmp_path / "results.json").exists()
