---
prd: docs/dev/project-management/prds/wip/00014-engram-findings-pack-correctness-v1.md
review: 2
date: 2026-11-16
head_sha: 5eb702bd265899f832cf2236eba1d576e4130df0
codex_thread_id: 01a1e470-aa5a-7012-8900-96187c8ec250
reviewers: alice,blake,bob,carl
agents:
  alice: available
  blake: available
  bob: available
  carl: available
dispatch_rows:
  bob: 8293ea87
  carl: 8f4ce026
---

# Review: 00014-engram-findings-pack-correctness-v1

Diff range: `90d530f94c3fc1f73deefce8c611525e60a5f8d2..5eb702bd265899f832cf2236eba1d576e4130df0`
(incremental: cycle 1's rework commits only)

codex_rung_guard: not fired

pack: ok

Notes: the fail-first replay produced no data this cycle (`0 touched test(s) ran, 5 test file(s)
could not be collected at base`) - the cycle-1 test split moved tests into files that do not exist
at the base commit. The tautological-shape check found no `[MECH]` lines in the 71 test functions
it examined, so no mechanical finding is absorbed below. Bob resumed his cycle-1 codex thread.

Gate note: `autopilot verify` exited 3 (its parser read no counts from the pytest summary line
`1397 passed, 1 deselected in 37.31s`), so `last-verification.json` was not refreshed. The
`Tests:` line below is composed from that run's own log
(`docs/dev/tmp/gate-5eb702b.log`), exit 0 at HEAD.

Decision-gate consolidation correction: the residual file-size defect arrived as two rows (Alice
citing `tests/test_cli_index_status.py`, Bob citing both files). They are one defect; the gate
merged Bob's `tests/test_cli_pack.py` row into R1 and removed the duplicate, so the table below
has 7 rows.

## Review Summary

Reviewed: 13 completed tasks (9 original + 4 cycle-1 rework)
PRDs checked: 00014-engram-findings-pack-correctness-v1

### Agent Status

- Alice: ✅ Available
- Blake: ✅ Available
- Bob: ✅ Available (codex, resumed thread)
- Carl: ✅ Available (copilot backend)

Prior-cycle verification: R1, R2, R3, R4, R6, R7, R9 and R10 of cycle 1 are confirmed resolved
by Alice and Bob independently. R5 is only partly resolved - see R1 below.

## Consolidated Findings

| Ref | Consensus | Severity | Issue | File | Task | Found By |
|-----|-----------|----------|-------|------|------|----------|
| R1 | [2/4] | 🟡 | Cycle 1's R5 is only partly resolved: only `tests/test_diffmap.py` was split (706 lines, plus the new `tests/test_diffmap_decoding.py` at 382). `tests/test_cli_index_status.py` (937 lines) and `tests/test_cli_pack.py` (917 lines) are unchanged by the rework and still exceed the 800-line limit R5 named for all three files. Split coherent groups into focused modules under 800 lines, for example the rebuild tests out of `tests/test_cli_index_status.py` and the `--diff` id tests out of `tests/test_cli_pack.py`. | tests/test_cli_index_status.py:937 | 13 | ALICE, BOB |
| R2 | [1/4] | 🟡 | The PRD mandates `codecs.escape_decode(inner.encode("utf-8"))[0].decode("utf-8")`, but a hand-rolled regex decoder replaces it (`_C_QUOTED_RE`, `_C_ESCAPE_RE`, `_C_ESCAPES`, `_unquote_c_path`). It handles the PRD's cases (octal escapes, `\t`, `\n`, `\"`). It diverges on invalid UTF-8: it uses `errors="replace"` where the spec'd call would raise `UnicodeDecodeError`. Blake records it as a documented, deliberate deviation, not a bug. | src/engram/diffmap.py:124 | Phase 0 C-quoted paths | BLAKE |
| R3 | [1/4] | 🟡 | The C-quoted diffmap tests are no longer in `tests/test_diffmap.py`, where the PRD's acceptance command points. They live in `tests/test_diffmap_decoding.py` after cycle 1's split, so `pytest -q tests/test_diffmap.py -k c_quoted` deselects all 20 tests and exits 5 (Blake ran it). The same tests pass from the new file. The PRD acceptance command no longer proves the behaviour. | tests/test_diffmap_decoding.py:151 | Phase 0 C-quoted paths | BLAKE |
| R4 | [1/4] | 🟡 | Two of the three harvest registry tests are not in `tests/test_harvest.py`: the symlinked and trailing-slash tests are in `tests/test_harvest_resolve.py`. The PRD's `-k` acceptance command on `test_harvest.py` still exits 0, but selects only the unreadable-registry tests (3 passed), so it does not prove the symlink or trailing-slash cases. | tests/test_harvest_resolve.py:132 | Phase 0 registry match | BLAKE |
| R5 | [1/4] | ⚪ | `_exclude` computes `os.path.realpath(hit.path)` inside the per-span `any()` loop, once per hit per span, costing repeated syscalls (up to 40 spans times hits). The spec only requires resolving span paths once, which is done. Hoisting the hit's realpath would be cheaper. | src/engram/pack.py:77 | Phase 0 canonical exclusion | BLAKE |
| R6 | [1/4] | ⚪ | `write_lock` lets an `OSError` from `os.open` (for example `PermissionError` on the lock path) propagate. `_run_harvest` and `_run_rebuild` catch only `StoreBusyError`, so a lock-file permission problem ends in a traceback rather than a clean exit 1. The spec asks for nothing more, and a test pins the propagation. | src/engram/store.py:104 | Phase 1 locking | BLAKE |
| R7 | [1/4] | ⚪ | `_run_harvest` never closes the store it opens. This predates the change. The lock is released on process exit, so it is harmless in a short-lived CLI process. | src/engram/cli.py:247 | Phase 1 locking | BLAKE |

### Auto-dismissed (ledger)

- [BLAKE] ⚪ The tests add extras beyond the named ones: a non-OS-error propagation test, a cross-process lock test, an fd-close test and others. They are harmless scope growth. | File: tests/test_write_lock.py:82 — single-voice; reviewer states they are harmless extras

## Alice

Implementation-aware consensus lens, incremental over the cycle-1 rework commits. Verified R1,
R2, R3, R4, R6, R7 and R9 of cycle 1 as resolved, each against the code. R5 partly resolved,
raised as R1 above. Reran the touched suites: 197 passed, 0 failed, 0 skipped. No new
tautological tests found.

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
R13: fail

## Blake

Blind lens (PRD only, no diff). Every one of the PRD's seven fixes verified present and matching
the spec by reading the code himself: the strict reviewers check, canonical registry match, the
write lock and `StoreBusyError`, the harvest lock, the rebuild lock and temp-file cleanup, the
unlocked plain index, and the collision-free `--diff` id. CHANGELOG `### Fixed` entries cover
every item. Ran three test files together: 137 passed. His findings are R2, R3, R4, R5, R6, R7
above plus the ledger-dismissed row; the three 🟡 ones are all spec-vs-placement deviations, not
behaviour defects.

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

Doubt lens + de-slop (codex, cycle-1 thread resumed). FIX bucket: the two residual file-size
rows, merged into R1 above. VERIFY: (none). KNOWN: (none). No verification-check queue was
written this cycle: the VERIFY bucket is empty.

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
R13: fail

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Carl

Gemini/copilot backend, frontend & design specialist (no UI surface in this PRD; reviewed as
generalist). Read the diff and the rework commits, checked line counts at base and at HEAD, and
read the changed source and test hunks.

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

Verdict: 7 findings
Tests: 1397 passed, 0 failed, 0 skipped (suite run this cycle)
