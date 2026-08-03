"""Context pack builder: reindex, retrieve, and render a diff-scoped pack."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from engram.client import embed, resolve_pinned_entry
from engram.diffmap import Symbol, changed_symbols
from engram.findings import FINDINGS_CORPUS
from engram.indexer import IndexReport, index
from engram.query import Pointer, query
from engram.store import Scope

MAX_SYMBOLS_PER_PACK = 40
RETRIEVAL_K = 5

_FRESHNESS_LINE = "Portfolio freshness: NOT refreshed this cycle (PRD 00002 pending)"
_SECTION_ORDER = ["Similar code", "Reuse precedent", "Findings precedent", "Task prose"]


@dataclass(frozen=True)
class PackSection:
    label: str
    body: str
    estimated_tokens: int


@dataclass(frozen=True)
class PackReport:
    path: Path
    sections: list[PackSection]
    total_estimated_tokens: int
    trimmed_sections: list[str]
    symbols_omitted: int
    index_report: IndexReport


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _symbol_query_text(symbol: Symbol, repo_root: Path, source_ref: str | None) -> str:
    try:
        if source_ref is None:
            content = Path(symbol.path).read_text(errors="replace")
        else:
            rel_path = Path(symbol.path).relative_to(repo_root)
            result = subprocess.run(
                ["git", "show", f"{source_ref}:{rel_path}"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                errors="replace",
            )
            if result.returncode != 0:
                raise OSError(result.stderr)
            content = result.stdout
    except (OSError, ValueError):
        return f"{symbol.kind} {symbol.name}"

    lines = content.splitlines()
    return "\n".join(lines[symbol.line_start - 1 : symbol.line_end])


def _exclude(hits: list[Pointer], spans: set[tuple[str, int, int]]) -> list[Pointer]:
    return [
        hit
        for hit in hits
        if not any(
            hit.path == span_path and hit.line_start <= span_end and span_start <= hit.line_end
            for span_path, span_start, span_end in spans
        )
    ]


def _dedup(hits: list[Pointer]) -> list[Pointer]:
    best: dict[tuple[str, int, int], Pointer] = {}
    for hit in hits:
        key = (hit.path, hit.line_start, hit.line_end)
        if key not in best or hit.score > best[key].score:
            best[key] = hit
    return list(best.values())


def _sort_pointers(hits: list[Pointer]) -> list[Pointer]:
    return sorted(
        hits,
        key=lambda p: (-p.score, p.repo, p.path, p.line_start, p.line_end, p.heading),
    )


def _render_pointer(pointer: Pointer) -> str:
    if pointer.corpus == FINDINGS_CORPUS:
        origin = f"{pointer.corpus}:{pointer.path}"
    else:
        origin = f"{pointer.repo}:{pointer.path}:{pointer.line_start}-{pointer.line_end}"
    return f"- {origin}\n  {pointer.body or ''}"


def _capsule_active_work_line(capsule_path: Path) -> str | None:
    try:
        text = capsule_path.read_text(errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if "Active Work" in line:
            return line
    return None


def _task_prose_entries(
    store, config, id_: str, prd_path: Path | None, capsule_path: Path | None
) -> list[str]:
    entries: list[str] = []
    if capsule_path is not None:
        line = _capsule_active_work_line(capsule_path)
        if line:
            entries.append(line)

    memory_hits = query(
        store,
        config,
        id_,
        Scope("portfolio", None),
        corpus="memory",
        k=RETRIEVAL_K,
        include_body=True,
    )
    for hit in memory_hits[:2]:
        if hit.body:
            entries.append(hit.body)

    if prd_path is not None:
        try:
            entries.append(prd_path.read_text(errors="replace"))
        except OSError:
            pass

    return entries


def _cap_items(items: list, render, cap_tokens: int) -> tuple[list, bool]:
    items = list(items)
    trimmed = False
    while items:
        body = "\n\n".join(render(item) for item in items)
        if _estimate_tokens(body) <= cap_tokens:
            break
        items.pop()
        trimmed = True
    return items, trimmed


def _render_full(sections: dict, symbols_omitted: int) -> str:
    lines = [_FRESHNESS_LINE, ""]
    if symbols_omitted > 0:
        lines.append(
            f"{symbols_omitted} changed symbol(s) omitted "
            f"(beyond the {MAX_SYMBOLS_PER_PACK}-symbol cap)."
        )
        lines.append("")
    for label in _SECTION_ORDER:
        items, render_fn = sections[label]
        lines.append(f"## {label}")
        lines.append("")
        if items:
            lines.append("\n\n".join(render_fn(item) for item in items))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _largest_section(sections: dict) -> str | None:
    best_label = None
    best_size = -1
    for label in _SECTION_ORDER:
        items, render_fn = sections[label]
        if not items:
            continue
        body = "\n\n".join(render_fn(item) for item in items)
        size = _estimate_tokens(body)
        if size > best_size:
            best_size = size
            best_label = label
    return best_label


def build(
    store,
    config,
    repo: str,
    repo_root: Path,
    id_: str,
    diff_path: Path,
    source_ref: str | None = None,
    prd_path: Path | None = None,
    capsule_path: Path | None = None,
    out_dir: Path = Path("dev/local/tmp"),
) -> PackReport:
    index_report = index(store, config, Scope("repo", repo))

    all_symbols = changed_symbols(diff_path, repo_root, source_ref)
    changed_spans = {(s.path, s.line_start, s.line_end) for s in all_symbols}

    query_symbols = all_symbols[:MAX_SYMBOLS_PER_PACK]
    symbols_omitted = max(0, len(all_symbols) - MAX_SYMBOLS_PER_PACK)

    query_texts = [_symbol_query_text(s, repo_root, source_ref) for s in query_symbols]
    entry = resolve_pinned_entry(config)
    vectors = embed(query_texts, entry)

    similar_hits: list[Pointer] = []
    reuse_hits: list[Pointer] = []
    findings_hits: list[Pointer] = []

    for text, vector in zip(query_texts, vectors):
        similar_hits.extend(
            query(
                store, config, text, Scope("repo", repo), corpus="code",
                k=RETRIEVAL_K, vector=vector, include_body=True,
            )
        )
        reuse_hits.extend(
            query(
                store, config, text, Scope("portfolio", None), corpus="code",
                k=RETRIEVAL_K, vector=vector, include_body=True,
            )
        )
        findings_hits.extend(
            query(
                store, config, text, Scope("repo", repo), corpus=FINDINGS_CORPUS,
                k=RETRIEVAL_K, vector=vector, include_body=True,
            )
        )
        findings_hits.extend(
            query(
                store, config, text, Scope("portfolio", None), corpus=FINDINGS_CORPUS,
                k=RETRIEVAL_K, vector=vector, include_body=True,
            )
        )

    reuse_hits = [hit for hit in reuse_hits if hit.repo != repo]

    similar_items = _sort_pointers(_dedup(_exclude(similar_hits, changed_spans)))
    reuse_items = _sort_pointers(_dedup(_exclude(reuse_hits, changed_spans)))
    findings_items = _sort_pointers(_dedup(_exclude(findings_hits, changed_spans)))
    prose_entries = _task_prose_entries(store, config, id_, prd_path, capsule_path)

    budget = config.pack_budget
    similar_items, similar_trimmed = _cap_items(
        similar_items, _render_pointer, budget.similar_cap_tokens
    )
    reuse_items, reuse_trimmed = _cap_items(reuse_items, _render_pointer, budget.reuse_cap_tokens)
    findings_items, findings_trimmed = _cap_items(
        findings_items, _render_pointer, budget.findings_cap_tokens
    )
    prose_entries, prose_trimmed = _cap_items(
        prose_entries, lambda text: text, budget.prose_cap_tokens
    )

    trimmed_sections = [
        label
        for label, was_trimmed in (
            ("Similar code", similar_trimmed),
            ("Reuse precedent", reuse_trimmed),
            ("Findings precedent", findings_trimmed),
            ("Task prose", prose_trimmed),
        )
        if was_trimmed
    ]

    sections = {
        "Similar code": (similar_items, _render_pointer),
        "Reuse precedent": (reuse_items, _render_pointer),
        "Findings precedent": (findings_items, _render_pointer),
        "Task prose": (prose_entries, lambda text: text),
    }

    rendered_text = _render_full(sections, symbols_omitted)
    while _estimate_tokens(rendered_text) > budget.hard_cap_tokens:
        label = _largest_section(sections)
        if label is None:
            break
        items, _ = sections[label]
        items.pop()
        if label not in trimmed_sections:
            trimmed_sections.append(label)
        rendered_text = _render_full(sections, symbols_omitted)

    final_sections = []
    for label in _SECTION_ORDER:
        items, render_fn = sections[label]
        body = "\n\n".join(render_fn(item) for item in items)
        final_sections.append(
            PackSection(label=label, body=body, estimated_tokens=_estimate_tokens(body))
        )

    total_estimated_tokens = _estimate_tokens(rendered_text)

    target_path = Path(out_dir) / f"engram-pack-{id_}.md"
    if not target_path.is_absolute():
        target_path = target_path.absolute()
    tmp_file = target_path.with_name(f".{target_path.name}.tmp")
    tmp_file.write_text(rendered_text)
    os.replace(tmp_file, target_path)

    return PackReport(
        path=target_path,
        sections=final_sections,
        total_estimated_tokens=total_estimated_tokens,
        trimmed_sections=trimmed_sections,
        symbols_omitted=symbols_omitted,
        index_report=index_report,
    )
