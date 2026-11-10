"""Plan the migration of Claude auto-memory files into repository memory."""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from engram.memory import (
    _ABSENT,
    ALLOWED_TYPES,
    CREDENTIAL_PATTERNS,
    INDEX_MAX_BYTES,
    INDEX_MAX_LINES,
    MEMORY_SUBDIR,
    NAME_RE,
    _split_frontmatter,
    memory_dir,
    memory_files,
    parse_memory,
    redact,
)

ACTIONS = (
    "migrate",
    "skip-user",
    "skip-credential",
    "skip-invalid",
    "skip-exists",
    "skip-identical",
)
OK_ACTIONS = frozenset({"migrate", "skip-identical"})
EVIDENCE_PLACEHOLDER = "none recorded before migration"
SOURCE_PREFIX = "migrated:claude-auto-memory/"
GITATTRIBUTES_LINE = "docs/dev/project-management/memory/MEMORY.md merge=union"
CLAUDE_IMPORT_LINE = "@docs/dev/project-management/memory/MEMORY.md"
AGENTS_HEADING = "## Project memory"
HOST_PATH_RE = re.compile(
    r"(?<![\w.:/~-])/(?:Users|home|root|private|tmp|var|opt|Volumes|mnt|srv|etc)/"
)
USER_DETAIL = "user memory stays in host-global memory"
HOST_DETAIL = "contains an absolute host path"
TARGET_PREFIX = "/".join(MEMORY_SUBDIR) + "/"
_FLATTEN = str.maketrans("\t\r\n", "   ")


@dataclass(frozen=True)
class MigrationLine:
    file: str
    action: str
    detail: str

    def tsv(self) -> str:
        file = self.file.translate(_FLATTEN)
        detail = self.detail.translate(_FLATTEN)
        return redact(f"{file}\t{self.action}\t{detail}")


class MigrationError(Exception):
    """Refusal before any write."""


@dataclass(frozen=True)
class _Candidate:
    """A source file that passed pass A and will be rendered into the repo."""

    file: str
    slug: str
    description: str
    kind: str
    body: str


def contains_host_path(text: str, src: Path) -> bool:
    markers = {str(src.resolve()), str(src.absolute()), str(Path.home())}
    return bool(HOST_PATH_RE.search(text)) or any(m in text for m in markers)


def _credential_labels(*texts: str) -> list[str]:
    return [
        label
        for label, pattern in CREDENTIAL_PATTERNS
        if any(pattern.search(text) for text in texts)
    ]


def _memory_type(front: dict) -> object:
    metadata = front.get("metadata")
    if "type" in front:
        return front["type"]
    if isinstance(metadata, dict) and "type" in metadata:
        return metadata["type"]
    return _ABSENT


def _field_problem(
    front: dict, kind: object, slug: str, body: str, src: Path
) -> str | None:
    name = front.get("name")
    description = front.get("description")
    if not isinstance(name, str) or not name:
        return "name missing"
    if not isinstance(description, str):
        return "description missing"
    if not description.strip():
        return "description empty"
    if "\n" in description.strip():
        return "description must be one line"
    if kind is _ABSENT:
        return "type missing"
    if not isinstance(kind, str) or kind not in ALLOWED_TYPES:
        return "type must be one of " + ", ".join(sorted(ALLOWED_TYPES))
    if not NAME_RE.fullmatch(slug):
        return f"slug {slug} must match {NAME_RE.pattern}"
    if slug.casefold() == "memory":
        return "slug memory collides with MEMORY.md"
    if contains_host_path(description, src) or contains_host_path(body, src):
        return HOST_DETAIL
    return None


def _classify_source(path: Path, src: Path) -> MigrationLine | _Candidate:
    """Pass A: rules 1-5 on the source text alone."""
    file = path.name
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return MigrationLine(file, "skip-invalid", "unreadable")
    front, body, problem = _split_frontmatter(text)
    if problem is not None:
        return MigrationLine(file, "skip-invalid", f"frontmatter {problem}")
    kind = _memory_type(front)
    if kind == "user":
        return MigrationLine(file, "skip-user", USER_DETAIL)
    slug = path.stem.lower().replace("_", "-")
    labels = _credential_labels(text, file, slug, SOURCE_PREFIX + file)
    if labels:
        return MigrationLine(file, "skip-credential", ",".join(labels))
    problem = _field_problem(front, kind, slug, body, src)
    if problem is not None:
        return MigrationLine(file, "skip-invalid", problem)
    return _Candidate(file, slug, front["description"].strip(), kind, body)


def _mark_collisions(
    results: list[MigrationLine | _Candidate],
) -> list[MigrationLine | _Candidate]:
    """Pass A rule 6: every candidate sharing a slug is skipped."""
    groups: dict[str, list[str]] = {}
    for result in results:
        if isinstance(result, _Candidate):
            groups.setdefault(result.slug, []).append(result.file)
    return [
        (
            MigrationLine(
                r.file,
                "skip-invalid",
                "slug collision: " + ", ".join(sorted(groups[r.slug])),
            )
            if isinstance(r, _Candidate) and len(groups[r.slug]) > 1
            else r
        )
        for r in results
    ]


def _render(slug: str, description: str, kind: str, file: str, body: str) -> str:
    front = yaml.safe_dump(
        {
            "name": slug,
            "description": description.strip(),
            "type": kind,
            "source": SOURCE_PREFIX + file,
            "evidence": [EVIDENCE_PLACEHOLDER],
        },
        sort_keys=False,
        allow_unicode=True,
        width=10_000,
    )
    return f"---\n{front}---\n{body}"


def _render_index(entries: list[tuple[str, str, str]]) -> str:
    """MEMORY.md text for (slug, name, description) entries, sorted by slug."""
    lines = [
        f"- [{name}]({slug}.md) — {description.strip()}"
        for slug, name, description in sorted(entries, key=lambda e: e[0])
    ]
    return "\n".join(lines) + "\n" if lines else ""


def _finish(
    candidate: _Candidate, renames: dict[str, str], target_dir: Path, src: Path
) -> MigrationLine:
    """Pass B: render with link rewriting, re-scan, compare against the target."""
    body = candidate.body
    for stem, slug in renames.items():
        body = body.replace(f"[[{stem}]]", f"[[{slug}]]")
    c = candidate
    text = _render(c.slug, c.description, c.kind, c.file, body)
    final = text + _render_index([(c.slug, c.slug, c.description)])
    labels = _credential_labels(final)
    if labels:
        return MigrationLine(c.file, "skip-credential", ",".join(labels))
    if contains_host_path(final, src):
        return MigrationLine(c.file, "skip-invalid", HOST_DETAIL)
    target = target_dir / f"{c.slug}.md"
    detail = TARGET_PREFIX + target.name
    if not target.exists():
        return MigrationLine(c.file, "migrate", detail)
    same = target.read_bytes() == text.encode("utf-8")
    return MigrationLine(c.file, "skip-identical" if same else "skip-exists", detail)


def _check_paths(src: Path, repo_root: Path) -> None:
    for label, path in (("source", src), ("repository", repo_root)):
        if not path.is_dir():
            raise MigrationError(redact(f"{label} is not a directory: {path}"))
    written = {
        repo_root,
        memory_dir(repo_root).resolve(),
        (repo_root / ".claude").resolve(),
    }
    if src in written:
        raise MigrationError(redact(f"source {src} is a directory migrate writes into"))
    aliased = [
        p.name for p in memory_files(src) if p.resolve().is_relative_to(repo_root)
    ]
    if aliased:
        raise MigrationError(
            redact("source files resolve inside the repository: " + ", ".join(aliased))
        )


def _existing_entries(target_dir: Path, src: Path) -> list[tuple[str, str, str]]:
    """Index entries of existing target files; refuse if any is invalid."""
    entries: list[tuple[str, str, str]] = []
    bad: list[str] = []
    for path in memory_files(target_dir):
        record, violations = parse_memory(path)
        if record is None:
            reason = violations[0].translate(_FLATTEN)
            bad.append(f"{path.name} ({reason})")
            continue
        entry = (record.slug, record.name, record.description)
        text = path.read_text(encoding="utf-8") + _render_index([entry])
        if contains_host_path(text, src):
            bad.append(f"{path.name} ({HOST_DETAIL})")
            continue
        entries.append(entry)
    if bad:
        raise MigrationError(redact("invalid existing memory files: " + "; ".join(bad)))
    return entries


def plan_migration(src: Path, repo_root: Path) -> list[MigrationLine]:
    """Classify every source memory file; write nothing."""
    root, repo = src.resolve(), repo_root.resolve()
    _check_paths(root, repo)
    target_dir = memory_dir(repo)
    existing = _existing_entries(target_dir, src)
    results = _mark_collisions([_classify_source(p, src) for p in memory_files(root)])
    candidates = [r for r in results if isinstance(r, _Candidate)]
    renames = {
        Path(c.file).stem: c.slug for c in candidates if Path(c.file).stem != c.slug
    }
    finished = {c.file: _finish(c, renames, target_dir, src) for c in candidates}
    new = [
        (c.slug, c.slug, c.description)
        for c in candidates
        if finished[c.file].action == "migrate"
    ]
    index = _render_index(existing + new)
    lines, size = len(index.splitlines()), len(index.encode("utf-8"))
    if lines > INDEX_MAX_LINES or size > INDEX_MAX_BYTES:
        raise MigrationError(
            f"MEMORY.md would have {lines} lines and {size} bytes, limits are "
            f"{INDEX_MAX_LINES} lines and {INDEX_MAX_BYTES} bytes"
        )
    return [r if isinstance(r, MigrationLine) else finished[r.file] for r in results]
