# Design: Engram Heavy Corpora (PRD 00002)

## Architecture fit

Extends the PRD-00001 layering (`client` → `store` → `chunker`/`corpora`/`indexer` → `query`/`cli`) with two new peer modules at the Core layer: `transcripts` and `symbols`. Both produce `Chunk`/`ChunkWithVector` objects and plug into the existing `indexer.index()` diff/embed/upsert/prune loop — no new pipeline, no new storage engine. The Integration layer gets one new external touchpoint: `claude-git-ferry`'s `catchup` skill calls the already-frozen `engram query`/`engram index` CLI contract; engram ships no code into that repo.

## Module placement

New files:
- `src/engram/transcripts.py` — Transcript Corpus (enumerate + chunk).
- `src/engram/symbols.py` — Code Corpus (enumerate + chunk).
- `tests/test_transcripts.py`, `tests/test_symbols.py`.
- `tests/fixtures/transcripts/*.jsonl` — small fixture transcripts (happy path, tool-chatter-only, malformed line).
- `tests/fixtures/code_repo/` — a tiny fixture git repo (`git init` in a `tmp_path` at test time, per the existing `test_corpora.py` convention — no fixture repo committed to disk).

Edits to existing files:
- `src/engram/corpora.py` — extract the inline repos.csv parsing (current lines 74-85 of `enumerate_corpora`) into a standalone `read_repos_csv(path: Path) -> list[tuple[str, str]]`, reused by `symbols.enumerate()`. `enumerate_corpora()` calls it too; no behavior change. Also: raise `FileNotFoundError` explicitly (with an accurate message) when `repos_csv` is missing, instead of letting `Path.read_text()`'s bare OS error propagate (see Interfaces — this makes the existing repos.csv-missing message and the new cellar-path-missing message both originate at their raise site instead of being reconstructed in `cli.py`).
- `src/engram/indexer.py` — two changes: (1) `index()`'s `files = list(enumerate_corpora())` becomes `files = list(enumerate_corpora()) + list(transcripts.enumerate()) + list(symbols.enumerate())` — without this, `engram index` never discovers a single transcript or code file, and the Phase 1 harness exit criterion is unreachable; (2) `_diff_and_embed` currently calls `chunk_markdown(...)` unconditionally; replace with a 3-way dispatch on `file.corpus` (see Interfaces).
- `src/engram/cli.py` — `_run_index`'s and `_run_status`'s `except FileNotFoundError:` handlers change from printing a hardcoded `f"{GITA_REPOS_CSV} not found; register repos with gita first"` string to printing `str(e)` — the message now lives at the raise site (`corpora.py`, `transcripts.py`) so it stays accurate regardless of which producer raised it. The default-path message text is unchanged (same string, now constructed where the check happens), so existing tests asserting that exact text keep passing.
- `src/engram/harness.py` — `_VALID_CORPORA` gains `"transcripts"` and `"code"`; `_baseline_hit_rate`'s `corpus_files` listing (currently `enumerate_corpora()` only) must also chain `transcripts.enumerate()` and `symbols.enumerate()`, same as `indexer.index()` (see Interfaces), so the rg baseline sees the new corpora's files too.
- `eval/goldset.yaml` — append transcript-paraphrase and cross-repo-duplicate-seed entries (data only, no schema change; `load_goldset` already accepts any corpus in `_VALID_CORPORA`).
- `pyproject.toml` — add `tree-sitter-language-pack` to `dependencies`.

External repo edit (`~/git/src/github.com/buvis/claude-git-ferry`):
- `skills/catchup/SKILL.md` — Phase 1 gets a new step: run `engram index --scope repo` (best-effort, non-fatal on error) then `engram query --scope repo <topic>` and `engram query --scope portfolio <topic>` where `<topic>` = current branch name + active PRD title if present. Phase 3's capsule template gains a `## Related Context` section (top-N scored pointers + a staleness stamp = the `engram index` run timestamp). Release via `dev/bin/release` with a CHANGELOG `Added` entry, per that repo's own release process — unchanged by this PRD.
- **Premise gate** (PRD-mandated): re-read `skills/catchup/SKILL.md`'s current Phase 1/Phase 3 structure immediately before editing. If it no longer matches the shape read during this design (a Gather phase feeding a Synthesize phase's markdown template), skip the edit and report the mismatch instead of forcing it.

## Interfaces & contracts

### `src/engram/corpora.py` (extracted helper)

```python
def read_repos_csv(repos_csv: Path) -> list[tuple[str, str]]:
    """Return [(repo_path, name), ...] from a gita repos.csv, skipping blank/short
    rows. Raises FileNotFoundError(f'{repos_csv} not found; register repos with
    gita first') when repos_csv doesn't exist — same message text
    enumerate_corpora() already relies on today (via a bare Path.read_text()
    OSError), now raised explicitly at the check site instead of reconstructed
    in cli.py's except handler. enumerate_corpora() calls this and no longer
    reads repos_csv itself."""
```

### `src/engram/transcripts.py`

```python
CELLAR_PROJECTS_DIR: Path = (
    Path.home() / "git" / "src" / "github.com" / "buvis" / "cellar" / ".claude" / "projects"
)

DEFAULT_ERROR_PATTERNS: list[str] = [
    r"Traceback \(most recent call last\)",
    r"panic:",
    r"\bERROR\b",
    r"\bFAIL\b",
    r"exit code [1-9]",
]

def enumerate(projects_dir: Path = CELLAR_PROJECTS_DIR) -> Iterator[CorpusFile]:
    """Yield CorpusFile(corpus='transcripts', repo='cellar', path) for every
    *.jsonl directly under projects_dir/<session>/. Raises
    FileNotFoundError(f'{projects_dir} not found; cellar transcripts corpus
    requires this path') if projects_dir is absent — the PRD's Test Strategy
    is explicit that a missing cellar path must be a loud failure, not a
    silent empty corpus (unlike corpora._enumerate_memory_corpora's per-repo
    no-op, which is a different case: one root among many registered repos,
    versus this module's one fixed, required root)."""

def chunk(
    path: Path, repo: str, content_hash: str, error_patterns: list[str] | None = None
) -> list[Chunk]:
    """Parse path as JSONL. One Chunk per kept line:
    - corpus='transcripts', doc_type='turn', path=str(path), repo=repo,
      heading=f'{role} turn', body=extracted text,
      line_start=line_end=1-indexed JSONL line number, chunk_ordinal=that same
      line number, content_hash=content_hash (the whole file's hash — same
      incremental granularity as chunk_markdown).
    - A line is kept when: it parses as JSON AND record['type'] in
      {'user','assistant'} AND record.get('isMeta') is not truthy AND
      record.get('isSidechain') is not truthy AND isinstance(record.get('message'), dict)
      AND (extracted text is non-empty and non-whitespace, OR the record's
      message.content contains a tool_result block matching an error pattern).
    - Extracted text: if message['content'] is a str, use it as-is; if it's a
      list, join every block's .get('text', '') for blocks where
      block.get('type') == 'text', in list order, with '\\n'; any other block
      type (tool_use, tool_result, etc.) contributes no text here (tool_result
      error-matching is a separate check, below, over the same content list).
    - Malformed JSON lines are skipped, not raised (a truncated final line from
      a session cut off mid-write is expected).
    - error_patterns defaults to _load_error_patterns() (below) when None;
      tests pass an explicit list to avoid depending on config.toml.
    """

def _load_error_patterns(config_path: Path = client.DEFAULT_CONFIG_PATH) -> list[str]:
    """Read [transcripts].error_patterns from config.toml via tomllib (same
    file client.load_config() already ensures exists); fall back to
    DEFAULT_ERROR_PATTERNS when the table/key is absent. Additive-only TOML
    table — never touches the existing [[embedding]]/[pinned] schema, so it
    does not need client.py's load_config() to change."""
```

### `src/engram/symbols.py`

```python
skipped_files: list[str] = []  # files with no grammar / unreadable, reset each enumerate() call

def enumerate(repos_csv: Path = GITA_REPOS_CSV) -> Iterator[CorpusFile]:
    """For each (repo_path, name) in corpora.read_repos_csv(repos_csv): run
    `git -C <repo_path> ls-files`. On non-zero exit (dir gone / not a git repo),
    append 'code:{name}' to corpora.missing_dirs and continue — reuses the
    existing missing-dirs reporting path (cli._print_missing), zero CLI changes.
    Otherwise yield CorpusFile('code', name, Path(repo_path) / rel_path) for
    every tracked path in the output."""

def chunk(path: Path, repo: str, content_hash: str) -> list[Chunk]:
    """
    language = detect_language_from_path(str(path))
    if language is None: skipped_files.append(str(path)); return []
    read source with errors='replace'; on OSError/UnicodeDecodeError:
      skipped_files.append(str(path)); return []
    if not source.strip(): return []
    result = process(source, ProcessConfig(language, structure=True))
    Recursively walk result.structure + item.children (no kind filtering —
    every StructureItem at every depth becomes its own chunk; a container's
    chunk and its children's chunks overlapping is intentional, see
    Alternatives). Per item:
      path=str(path), repo=repo, corpus='code',
      doc_type=str(item.kind).lower(), heading=f'{item.kind} {item.name}',
      body='\\n'.join(source.splitlines()[item.span.start_line : item.span.end_line + 1])
        (item.span is 0-indexed/inclusive; slice end is exclusive so +1),
      line_start=item.span.start_line + 1, line_end=item.span.end_line + 1
        (convert to 1-indexed to match chunk_markdown's convention),
      chunk_ordinal=running counter, content_hash=content_hash.
    (Neither symbols=True nor docstrings=True is set: both were live-tested —
    including docstrings=True specifically — and item.signature/item.doc_comment
    stayed None regardless in the installed 1.14.0, and result.symbols is
    unread by this design; requesting either flag would only add extraction
    cost for discarded output. str(item.kind) was verified live to already
    render as the plain name, e.g. 'Function' — no enum-repr prefix — so
    '.lower()' produces 'function' as intended.)
    """

def count_skipped(repos_csv: Path = GITA_REPOS_CSV) -> int:
    """Cheap re-scan (extension check via detect_language_from_path only, no
    file read/parse) for `engram status` to report grammarless-file counts
    without re-running the full index. Mirrors how cli._run_status already
    re-calls enumerate_corpora() live rather than caching missing_dirs."""
```

### `src/engram/indexer.py` (enumeration + dispatch changes)

```python
def _chunk_file(file: CorpusFile, content_hash: str) -> list[Chunk]:
    if file.corpus == "transcripts":
        return transcripts.chunk(file.path, file.repo, content_hash)
    if file.corpus == "code":
        return symbols.chunk(file.path, file.repo, content_hash)
    return chunk_markdown(file.path, file.corpus, file.repo, content_hash)
```
`_diff_and_embed` calls `_chunk_file(file, h)` instead of `chunk_markdown(file.path, file.corpus, file.repo, h)`. No other change to the diff/embed/upsert/prune loop — corpus-specific chunking is the only seam.

**Enumeration wiring (required, not optional):** `index()`'s first line —
`files = list(enumerate_corpora())` — is the sole producer of the file list
`_diff_and_embed` consumes (confirmed against `tests/test_indexer.py`'s
`monkeypatch.setattr("engram.indexer.enumerate_corpora", ...)` pattern).
Without a change here, `transcripts.enumerate()`/`symbols.enumerate()` are
never called by `engram index` at all. Change that line to:
```python
files = list(enumerate_corpora()) + list(transcripts.enumerate()) + list(symbols.enumerate())
```
This is also what makes `harness._score_candidate`'s per-corpus `index(...,
corpus=corpus)` calls see transcript/code files. `harness._baseline_hit_rate`
needs the identical three-iterator chain independently (it builds its own
`corpus_files` list rather than calling `index()`): change
`[f.path for f in enumerate_corpora() if f.corpus in goldset_corpora]` to
filter over `chain(enumerate_corpora(), transcripts.enumerate(), symbols.enumerate())`
the same way, so the rg baseline sees the new corpora's files too.

### `src/engram/cli.py` (status output)

`_run_status` gains one line when `symbols.count_skipped()` returns > 0, printed alongside the existing `_print_missing` block (exact text is a task-level detail; the contract is: non-zero count must be visible in `status` output, matching the PRD's "grammarless files ... counted in status").

## Data flow

1. `engram index` (unchanged entry point) → `enumerate_corpora()` (memory/prd/decision/discovery, unchanged) is joined by two new producers the CLI/harness call the same way: `transcripts.enumerate()` and `symbols.enumerate()`. (Wiring these into the single `enumerate_corpora()` generator vs. keeping them as separate calls is the first Alternative below.)
2. Each `CorpusFile` flows through the existing `hash_source` → `known_sources` diff → `_chunk_file` dispatch → `embed()` → `ChunkWithVector` → `store.upsert_chunks()` → `store.prune()` pipeline, untouched except for the dispatch seam.
3. `engram query` is corpus-filterable already (`--corpus transcripts` / `--corpus code`); no query-path change needed — RRF fusion and `Pointer` output are corpus-agnostic.
4. Capsule Integration: `git-ferry:catchup` Phase 1 shells out to the two CLI commands above (refresh-then-query), and Phase 3 writes the returned pointers into `project-capsule.md`'s new `## Related Context` section. Engram has no awareness of this consumer beyond its existing CLI contract.

## Reuse inventory

- `engram.corpora.CorpusFile`, `hash_source` — reused as-is by both new modules (searched: `class CorpusFile`, `def hash_source` in `corpora.py`).
- `engram.store.Chunk`, `ChunkWithVector`, `Store.upsert_chunks/known_sources/prune` — reused as-is; no schema change (searched: `class Chunk`, `upsert_chunks` in `store.py`).
- `engram.client.embed`, `resolve_pinned_entry` — reused as-is via `indexer.index()`, which already calls them corpus-agnostically.
- `engram.indexer.index()`'s diff/embed/upsert/prune loop — reused with a one-line dispatch change (see above); nothing rewritten.
- CSV-parsing for `repos.csv` — existing inline logic in `corpora.enumerate_corpora` (searched: `csv.reader`, `slug_to_name`) extracted into `read_repos_csv` rather than duplicated in `symbols.py` (rationalizations.md "couldn't find existing helper" — it existed, just needed extracting).
- `cli.py`'s `_print_missing` / `corpora.missing_dirs` reporting path — reused for code-enumeration repo misses (searched: `missing_dirs`, `_print_missing`) instead of inventing a parallel mechanism.
- Git subprocess pattern for repo introspection — `cli._resolve_repo_name`'s `subprocess.run(["git", ...], capture_output=True, text=True)` shape reused for `git -C <repo> ls-files` (searched: `subprocess.run` in `cli.py`).
- `tree-sitter-language-pack` (new dependency): nothing pre-existing in-repo does symbol-level code parsing (searched: `tree_sitter`, `ast.parse`, `symbol` — nothing found). Verified via Context7 docs + a live `uv run --with tree-sitter-language-pack` probe that `process()`'s `item.signature`/`item.doc_comment` fields are unpopulated (`None`) for both Python and Rust in the installed 1.14.0 — the design does not depend on them (see Risks).

## Alternatives considered

1. **Two standalone `enumerate()` functions (chosen)** vs. **folding transcripts/code into `enumerate_corpora()` itself** (smallest-diff option: add two more `yield from` calls inside the existing generator). Rejected the fold-in: `enumerate_corpora()`'s signature (`repos_csv`, `projects_dir`) doesn't carry a cellar-specific root, and code enumeration needs a `git ls-files` subprocess per repo that the other three corpora don't — folding it in would grow that function's parameter list and mix a fixed-root corpus (transcripts) with a per-repo one (code, like prd/decision/discovery) in one signature. Two peer `enumerate()` functions the CLI/indexer call alongside `enumerate_corpora()` keep each module single-purpose, at the cost of `cli._run_index`/`harness._baseline_hit_rate` needing to chain three iterators instead of one (small, contained cost).
2. **Slice raw source lines by `item.span` (chosen)** vs. **rely on `item.signature`/`item.doc_comment`** (the PRD's literal words: "signature + docstring embedded"). Rejected relying on the fields: empirically `None` for every language tested against the installed package version (verified live, not from docs alone). Line-slicing the whole `span` gets the signature and, for languages where the docstring is a body statement (Python), the docstring too — for external-doc-comment languages (Rust `///`, Go `//`) the leading comment is outside `span` and would be dropped; flagged in Risks rather than chased with comment-stitching logic that adds real complexity for a nice-to-have.
3. **No kind filtering, chunk every `StructureItem` recursively (chosen)** vs. **allow-list top-level Function/Class only**. An allow-list needs curation per language (Rust's `Impl`/`Trait`/`Struct`, Go's method receivers, etc.) and risks silently missing patterns in less-common languages across a 26-repo polyglot portfolio. Chunking every item uniformly is zero-curation and matches "whole-symbol chunks" literally; the cost is intentional overlap between a container chunk (e.g. `impl Shape for Point`) and its child chunks (e.g. `fn area`) — acceptable duplication for retrieval recall, not a correctness bug.

## Risks & edge cases

- **Doc-comment loss for non-Python languages**: `item.span` excludes leading `///`/`//`/`/** */` comments (verified live), so a Rust/Go/TS function's chunk has its body but not its doc comment. Acceptable now (the PRD's own success metric is cross-repo *pattern* duplication, not doc-comment recall); if it matters later, `result.comments` gives independently-spanned comments that could be stitched to the nearest following item by line adjacency.
- **`tree-sitter-language-pack` version drift**: the field-emptiness finding above is pinned to `1.14.0` (probed live during this design). `plan-tasks`/`work` should pin that version (or re-verify) rather than float, since a future release populating `signature`/`doc_comment` would be a welcome but silent behavior change to the chunk body content.
- **Goldset path drift**: `eval/goldset.yaml`'s existing `prd` corpus entries for 00002/00003 point at `dev/local/prds/backlog/...`; PRD-lifecycle moves (this very build gate just moved 00002 to `wip/`) break `load_goldset`'s existence check for those two rows. Pre-existing drift, not introduced by this PRD, but the Phase 1 gold-set-extension task will touch this file anyway — worth a one-line fix in the same commit rather than a separate follow-up.
- **Likely next changes this design should not box in**: (1) turn summarization for noisy transcripts (named in the PRD as a nice-to-have) — chunking one-turn-per-chunk today doesn't prevent a later summarization pass from replacing the body text before embedding; (2) LLM one-liner enrichment for code chunks (named nice-to-have) — the recursive per-item chunking gives a natural unit to attach an enrichment string to later; (3) a `decision` corpus finally getting real files — unrelated to this PRD's corpora but shares `_VALID_CORPORA`, already extensible.
- **Initial transcript index is a ~900MB one-time cost**: incremental re-runs are no-ops (file-hash unchanged), matching the PRD's stated one-time-cost risk; no design change needed, just an execution-time (not design-time) concern for whoever runs the first `engram index`.

## Test strategy outline

- `tests/test_transcripts.py`: fixture JSONL covering — happy path (user+assistant text turns kept), tool-chatter-only session (zero chunks), error-bearing tool_result kept despite no plain text, malformed JSON line skipped without raising, `isMeta`/`isSidechain` lines excluded, missing `projects_dir` raises `FileNotFoundError` (loud, not a silent empty corpus — matches the PRD's Test Strategy error case).
- `tests/test_symbols.py`: fixture git repo (`git init` + commit in `tmp_path`) with a `.py` file (function + class + method) and a grammarless file (e.g. `.bin` or unrecognized extension) — assert chunk counts, line ranges, and that the grammarless file lands in `skipped_files` / `count_skipped()`; a non-UTF-8 file is skipped, not raised; a repo directory that doesn't exist appends to `corpora.missing_dirs` without raising.
- `tests/test_indexer.py`: extend with a case per corpus proving `_chunk_file` dispatches correctly (transcripts/code/other), reusing the existing `Store`/`EngramConfig` fixtures already in that file.
- `eval/harness.py` gate: extend `eval/goldset.yaml` per the PRD's Phase 1 task (transcript paraphrases + cross-repo duplicate seeds); harness already reports per-corpus hit rate, so the existing `format_report` output is the acceptance check for the two new >=80% thresholds — no harness code change beyond `_VALID_CORPORA`.
- Timing: a test (or the harness run itself) asserting a second `index()` call over an already-indexed portfolio completes in under 60s, per the PRD's incremental-reindex success metric.
- Capsule Integration is verified by running `git-ferry:catchup` in a sample repo post-edit and checking the emitted `## Related Context` section — an integration check, not a unit test; covered by that repo's own test suite plus a manual run noted in the PRD's Phase 2 acceptance criteria.

## Review log

- Dispatch 1 (Claude) non-blockers/questions not fixed, recorded only:
  - `symbols.count_skipped()` re-scans the whole portfolio on every `engram status` call — not incorrect, note as a possible future optimization (cache last-run skip count) if `status` latency becomes noticeable across a 26-repo portfolio.
  - "Extracted text" algorithm ambiguity was fixed inline (blocking-adjacent, addressed in Interfaces).
  - `path`/`repo` field omissions were fixed inline (addressed in Interfaces).
  - `str(item.kind)` enum-stringification question was verified live (renders as plain name, e.g. `'Function'`, no enum-repr prefix) — no fix needed, confirmed correct as designed.
dispatch 1 (claude): cardinal-sin 0, blocker 4, non-blocker 2, question 3
