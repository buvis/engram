---
prd: docs/dev/project-management/prds/wip/00011-memory-migrate-command-v1.md
review: 1
date: 2026-11-10
head_sha: 50fb01c853c16c44d5ce2f0d43a26b27acc06bb7
codex_thread_id: 01a1c747-8c3c-7980-a4af-f810b3f404ba
reviewers: alice,blake,bob
agents:
  alice: available
  blake: available
  bob: available
dispatch_rows:
  bob: b11b78e5
---

# Review: 00011-memory-migrate-command-v1

Diff range: `0b8c77153329d738a35e44217e31addc510ac5ec..50fb01c853c16c44d5ce2f0d43a26b27acc06bb7`

codex_rung_guard: not fired

## Review Summary

Reviewed: 4 completed tasks (full review, cycle 1, since `work_start_sha` `0b8c771`)
PRDs checked: 00011-memory-migrate-command-v1

- Consensus engine: legacy (single Alice subagent).
- pack: ok (`docs/dev/tmp/engram-pack-00011c1.md`).
- Carl: not dispatched this cycle (diff has no frontend; his route spends Copilot credits). Roster is alice,blake,bob.
- Bob ran on the inlined prompt (207,571 bytes), fresh codex thread.
- Mechanical test checks: no `[MECH]` rows. Fail-first replay skipped by Alice (no `.venv` in her run); `migrate.py` is new at the base commit, so no test of it can pass against the pre-change code.
- Consolidation: script (`consolidate_findings.py`), no ledger (cycle 1). The script folded the "wiring files read twice" finding (Alice 🟡 + Bob 🟡) into R1; it is restored as its own row R11 by hand.
- Process note: Alice's verdict list has no R5, and Bob's has none either. The consensus rubric has no R5. Both lists are complete.
- Test gate: `review-stage` and `autopilot verify` (exit 3) both ran the suite (exit 0) but could not parse pytest's plain `841 passed` summary. The `Tests:` line below is read from `docs/dev/tmp/gate-50fb01c.log` line 41; `last-verification.json` was not written.

### Agent Status

- Alice (Claude, consensus): ✅ Available - 5 findings
- Blake (Claude, blind/PRD-only): ✅ Available - 5 findings (all ⚪), B1-B19 all pass
- Bob (codex, consensus + doubt): ✅ Available - 5 FIX findings, D1-D5 all pass

## Consolidated Findings

| Ref | Consensus | Severity | Issue | File | Task | Found By |
|-----|-----------|----------|-------|------|------|----------|
| R1 | [2/3] | 🟠 | Symlinked wiring files are silently replaced by regular files and can lose content. `_write_if_changed` calls `os.replace(tmp, path)` on the link itself, and `_plan_wiring` reads through the link. Reproduced with `CLAUDE.md` as a symlink to `AGENTS.md`: after `apply`, `CLAUDE.md` is a regular file with the old `AGENTS.md` text plus the import line, without the new `## Project memory` section. Rollback also loses the link (Bob: a failure after replacement restores regular-file bytes, not the link). No test covers it. Fix: resolve each wiring path before reading and writing and plan one write per resolved target, or refuse with `MigrationError` when a wiring file is a symlink; journal link targets for rollback. Add a test. | src/engram/migrate.py:327 | 2 | ALICE, BOB |
| R2 | [2/3] | 🟡 | The README undo step says to run `git restore` and `git clean` "on the reported paths". The report lists source file names and target memory paths, but never `MEMORY.md` or the four wiring files (`.gitattributes`, `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`). Name them in the undo sentence. | README.md:55 | 4 | ALICE, BOB |
| R3 | [1/3] | 🟠 | Destination directory symlinks can redirect writes into the source tree: `repo/docs -> src` passes validation and creates files beneath `src/dev/`. Validate resolved destination containment before writing; add a source-preservation regression. | src/engram/migrate.py:248 | 2 | BOB |
| R4 | [1/3] | 🟡 | The step-6 postcondition rollback is untested. `check_directory` returning problems raises `MigrationError` inside the `try`, which then restores the repository. Only the `OSError` rollback paths have tests. Add a test that monkeypatches `check_directory` to return a violation and asserts the repository snapshot is unchanged and the message starts with "apply failed, repository restored: postcondition failed". | src/engram/migrate.py:454 | 2 | ALICE |
| R5 | [1/3] | 🟡 | Description validation rejects only LF; YAML-escaped CR or Unicode line separators pass and produce multiline index entries. Validate with `splitlines()` and add rejection tests. | src/engram/migrate.py:137 | 1 | BOB |
| R6 | [1/3] | ⚪ | `tests/test_memory_migrate.py` is 1355 lines, over the 800-line limit. The assumptions ledger records an accepted exception at 1054 lines because the PRD acceptance commands pin the file, but it has grown with the CLI tests. Record the new size in the exception, or move more fixtures into `tests/_migrate_helpers.py`. | tests/test_memory_migrate.py:1 | general | ALICE |
| R7 | [1/3] | ⚪ | Extra `skip-invalid` reasons the spec does not list: a source with an absolute host path, a slug collision between two sources, and a slug named `memory`. All three are defensive and in the spirit of "no absolute host path is written". Accepted additions, but an operator will see `skip-invalid` details the PRD never defines. | src/engram/migrate.py:144 | 1 | BLAKE |
| R8 | [1/3] | ⚪ | Extra refusals and rollback beyond the spec: `MigrationError` when the source overlaps the repository, when an existing target file is invalid, or when `MEMORY.md` would exceed the index limits; `apply_migration` also journals writes and restores them on failure. Safe, tested, mild scope growth. | src/engram/migrate.py:248 | 2 | BLAKE |
| R9 | [1/3] | ⚪ | The `AGENTS.md` heading check is an exact-line match on `## Project memory`. A hand-written `## Project Memory` or `### Project memory` would not count, so a second section could be appended. The spec leaves the match undefined. | src/engram/migrate.py:361 | 2 | BLAKE |
| R10 | [1/3] | ⚪ | `.claude/settings.json` is re-serialised with `json.dumps(indent=2)` whenever it changes. Key order is kept, but original formatting and duplicate keys are lost. Within spec. | src/engram/migrate.py:380 | 2 | BLAKE |
| R11 | [2/3] | 🟡 | `_plan_wiring` reads every wiring file twice (once to build the new text, again in the `_read_wiring(path) != text` filter). Read each file once into a dict and reuse it. For `.gitattributes` the `addition` and `fresh` arguments to `_appended` are the same string; `_write_if_changed` calls `path.exists()` twice back to back. | src/engram/migrate.py:384 | 2 | ALICE, BOB |

## Alice

5 findings (raw: `docs/dev/tmp/alice-output-00011c1.txt`). Her narrow run of `tests/test_memory_migrate.py`: 161 passed. Her full run with `-x` stopped at `tests/test_harness.py` (`ModuleNotFoundError: No module named 'eval'`, outside this diff and a no-`.venv` artifact; the gate's own run with the project venv passed 841). Rubric: R13 fail, all others pass.

## Blake

5 findings, all ⚪ (raw: `docs/dev/tmp/blake-output-00011c1.txt`). 161 tests pass on his narrow run, `git diff --check` clean. Rubric: B1-B19 all pass.

## Bob

5 FIX findings (raw: `docs/dev/tmp/bob-output-00011c1.txt`). VERIFY and KNOWN buckets empty, so no checks were queued. Rubric: R1, R7, R9, R10 fail; others pass.

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

Verdict: 11 findings
Tests: 841 passed (suite run this cycle; counts read from gate log, autopilot verify could not parse the pytest summary)
