---
default_model: opus
model_tier_rationale: concurrent writers, atomic replacement, interrupt cleanup and data recovery
---

# Protect rebuilds and concurrent store writes

Source: 2026-11-16 #10, 2026-11-16 #15, 2026-11-16 #17, 2026-11-16 #18, 2026-11-16 #29. Original packets: docs/dev/project-management/audit-results/agoge-2026-11-16.md and docs/dev/project-management/audit-results/agoge-2026-11-15-2.md.
Decision: docs/dev/project-management/audit-results/agoge-triage-2026-11-23.md. This is a bounded QA correction, not a replacement of the completed feature PRDs.

## Overview

### Problem Statement
Only harvest and rebuild hold the store lock. Other writers can succeed on a store that rebuild discards. Interrupts leave temporary stores, first writers race, and corruption prevents recovery.

### Target Users
The solo developer and local agents using Engram to index repositories and recall prior work.

### Success Metrics
Every Critical Scenario passes with synthetic data in isolated temporary roots. Historical evidence below is from the QA run, not a fresh measurement. No suite-wide test count or timing target is imposed.

## Functional Decomposition

### Capability: Protect rebuilds and concurrent store writes
Apply the recorded disposition without changing unrelated behavior.

#### Feature: Lock the full write lifecycle
- **Description**: Lock the full write lifecycle.
- **Inputs**: Every CLI write path, including pack's index step.
- **Outputs**: One nonblocking writer lease before opening or mutating the store.
- **Behavior**: Hold the same lock through open, write, close and rebuild replacement for index, backfill, re-embed, harvest, rebuild and pack indexing. A separate check followed by an unlocked write is insufficient. Avoid nested acquisition. Preserve read-only query access where possible; guard first schema/vector creation with an immediate transaction and recheck, reporting busy errors clearly.

#### Feature: Clean up safely
- **Description**: Clean up safely.
- **Inputs**: Owned temporary store and lock files.
- **Outputs**: No stale temp after ordinary failures or SIGINT; live data retained.
- **Behavior**: Create lock files with mode 0600 and no symlink following; reject non-regular lock objects. Clean only the temp file owned under the acquired lock in a finally block after closing handles. Do not unlink a lock file or another process's temp. Preserve the original exception/exit semantics.

#### Feature: Provide explicit corruption recovery
- **Description**: Provide explicit corruption recovery.
- **Inputs**: A corrupt live store and index --rebuild --discard-findings.
- **Outputs**: Opt-in fresh store plus a retained copy of the previous database.
- **Behavior**: Default rebuild refuses to replace the store if findings cannot be preserved. Add --discard-findings only with --rebuild; it bypasses findings copy with a clear loss warning. Retain the old database as a collision-safe sibling backup before replacement and report its exact path. Abort if backup creation fails. Do not operate on the user's real store during implementation or tests.

## Structural Decomposition

### Repository Structure

```text
src/engram/store.py
src/engram/cli.py
src/engram/pack.py
tests/test_write_lock.py
tests/test_cli_index_rebuild.py
tests/test_cli_index_status.py
tests/test_cli_pack.py
tests/test_store.py
README.md
CHANGELOG.md
```

### Module: Product correction
- **Maps to capability**: Protect rebuilds and concurrent store writes
- **Responsibility**: Implement the Features in the existing modules; no new public API is required.
- **Location**: `src/engram/store.py`, `src/engram/cli.py`, `src/engram/pack.py`
- **Exports**: `write_lock`, `open_store`, `main`, `build`

### Module: Verification and guidance
- **Maps to capability**: Protect rebuilds and concurrent store writes
- **Responsibility**: Prove the regression, preserve compatibility, and explain changed behavior.
- **Location**: `tests/test_write_lock.py`, `tests/test_cli_index_rebuild.py`, `tests/test_cli_index_status.py`, `tests/test_cli_pack.py`, `tests/test_store.py`, `README.md`, `CHANGELOG.md`
- **Exports**: Existing test entry points and user documentation; no runtime exports.

## Dependency Graph

### Foundation Layer (Phase 0)
- **Verification and guidance**: No internal dependencies; establish reproductions and current premises first.
- External prerequisites: None.

### Core Layer (Phase 1)
- **Product correction**: Depends on Phase 0 evidence and the external prerequisites above.

### Integration Layer (Phase 2)
- **Verification and guidance**: Depends on Product correction for final checks and user guidance.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Establish the precise existing failure or documentation premise.

**Tasks**:
- [ ] Add regressions from Critical Scenarios in the listed test files; run each bug regression against old code and record the expected failure once. (no internal deps) - Acceptance: record command, expected failure or premise, and output for each applicable Critical Scenario. Use only planted markers and temporary data.

**Exit Criteria**: Failure evidence or current documentation premises are recorded; no secrets or live stores are involved.

### Phase 1: Core
**Goal**: Deliver the Functional Decomposition.

**Tasks**:
- [ ] Implement the specified behavior in the listed production modules, preserving the stated safety and compatibility rules. (depends on: Phase 0) - Acceptance: uv run --no-sync python -m pytest -q tests/test_write_lock.py tests/test_cli_index_rebuild.py tests/test_cli_index_status.py tests/test_cli_pack.py tests/test_store.py

**Exit Criteria**: All Critical Scenarios pass; required negative checks fail clearly and preserve data as specified.

### Phase 2: Integration
**Goal**: Verify the complete correction and record its limits.

**Tasks**:
- [ ] Update README and add scoped CHANGELOG entries for the implemented behavior; run the selected tests. (depends on: Phase 1) - Acceptance: review the diff against each Feature, confirm all listed scenarios, and run git diff --check.

**Exit Criteria**: Run the repository main gate once: uv run --no-sync python -m pytest -q --ignore=eval -m "not private". Then run the evaluation gate once: PYTHONPATH=src:. uv run --no-sync python -m pytest -q eval -m "not private". Report deselected private tests explicitly. No real portfolio or live database mutation is permitted.

## Test Strategy

### Critical Scenarios
- Use two real processes: while rebuild holds the lock, each writer exits busy before embedding; it never reports success for discarded work.
- Concurrent first opens either serialize safely or produce a clean busy error, never a traceback or partial schema.
- SIGINT and an injected failure remove only the owned temp, retain live rows, and release the lock; losing a lock race leaves the winner's temp untouched.
- A corrupt fixture fails safely by default; explicit discard rebuild succeeds only with a retained byte-identical backup. Lock symlinks/directories are refused without touching their targets.

### Original QA evidence
Verbatim evidence follows. Mocked observations retain that status; local fixture tests do not turn them into real-server measurements. Isolate fixture setup from the user's actual HOME and store.

````text
2026-11-16 #10
With pages 3 to 40 of a scratch `engram.db` overwritten: `engram index --rebuild` printed `rebuild failed: database disk image is malformed`, rc 1, after doing the whole re-index. `status`, `query`, `lookup` and `index` each ended in a traceback with the same SQLite error. Confidence: confirmed.
2026-11-16 #15
SIGINT sent to a running `engram index --rebuild`: rc -2, a traceback ending in `KeyboardInterrupt`, and `engram.db.rebuild-tmp` (12.7 MB in one fixture, 17 MB in another) still in the directory. The live store was intact, and the next rebuild removed the leftover. CHANGELOG.md:87-89 says the temp file is removed "on any failure". The cause (the handler catches `Exception` only) was read, not run. Confidence: confirmed.
2026-11-16 #17
While `engram index --rebuild` ran on a 250-file repo, a function was added and `engram index` returned rc 0. After the rebuild finished: `lookup --name written_during_rebuild` gives `no symbol matched`, and `status` shows `code 6 stale=1`, rc 1. `--backfill-code` and `--reembed-code` also ran to rc 0 during the rebuild (`re-embedded 1007 code chunks`, all discarded). Confidence: confirmed.
2026-11-16 #18
With the store moved aside, two `engram index --scope portfolio` started together: one rc 0, the other rc 1 with a traceback at `CREATE VIRTUAL TABLE chunks_vec` and `sqlite3.OperationalError: database is locked`. On an existing store, three concurrent writers all exited 0. Confidence: confirmed.
2026-11-16 #29
One example each: `reviewers: [[[[...` nested 5000 deep makes `engram harvest good.md deep.md good.md` print a `RecursionError` traceback of about 200 KB and no result lines at all. `engram.db.lock` as a dangling symlink is followed and the target is created with mode 0755. The lock as a directory ends in an uncaught `IsADirectoryError`. A transcript with one bad line is skipped whole, valid turns included. A `config.toml` with bad TOML or no `endpoint` gives a traceback from `query` (`mcp` and `nudge` report it cleanly). A diff line with form feeds is split into a fake section and aborts the pack; the path guard still held. Confidence: confirmed.
````

## Risks

- Concurrent hooks now receive busy failures. Recovery intentionally excludes findings only under the explicit flag and keeps the old database recoverable.
- Requirements are resolved. Implementation must not ask for a preference, touch a real store, or weaken assertions to obtain a pass.
