---
prd: docs/dev/project-management/prds/wip/00011-memory-migrate-command-v1.md
review: 2
date: 2026-11-10
head_sha: e386c75d6bc0c7cbce4a0abe3344698932c900bf
codex_thread_id: 01a1c747-8c3c-7980-a4af-f810b3f404ba
reviewers: alice,blake,bob
agents:
  alice: available
  blake: available
  bob: available
dispatch_rows:
  bob: 3b8ef591
---

# Review: 00011-memory-migrate-command-v1

Diff range: `50fb01c853c16c44d5ce2f0d43a26b27acc06bb7..e386c75d6bc0c7cbce4a0abe3344698932c900bf`

codex_rung_guard: not fired

## Review Summary

Reviewed: 6 completed tasks (incremental review, cycle 2, since `50fb01c`)
PRDs checked: 00011-memory-migrate-command-v1

- Consensus engine: legacy (single Alice subagent).
- pack: ok (`docs/dev/tmp/engram-pack-00011c2.md`).
- Carl: not dispatched (diff has no frontend). Roster is alice,blake,bob.
- Bob ran on the inlined prompt, resumed his cycle 1 codex thread.
- Mechanical test checks: no `[MECH]` rows besides Bob's R3 hedge row (merged by hand with Alice's R2 hedge finding is NOT done: they cite different lines, 490 and 238, so both stay).
- Consolidation: script (`consolidate_findings.py`) with settled ledger; one Blake finding auto-dismissed.
- Cycle 1 findings R1, R2, R3, R11 verified resolved by Alice (183 tests on the two migrate test files).
- Reproduced by the orchestrator: with `repo/docs -> missing` (dangling), `apply_migration` raises `apply failed, repository restored: [Errno 17] File exists` and the link is gone afterwards (`os.path.islink` false). Bob's R1 is real.
- Test gate: `review-stage` suite run exit 0; counts read from `docs/dev/tmp/gate-00011c2.log` line 13 (`863 passed`).

### Agent Status

- Alice (Claude, consensus): ✅ Available - 3 findings
- Blake (Claude, blind/PRD-only): ✅ Available - 5 findings (all ⚪), B1-B19 all pass
- Bob (codex, consensus + doubt): ✅ Available - 2 FIX findings, D1-D5 all pass

## Consolidated Findings

| Ref | Consensus | Severity | Issue | File | Task | Found By |
|-----|-----------|----------|-------|------|------|----------|
| R1 | [1/3] | 🟠 | Dangling internal directory symlinks pass `_check_destination`: `repo/docs -> missing` resolves inside the repository. Apply then fails during directory creation; its journal treats the dangling link as absent and rollback deletes it. Reject dangling destination links before writing, or preserve their link identity in the journal. Add a regression asserting the link survives. | src/engram/migrate.py:270 | 5 | BOB |
| R2 | [1/3] | 🟡 | The assertion `assert "symlink" in message or "resolves" in message` is an either-or hedge. The refusal message always contains both words, so this assert cannot fail on its own. Drop the `or` and assert `"symlink resolves" in message`. | tests/test_memory_migrate_symlinks.py:490 | 5 | ALICE |
| R3 | [1/3] | 🟡 | Mechanical check flags the diagnostic hedge `"symlink" in message or "resolves" in message`. Replace it with the specific expected diagnostic for each fixture. | tests/test_memory_migrate_symlinks.py:238 | 5 | BOB |
| R4 | [1/3] | ⚪ | `_check_destination` over-refuses with a misleading "symlink" message when an empty source sits inside the repository or the repository sits inside the source. Narrow the overlap test or reword. | src/engram/migrate.py:277 | 5 | ALICE |
| R5 | [1/3] | ⚪ | Dry run does not check for symlinked wiring files, so it can exit 0 where `--apply` refuses. Pinned on purpose; same accepted gap as a bad `settings.json`. | src/engram/migrate.py:411 | 5 | ALICE |
| R6 | [1/3] | ⚪ | Absolute-host-path skip is stricter than the spec; documented in the README. | src/engram/migrate.py:63 | 1 | BLAKE |
| R7 | [1/3] | ⚪ | Slug collision `skip-invalid` is outside the spec's defined cases. | src/engram/migrate.py:174 | 1 | BLAKE |
| R8 | [1/3] | ⚪ | Fail-closed `MigrationError` refusals print no TSV report, though the spec says the dry run lists every source file. | src/engram/migrate.py:248 | 1 | BLAKE |
| R9 | [1/3] | ⚪ | `memory_files` omits a broken symlink named `x.md` from the report. | src/engram/memory.py:44 | 1 | BLAKE |

### Auto-dismissed (ledger)

- [BLAKE] ⚪ Apply rewrites an existing `.claude/settings.json` with `json.dumps(indent=2)`. Keys are kept, formatting changes. The spec allows this. | File: src/engram/migrate.py:401 — single-voice; within spec

## Alice

3 findings (raw: `docs/dev/tmp/alice-output-00011c2.txt`). Prior R1, R2, R3, R11 resolved. 183 passed on the two migrate test files. Rubric: R2 fail, all others pass.

## Blake

5 findings, all ⚪ (raw: `docs/dev/tmp/blake-output-00011c2.txt`). B1-B19 all pass.

## Bob

2 FIX findings (raw: `docs/dev/tmp/bob-output-00011c2.txt`). VERIFY and KNOWN empty, so no checks queued. Rubric: R1, R2, R7, R9, R10 fail; others pass.

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

Verdict: 9 findings
Tests: 863 passed (suite run this cycle; counts read from gate log, autopilot verify could not parse the pytest summary)
