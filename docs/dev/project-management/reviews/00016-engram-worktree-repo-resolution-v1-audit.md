# Decision Audit Log: 00016-engram-worktree-repo-resolution-v1

PRD: `00016-engram-worktree-repo-resolution-v1.md`
Started: 2026-11-16T17:44:33Z
Completed: 2026-11-16T17:44:33Z
Autonomous: 14  |  Deferred: 0  |  Doubts: 0

### [autonomous] 2026-11-16T17:44:33Z

**Decision**: Cycle 1: 5 findings auto-fixed (R1 test file over 800 lines, R2 _worktree_pack over 50 lines, R3 combined git rev-parse deviating from the PRD fallback, R4 missing index_root.resolve() guard, R5 test_harvest _git helper unpinned safe.bareRepository)

**Choice**: auto-fix via decision-gate D1 tasks

**Rationale**: all five are mechanical or spec-restoring fixes with no signature, schema or API change; R5 verified as a real test-portability defect though its reporter's environment-specific failure does not reproduce here

### [autonomous] 2026-11-16T17:44:33Z

**Decision**: Cycle 1: 12 findings discarded (R6-R17)

**Choice**: discard, recorded in the settled-decisions ledger

**Rationale**: ten are single-voice Medium/Low re-wordings of fixed rows or of style churn; R11 contradicts the computed mechanical facts (_run_pack is 50 lines, not 51); R16/R17 are mech-check replays of tests that pin required pre-existing behavior

### [autonomous] 2026-11-16T17:44:33Z

**Decision**: tests/test_pack_regressions.py is now 898 lines (was about 686), over the 800-line limit. This diff added about 212 lines. Move the worktree tests and helpers (`_write_files_diff`, `_worktree_pack` and the three tests) into a new module, e.g. tests/test_pack_worktree.py.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T17:44:33Z

**Decision**: New helper `_worktree_pack` is 51 lines (716-767), over the 50-line limit. The per-chunk store seeding and the embed monkeypatching can be extracted.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T17:44:33Z

**Decision**: Deviates from the PRD's Main checkout fallback and widens the blast radius. The PRD runs the toplevel lookup unchanged first and calls `git rev-parse --path-format=absolute --git-common-dir` only when no row matched. The diff adds `--path-format=absolute --git-common-dir` to the single primary call. On git older than 2.31 (no `--path-format`), every resolution now falls into the except branch and returns None or "claude-home", even for a registered main checkout. The PRD says main-checkout behavior must not change. The two-line unpack `toplevel_out, common_dir_out = result.stdout.strip().splitlines()` also raises an uncaught `ValueError` if git ever prints a different number of lines. Move the common-dir call into the no-match path with its own `CalledProcessError`/`OSError` handling that returns None.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T17:44:33Z

**Decision**: `_reindex_and_resolve_symbols` adds the second span set whenever `index_root` is not None. The spec says to add it only when `index_root.resolve() != repo_root.resolve()`. In a main checkout the extra spans are duplicates or equal, so this is harmless. There is also a small `relative_to` `ValueError` risk if a symbol path is not under `repo_root`, which `_run_pack` would turn into exit 1.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T17:44:33Z

**Decision**: Test fails with CalledProcessError because git worktree add on bare repo lacks -c safe.bareRepository=all

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T17:44:33Z

**Decision**: R1 cycle 2: unused import pytest in tests/test_pack_regressions.py

**Choice**: auto-fix, swept in the converged cycle's tail sweep

**Rationale**: mechanical two-voice fix (ALICE, BOB); dead import left by the cycle-1 test split

### [autonomous] 2026-11-16T17:44:33Z

**Decision**: R2 cycle 2: the PRD's Phase 1 acceptance command selects zero tests after the test move

**Choice**: auto-fix, swept in the converged cycle's tail sweep

**Rationale**: two-voice (BLAKE, BOB); the named test now lives in tests/test_pack_worktree.py, so the PRD's acceptance command and file mapping must be updated to match

### [autonomous] 2026-11-16T17:44:33Z

**Decision**: R4 cycle 2 (with R5 merged): silent except ValueError drops a main-checkout exclusion span

**Choice**: auto-fix, swept in the converged cycle's tail sweep

**Rationale**: BOB and BLAKE raised the same defect at different citation depths; fix resolves both paths before relative_to, keeps the guard against a crash, and adds the regression test the error branches lack

### [autonomous] 2026-11-16T17:44:33Z

**Decision**: R3, R5, R6 cycle 2: single-voice or duplicate medium/low rows

**Choice**: discarded, recorded in the settled-decisions ledger

**Rationale**: R3 and R5 are the same defect as the swept R4 and are covered by its fix and test; R6 reports extra tests its own reviewer calls harmless

### [autonomous] 2026-11-16T17:44:33Z

**Decision**: Dead import: the move to `tests/test_pack_worktree.py` removed the only `pytest` uses from `tests/test_pack_regressions.py` (the `parametrize` calls). `import pytest` at line 1 is now unused (F401). Delete it.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T17:44:33Z

**Decision**: Phase 1 acceptance command `pytest -q tests/test_pack_regressions.py -k main_checkout` selects zero tests (exit 5, "no tests ran"). The required test `test_pack_in_worktree_excludes_changed_spans_indexed_under_main_checkout` lives in tests/test_pack_worktree.py:106, not in tests/test_pack_regressions.py. Update the PRD's Phase 1 test location and acceptance command to name tests/test_pack_worktree.py.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T17:44:33Z

**Decision**: The new `except ValueError: continue` silently omits a main-checkout exclusion when a symbol path cannot be made relative to `repo_root`, allowing publication with incomplete self-match filtering. Resolve both the symbol path and `repo_root` before `relative_to` so a non-canonical or symlinked `repo_root` still matches, keep the guard so an unrelated path cannot crash the pack, and add a regression test for that path plus one for the `CalledProcessError`/`OSError` branch of `_resolve_main_checkout` (the PRD Test Strategy's "Error case ... Expected: None, no crash").

**Choice**: auto-fixed

**Rationale**: fixed by review-close
