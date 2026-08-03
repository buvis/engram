"""Map unified-diff hunks to the source symbols (functions/classes) they change."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tree_sitter_language_pack import ProcessConfig, detect_language_from_path, process

_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass(frozen=True)
class Symbol:
    path: str
    name: str
    kind: str
    line_start: int
    line_end: int


def changed_symbols(
    diff_path: Path,
    repo_root: Path,
    source_ref: str | None = None,
) -> list[Symbol]:
    lines = diff_path.read_text(errors="replace").splitlines()
    sections = _split_sections(lines)

    seen: set[tuple[str, str, int, int]] = set()
    results: list[Symbol] = []

    def _add(symbol: Symbol) -> None:
        key = (symbol.path, symbol.name, symbol.line_start, symbol.line_end)
        if key not in seen:
            seen.add(key)
            results.append(symbol)

    for section in sections:
        # ponytail: paths with spaces handled via the +++/--- lines; git's C-quoted
        # form ("b/caf\303\251.py") is not unquoted - decode it here if non-ASCII
        # paths ever show up in a reviewed diff.
        plus_line = next((line for line in section if line.startswith("+++ ")), None)
        if plus_line is None:
            continue
        is_deletion = plus_line == "+++ /dev/null"
        if is_deletion:
            minus_line = next(
                (line for line in section if line.startswith("--- ")), None
            )
            if minus_line is None:
                continue
            rel_path = minus_line[4:]
            rel_path = rel_path.removeprefix("a/")
        else:
            rel_path = plus_line[4:]
            rel_path = rel_path.removeprefix("b/")
        abs_path = str(repo_root / rel_path)
        name = Path(rel_path).name

        if is_deletion:
            _add(_file_symbol(abs_path, name, 1))
            continue

        language = detect_language_from_path(abs_path)
        structure = None
        if language is not None:
            content = _read_content(repo_root, rel_path, source_ref)
            if content is not None:
                structure = process(
                    content,
                    ProcessConfig(language, structure=True),
                ).structure

        for c, body in _hunks(section):
            changed = _changed_lines(body, c)
            if not changed:
                _add(_file_symbol(abs_path, name, c))
                continue
            for line in changed:
                item = _smallest_enclosing(structure, line) if structure else None
                if item is not None:
                    _add(
                        Symbol(
                            path=abs_path,
                            name=item.name,
                            kind=str(item.kind).lower(),
                            line_start=item.span.start_line + 1,
                            line_end=item.span.end_line + 1,
                        ),
                    )
                else:
                    _add(_file_symbol(abs_path, name, line))

    return results


def _file_symbol(path: str, name: str, line: int) -> Symbol:
    return Symbol(path=path, name=name, kind="file", line_start=line, line_end=line)


def _split_sections(lines: list[str]) -> list[list[str]]:
    indices = [i for i, line in enumerate(lines) if line.startswith("diff --git ")]
    sections = []
    for idx, i in enumerate(indices):
        end = indices[idx + 1] if idx + 1 < len(indices) else len(lines)
        sections.append(lines[i:end])
    return sections


def _hunks(section: list[str]) -> list[tuple[int, list[str]]]:
    indices = [i for i, line in enumerate(section) if _HUNK_HEADER_RE.match(line)]
    hunks = []
    for idx, i in enumerate(indices):
        match = _HUNK_HEADER_RE.match(section[i])
        c = int(match.group(1))
        end = indices[idx + 1] if idx + 1 < len(indices) else len(section)
        hunks.append((c, section[i + 1 : end]))
    return hunks


def _changed_lines(body: list[str], start: int) -> list[int]:
    counter = start
    changed = []
    for line in body:
        marker = line[:1]
        if marker == "+":
            changed.append(counter)
            counter += 1
        elif marker == " ":
            counter += 1
        # '-' lines have no post-image line: counter stays put
    return changed


def _smallest_enclosing(items, line: int):
    for item in items:
        start = item.span.start_line + 1
        end = item.span.end_line + 1
        if start <= line <= end:
            return _smallest_enclosing(item.children, line) or item
    return None


def _read_content(repo_root: Path, rel_path: str, source_ref: str | None) -> str | None:
    if source_ref is None:
        try:
            return (repo_root / rel_path).read_text(errors="replace")
        except OSError:
            return None

    result = subprocess.run(
        ["git", "show", f"{source_ref}:{rel_path}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        errors="replace",
    )
    if result.returncode != 0:
        return None
    return result.stdout
