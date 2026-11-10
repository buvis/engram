# Decision Audit Log: 00011-memory-migrate-command-v1

PRD: `00011-memory-migrate-command-v1.md`
Started: 2026-11-10T21:40:46Z
Completed: 2026-11-10T21:40:46Z
Autonomous: 9  |  Deferred: 0  |  Doubts: 0

### [autonomous] 2026-11-10T21:40:46Z

**Decision**: design approach for 00011 memory migrate

**Choice**: migrate.py with shared two-pass classify/render for plan and apply; plan refuses overlap, source aliases, invalid target state, index overflow; HOST_PATH_RE defines absolute host path; undo-journal rollback on failed apply

**Rationale**: 3 design dispatches (claude, codex, codex); 1 cardinal sin and 10 blockers fixed; open non-blockers in design Review log, dispatch 3 blocker fixes not reviewer-verified

### [autonomous] 2026-11-10T21:40:46Z

**Decision**: tests/test_memory_migrate.py exceeds 800 lines (1008) after task 2 tests

**Choice**: accepted the overage; shared helpers moved to tests/_migrate_helpers.py, all test functions stay in the pinned file

**Rationale**: PRD acceptance commands pin tests/test_memory_migrate.py with -k filters; same precedent as PRD 00010 test_repo_memory.py

### [autonomous] 2026-11-10T21:40:46Z

**Decision**: Symlinked wiring files are silently replaced by regular files and can lose content. `_write_if_changed` calls `os.replace(tmp, path)` on the link itself, and `_plan_wiring` reads through the link. Reproduced with `CLAUDE.md` as a symlink to `AGENTS.md`: after `apply`, `CLAUDE.md` is a regular file with the old `AGENTS.md` text plus the import line, without the new `## Project memory` section. Rollback also loses the link (Bob: a failure after replacement restores regular-file bytes, not the link). No test covers it. Fix: resolve each wiring path before reading and writing and plan one write per resolved target, or refuse with `MigrationError` when a wiring file is a symlink; journal link targets for rollback. Add a test.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-10T21:40:46Z

**Decision**: The README undo step says to run `git restore` and `git clean` "on the reported paths". The report lists source file names and target memory paths, but never `MEMORY.md` or the four wiring files (`.gitattributes`, `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`). Name them in the undo sentence.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-10T21:40:46Z

**Decision**: Destination directory symlinks can redirect writes into the source tree: `repo/docs -> src` passes validation and creates files beneath `src/dev/`. Validate resolved destination containment before writing; add a source-preservation regression.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-10T21:40:46Z

**Decision**: `_plan_wiring` reads every wiring file twice (once to build the new text, again in the `_read_wiring(path) != text` filter). Read each file once into a dict and reuse it. For `.gitattributes` the `addition` and `fresh` arguments to `_appended` are the same string; `_write_if_changed` calls `path.exists()` twice back to back.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-10T21:40:46Z

**Decision**: Dangling internal directory symlinks pass `_check_destination`: `repo/docs -> missing` resolves inside the repository. Apply then fails during directory creation; its journal treats the dangling link as absent and rollback deletes it. Reject dangling destination links before writing, or preserve their link identity in the journal. Add a regression asserting the link survives.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-10T21:40:46Z

**Decision**: Cycle 2 R2/R3 test-hedge asserts (single-voice medium) and R4-R9 (single-voice low)

**Choice**: discarded to ledger; R1 HIGH fixed via task 7

**Rationale**: review-close refuses single-voice medium/low as tasks; ledger prevents re-raise

### [autonomous] 2026-11-10T21:40:46Z

**Decision**: Cycle 3 findings R1-R5 (all single-voice low)

**Choice**: discarded to ledger

**Rationale**: single-voice low never blocks convergence; no CRITICAL/HIGH; cycle 3 converged, tail sweep skipped
