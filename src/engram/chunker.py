"""Split a Markdown file into flat heading-delimited chunks."""

import re
from pathlib import Path

from engram.store import Chunk

_HEADING_RE = re.compile(r"^#{1,6}(?:\s|$)")


def chunk_markdown(
    path: Path, corpus: str, repo: str, content_hash: str
) -> list[Chunk]:
    text = path.read_text()
    if not text.strip():
        return []

    # Remove trailing newline so split doesn't produce a phantom empty last line
    lines = text.rstrip("\n").split("\n")

    heading_indices = [
        i for i, line in enumerate(lines) if _HEADING_RE.match(line)
    ]

    if not heading_indices:
        # No headings — single preamble chunk (content already verified non-empty)
        return [
            Chunk(
                corpus=corpus,
                repo=repo,
                doc_type="md",
                path=str(path),
                heading="",
                body="\n".join(lines).rstrip(),
                line_start=1,
                line_end=len(lines),
                content_hash=content_hash,
                chunk_ordinal=0,
            )
        ]

    chunks: list[Chunk] = []
    ordinal = 0

    # Preamble (text before first heading)
    first_heading = heading_indices[0]
    if first_heading > 0:
        preamble_lines = lines[0:first_heading]
        if any(line.strip() for line in preamble_lines):
            chunks.append(
                Chunk(
                    corpus=corpus,
                    repo=repo,
                    doc_type="md",
                    path=str(path),
                    heading="",
                    body="\n".join(preamble_lines).rstrip(),
                    line_start=1,
                    line_end=first_heading,
                    content_hash=content_hash,
                    chunk_ordinal=ordinal,
                )
            )
            ordinal += 1

    # Heading chunks
    for idx, h_idx in enumerate(heading_indices):
        heading_text = re.sub(r"^#+\s*", "", lines[h_idx]).strip()

        next_h = heading_indices[idx + 1] if idx + 1 < len(heading_indices) else None
        body_lines = lines[h_idx + 1 : next_h] if next_h is not None else lines[h_idx + 1 :]

        line_end = next_h if next_h is not None else len(lines)

        chunks.append(
            Chunk(
                corpus=corpus,
                repo=repo,
                doc_type="md",
                path=str(path),
                heading=heading_text,
                body="\n".join(body_lines).rstrip(),
                line_start=h_idx + 1,
                line_end=line_end,
                content_hash=content_hash,
                chunk_ordinal=ordinal,
            )
        )
        ordinal += 1

    return chunks
