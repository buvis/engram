"""Repository-owned shared project memory: schema, index and credential checks."""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

MEMORY_SUBDIR: tuple[str, ...] = ("docs", "dev", "project-management", "memory")
INDEX_NAME = "MEMORY.md"
INDEX_MAX_LINES = 200
INDEX_MAX_BYTES = 25_000
ALLOWED_TYPES = frozenset({"project", "feedback", "reference"})
FORBIDDEN_KEYS = ("author", "date")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
INDEX_ENTRY_RE = re.compile(r"^- \[(?P<title>[^\]]*)\]\((?P<slug>[^()/\s]+)\.md\)")
CREDENTIAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github-token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("github-pat", re.compile(r"github_pat_[A-Za-z0-9_]{22,}")),
    ("sk-key", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
)
_ABSENT = object()


@dataclass(frozen=True)
class MemoryFile:
    slug: str
    name: str
    description: str
    type: str
    source: str
    evidence: tuple[str, ...]
    body: str


def memory_dir(repo_root: Path) -> Path:
    """repo_root / docs/dev/project-management/memory (no existence check)."""
    return repo_root.joinpath(*MEMORY_SUBDIR)


def memory_files(directory: Path) -> list[Path]:
    """Sorted regular '*.md' files directly in directory, excluding MEMORY.md."""
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.iterdir()
        if p.suffix == ".md" and p.name != INDEX_NAME and p.is_file()
    )


def redact(text: str) -> str:
    """Replace every CREDENTIAL_PATTERNS match in text with '[redacted:<label>]'."""
    for label, pattern in CREDENTIAL_PATTERNS:
        text = pattern.sub(f"[redacted:{label}]", text)
    return text


def _credential_violations(text: str) -> list[str]:
    return [
        f"credential\t{label}"
        for label, pattern in CREDENTIAL_PATTERNS
        if pattern.search(text)
    ]


def _forbidden_keys(node: object, prefix: str, ancestors: set[int]) -> list[str]:
    if isinstance(node, dict):
        items = [(str(k), v) for k, v in node.items()]
    elif isinstance(node, list):
        items = [(str(i), v) for i, v in enumerate(node)]
    else:
        return []
    if id(node) in ancestors:
        return []
    ancestors.add(id(node))
    found = []
    for key, value in items:
        path = f"{prefix}.{key}" if prefix else key
        if key in FORBIDDEN_KEYS:
            found.append(f"forbidden-key\t{path}: Git records it")
        found += _forbidden_keys(value, path, ancestors)
    ancestors.discard(id(node))
    return found


def _field_violations(front: dict, stem: str) -> list[str]:
    found = []
    name = front.get("name")
    if not isinstance(name, str):
        found.append("name\tmissing")
    elif not NAME_RE.match(name):
        found.append(f"name\tmust match {NAME_RE.pattern}")
    elif name != stem:
        found.append(f"name\tdoes not match file stem {stem}")

    description = front.get("description")
    if not isinstance(description, str):
        found.append("description\tmissing")
    elif not description.strip():
        found.append("description\tempty")
    elif "\n" in description.strip():
        found.append("description\tmust be one line")

    metadata = front.get("metadata")
    if "type" in front:
        memory_type = front["type"]
    elif isinstance(metadata, dict) and "type" in metadata:
        memory_type = metadata["type"]
    else:
        memory_type = _ABSENT
    if memory_type is _ABSENT:
        found.append("type\tmissing")
    elif memory_type == "user":
        found.append("type\tuser memory belongs in host-global memory")
    elif not isinstance(memory_type, str) or memory_type not in ALLOWED_TYPES:
        found.append("type\tmust be one of " + ", ".join(sorted(ALLOWED_TYPES)))

    source = front.get("source")
    if not isinstance(source, str):
        found.append("source\tmissing")
    elif not source.strip():
        found.append("source\tempty")

    evidence = front.get("evidence")
    if "evidence" not in front:
        found.append("evidence\tmissing")
    elif not isinstance(evidence, list):
        found.append("evidence\tmust be a list")
    elif not evidence:
        found.append("evidence\tempty")
    else:
        found += [
            f"evidence\titem {i} empty or not a string"
            for i, item in enumerate(evidence)
            if not isinstance(item, str) or not item.strip()
        ]

    return found + _forbidden_keys(front, "", set())


def _split_frontmatter(text: str) -> tuple[object, str, str | None]:
    """Return (front, body, violation); violation is a 'frontmatter' detail."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None, "", "missing"
    end = next(
        (i for i in range(1, len(lines)) if lines[i].rstrip("\r\n") == "---"),
        None,
    )
    if end is None:
        return None, "", "unterminated"
    try:
        front = yaml.safe_load("".join(lines[1:end]))
    except yaml.YAMLError:
        return None, "", "unparseable"
    if not isinstance(front, dict):
        return None, "", "not a mapping"
    return front, "".join(lines[end + 1 :]), None


def parse_memory(path: Path) -> tuple[MemoryFile | None, list[str]]:
    """Return (record, violations). record is None iff violations is non-empty.
    Each violation string is '<rule>\\t<detail>'."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, [redact(f"read\tunreadable: {type(exc).__name__}")]

    front, body, problem = _split_frontmatter(text)
    if problem is not None:
        violations = [f"frontmatter\t{problem}"]
    else:
        violations = _field_violations(front, path.stem)
    violations += _credential_violations(text)
    if violations:
        return None, [redact(v) for v in violations]

    metadata = front.get("metadata")
    memory_type = front["type"] if "type" in front else metadata["type"]
    record = MemoryFile(
        slug=path.stem,
        name=front["name"],
        description=front["description"],
        type=memory_type,
        source=front["source"],
        evidence=tuple(front["evidence"]),
        body=body,
    )
    return record, []


def _index_violations(index: Path, files: list[Path]) -> list[str]:
    if not index.exists():
        return [f"{f}\tindex-missing-entry\t{f.name}" for f in files]
    try:
        raw = index.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{index}\tread\tunreadable: {type(exc).__name__}"]

    found = [f"{index}\t{v}" for v in _credential_violations(text)]
    lines = text.splitlines()
    entries = [m.group("slug") for line in lines if (m := INDEX_ENTRY_RE.match(line))]
    unique = list(dict.fromkeys(entries))
    names = {f.name for f in files}
    found += [
        f"{index}\tindex-missing-file\t{slug}.md"
        for slug in unique
        if f"{slug}.md" not in names
    ]
    found += [
        f"{f}\tindex-missing-entry\t{f.name}" for f in files if f.stem not in unique
    ]
    found += [
        f"{index}\tindex-duplicate\t{slug}.md"
        for slug in unique
        if entries.count(slug) > 1
    ]
    if entries != sorted(entries):
        found.append(f"{index}\tindex-unsorted\tentries must be sorted by slug")
    if len(lines) > INDEX_MAX_LINES:
        found.append(
            f"{index}\tindex-too-long\t{len(lines)} lines > {INDEX_MAX_LINES}",
        )
    if len(raw) > INDEX_MAX_BYTES:
        found.append(
            f"{index}\tindex-too-large\t{len(raw)} bytes > {INDEX_MAX_BYTES}",
        )
    return found


def check_directory(path: Path) -> list[str]:
    """All violations for one memory directory, each '<file>\\t<rule>\\t<detail>'.
    Per-file violations in memory_files order, then MEMORY.md violations.
    Not a directory -> ['<path>\\tdirectory\\tnot found']."""
    if not path.is_dir():
        return [redact(f"{path}\tdirectory\tnot found")]
    files = memory_files(path)
    found = []
    for file in files:
        _, violations = parse_memory(file)
        found += [f"{file}\t{v}" for v in violations]
    found += _index_violations(path / INDEX_NAME, files)
    return [redact(line) for line in found]
