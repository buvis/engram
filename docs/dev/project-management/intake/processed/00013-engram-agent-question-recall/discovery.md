# Discovery: Index source outside parsed symbols

## Classification

Depth: comprehensive | Date: 2026-11-15
Source: `idea.md` beside this file.
Disposition: promote the code-coverage slice to PRD 00013; retain other candidates
below with explicit reopening conditions.

## Problem

The adoption blocker in the original idea is resolved: the user accepted the
relevance spot check, and PRD 00012 shipped MCP and nudge. A narrower coverage
defect remains. `symbols.chunk` emits parsed structures, leaving some imports,
constants and other top-level text unindexed. A local fixture on 2026-11-15
produced only function lines 4–5 from a seven-line Python file containing an
import, constant and trailing table; the import/constant-only fixture produced
zero chunks. This is missing source coverage independently of ranking scores.

## Requirements

### Must have

- R1: For a supported, successfully parsed file, retain existing symbol chunks
  and cover every nonblank source line outside their spans with source-context
  chunks. A file with no emitted symbols but nonblank text gets context chunks.
- R2: Each added chunk identifies a contiguous original source range. Its body
  must equal that source slice; do not concatenate disjoint gaps under one
  misleading start/end pointer. Omit whitespace-only gaps.
- R3: Preserve existing symbol metadata, bodies, traversal order and ordinals.
  Append context chunks in source order with distinct subsequent ordinals.
  A line covered by an emitted symbol must not enter a context chunk.
- R4: Keep source-context chunks out of name-based symbol lookup. File lookup
  and corpus search may return them. Repository, corpus and exclusion semantics
  remain unchanged.
- R5: Use ordinary incremental indexing for new or changed files. Do not
  invalidate all source hashes or empty-source markers. Unchanged files,
  including those previously cached as empty, retain their current index until
  changed or separately backfilled. Existing legacy-anonymous migration remains.
- R6: Unsupported grammars and whitespace-only sources still produce no chunks.
  Read and parser failures still propagate to the indexer's retry/preservation
  behavior. A parse failure must never become a whole-file success fallback.

### Out of scope

Rank/fusion changes, corpus expansion, query rewriting, model changes, automatic
backfill, new reindex flags, new chunk-size budgets and adoption-gate changes.
No live index or server operation is part of this specification pass or its build.

## Constraints

Preserve source pointers, source hashes and the current embedding model.
Tests use temporary sources/stores and fake embeddings. Existing embedding input
limits still apply: full context bodies are searchable lexically, but a long
body's tail is not guaranteed to enter its dense vector. Do not claim improved
production recall from a fixture coverage test.

## Codebase Context

- `src/engram/symbols.py`: recursive structure walk, inclusive parser line
  ranges converted to one-based `Chunk` pointers; includes kinds beyond
  functions/classes, so compute gaps from emitted spans rather than kind names.
- `src/engram/store.py`: `Chunk`, unique source/hash/ordinal keys,
  `lookup_by_name` and `lookup_by_path`. Name lookup currently matches headings
  for every code chunk, so new context records need an explicit exclusion.
- `src/engram/indexer.py`: hashes skip unchanged sources and empty results;
  changed sources are chunked, embedded and old hashes pruned.
- `tests/test_symbols.py`, `tests/test_indexer.py`,
  `tests/test_empty_sources.py` and `tests/test_backlog_delivery.py` provide
  parser, cache, retry and lookup patterns.
- `src/engram/client.py`: existing embedding input limits; no change required.

## Approach

Compute the union of emitted symbol line spans and its complement over the source.
For each maximal uncovered run, trim leading/trailing blank lines; emit it only
if nonblank text remains. Keep internal blanks. Use reserved doc type
`module_context` and heading `Module context` to distinguish these records;
exclude that type from symbol-name
lookup. These are agent-selected local implementation conventions, not prior
user choices. The reserved type avoids conflating context with a parser's module
symbol kind. The declaration makes the downstream contract explicit.

Reject one chunk concatenating all gaps: its pointer would include omitted
symbols. Reject a whole-file chunk beside every symbol: it duplicates symbol
content. Reject a global format-version invalidation: it silently schedules a
large re-embedding job and contradicts unchanged-source caching. Retain the
existing truncation behavior rather than add a second chunk-budget mechanism.

## Success Criteria

- Fixtures cover a preamble, inter-symbol gap, trailing gap, no-symbol file,
  nested/overlapping symbols, blank-only gaps and non-ASCII source. Added bodies
  equal their source slices and include each uncovered nonblank line once.
- Existing symbol chunks compare equal before/after on controlled fixtures.
- In a temporary indexed fixture, lexical search finds a token appearing only
  outside symbols, name lookup excludes context and file lookup includes it.
- Incremental tests cover new/changed files, an unchanged second run with zero
  embeddings, legacy cached-empty unchanged files, changed cached-empty files,
  source deletion and failure retention. No real model service is needed.

## Risks

- Pointer corruption from disjoint text: contiguous chunks and source-slice tests.
- Accidental symbol duplication: union all emitted spans, including nesting.
- Surprising partial rollout: document unchanged/cached-empty behavior in README.
- Dense tail truncation: disclose the existing limit; no full-dense-coverage claim.
- Lookup pollution: test the context heading against exact and prefix lookup.

## Deferred candidates and ownership

| Candidate from original idea | Disposition and reopening condition |
|---|---|
| Lexical OR | Owned by intake 00009; requires fresh paired relevance evidence. |
| File-seeking scope / corpus quotas | Deferred. The second set found useful findings and transcript hits; do not suppress them from the first set's label distribution. Reopen on caller-specific relevance failures. |
| Worktree/plugin-cache canonical paths | Deferred. Specify separate scoring identity and nudge suppression semantics from a reproducible duplicate-path failure. Do not infer that the present nudge has an already-seen filter. |
| Extra project-management folders | Deferred. Start with a concrete missing-answer example and corpus/exclusion ownership; do not silently expand discovery enumeration. |
| Dotfiles, host rules/hooks, notes vault | Deferred. Separate source boundary and exposure policy needed before indexing. |
| Wide-pool reranking | Owned by intake 00008; requires gain/latency evidence. |
| Backfill unchanged code | Separate attended operation. Quantify affected sources and cost before authorization; re-embedding existing chunks alone cannot add missing source spans. |
| Split/gate PRD 00012 | Superseded by the accepted adoption check and completed PRD. |

## Discovery Log

- Prior user decision: relevance-based top-3 scoring, human spot check, unchanged
  60% bar. The check passed on 2026-11-15; do not repeat it as a new blocker.
- Observed local fixture: only `Function run` at 4–5; module-only chunk count 0.
  Temporary files were removed automatically; no index or model was accessed.
- Agent scope decision under standing authorization: the independently
  demonstrable coverage defect is buildable now; ranking and source expansion
  stay separate. Contiguous gaps refine the idea's one-chunk-per-file sketch to
  satisfy the existing source-pointer contract.
- R5 resolves rollout without a full rebuild. Shipping the chunker does not
  mean the already-indexed portfolio has gained this coverage.
- All comprehensive question categories were resolved from existing decisions,
  observed code or the reversible defaults above. No new user answer is claimed.

## Open Questions

None block this slice. The deferred table preserves the evidence/authorization
needed for later work; those items are not tasks in PRD 00013.
