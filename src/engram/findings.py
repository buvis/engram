from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

FINDINGS_CORPUS = "findings"

VERDICT_RE = re.compile(r"^Verdict:\s*(.+)$", re.M)
TESTS_RE = re.compile(r"^Tests:\s*(.+)$", re.M)
TABLE_SEPARATOR_CELL_RE = re.compile(r"^[-: ]+$")
BULLET_RE = re.compile(
    r"^\s*-\s+(?:\[\d+/\d+\]\s*)?[🔴🟠🟡⚪]\s*(?:\[\d+/\d+\]\s*)?(.*)$"
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
                cells = line[1:-1].split("|")
                is_separator = all(
                    TABLE_SEPARATOR_CELL_RE.fullmatch(cell) for cell in cells
                )
                next_is_separator = index + 1 < len(body_lines) and (
                    body_lines[index + 1].startswith("|")
                    and body_lines[index + 1].endswith("|")
                    and all(
                        TABLE_SEPARATOR_CELL_RE.fullmatch(cell)
                        for cell in body_lines[index + 1][1:-1].split("|")
                    )
                )

                if next_is_separator:
                    issue_column = next(
                        (
                            cell_index
                            for cell_index, cell in enumerate(cells)
                            if cell.strip().casefold() == "issue"
                        ),
                        None,
                    )
                elif not is_separator:
                    body = line.strip()
                    heading = (
                        cells[issue_column].strip()
                        if issue_column is not None and issue_column < len(cells)
                        else body
                    )
                    records.append(
                        Record(heading, body, line_number, line_number, True)
                    )
                index += 1
                continue

            issue_column = None
            bullet_match = BULLET_RE.match(line)
            if bullet_match:
                end_index = index
                while end_index + 1 < len(body_lines):
                    continuation = body_lines[end_index + 1]
                    if not continuation.strip() or not continuation[0].isspace():
                        break
                    end_index += 1

                body = "\n".join(body_lines[index : end_index + 1]).rstrip()
                bold_match = BOLD_RE.search(body)
                heading = (
                    bold_match.group(1)
                    if bold_match
                    else bullet_match.group(1).strip()
                )
                records.append(
                    Record(
                        heading,
                        body,
                        line_number,
                        frontmatter_end + end_index + 2,
                        True,
                    )
                )
                index = end_index + 1
                continue

            if line.strip():
                body = line.strip()
                records.append(
                    Record(current_heading, body, line_number, line_number, False)
                )
                heading_match = HEADING_RE.match(line)
                if heading_match:
                    current_heading = heading_match.group(1).strip()

            index += 1

        return records
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"unable to parse {path}") from exc
