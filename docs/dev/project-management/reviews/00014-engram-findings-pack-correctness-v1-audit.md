# Decision Audit Log: 00014-engram-findings-pack-correctness-v1

PRD: `00014-engram-findings-pack-correctness-v1.md`
Started: 2026-11-16T13:52:38Z
Completed: 2026-11-16T13:52:38Z
Autonomous: 25  |  Deferred: 1  |  Doubts: 0

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: Rebuild cleanup does not cover os.replace. `os.replace(tmp_path, DEFAULT_DB_PATH)` sits outside the try/except. If it raises (EXDEV, EACCES), a raw traceback is printed and the multi-GB `engram.db.rebuild-tmp` stays on disk. The PRD says "on any exception after .rebuild-tmp is created ... unlink". The test `test_rebuild_replace_error_is_not_reported_as_success_and_releases_the_lock` never checks that the temp file is removed, so the gap is untested. Fix: move `os.replace` inside the guarded block, or unlink in a `finally` when the swap did not succeed.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: `_unquote_c_path` does not use the PRD's named expression (`codecs.escape_decode(inner.encode("utf-8"))[0].decode("utf-8")`). It adds `_C_QUOTED_RE`, `_C_ESCAPE_RE`, an `_C_ESCAPES` table and a nested `_replace`, about 30 lines. It produces the same output for git's quoting, and no behavior difference was found. Either use the one-liner, or record the deliberate substitution in a code comment (for example that `escape_decode` is undocumented).

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: `tests/_harvest_helpers.py` copies `_init_git_repo` and `_write_repos_csv` from `tests/_cli_helpers.py:9`. Import the existing helpers instead of adding a second module.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: Two new tests hedge with `or`, so either outcome passes. `assert raised is boom or (code not in (0, None) and ...)`. `_run_harvest` and `_run_rebuild` do not catch these errors, so the exception always propagates. Assert `raised is boom` instead.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: File-size limit (800 max). `tests/test_diffmap.py` was about 845 lines before and is now 1094, `tests/test_cli_index_status.py` is now 937 and `tests/test_cli_pack.py` is 917. The harvest tests were split into `test_harvest_resolve.py` to stay under the limit, but these three were not. Split coherent test groups into focused modules capped at 800 lines (for example move the C-quoted tests into a new `tests/test_diffmap_cquoted.py`).

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: The harvest error test hedges between propagation and reporting. Require `pytest.raises(ValueError)` and assert the original exception identity; retain lock-release checks.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: The replacement error test accepts a propagated exception and never checks temp cleanup, allowing the rebuild defect through. Require exit 1, the specified stderr message, and no temp DB.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: test_harvest_step_error_propagates_without_busy_and_releases_the_lock hedges with or: either outcome satisfies it

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: R1 rebuild cleanup does not cover os.replace (cli.py:315)

**Choice**: auto-fix (cycle 1 rework task)

**Rationale**: 4/4 consensus, mechanical fix: move os.replace inside the guarded block or unlink in a finally

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: R2 _unquote_c_path deviates from the PRD's codecs.escape_decode expression (diffmap.py:124)

**Choice**: auto-fix (cycle 1 rework task)

**Rationale**: 3/4 consensus, clear mechanical fix: use the prescribed expression or document the deliberate substitution

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: R3 tests/_harvest_helpers.py duplicates helpers from tests/_cli_helpers.py

**Choice**: auto-fix (cycle 1 rework task)

**Rationale**: 3/4 consensus, mechanical fix: import the existing helpers

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: R4/R6/R7/R9 hedged test assertions in tests/test_write_lock.py

**Choice**: auto-fix (cycle 1 rework task)

**Rationale**: two voices each including the mechanical tautological-shape check; assert exception identity instead of hedging with or

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: R5 three changed test modules exceed the 800-line limit

**Choice**: auto-fix (cycle 1 rework task); gate merged five duplicate rows into one three-voice row

**Rationale**: Alice, Bob and three Carl rows describe one defect that the consolidator could not merge because each named a different file cell; merged per the gate's issue-text-plus-file judgment, so it is not single-voice

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: R10 Carl's _unquote_c_path row

**Choice**: discard

**Rationale**: duplicate of R2, same defect and same file; fixed under R2 this cycle

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: R14 unguarded Path(repo_path).resolve() per registry row

**Choice**: discard

**Rationale**: single-voice

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: R15 lock tests sleep 1.5s and assert elapsed < 0.5

**Choice**: discard

**Rationale**: single-voice

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: R16 some new tests pass against the pre-change code

**Choice**: discard

**Rationale**: single-voice; the reviewer itself calls them acceptable non-regression guards

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: R17 two harvest resolve tests live in test_harvest_resolve.py, not test_harvest.py

**Choice**: discard

**Rationale**: single-voice; the split was a deliberate file-size measure and both tests exist and pass

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: R18 write_lock does not catch OSError from os.open

**Choice**: discard

**Rationale**: single-voice; unspecified by the PRD and pinned by an existing test

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: R19 tests add cases beyond the PRD's named symbols

**Choice**: discard

**Rationale**: single-voice; harmless extras

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: Fail-first replay skipped this cycle

**Choice**: logged, no task

**Rationale**: the replay runner could not start (.venv/bin/python missing in the base worktree); the tautological-shape check still ran and its findings are absorbed into R4/R6/R7/R9

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: Task 13 finding also named test_cli_index_status.py (937 lines) and test_cli_pack.py (917 lines) as over the 800-line limit, but only tests/test_diffmap.py was in this [D1] task's scope

**Choice**: fixed test_diffmap.py only; left the other two files untouched

**Rationale**: no separate task was created for test_cli_index_status.py or test_cli_pack.py; scope creep beyond the task name was avoided

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: Cycle 2 R1: cycle 1's R5 only partly resolved - tests/test_cli_index_status.py (937) and tests/test_cli_pack.py (917) still over the 800-line limit

**Choice**: auto-fix via tail sweep

**Rationale**: two-voice (ALICE, BOB) mechanical fix; medium never blocks convergence, so it is swept not deferred

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: Cycle 2 R2, R4, R5, R6, R7: five single-voice medium/low findings (diffmap decoder substitution, harvest test placement, pack realpath hoist, store OSError propagation, unclosed store)

**Choice**: discarded

**Rationale**: single-voice; R2/R4/R6 were already settled in cycle 1 with the same reasons; all five recorded in the settled-decisions ledger

### [autonomous] 2026-11-16T13:52:38Z

**Decision**: Cycle 1's R5 is only partly resolved: only `tests/test_diffmap.py` was split (706 lines, plus the new `tests/test_diffmap_decoding.py` at 382). `tests/test_cli_index_status.py` (937 lines) and `tests/test_cli_pack.py` (917 lines) are unchanged by the rework and still exceed the 800-line limit R5 named for all three files. Split coherent groups into focused modules under 800 lines, for example the rebuild tests out of `tests/test_cli_index_status.py` and the `--diff` id tests out of `tests/test_cli_pack.py`.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [deferred] 2026-11-16T13:52:38Z

**Decision**: The C-quoted diffmap tests are no longer in `tests/test_diffmap.py`, where the PRD's acceptance command points, so `pytest -q tests/test_diffmap.py -k c_quoted` deselects all 20 tests and exits 5.

**Choice**: deferred

**Rationale**: deferred by review-close
