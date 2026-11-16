---
design: skip
default_model: opus
model_tier_rationale: replaces indexed chunks of unchanged sources with vector reuse; a wrong identity check either re-embeds everything or keeps stale chunks silently
---

# Engram module-context backfill

Source: PRD 00013 (`docs/dev/project-management/prds/done/00013-engram-module-context-v1.md`)
left backfill as "a separate, explicit operation" (README, module context
paragraph). User decision 2026-11-16: specify it.

## Overview

### Problem Statement

PRD 00013 indexes code outside parsed symbols as `Module context` chunks, but
only when a file is first indexed or changes. The hash cache
(`src/engram/indexer.py:84-89`) skips unchanged sources, so most of the
portfolio has no module context. Files cached as empty (top-level scripts with
no functions) stay invisible. `--reembed-code` refreshes vectors of existing
chunks only and cannot add missing spans. The 2026-11-10 parser upgrade
(tree-sitter-language-pack 1.25) left 760 unchanged files with stale
1.14-era symbol chunks for the same reason.

### Target Users

The maintainer, who runs it once on the production index after a backup, and
agents whose queries then see module-level code across the portfolio.

### Success Metrics

- Every test in `tests/test_backfill.py` passes.
- A second backfill run over the same store embeds zero chunks and writes nothing.
- Chunks whose heading and body are unchanged keep their stored vectors (no
  embed call for them).

## Functional Decomposition

### Capability: Code re-chunking of unchanged sources

#### Feature: Backfill pass
- **Description**: Re-chunk unchanged code sources with the current chunker and
  store the result, embedding only chunks that are new.
- **Inputs**: Store, config, scope (`repo` or `portfolio`).
- **Outputs**: `BackfillReport(sources_rechunked, chunks_embedded,
  vectors_reused, empty_cleared, failed_sources)`.
- **Behavior**:
  1. Resolve the pinned entry and call `store.assert_configured_model(entry.id)`.
  2. Enumerate with `symbols.enumerate(exclude_globs=config.exclude_globs)`,
     filtered to `scope.repo` for repo scope.
  3. Load `known = store.known_sources(scope, "code")` and
     `known_empty = store.known_empty_sources_by_corpus(scope, "code")`.
  4. Per file: `h = hash_source(file.path)`; an `OSError` appends the path to
     `failed_sources`. Skip the file unless `(repo, path, h)` is in `known` or
     `("code", repo, path, h)` is in `known_empty`. New or changed files are
     the normal index pass's job.
  5. `fresh = symbols.chunk(file.path, file.repo, h)`. Any exception appends
     the path to `failed_sources` and leaves its rows untouched.
  6. Known source: `stored = store.code_chunks_with_vectors(path)`. If
     `[item.chunk for item in stored] == fresh`, skip. Otherwise build items:
     reuse the stored vector of any stored chunk with the same
     `(heading, body)`, embed the rest in one `embed` call, then
     `store.replace_chunks_for_source("code", path, items)`. When `fresh` is
     empty, replace with `[]` and `store.mark_empty_source("code", repo, path, h)`.
  7. Known-empty source: if `fresh` is empty, skip. Otherwise embed all,
     `store.upsert_chunks(items)` and `store.unmark_empty_source("code", repo, path)`.
  8. Each source commits on its own, so an interrupted run is safe to repeat.

#### Feature: CLI flag
- **Description**: `engram index --backfill-code [--scope repo|portfolio]`.
- **Inputs**: CLI args.
- **Outputs**: stdout `backfilled {sources_rechunked} code sources: {chunks_embedded} chunks embedded, {vectors_reused} vectors reused, {empty_cleared} empty marks cleared`;
  failed sources through `_print_failed`.
- **Behavior**: Scope defaults to `repo`, as for plain `index`. `--corpus`,
  `--rebuild` and `--reembed-code` with `--backfill-code` are a parser error.
  `StoreModelMismatchError` prints the existing rebuild hint and exits 1;
  `EmbeddingServerError` and `EmbeddingPreflightError` print and exit 1.
  Otherwise exit 0.

### Capability: Store access

#### Feature: Stored vectors per source
- **Description**: Read a code source's chunks with their vectors.
- **Inputs**: Path.
- **Outputs**: `list[ChunkWithVector]` ordered by `chunk_ordinal`.
- **Behavior**: Join `chunks` with `chunks_vec` on `chunk_id`, filtered to
  `corpus = 'code'` and the path. Decode each embedding blob with
  `struct.unpack(f"{dim}f", blob)`, where `dim` and `model_id` come from the
  `embedding_dim` and `embedding_model_id` meta keys. Return `[]` when the
  vector table does not exist yet.

#### Feature: Clear an empty mark
- **Description**: Delete one `empty_sources` row.
- **Inputs**: Corpus, repo, path.
- **Outputs**: None.
- **Behavior**: `DELETE FROM empty_sources WHERE corpus = ? AND repo = ? AND path = ?`.

## Structural Decomposition

### Repository Structure

```
src/engram/
├── indexer.py   # Maps to: Backfill pass
├── store.py     # Maps to: Stored vectors per source, Clear an empty mark
└── cli.py       # Maps to: CLI flag
tests/
└── test_backfill.py
README.md
CHANGELOG.md
```

### Module: store
- **Maps to capability**: Store access
- **Responsibility**: Read chunk vectors per source; clear empty marks.
- **Location**: `src/engram/store.py`
- **Exports**:
  - `Store.code_chunks_with_vectors(path)` - chunks plus decoded vectors.
  - `Store.unmark_empty_source(corpus, repo, path)` - delete one empty mark.
- New symbols: `code_chunks_with_vectors`, `unmark_empty_source`

### Module: indexer
- **Maps to capability**: Code re-chunking of unchanged sources
- **Responsibility**: The backfill pass.
- **Location**: `src/engram/indexer.py`
- **Exports**:
  - `backfill_code(store, config, scope)` - returns `BackfillReport`.
  - `BackfillReport` - frozen dataclass with the five fields above.
- New symbols: `backfill_code`, `BackfillReport`

### Module: cli
- **Maps to capability**: Code re-chunking of unchanged sources
- **Responsibility**: `--backfill-code` flag and its output.
- **Location**: `src/engram/cli.py`
- **Exports**: none new.

### Module: tests
- **Maps to capability**: all
- **Responsibility**: Regression tests on temporary stores with a fake embedder.
- **Location**: `tests/test_backfill.py`
- New symbols: `test_backfill_adds_module_context_and_reuses_symbol_vectors`, `test_backfill_indexes_source_cached_as_empty_and_clears_mark`, `test_backfill_second_run_embeds_nothing`, `test_backfill_skips_new_and_changed_sources`, `test_backfill_chunker_failure_keeps_existing_rows`, `test_backfill_repo_scope_leaves_other_repos_untouched`, `test_code_chunks_with_vectors_round_trips_stored_vectors`, `test_cli_backfill_rejects_corpus_rebuild_and_reembed`, `test_cli_backfill_prints_summary`

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **store**: `code_chunks_with_vectors`, `unmark_empty_source`.

### Core Layer (Phase 1)
- **indexer**: Depends on [store].

### Integration Layer (Phase 2)
- **cli**: Depends on [indexer].
- **README.md, CHANGELOG.md**: Depend on [cli].

## Implementation Phases

### Phase 0: Foundation
**Goal**: Store reads vectors per source and clears empty marks.

**Tasks**:
- [ ] Add the `code_chunks_with_vectors` and `unmark_empty_source` methods to `Store` in
  `src/engram/store.py`; add `test_code_chunks_with_vectors_round_trips_stored_vectors`
  in `tests/test_backfill.py` (no deps) - Acceptance:
  `.venv/bin/python -m pytest -q tests/test_backfill.py -k round_trips` passes.

**Exit Criteria**: Stored vectors read back equal to the written values.

### Phase 1: Core
**Goal**: The backfill pass.

**Tasks**:
- [ ] Add `backfill_code` and `BackfillReport` in `src/engram/indexer.py` per
  the Backfill pass Feature; add
  `test_backfill_adds_module_context_and_reuses_symbol_vectors` (the fake
  embedder receives only the module-context texts),
  `test_backfill_indexes_source_cached_as_empty_and_clears_mark`,
  `test_backfill_second_run_embeds_nothing`,
  `test_backfill_skips_new_and_changed_sources`,
  `test_backfill_chunker_failure_keeps_existing_rows` and
  `test_backfill_repo_scope_leaves_other_repos_untouched` in
  `tests/test_backfill.py`. Seed "pre-00013" stores by writing only the symbol
  chunks of a file (drop the module-context chunks) under its current hash
  (depends on: Phase 0) - Acceptance:
  `.venv/bin/python -m pytest -q tests/test_backfill.py -k "test_backfill_"` passes.

**Exit Criteria**: All backfill pass tests pass.

### Phase 2: Integration
**Goal**: CLI flag and docs.

**Tasks**:
- [ ] Add `--backfill-code` to the index parser and handling in `_run_index` in
  `src/engram/cli.py` per the CLI flag Feature; add
  `test_cli_backfill_rejects_corpus_rebuild_and_reembed` and
  `test_cli_backfill_prints_summary` in `tests/test_backfill.py`. Tests must
  patch the store path to `tmp_path`, never the production DB (depends on:
  Phase 1) - Acceptance: `.venv/bin/python -m pytest -q tests/test_backfill.py -k cli_backfill` passes.
- [ ] In `README.md`, replace the sentence "A backfill is a separate, explicit
  operation." with a description of `engram index --backfill-code`, and add it
  to the Usage block; add an `### Added` entry for **index** in `CHANGELOG.md`
  under `[Unreleased]` (depends on: Phase 2 task 1) - Acceptance:
  `rg -n "backfill-code" README.md CHANGELOG.md` shows both files, and
  `rg -c "A backfill is a separate, explicit operation" README.md` reports 0.

**Exit Criteria**: `.venv/bin/python -m pytest -q --ignore=eval` and
`PYTHONPATH=src:. .venv/bin/python -m pytest -q eval` pass; `git diff --check` passes.

## Test Strategy

### Critical Scenarios
- **Happy path**: unchanged file indexed before 00013 → Expected: module
  context chunks added, symbol vectors reused, no embed call for symbols.
- **Edge case**: file cached as empty that has top-level code → Expected:
  context chunks stored, empty mark removed.
- **Edge case**: stored symbols differ from fresh ones (parser upgrade) →
  Expected: source replaced; changed chunks embedded, unchanged ones reused.
- **Edge case**: second run → Expected: zero chunks embedded, zero sources rechunked.
- **Error case**: chunker raises for one file → Expected: path in
  `failed_sources`, its rows unchanged, other files processed.

## Risks

- **Running on production**: out of scope for this PRD. No task runs the
  command against `~/.local/share/engram/engram.db`. The maintainer runs it
  after a backup.
- **Large embed volume**: files whose symbols changed with the parser upgrade
  (about 760 on 2026-11-10) re-embed their changed chunks; the rest embed only
  new context chunks.
