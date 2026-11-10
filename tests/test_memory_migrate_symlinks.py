import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from _migrate_helpers import DEST, GITATTRS, IMPORT, valid, write

from engram.migrate import MigrationError, apply_migration, plan_migration


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: path))
    return path


@pytest.fixture
def src(tmp_path: Path) -> Path:
    path = tmp_path / "claude-memory"
    path.mkdir()
    write(path, "note.md", valid(name="note", description="A fact"))
    write(path, "other-fact.md", valid(name="other-fact", description="Another"))
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    return path


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    path = tmp_path / "outside"
    path.mkdir()
    write(path, "keep.txt", "untouched\n")
    (path / "settings.json").write_text('{"theme": "dark"}\n')
    return path


def tree(root: Path) -> dict[str, tuple[str, str | bytes | None]]:
    """Every path under root without following symlinks: kind plus bytes or target."""
    out: dict[str, tuple[str, str | bytes | None]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            rel = str(path.relative_to(root))
            if path.is_symlink():
                out[rel] = ("link", os.readlink(path))
            elif path.is_dir():
                out[rel] = ("dir", None)
            else:
                out[rel] = ("file", path.read_bytes())
    return out


def link_wiring(repo: Path, name: str) -> None:
    """Make wiring file `name` a symlink in the shape its test case needs."""
    if name == "CLAUDE.md":
        (repo / "AGENTS.md").write_text("# Agents\n")
        os.symlink("AGENTS.md", repo / "CLAUDE.md")
    elif name == ".gitattributes":
        os.symlink("missing-attrs", repo / ".gitattributes")
    else:
        (repo / ".claude").mkdir()
        (repo / ".claude" / "real-settings.json").write_text('{"theme": "dark"}\n')
        os.symlink("real-settings.json", repo / ".claude" / "settings.json")


WIRING_NAMES = ["CLAUDE.md", ".gitattributes", ".claude/settings.json"]


@pytest.mark.parametrize("name", WIRING_NAMES)
def test_apply_refuses_symlinked_wiring_file_and_changes_nothing(
    tmp_path: Path,
    src: Path,
    repo: Path,
    name: str,
) -> None:
    link_wiring(repo, name)
    before = tree(tmp_path)

    with pytest.raises(MigrationError) as err:
        apply_migration(src, repo)

    assert name in str(err.value)
    assert "symlink" in str(err.value)
    assert tree(tmp_path) == before
    assert (repo / name).is_symlink()
    assert not (repo / DEST).exists()


def test_apply_symlink_refusal_names_only_the_offending_wiring_file(
    src: Path,
    repo: Path,
) -> None:
    link_wiring(repo, ".gitattributes")

    with pytest.raises(MigrationError) as err:
        apply_migration(src, repo)

    message = str(err.value)
    assert ".gitattributes" in message
    assert "CLAUDE.md" not in message
    assert "settings.json" not in message


def test_apply_refuses_symlinked_wiring_even_when_other_wiring_is_regular(
    tmp_path: Path,
    src: Path,
    repo: Path,
) -> None:
    (repo / "AGENTS.md").write_text("# Agents\n")
    (repo / ".gitattributes").write_text("*.png binary\n")
    link_wiring(repo, ".claude/settings.json")
    before = tree(tmp_path)

    with pytest.raises(MigrationError):
        apply_migration(src, repo)

    assert tree(tmp_path) == before
    assert (repo / "AGENTS.md").read_text() == "# Agents\n"
    assert (repo / ".gitattributes").read_text() == "*.png binary\n"


@pytest.mark.parametrize("name", WIRING_NAMES)
def test_plan_ignores_symlinked_wiring_file_and_writes_nothing(
    tmp_path: Path,
    src: Path,
    repo: Path,
    name: str,
) -> None:
    link_wiring(repo, name)
    before = tree(tmp_path)

    lines = plan_migration(src, repo)

    assert {line.file for line in lines} >= {"note.md", "other-fact.md"}
    assert tree(tmp_path) == before


def regular_claude(repo: Path) -> None:
    (repo / "AGENTS.md").write_text("# Agents\n")
    (repo / "CLAUDE.md").write_text("# Agents\n")


def regular_attrs(repo: Path) -> None:
    (repo / ".gitattributes").write_text("*.png binary\n")


def regular_settings(repo: Path) -> None:
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text('{"theme": "dark"}\n')


REGULAR = [
    ("CLAUDE.md", regular_claude, lambda text: IMPORT in text),
    (".gitattributes", regular_attrs, lambda text: GITATTRS in text),
    (
        ".claude/settings.json",
        regular_settings,
        lambda text: json.loads(text) == {"theme": "dark", "autoMemoryEnabled": False},
    ),
]


@pytest.mark.parametrize(("name", "setup", "check"), REGULAR)
def test_apply_writes_regular_wiring_file_with_same_content_as_symlink_case(
    src: Path,
    repo: Path,
    name: str,
    setup: Callable[[Path], None],
    check: Callable[[str], bool],
) -> None:
    setup(repo)

    apply_migration(src, repo)

    assert not (repo / name).is_symlink()
    assert check((repo / name).read_text())
    assert (repo / DEST / "note.md").is_file()
    assert (repo / DEST / "other-fact.md").is_file()


def dir_to_src(repo: Path, src: Path, outside: Path) -> None:
    os.symlink(src, repo / "docs")


def dir_to_outside(repo: Path, src: Path, outside: Path) -> None:
    os.symlink(outside, repo / "docs")


def claude_to_outside(repo: Path, src: Path, outside: Path) -> None:
    os.symlink(outside, repo / ".claude")


def nested_to_outside(repo: Path, src: Path, outside: Path) -> None:
    (repo / "docs").mkdir()
    os.symlink(outside, repo / "docs" / "dev")


# (case id, link builder, offending repo-relative path)
BAD_DIRS = [
    ("docs-to-src", dir_to_src, "docs"),
    ("docs-to-outside", dir_to_outside, "docs"),
    ("claude-to-outside", claude_to_outside, ".claude"),
    ("nested-to-outside", nested_to_outside, "docs/dev"),
]


@pytest.mark.parametrize("operation", [plan_migration, apply_migration])
@pytest.mark.parametrize(
    ("link", "offender"),
    [case[1:3] for case in BAD_DIRS],
    ids=[case[0] for case in BAD_DIRS],
)
def test_migration_refuses_symlinked_destination_directory_and_changes_nothing(
    tmp_path: Path,
    src: Path,
    repo: Path,
    outside: Path,
    operation: Callable[[Path, Path], object],
    link: Callable[[Path, Path, Path], None],
    offender: str,
) -> None:
    link(repo, src, outside)
    before = tree(tmp_path)

    with pytest.raises(MigrationError) as err:
        operation(src, repo)

    message = str(err.value)
    assert offender in message
    assert "symlink" in message or "resolves" in message
    assert tree(tmp_path) == before


@pytest.mark.parametrize("operation", [plan_migration, apply_migration])
def test_migration_refuses_dangling_destination_symlink_and_keeps_the_link(
    tmp_path: Path,
    src: Path,
    repo: Path,
    operation: Callable[[Path, Path], object],
) -> None:
    os.symlink("missing", repo / "docs")
    before = tree(tmp_path)

    with pytest.raises(MigrationError, match="docs: dangling symlink"):
        operation(src, repo)

    assert (repo / "docs").is_symlink()
    assert os.readlink(repo / "docs") == "missing"
    assert tree(tmp_path) == before


def test_apply_allows_symlinked_docs_resolving_to_unrelated_dir_inside_repo(
    src: Path,
    repo: Path,
) -> None:
    (repo / "real-docs").mkdir()
    os.symlink("real-docs", repo / "docs")
    source_before = tree(src)

    apply_migration(src, repo)

    assert (repo / "real-docs/dev/project-management/memory/note.md").is_file()
    assert (repo / DEST / "other-fact.md").is_file()
    assert (repo / "docs").is_symlink()
    assert tree(src) == source_before


def test_apply_allows_symlinked_claude_resolving_to_unrelated_dir_inside_repo(
    src: Path,
    repo: Path,
) -> None:
    (repo / "real-claude").mkdir()
    os.symlink("real-claude", repo / ".claude")

    apply_migration(src, repo)

    settings = json.loads((repo / "real-claude" / "settings.json").read_text())
    assert settings == {"autoMemoryEnabled": False}
    assert (repo / ".claude").is_symlink()


def test_plan_allows_symlinked_docs_resolving_to_unrelated_dir_inside_repo(
    tmp_path: Path,
    src: Path,
    repo: Path,
) -> None:
    (repo / "real-docs").mkdir()
    os.symlink("real-docs", repo / "docs")
    before = tree(tmp_path)

    lines = plan_migration(src, repo)

    assert {line.file for line in lines} >= {"note.md", "other-fact.md"}
    assert tree(tmp_path) == before
