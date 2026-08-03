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
            hit.path == span_path
            and hit.line_start <= span_end
            and span_start <= hit.line_end
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
        origin = (
            f"{pointer.repo}:{pointer.path}:{pointer.line_start}-{pointer.line_end}"
        )
    return f"- {origin}\n  {pointer.body}"


def _capsule_active_work_section(capsule_path: Path) -> str | None:
    try:
        text = capsule_path.read_text(errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("## ") and "Active Work" in line:
            section_lines = []
            for next_line in lines[i + 1 :]:
                if next_line.startswith("## "):
                    break
                section_lines.append(next_line)
            content = "\n".join(section_lines).strip()
            return content or None
    return None


def _append_prose_entry(entries: list[str], text: str, cap_chars: int) -> None:
    # Budget in characters, and count the "\n\n" that will join this entry to
    # the entries already added. Going through _estimate_tokens first rounds
    # twice, which leaves the rejoined section one token over the cap for
    # half of all entry lengths - and _cap_items then drops the entry whole,
    # which is the bug this truncation exists to prevent.
    used_chars = len("\n\n".join(entries))
    if entries:
        used_chars += 2
    remaining_chars = cap_chars - used_chars
    if remaining_chars > 0:
        entries.append(text[:remaining_chars])


def _prd_query_text(prd_text: str | None, prd_path: Path) -> str:
    for line in (prd_text or "").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return prd_path.stem


def _task_prose_entries(
    store,
    config,
    id_: str,
    prd_path: Path | None,
    capsule_path: Path | None,
    prose_cap_tokens: int,
) -> list[str]:
    entries: list[str] = []
    total_cap_chars = 4 * prose_cap_tokens
    # When a PRD is present, the capsule and memory hits ahead of it may only
    # spend half the budget between them, so the PRD always has room left.
    leading_cap_chars = (
        total_cap_chars // 2 if prd_path is not None else total_cap_chars
    )

    if capsule_path is not None:
        section = _capsule_active_work_section(capsule_path)
        if section:
            _append_prose_entry(entries, section, leading_cap_chars)

    if prd_path is not None:
        try:
            prd_text = prd_path.read_text(errors="replace")
        except OSError:
            prd_text = None

        memory_hits = query(
            store,
            config,
            _prd_query_text(prd_text, prd_path),
            Scope("portfolio", None),
            corpus="memory",
            k=RETRIEVAL_K,
            include_body=True,
        )
        for hit in memory_hits[:2]:
            if hit.body:
                _append_prose_entry(entries, hit.body, leading_cap_chars)

        if prd_text is not None:
            _append_prose_entry(entries, prd_text, total_cap_chars)

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
            f"(beyond the {MAX_SYMBOLS_PER_PACK}-symbol cap).",
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


def _reindex_and_resolve_symbols(
    store,
    config,
    repo: str,
    repo_root: Path,
    diff_path: Path,
    source_ref: str | None,
) -> tuple[IndexReport, set[tuple[str, int, int]], list[Symbol], int]:
    index_report = index(store, config, Scope("repo", repo))

    all_symbols = changed_symbols(diff_path, repo_root, source_ref)
    changed_spans = {(s.path, s.line_start, s.line_end) for s in all_symbols}

    query_symbols = all_symbols[:MAX_SYMBOLS_PER_PACK]
    symbols_omitted = max(0, len(all_symbols) - MAX_SYMBOLS_PER_PACK)

    return index_report, changed_spans, query_symbols, symbols_omitted


def _query_hits_for_symbol(
    store,
    config,
    repo: str,
    text: str,
    vector,
) -> tuple[list[Pointer], list[Pointer], list[Pointer]]:
    def hits_for(scope: Scope, corpus: str) -> list[Pointer]:
        return query(
            store,
            config,
            text,
            scope,
            corpus=corpus,
            k=RETRIEVAL_K,
            vector=vector,
            include_body=True,
        )

    repo_scope = Scope("repo", repo)
    portfolio_scope = Scope("portfolio", None)

    similar = hits_for(repo_scope, "code")
    reuse = hits_for(portfolio_scope, "code")
    findings = hits_for(repo_scope, FINDINGS_CORPUS) + hits_for(
        portfolio_scope,
        FINDINGS_CORPUS,
    )
    return similar, reuse, findings


def _retrieve_pack_hits(
    store,
    config,
    repo: str,
    repo_root: Path,
    query_symbols: list[Symbol],
    source_ref: str | None,
) -> tuple[list[Pointer], list[Pointer], list[Pointer]]:
    query_texts = [_symbol_query_text(s, repo_root, source_ref) for s in query_symbols]
    entry = resolve_pinned_entry(config)
    vectors = embed(query_texts, entry)

    similar_hits: list[Pointer] = []
    reuse_hits: list[Pointer] = []
    findings_hits: list[Pointer] = []

    for text, vector in zip(query_texts, vectors):
        similar, reuse, findings = _query_hits_for_symbol(
            store,
            config,
            repo,
            text,
            vector,
        )
        similar_hits.extend(similar)
        reuse_hits.extend(reuse)
        findings_hits.extend(findings)

    reuse_hits = [hit for hit in reuse_hits if hit.repo != repo]

    return similar_hits, reuse_hits, findings_hits


def _prepare_section_items(
    hits: list[Pointer],
    changed_spans: set[tuple[str, int, int]],
    cap_tokens: int,
) -> tuple[list, bool]:
    items = _sort_pointers(_dedup(_exclude(hits, changed_spans)))
    return _cap_items(items, _render_pointer, cap_tokens)


def _build_pack_sections(
    store,
    config,
    id_: str,
    hits: tuple[list[Pointer], list[Pointer], list[Pointer]],
    changed_spans: set[tuple[str, int, int]],
    prd_path: Path | None,
    capsule_path: Path | None,
    budget,
) -> tuple[dict, list[str]]:
    similar_hits, reuse_hits, findings_hits = hits
    sections: dict = {}
    trimmed_sections: list[str] = []

    for label, section_hits, cap_tokens in (
        ("Similar code", similar_hits, budget.similar_cap_tokens),
        ("Reuse precedent", reuse_hits, budget.reuse_cap_tokens),
        ("Findings precedent", findings_hits, budget.findings_cap_tokens),
    ):
        items, was_trimmed = _prepare_section_items(
            section_hits, changed_spans, cap_tokens
        )
        sections[label] = (items, _render_pointer)
        if was_trimmed:
            trimmed_sections.append(label)

    prose_entries = _task_prose_entries(
        store,
        config,
        id_,
        prd_path,
        capsule_path,
        budget.prose_cap_tokens,
    )
    prose_entries, prose_trimmed = _cap_items(
        prose_entries,
        lambda text: text,
        budget.prose_cap_tokens,
    )
    sections["Task prose"] = (prose_entries, lambda text: text)
    if prose_trimmed:
        trimmed_sections.append("Task prose")

    return sections, trimmed_sections


def _finalize_pack(
    sections: dict,
    trimmed_sections: list[str],
    symbols_omitted: int,
    budget,
    id_: str,
    out_dir: Path,
    index_report: IndexReport,
) -> PackReport:
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
            PackSection(
                label=label,
                body=body,
                estimated_tokens=_estimate_tokens(body),
            ),
        )

    total_estimated_tokens = _estimate_tokens(rendered_text)

    target_path = Path(out_dir) / f"engram-pack-{id_}.md"
    if not target_path.is_absolute():
        target_path = target_path.absolute()
    tmp_file = target_path.with_name(f".{target_path.name}.tmp")
    target_path.parent.mkdir(parents=True, exist_ok=True)
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
    index_report, changed_spans, query_symbols, symbols_omitted = (
        _reindex_and_resolve_symbols(
            store,
            config,
            repo,
            repo_root,
            diff_path,
            source_ref,
        )
    )

    hits = _retrieve_pack_hits(
        store,
        config,
        repo,
        repo_root,
        query_symbols,
        source_ref,
    )

    budget = config.pack_budget
    sections, trimmed_sections = _build_pack_sections(
        store,
        config,
        id_,
        hits,
        changed_spans,
        prd_path,
        capsule_path,
        budget,
    )

    return _finalize_pack(
        sections,
        trimmed_sections,
        symbols_omitted,
        budget,
        id_,
        out_dir,
        index_report,
    )
