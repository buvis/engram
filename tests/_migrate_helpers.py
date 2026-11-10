"""Shared constants, fixture data and helpers for the memory migration tests."""

import json
from pathlib import Path

import yaml

from engram.memory import INDEX_ENTRY_RE, memory_dir
from engram.migrate import AGENTS_SECTION, MigrationLine

DEST = "docs/dev/project-management/memory/"
TOKEN = "ghp_" + "A1b2C3d4E5" * 3 + "F6g7H8"  # github-token: ghp_ + 36 alnum
AWS_KEY = "AKIA" + "ABCDEFGHIJ234567"  # aws-access-key: AKIA + 16
SK_STEM = "SK_ABCDEFGHIJKLMNOPQRST"
SK_SLUG = "sk-" + "abcdefghijklmnopqrst"  # slug of SK_STEM, an sk-key match
USER_SKIP = "user memory stays in host-global memory"
HOST = "contains an absolute host path"
GITATTRS = "docs/dev/project-management/memory/MEMORY.md merge=union\n"
IMPORT = "@docs/dev/project-management/memory/MEMORY.md\n"


def memory_text(front: object, body: str = "Body.\n") -> str:
    dumped = yaml.safe_dump(front, sort_keys=False, allow_unicode=True, width=100_000)
    return f"---\n{dumped}---\n{body}"


def valid(
    name: str = "note",
    description: str = "A fact",
    kind: str = "project",
    body: str = "Body.\n",
    **extra: object,
) -> str:
    front = {"name": name, "description": description, "type": kind, **extra}
    return memory_text(front, body)


def write(directory: Path, filename: str, content: str | bytes) -> Path:
    path = directory / filename
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def rendered(slug: str, description: str, kind: str, source: str, body: str) -> bytes:
    front = yaml.safe_dump(
        {
            "name": slug,
            "description": description.strip(),
            "type": kind,
            "source": "migrated:claude-auto-memory/" + source,
            "evidence": ["none recorded before migration"],
        },
        sort_keys=False,
        allow_unicode=True,
        width=10_000,
    )
    return f"---\n{front}---\n{body}".encode()


def write_target(repo: Path, slug: str, content: bytes | None = None) -> Path:
    target_dir = memory_dir(repo)
    target_dir.mkdir(parents=True, exist_ok=True)
    default = rendered(slug, "Existing fact", "project", f"{slug}.md", "Kept.\n")
    path = target_dir / f"{slug}.md"
    path.write_bytes(default if content is None else content)
    return path


def snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        str(p.relative_to(root)): None if p.is_dir() else p.read_bytes()
        for p in sorted(root.rglob("*"))
    }


def mtimes(root: Path) -> dict[str, int]:
    return {str(p.relative_to(root)): p.stat().st_mtime_ns for p in root.rglob("*")}


def triples(lines: list[MigrationLine]) -> list[tuple[str, str, str]]:
    return [(line.file, line.action, line.detail) for line in lines]


def index_slugs(repo: Path) -> list[str]:
    text = (memory_dir(repo) / "MEMORY.md").read_text(encoding="utf-8")
    matches = (INDEX_ENTRY_RE.match(line) for line in text.splitlines())
    return [m.group("slug") for m in matches if m]


def settings_json(obj: dict) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


KEPT_ATTRS = "*.png binary\r\n  " + GITATTRS[:-1] + "  \r\n"
KEPT_AGENTS = "# A\n\n  ## Project memory \r\nOld text\n"
KEPT_CLAUDE = "@AGENTS.md\n" + IMPORT[:-1] + "\r\n"
NEAR_ATTRS = GITATTRS[:-1] + " -diff\n"
NEAR_AGENTS = "## Project memory notes\n"

# (wiring file, content before apply or None when absent, content after apply)
WIRING = [
    (".gitattributes", None, GITATTRS),
    (".gitattributes", "", GITATTRS),
    (".gitattributes", "*.png binary", "*.png binary\n" + GITATTRS),
    (".gitattributes", "# " + GITATTRS, "# " + GITATTRS + GITATTRS),
    (".gitattributes", NEAR_ATTRS, NEAR_ATTRS + GITATTRS),
    (".gitattributes", KEPT_ATTRS, KEPT_ATTRS),
    ("AGENTS.md", None, AGENTS_SECTION),
    ("AGENTS.md", "", AGENTS_SECTION),
    ("AGENTS.md", "# Agents", "# Agents\n\n" + AGENTS_SECTION),
    ("AGENTS.md", NEAR_AGENTS, NEAR_AGENTS + "\n" + AGENTS_SECTION),
    ("AGENTS.md", KEPT_AGENTS, KEPT_AGENTS),
    ("CLAUDE.md", None, "@AGENTS.md\n" + IMPORT),
    ("CLAUDE.md", "", IMPORT),
    ("CLAUDE.md", "@AGENTS.md", "@AGENTS.md\n" + IMPORT),
    ("CLAUDE.md", "see " + IMPORT, "see " + IMPORT + IMPORT),
    ("CLAUDE.md", KEPT_CLAUDE, KEPT_CLAUDE),
]

COMPACT_FALSE = '{"z":1,"autoMemoryEnabled":false}'
CAFE = {"theme": "dark", "env": {"NAME": "Café"}}
# (settings.json before apply, settings.json after apply)
SETTINGS = [
    (json.dumps(CAFE), settings_json({**CAFE, "autoMemoryEnabled": False})),
    (
        '{"autoMemoryEnabled": true, "z": 1}',
        settings_json({"autoMemoryEnabled": False, "z": 1}),
    ),
    ('{"autoMemoryEnabled": 0}', settings_json({"autoMemoryEnabled": False})),
    (COMPACT_FALSE, COMPACT_FALSE),
]

# (wiring file, unusable content) that apply must refuse before writing anything
REFUSALS = [
    (".claude/settings.json", b"[]\n"),
    (".claude/settings.json", b'{"autoMemoryEnabled": false'),
    (".claude/settings.json", b'"autoMemoryEnabled"\n'),
    ("CLAUDE.md", b"@AGENTS.md\n\xff\xfe\n"),
    ("AGENTS.md", b"# Agents\n\xff\n"),
]
