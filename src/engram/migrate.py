"""Plan and apply the migration of Claude auto-memory files into repository memory."""

import json
import os
import re
import stat
import tempfile
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
    check_directory,
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
AGENTS_SECTION = f"""{AGENTS_HEADING}

Durable project facts live in `docs/dev/project-management/memory/`, one
`<slug>.md` file per fact. Frontmatter fields:

- `name`: equals the file stem.
- `description`: one line.
- `type`: `project`, `feedback`, or `reference`.
- `source`: where the fact came from.
- `evidence`: a non-empty list.

Leave out `author` and `date`; git records them. `MEMORY.md` is the sorted
index of every memory file.

Memory must be public-safe: no secrets, personal facts, or host-private
facts. Those belong in host-global memory.

Read `MEMORY.md` before starting work. Make one `docs(memory): <verb> <slug>`
commit per change. Validate with `engram memory check`.
"""
HOST_PATH_RE = re.compile(
    r"(?<![\w.:/~-])/(?:Users|home|root|private|tmp|var|opt|Volumes|mnt|srv|etc)/",
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
    """Refusal before any write, or a failed apply after rollback."""


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
    front: dict,
    kind: object,
    slug: str,
    body: str,
    src: Path,
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
    candidate: _Candidate,
    renames: dict[str, str],
    target_dir: Path,
    src: Path,
) -> tuple[MigrationLine, str]:
    """Pass B: render with link rewriting, re-scan, compare against the target."""
    body = candidate.body
    for stem, slug in renames.items():
        body = body.replace(f"[[{stem}]]", f"[[{slug}]]")
    c = candidate
    text = _render(c.slug, c.description, c.kind, c.file, body)
    final = text + _render_index([(c.slug, c.slug, c.description)])
    labels = _credential_labels(final)
    if labels:
        return MigrationLine(c.file, "skip-credential", ",".join(labels)), text
    if contains_host_path(final, src):
        return MigrationLine(c.file, "skip-invalid", HOST_DETAIL), text
    target = target_dir / f"{c.slug}.md"
    detail = TARGET_PREFIX + target.name
    if not target.exists():
        return MigrationLine(c.file, "migrate", detail), text
    same = target.read_bytes() == text.encode("utf-8")
    action = "skip-identical" if same else "skip-exists"
    return MigrationLine(c.file, action, detail), text


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
            redact("source files resolve inside the repository: " + ", ".join(aliased)),
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
    return _plan(src, repo_root)[0]


def _plan(
    src: Path,
    repo_root: Path,
) -> tuple[list[MigrationLine], dict[Path, bytes]]:
    """Plan lines plus the bytes of every migrated file and MEMORY.md, in order."""
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
    migrated = [c for c in candidates if finished[c.file][0].action == "migrate"]
    new = [(c.slug, c.slug, c.description) for c in migrated]
    index = _render_index(existing + new)
    lines, size = len(index.splitlines()), len(index.encode("utf-8"))
    if lines > INDEX_MAX_LINES or size > INDEX_MAX_BYTES:
        raise MigrationError(
            f"MEMORY.md would have {lines} lines and {size} bytes, limits are "
            f"{INDEX_MAX_LINES} lines and {INDEX_MAX_BYTES} bytes",
        )
    writes = {
        target_dir / f"{c.slug}.md": finished[c.file][1].encode("utf-8")
        for c in migrated
    }
    writes[target_dir / "MEMORY.md"] = index.encode("utf-8")
    lines = [r if isinstance(r, MigrationLine) else finished[r.file][0] for r in results]
    return lines, writes


def _write_if_changed(path: Path, data: bytes) -> None:
    """Atomically replace path with data through a unique temporary file."""
    if path.exists() and path.read_bytes() == data:
        return
    if path.exists():
        mode = stat.S_IMODE(path.stat().st_mode)
    else:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_wiring(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise MigrationError(redact(f"{path}: not UTF-8 text")) from error


def _appended(text: str | None, line: str, addition: str, fresh: str) -> str:
    """text with addition appended unless a line already equals line."""
    if text is None:
        return fresh
    if any(old.rstrip("\r\n").strip() == line for old in text.splitlines()):
        return text
    if text and not text.endswith("\n"):
        text += "\n"
    return text + addition


def _settings_text(path: Path) -> str:
    text = _read_wiring(path)
    obj: object = {}
    if text is not None:
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            obj = None
        if not isinstance(obj, dict):
            raise MigrationError(redact(f"{path}: not a JSON object"))
        if obj.get("autoMemoryEnabled") is False:
            return text
    settings = {**obj, "autoMemoryEnabled": False}
    return json.dumps(settings, indent=2, ensure_ascii=False) + "\n"


def _plan_wiring(repo_root: Path) -> dict[Path, bytes]:
    """New bytes for every wiring file that must change; write nothing."""
    attrs, agents, claude = (
        repo_root / name for name in (".gitattributes", "AGENTS.md", "CLAUDE.md")
    )
    settings = repo_root / ".claude" / "settings.json"
    agents_text = _read_wiring(agents)
    new = {
        attrs: _appended(
            _read_wiring(attrs),
            GITATTRIBUTES_LINE,
            GITATTRIBUTES_LINE + "\n",
            GITATTRIBUTES_LINE + "\n",
        ),
        agents: _appended(
            agents_text,
            AGENTS_HEADING,
            "\n" + AGENTS_SECTION if agents_text else AGENTS_SECTION,
            AGENTS_SECTION,
        ),
        claude: _appended(
            _read_wiring(claude),
            CLAUDE_IMPORT_LINE,
            CLAUDE_IMPORT_LINE + "\n",
            "@AGENTS.md\n" + CLAUDE_IMPORT_LINE + "\n",
        ),
        settings: _settings_text(settings),
    }
    return {
        path: text.encode("utf-8")
        for path, text in new.items()
        if _read_wiring(path) != text
    }


def _restore(journal: list[tuple[Path, bytes | None]]) -> list[str]:
    """Undo journaled writes in reverse order; return the paths left unrestored."""
    failed: list[str] = []
    for path, original in reversed(journal):
        try:
            if original is not None:
                _write_if_changed(path, original)
            elif path.is_dir():
                path.rmdir()
            else:
                path.unlink(missing_ok=True)
        except OSError:
            failed.append(str(path))
    return failed


def apply_migration(src: Path, repo_root: Path) -> list[MigrationLine]:
    """Write the planned memory files, MEMORY.md and wiring; roll back on failure."""
    lines, writes = _plan(src, repo_root)
    repo = repo_root.resolve()
    wiring = _plan_wiring(repo)
    target_dir = memory_dir(repo)
    rel = target_dir.relative_to(repo).parts
    dirs = [repo.joinpath(*rel[:i]) for i in range(1, len(rel) + 1)]
    journal: list[tuple[Path, bytes | None]] = [
        (d, None) for d in (*dirs, repo / ".claude") if not d.exists()
    ]
    journal += [
        (p, p.read_bytes() if p.exists() else None) for p in (*writes, *wiring)
    ]
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        for path, data in (*writes.items(), *wiring.items()):
            path.parent.mkdir(exist_ok=True)
            _write_if_changed(path, data)
        problems = check_directory(target_dir)
        if problems:
            raise MigrationError("postcondition failed: " + "; ".join(map(str, problems)))
    except (OSError, MigrationError) as error:
        failed = _restore(journal)
        message = f"apply failed, repository restored: {error}"
        if failed:
            message += "; could not restore: " + ", ".join(failed)
        raise MigrationError(redact(message)) from error
    return lines
