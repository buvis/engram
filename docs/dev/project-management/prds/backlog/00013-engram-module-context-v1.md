---
default_model: opus
model_tier_rationale: preserve existing symbol output while adding complementary spans and lookup semantics
design: run
---

# Index code outside parsed symbols

Source: `docs/dev/project-management/intake/processed/00013-engram-agent-question-recall/discovery.md`

## Overview

### Problem Statement

Imports, constants and other source text outside emitted symbol spans can be
absent from the code index. A supported Python file with only imports/constants
currently produces no chunks. This PRD delivers the source-coverage slice of
intake 00013. Adoption has already passed and PRD 00012 is done.

### Target Users

Agents seeking code through query, packs, MCP or nudge, and developers using
file lookup. Name lookup must continue to return actual symbols.

### Success Metrics

Every nonblank line outside emitted symbol spans appears once in added context
on controlled fixtures. Existing symbol chunks retain their field values and
order. Temporary-store tests demonstrate lexical retrieval of previously absent
text and zero embedding calls on the next unchanged run. This is a coverage
guarantee, not an aggregate relevance claim or a portfolio backfill.

## Functional Decomposition

### Capability: Complete source coverage

Add source context without duplicating emitted symbols.

#### Feature: Contiguous source-context chunks
- **Description**: Index the complement of emitted symbol line spans.
- **Inputs**: The decoded source and existing symbol chunks from `symbols.chunk`.
- **Outputs**: Existing chunks followed by source-context `Chunk` records.
- **Behavior**: Union the inclusive one-based spans of all emitted chunks,
  including nested/overlapping chunks. Compute maximal uncovered runs over the
  original source lines. Trim only leading/trailing whitespace-only lines in
  each run; omit empty runs. Emit the exact remaining source slice joined with
  newlines, preserving internal whitespace. Use corpus code, reserved doc type
  module_context, heading Module context, and the same repo/path/content hash.
  Append runs in source order with ordinals after the last existing ordinal
  (start at 1 if none). Existing chunks remain field-for-field unchanged.
  A supported nonblank file with no symbols follows the same gap rule. No new
  size splitting or embedding budget is introduced; existing limits still apply.

#### Feature: Preserve parsing boundaries
- **Description**: Do not turn failed or unsupported parsing into success.
- **Inputs**: Unsupported, whitespace-only, unreadable and parse-failing files.
- **Outputs**: Existing skip/empty/error outcomes.
- **Behavior**: Unsupported grammars still skip. Blank sources emit no chunks.
  Read/parser exceptions propagate as today; context is emitted only after a
  successful parse. Enumeration and exclusion rules are unchanged.

### Capability: Compatible retrieval and incremental rollout

Expose context through search/file lookup while preserving symbol lookup and caches.

#### Feature: Context-aware lookup
- **Description**: Context is searchable source, not a named symbol.
- **Inputs**: Stored code chunks and existing name/file lookup requests.
- **Outputs**: Name lookup excludes module_context; file lookup includes it.
- **Behavior**: `Store.lookup_by_name` excludes the reserved context type in
  exact matching, explicit prefix matching and its prefix fallback. Preserve
  scopes and ordering. `Store.lookup_by_path` and ordinary corpus search include
  context without new flags or changes to query/fusion defaults.

#### Feature: Incremental rollout with explicit limits
- **Description**: Apply new chunking when ordinary indexing processes a source.
- **Inputs**: New, changed, unchanged and cached-empty code sources.
- **Outputs**: Context for newly processed sources; existing caches remain valid.
- **Behavior**: Keep current hash/empty-cache skips and legacy-anonymous migration.
  A new/changed source gains context; a changed formerly empty source is retried;
  an unchanged formerly empty source remains cached. Preserve failure retention
  and deletion pruning. Do not bump cache versions, clear hashes, add migrations
  or run a live index. README explains this partial rollout and that re-embedding
  existing chunks alone does not discover missing spans. Backfill is separate.

## Structural Decomposition

### Repository Structure

```text
src/engram/
  symbols.py                    # Source-context generation
  store.py                      # Name lookup exclusion
tests/
  test_module_context.py        # New coverage and integration regressions
README.md                       # Rollout limits
```

### Module: Source chunking
- **Maps to capability**: Complete source coverage
- **Responsibility**: Extend `src/engram/symbols.py` after its existing walk.
- **Exports**: Existing `chunk`; no new public API.

### Module: Lookup
- **Maps to capability**: Compatible retrieval and incremental rollout
- **Responsibility**: Exclude reserved context records from symbol-name matching.
- **Exports**: Existing `Store.lookup_by_name` and `Store.lookup_by_path`.

### Module: Coverage verification and documentation
- **Maps to capability**: Both capabilities
- **Responsibility**: Exercise real chunk/store/index behavior on temporary data;
  describe limitations in README. Reuse fixture patterns from existing tests.
- **Exports**: Pytest cases, no runtime API.
- New symbols: `tests/test_module_context.py`

## Dependency Graph

### Foundation Layer (Phase 0)
- **Source chunking**: Existing `Chunk` and parser interfaces; no new dependency.

### Core Layer (Phase 1)
- **Lookup**: Depends on source chunking's reserved module_context type.

### Integration Layer (Phase 2)
- **Coverage verification and documentation**: Depends on source chunking and
  lookup; exercises the existing indexer without changing its rollout policy.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Add truthful contiguous source coverage.

**Tasks**:
- [ ] Implement gap chunks and additive fixture tests (no deps). Acceptance:
  `.venv/bin/python -m pytest -q tests/test_module_context.py -k chunk` passes
  non-vacuously with preamble/interstitial/tail, no-symbol, nested/overlapping,
  whitespace and non-ASCII cases. Compare original symbol chunks exactly.
  `.venv/bin/python -m pytest -q tests/test_symbols.py` also passes unchanged.

**Exit Criteria**: Exact source slices cover every uncovered nonblank fixture
line once, without altering symbol chunks or swallowing parser errors.

### Phase 1: Core
**Goal**: Keep symbol lookup distinct from source search.

**Tasks**:
- [ ] Exclude context in name lookup and add lookup regressions (depends on:
  Phase 0). Acceptance: `.venv/bin/python -m pytest -q tests/test_module_context.py -k lookup`
  passes non-vacuously, covering exact/prefix/fallback exclusion, file inclusion,
  lexical retrieval of an outside-symbol token and repository isolation.
  `.venv/bin/python -m pytest -q tests/test_backlog_delivery.py -k lookup` passes.

**Exit Criteria**: Context is available to search and file lookup, never reported
as a symbol named by its synthetic heading.

### Phase 2: Integration
**Goal**: Verify incremental behavior and document partial rollout.

**Tasks**:
- [ ] Add temporary-store incremental regressions and README rollout guidance
  (depends on: Phase 1). Acceptance: `.venv/bin/python -m pytest -q tests/test_module_context.py -k index`
  passes non-vacuously for new/changed, unchanged, cached-empty unchanged/changed,
  deletion and failure-retention cases using fake embeddings. README contains
  the phrases "unchanged files" and "backfill" and explains no automatic migration.
  `.venv/bin/python -m pytest -q tests/test_indexer.py tests/test_empty_sources.py tests/test_backlog_delivery.py`
  passes, including existing legacy-anonymous migration. Run portable main tests
  with `.venv/bin/python -m pytest -q --ignore=eval -m 'not private'` and evaluation
  tests with `PYTHONPATH=src:. .venv/bin/python -m pytest -q eval -m 'not private'`.

**Exit Criteria**: Tests show no new automatic cache invalidation, preserve retry
and pruning behavior, and document deferred coverage for unchanged sources.

## Test Strategy

### Critical Scenarios
- **Happy path**: Outside-symbol identifier enters a context chunk and FTS search.
- **Edge case**: No symbols, nested spans, blank runs and non-ASCII line offsets.
- **Error case**: Read/parser failure preserves old indexed rows and retries.
- **Compatibility**: Exact symbol records and name lookup stay intact; file lookup
  includes context; unchanged source caches prevent unnecessary embeddings.
- Tests use temporary stores and fake embeddings, never the production index.
  Keep existing tests; add coverage rather than weakening assertions. Historical
  evaluation artifacts and adoption decisions are outside this change.

## Risks

- Added chunks increase indexing cost only for processed sources; no bulk backfill.
- Long context tails can exceed existing dense-input limits; FTS keeps the body.
- A parser kind named module must remain a symbol; only reserved module_context
  records are filtered. Do not filter generic module kinds.
- User-facing impact: code search/file lookup gains context on processed sources;
  existing unchanged sources do not gain it automatically. No ranking gain claimed.
