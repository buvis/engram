# Decision Audit Log: 00015-engram-module-context-backfill-v1

PRD: `00015-engram-module-context-backfill-v1.md`
Started: 2026-11-16T15:57:24Z
Completed: 2026-11-16T15:57:24Z
Autonomous: 12  |  Deferred: 0  |  Doubts: 0

### [autonomous] 2026-11-16T15:57:24Z

**Decision**: R3: empty-source transition is not atomic (indexer.py:228-229) - a crash between replace_chunks_for_source([]) and mark_empty_source drops the source from both known and known_empty, so line 187 skips it on every later backfill

**Choice**: auto-fix (additive: wrap the pair in one transaction plus a regression test)

**Rationale**: Confirmed by reading indexer.py:187 and 227-230; fix adds code and a test without touching any signature, type or schema

### [autonomous] 2026-11-16T15:57:24Z

**Decision**: R1: _rechunk_source forces stored=[] when was_empty, so a crash before unmark_empty_source makes the next run re-embed every chunk instead of reusing stored vectors

**Choice**: auto-fix (read stored rows unconditionally, drop the was_empty conditional)

**Rationale**: Low severity, two-reviewer consensus, mechanical fix in the same function as R3

### [autonomous] 2026-11-16T15:57:24Z

**Decision**: R2 and nine single-voice Medium/Low findings (R4-R13)

**Choice**: discard, recorded in the settled-decisions ledger

**Rationale**: R4-R13 are each [1/4] Medium or Low, which the decision gate discards as single-voice; R2 is discarded on a verified equivalence (path component is constant within one _rechunk_source call)

### [autonomous] 2026-11-16T15:57:24Z

**Decision**: `_rechunk_source` ignores stored rows when `was_empty` (`stored = [] if was_empty else ...`). A crash between `replace_chunks_for_source` (commit) and `unmark_empty_source` (autocommit) leaves a source with both rows and an empty mark. The next run then re-embeds every chunk instead of reusing the stored vectors, which defeats the "safe to repeat" and reuse goals. Calling `store.code_chunks_with_vectors(path)` unconditionally closes that window and drops the conditional. It returns [] for a genuinely empty source.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T15:57:24Z

**Decision**: Empty-source transition lacks a transaction spanning chunk replacement and empty marking. Interruption between these calls leaves neither chunks nor an empty mark, so subsequent backfills skip the source. Commit both operations atomically and add an interruption regression test.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T15:57:24Z

**Decision**: R1 empty_cleared counts a rewritten empty mark as cleared (src/engram/indexer.py:201)

**Choice**: discard

**Rationale**: single-voice; report-counter nit the finding itself calls optional (cycle 2)

### [autonomous] 2026-11-16T15:57:24Z

**Decision**: R2 vector reuse keyed on text_for_embedding, not the spec's (heading, body) (src/engram/indexer.py:230)

**Choice**: discard

**Rationale**: single-voice; cycle 1 settled this as verified-equivalent, re-raised by the blind lens which never sees the ledger (cycle 2)

### [autonomous] 2026-11-16T15:57:24Z

**Decision**: R3 replace_source_chunks_and_empty_mark is an undeclared new symbol (src/engram/store.py:385)

**Choice**: discard

**Rationale**: single-voice; the symbol exists because cycle 1's orange finding required atomicity two separate calls cannot give (cycle 2)

### [autonomous] 2026-11-16T15:57:24Z

**Decision**: R4 _rechunk_source reuses stored rows under an empty mark, undescribed by the spec (src/engram/indexer.py:222)

**Choice**: discard

**Rationale**: single-voice; this is cycle 1 finding R1's accepted fix, invisible to the blind lens by construction (cycle 2)

### [autonomous] 2026-11-16T15:57:24Z

**Decision**: R5 symbols.chunk returns [] silently for an undetectable language (src/engram/symbols.py:101)

**Choice**: discard

**Rationale**: single-voice; pre-existing chunker behavior shared with plain index, outside this PRD's scope (cycle 2)

### [autonomous] 2026-11-16T15:57:24Z

**Decision**: R6 the PRD's rg -c acceptance check exits 1 on zero matches (README.md:177)

**Choice**: discard

**Rationale**: single-voice; a note about the PRD's own acceptance command, not the shipped code, and the intent is met (cycle 2)

### [autonomous] 2026-11-16T15:57:24Z

**Decision**: R7 assumptions.md still says unmark_empty_source has no production caller (docs/dev/project-management/meta/assumptions.md:52)

**Choice**: discard

**Rationale**: single-voice; stale line in an autopilot process artifact the build gate rewrites per PRD (cycle 2)
