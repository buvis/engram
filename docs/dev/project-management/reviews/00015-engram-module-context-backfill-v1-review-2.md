---
prd: docs/dev/project-management/prds/wip/00015-engram-module-context-backfill-v1.md
review: 2
date: 2026-11-16
head_sha: ecff97c2f618aa0f5a6164ae90a592df32358b85
codex_thread_id: 01a1e4da-4772-7280-8378-c1a4803781f9
reviewers: alice,blake,bob,carl
agents:
  alice: available
  blake: available
  bob: available
  carl: available
dispatch_rows:
  bob: 367c35f4
  carl: dec0e8e8
---

# Review: 00015-engram-module-context-backfill-v1

Diff range: `9b94153f1d975366ae7237354c9ffecb45201538..ecff97c2f618aa0f5a6164ae90a592df32358b85`

codex_rung_guard: not fired

## Review Summary

Incremental review (cycle 2) of the cycle-1 rework: the atomic empty-source
transition (task 5) plus its tests.

Reviewed: 5 completed tasks
PRDs checked: 00015-engram-module-context-backfill-v1.md

### Agent Status

- Alice: ✅ Available (native Claude subagent, consensus lens)
- Blake: ✅ Available (native Claude subagent, blind/PRD-only lens)
- Bob: ✅ Available (codex, doubt lens D1-D5 + de-slop, resumed thread
  `01a1e4da-4772-7280-8378-c1a4803781f9`)
- Carl: ✅ Available (gemini-run backend=copilot)

Context pack: ok. Mechanical checks: 0 tautological test shapes in 9 checked
test functions. The fail-first replay was **skipped** this cycle - the replay
runner could not find `.venv/bin/python` in its base worktree - so no
`[MECH]` replay line exists to absorb. Alice replayed the new tests by
reading instead and reports the new store tests and the crash-window backfill
tests both fail against `9b94153f1d97`.

Test gate: the staged `## Test gate` line carried no parseable counts
(`pytest -q` prints a one-category summary), so `autopilot verify` ran the
suite once this cycle through a wrapper that emits the PASS/FAIL/SKIP/EXIT
line; the counts below come from that run.

Prior-cycle findings routed to rework (R1, R3 of cycle 1) are both confirmed
resolved by Alice; Carl found no issues; Bob's FIX bucket holds one
documentation-accuracy item.

## Consolidated Findings

| Ref | Consensus | Severity | Issue | File | Task | Found By |
|-----|-----------|----------|-------|------|------|----------|
| R1 | [1/4] | ⚪ | `empty_cleared` is incremented for every known-empty source that is rechunked (`cleared += int(was_empty)`, src/engram/indexer.py:201). It also counts the unlikely case where the source had stored rows plus a mark and the chunker now returns nothing, because the mark is then rewritten rather than cleared. The report overstates "empty marks cleared" in that case. Only the count is wrong, so a fix is optional. Increment it only when `chunks` is non-empty. | src/engram/indexer.py:201 | 5 | ALICE |
| R2 | [1/4] | ⚪ | Vector reuse is keyed on `Chunk.text_for_embedding` (heading, repo-relative path and body), not the spec's `(heading, body)`. A stored vector is not reused if the repo name or path prefix differs, and the stricter key is arguably more correct. Behavior still matches the spec's tests and metrics. | src/engram/indexer.py:230 | 2 | BLAKE |
| R3 | [1/4] | ⚪ | Spec step 7 says known-empty sources use `store.upsert_chunks` followed by `store.unmark_empty_source`. The code instead uses a new public `Store.replace_source_chunks_and_empty_mark`, which is not in the spec's "New symbols" list. It deletes existing rows first and commits chunks and mark together. The atomicity serves spec step 8, but it is an undeclared addition. | src/engram/store.py:385 | 2 | BLAKE |
| R4 | [1/4] | ⚪ | `_rechunk_source` reuses stored rows and vectors even for sources under an empty mark. A comment explains this as crash recovery. The spec does not describe it, and it only changes behavior in an inconsistent-store state. | src/engram/indexer.py:222 | 2 | BLAKE |
| R5 | [1/4] | ⚪ | `symbols.chunk` returns `[]` without raising when `detect_language_from_path` yields None. A known source whose language is no longer detected would have its chunks deleted and be marked empty, with no failure reported. This follows the spec literally and is unlikely in practice. A guard on `skipped_files` would be safer. | src/engram/symbols.py:101 | 2 | BLAKE |
| R6 | [1/4] | ⚪ | The acceptance check `rg -c "A backfill is a separate, explicit operation" README.md` prints nothing and exits 1 when there are zero matches, rather than printing 0. The sentence is gone, so the intent is met. | README.md:177 | 3 | BLAKE |
| R7 | [1/4] | ⚪ | The assumption ledger says `unmark_empty_source` has no production caller, but the new `replace_source_chunks_and_empty_mark` calls it. Update the bullet to describe its use inside the atomic transaction. | docs/dev/project-management/meta/assumptions.md:52 | 5 | BOB |

### Auto-dismissed (ledger)

- [BLAKE] ⚪ The CLI also catches `FileNotFoundError` and exits 1, which the spec's error list omits. It mirrors plain `index` and is harmless. | File: src/engram/cli.py:350 — single-voice

## Alice

Consensus lens, implementation-aware. She verified both prior-cycle rework
findings and found one new ⚪ counting nit (R1).

- **R3 of cycle 1 (🟠, empty-source transition not atomic): resolved.**
  `Store.replace_source_chunks_and_empty_mark` (src/engram/store.py:385)
  deletes the rows and then either inserts the new rows and clears the empty
  mark, or writes the empty mark, all inside one `BEGIN` with rollback on
  error. `_rechunk_source` calls it at src/engram/indexer.py:235 for both the
  empty and non-empty cases. The interruption regression test fails each
  individual write in turn and asserts the state is unchanged; a second test
  uses an observer connection to check the rows and the mark never show apart.
- **R1 of cycle 1 (⚪, stored rows ignored under an empty mark): resolved.**
  `_rechunk_source` reads `code_chunks_with_vectors` unconditionally
  (src/engram/indexer.py:226). The `and not (was_empty and chunks)` guard
  (src/engram/indexer.py:227) still clears a stale mark on rows that already
  match the chunker, and keeps the mark of a source that still chunks to
  nothing.

She ran `tests/test_backfill.py` and `tests/test_backfill_empty_transition.py`
with `.venv/bin/python -m pytest -q`: 38 passed, 0 skipped. New function and
test-file sizes are inside the 50-line / 800-line limits. No TODOs, skips or
debug output. No regression found in the scoped diff.

R1: pass
R2: pass
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: pass
R10: pass
R11: pass
R12: pass
R13: pass

## Blake

Blind lens, PRD-only prompt (no diff, no file list, no history, no ledger). He
located the code himself and walked the spec end to end. Six ⚪ findings (five
in the table, one auto-dismissed against the ledger); every blind rubric rule
pass. `.venv/bin/python -m pytest -q tests/test_backfill.py`: 25 passed. Every
spec-listed test name exists, plus extras; README.md and CHANGELOG.md both
mention `--backfill-code`.

B1: pass
B2: pass
B3: pass
B4: pass
B5: pass
B6: pass
B7: pass
B8: pass
B9: pass
B10: pass
B11: pass
B12: pass
B13: pass
B14: pass
B15: pass
B16: pass
B17: pass
B18: pass
B19: pass

## Bob

Doubt lens (D1-D5 + de-slop), codex, static sandbox, resumed cycle-1 thread.

FIX:
- (low) The assumption ledger says `unmark_empty_source` has no production caller, but the new `replace_source_chunks_and_empty_mark` calls it (R7).

VERIFY:
- (none)

KNOWN:
- (none)

R1: pass
R2: pass
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: pass
R10: pass
R11: pass
R12: pass
R13: pass
D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Carl

Frontend & design specialist, generalist here (backend=copilot). He read the
pack, the context, the full rework diff and the touched regions of
`indexer.py`, `store.py` and the two test files, and searched for skips,
xfails, TODOs and debug statements (none found). His one shell attempt
(`pytest -q` on the two backfill test files) was denied by the
non-interactive approval guard, so his verdicts rest on static reading plus
the supplied test-gate line.

[CARL] ✅ No issues found

R1: pass
R2: pass
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: pass
R10: pass
R11: pass
R12: pass
R13: pass

## Decision gate notes

**Converged.** No 🔴 and no 🟠 row survives this cycle: the single 🟠 of cycle
1 (R3, the non-atomic empty-source transition) is confirmed fixed by Alice,
with a dedicated interruption regression test and an observer-connection test
pinning it, and no reviewer re-raised it. Every row above is ⚪ low and raised by
exactly one reviewer, so each is discarded with reason `single-voice` per the
decision gate's Single-voice Medium/Low rule and appended to the ledger. That
leaves zero actionable Medium/Low rows, so the tail sweep is skipped and the
PRD goes to the finalize session.

Two rows deserve a named reason beyond `single-voice`:

- **R3 and R4** (Blake, spec-literalism): `replace_source_chunks_and_empty_mark`
  is not in the PRD's "New symbols" list and the crash-recovery read is not in
  the spec, but both exist *because* cycle 1's 🟠 required spec step 8's
  atomicity. Blake is blind to that history by construction. The deviation is
  the fix the previous review demanded, not drift.
- **R2** is the same `text_for_embedding` keying question cycle 1 settled as
  verified-equivalent; Blake re-raised it blind (he never sees the ledger) and
  his own text agrees the behavior matches.

Verdict: 7 findings
Tests: 1383 passed, 0 failed, 0 skipped (suite run this cycle)
