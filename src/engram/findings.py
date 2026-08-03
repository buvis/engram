from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from engram.client import EngramConfig, embed, resolve_pinned_entry
from engram.store import Chunk, ChunkWithVector, Store

FINDINGS_CORPUS = "findings"

VERDICT_RE = re.compile(r"^Verdict:\s*(.+)$", re.MULTILINE)
TESTS_RE = re.compile(r"^Tests:\s*(.+)$", re.MULTILINE)
TABLE_SEPARATOR_CELL_RE = re.compile(r"^[-: ]+$")
BULLET_RE = re.compile(
    r"^\s*-\s+(?:\[\d+/\d+\]\s*)?[🔴🟠🟡⚪]\s*(?:\[\d+/\d+\]\s*)?(.*)$",
)
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
HEADING_RE = re.compile(r"^#+\s+(.*)$")


@dataclass(frozen=True)
class Record:
    heading: str
    body: str
    line_start: int
    line_end: int
    structured: bool


def _is_separator_row(line: str) -> bool:
    if not (line.startswith("|") and line.endswith("|")):
        return False
    cells = line[1:-1].split("|")
    return all(TABLE_SEPARATOR_CELL_RE.fullmatch(cell) for cell in cells)


def _parse_table_row(
    records: list[Record],
    body_lines: list[str],
    index: int,
    line: str,
    line_number: int,
    issue_column: int | None,
) -> int | None:
    cells = line[1:-1].split("|")
    is_separator = _is_separator_row(line)
    next_line = body_lines[index + 1] if index + 1 < len(body_lines) else None
    next_is_separator = next_line is not None and _is_separator_row(next_line)

    if next_is_separator:
        return next(
            (
                cell_index
                for cell_index, cell in enumerate(cells)
                if cell.strip().casefold() == "issue"
            ),
            None,
        )
    if is_separator:
        return issue_column

    body = line.strip()
    heading = (
        cells[issue_column].strip()
        if issue_column is not None and issue_column < len(cells)
        else body
    )
    records.append(Record(heading, body, line_number, line_number, True))
    return issue_column


def _parse_bullet(
    records: list[Record],
    body_lines: list[str],
    index: int,
    bullet_match: re.Match[str],
    frontmatter_end: int,
) -> int:
    line_number = frontmatter_end + index + 2
    end_index = index
    while end_index + 1 < len(body_lines):
        continuation = body_lines[end_index + 1]
        if not continuation.strip() or not continuation[0].isspace():
            break
        end_index += 1

    body = "\n".join(body_lines[index : end_index + 1]).rstrip()
    bold_match = BOLD_RE.search(body)
    heading = bold_match.group(1) if bold_match else bullet_match.group(1).strip()
    records.append(
        Record(heading, body, line_number, frontmatter_end + end_index + 2, True),
    )
    return end_index + 1


def _parse_unstructured(
    records: list[Record],
    line: str,
    line_number: int,
    current_heading: str,
) -> str:
    if not line.strip():
        return current_heading

    body = line.strip()
    records.append(Record(current_heading, body, line_number, line_number, False))

    heading_match = HEADING_RE.match(line)
    return heading_match.group(1).strip() if heading_match else current_heading


def parse(path: Path) -> list[Record]:
    try:
        lines = path.read_text().splitlines()
        if not lines or lines[0] != "---":
            raise ValueError("missing frontmatter")

        frontmatter_end = lines.index("---", 1)

        metadata = yaml.safe_load("\n".join(lines[1:frontmatter_end]))
        if not isinstance(metadata, Mapping) or not metadata.get("reviewers"):
            raise ValueError("frontmatter must contain reviewers")

        body_lines = lines[frontmatter_end + 1 :]
        body_text = "\n".join(body_lines)
        if not VERDICT_RE.search(body_text):
            raise ValueError("missing verdict")
        if not TESTS_RE.search(body_text):
            raise ValueError("missing tests")

        records: list[Record] = []
        current_heading = ""
        issue_column: int | None = None
        index = 0
        while index < len(body_lines):
            line = body_lines[index]
            line_number = frontmatter_end + index + 2
            if line.startswith("|") and line.endswith("|"):
                issue_column = _parse_table_row(
                    records, body_lines, index, line, line_number, issue_column,
                )
                index += 1
                continue
            issue_column = None
            bullet_match = BULLET_RE.match(line)
            if bullet_match:
                index = _parse_bullet(
                    records, body_lines, index, bullet_match, frontmatter_end,
                )
                continue
            current_heading = _parse_unstructured(
                records, line, line_number, current_heading,
            )
            index += 1

        return records
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"unable to parse {path}") from exc


def upsert(
    store: Store,
    config: EngramConfig,
    repo: str,
    path: Path,
    records: list[Record],
) -> int:
    chunks = [
        Chunk(
            corpus=FINDINGS_CORPUS,
            repo=repo,
            doc_type="finding",
            path=str(path),
            heading=record.heading,
            body=record.body,
            line_start=record.line_start,
            line_end=record.line_end,
            content_hash=hashlib.sha1(record.body.encode()).hexdigest(),
            chunk_ordinal=i,
        )
        for i, record in enumerate(records)
    ]
    texts = [c.text_for_embedding for c in chunks]

    vectors = embed(texts, resolve_pinned_entry(config)) if texts else []

    items = [ChunkWithVector(chunk=c, vector=v) for c, v in zip(chunks, vectors)]
    store.replace_chunks_for_source(FINDINGS_CORPUS, str(path), items)

    return len(records)
