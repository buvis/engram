---
prd: docs/dev/project-management/prds/wip/00014-engram-findings-pack-correctness-v1.md
review: 1
date: 2026-11-16
head_sha: 90d530f94c3fc1f73deefce8c611525e60a5f8d2
codex_thread_id: 01a1e470-aa5a-7012-8900-96187c8ec250
reviewers: alice,blake,bob,carl
agents:
  alice: available
  blake: available
  bob: available
  carl: available
dispatch_rows:
  bob: a65042b2
  carl: 758d5e9c
---

# Review: 00014-engram-findings-pack-correctness-v1

Diff range: `909d79756a602f82148e73b9311d73d79376b9f6..90d530f94c3fc1f73deefce8c611525e60a5f8d2`

codex_rung_guard: not fired

pack: ok

Notes: the fail-first replay was skipped this cycle (`replay: skipped (runner did not
complete: [Errno 2] No such file or directory: '.venv/bin/python')`) - the replay runs in a
base worktree where the repo-relative venv path does not exist. The two tautological-shape
`[MECH]` lines were produced and are absorbed into rows R4, R6 and R9 below (`mech-check`
added to Found By).

Decision-gate consolidation correction: the 800-line file-size defect arrived as five rows
(Alice, Bob, and three Carl rows) that the consolidator could not merge because each named a
different file cell. They are one defect; the gate merged them into a single three-voice R5 row
and removed the four duplicates, so the table below has 15 rows.

## Review Summary

Reviewed: 9 completed tasks
PRDs checked: 00014-engram-findings-pack-correctness-v1

### Agent Status

- Alice: ✅ Available
- Blake: ✅ Available
- Bob: ✅ Available (codex)
- Carl: ✅ Available (copilot backend)

## Consolidated Findings

| Ref | Consensus | Severity | Issue | File | Task | Found By |
|-----|-----------|----------|-------|------|------|----------|
| R1 | [4/4] | 🟠 | Rebuild cleanup does not cover os.replace. `os.replace(tmp_path, DEFAULT_DB_PATH)` sits outside the try/except. If it raises (EXDEV, EACCES), a raw traceback is printed and the multi-GB `engram.db.rebuild-tmp` stays on disk. The PRD says "on any exception after .rebuild-tmp is created ... unlink". The test `test_rebuild_replace_error_is_not_reported_as_success_and_releases_the_lock` never checks that the temp file is removed, so the gap is untested. Fix: move `os.replace` inside the guarded block, or unlink in a `finally` when the swap did not succeed. | src/engram/cli.py:315 | 6 | ALICE, BLAKE, BOB, CARL |
| R2 | [3/4] | 🟡 | `_unquote_c_path` does not use the PRD's named expression (`codecs.escape_decode(inner.encode("utf-8"))[0].decode("utf-8")`). It adds `_C_QUOTED_RE`, `_C_ESCAPE_RE`, an `_C_ESCAPES` table and a nested `_replace`, about 30 lines. It produces the same output for git's quoting, and no behavior difference was found. Either use the one-liner, or record the deliberate substitution in a code comment (for example that `escape_decode` is undocumented). | src/engram/diffmap.py:124 | 5 | ALICE, BLAKE, BOB |
| R3 | [3/4] | 🟡 | `tests/_harvest_helpers.py` copies `_init_git_repo` and `_write_repos_csv` from `tests/_cli_helpers.py:9`. Import the existing helpers instead of adding a second module. | tests/_harvest_helpers.py:5 | 2 | ALICE, BOB, CARL |
| R4 | [2/4] | 🟡 | Two new tests hedge with `or`, so either outcome passes. `assert raised is boom or (code not in (0, None) and ...)`. `_run_harvest` and `_run_rebuild` do not catch these errors, so the exception always propagates. Assert `raised is boom` instead. | tests/test_write_lock.py:2208 | 7 | ALICE, mech-check |
| R5 | [3/4] | 🟡 | File-size limit (800 max). `tests/test_diffmap.py` was about 845 lines before and is now 1094, `tests/test_cli_index_status.py` is now 937 and `tests/test_cli_pack.py` is 917. The harvest tests were split into `test_harvest_resolve.py` to stay under the limit, but these three were not. Split coherent test groups into focused modules capped at 800 lines (for example move the C-quoted tests into a new `tests/test_diffmap_cquoted.py`). | tests/test_diffmap.py:1094 | 5 | ALICE, BOB, CARL |
| R6 | [2/4] | 🟡 | The harvest error test hedges between propagation and reporting. Require `pytest.raises(ValueError)` and assert the original exception identity; retain lock-release checks. | tests/test_write_lock.py:428 | general | BOB, mech-check |
| R7 | [2/4] | 🟡 | The replacement error test accepts a propagated exception and never checks temp cleanup, allowing the rebuild defect through. Require exit 1, the specified stderr message, and no temp DB. | tests/test_write_lock.py:579 | 6 | BOB, mech-check |
| R9 | [2/4] | 🟡 | test_harvest_step_error_propagates_without_busy_and_releases_the_lock hedges with or: either outcome satisfies it | tests/test_write_lock.py:428 | general | CARL, mech-check |
| R10 | [1/4] | 🟡 | _unquote_c_path reimplements stdlib codecs.escape_decode with custom regex and escape table | src/engram/diffmap.py:124 | 5 | CARL |
| R14 | [1/4] | ⚪ | `Path(repo_path).resolve()` runs per registry row with no guard. The same function guards `path.resolve()` with `(OSError, RuntimeError)` a few lines earlier. A registry row with a symlink loop could raise `RuntimeError` and abort the batch. | src/engram/harvest.py:65 | 2 | ALICE |
| R15 | [1/4] | ⚪ | `test_write_lock_holds_an_exclusive_flock_on_the_given_path` sleeps 1.5 s. `test_write_lock_does_not_wait_for_a_held_lock` asserts `elapsed < 0.5`. Both slow the suite or can flake on a loaded runner. | tests/test_write_lock.py:1917 | 3 | ALICE |
| R16 | [1/4] | ⚪ | Several new tests pass against the pre-change code. They are non-regression guards, not fail-first tests: `test_parse_accepts_string_or_list_of_names`, `test_exclude_keeps_hit_whose_path_is_not_a_symlink_of_changed_span`, `test_changed_symbols_leaves_unquoted_path_unchanged_not_c_quoted_decoded` and `test_harvest_unreadable_registry_non_os_error_propagates_instead_of_being_swallowed`. They are acceptable guards. The fail-first replay was skipped, so this could not be confirmed mechanically. | tests/test_findings.py:1197 | general | ALICE |
| R17 | [1/4] | ⚪ | `test_resolve_repo_for_path_matches_symlinked_registry_path` and `..._trailing_slash_registry_path` live in `tests/test_harvest_resolve.py`, not `tests/test_harvest.py` as the PRD says. The PRD's acceptance command on `tests/test_harvest.py` therefore only exercises the unreadable-registry test. The tests exist and pass. | tests/test_harvest_resolve.py:132 | Phase 0 harvest | BLAKE |
| R18 | [1/4] | ⚪ | `write_lock` does not catch `OSError` from `os.open`, for example when the lock directory is unwritable. `_run_harvest` and `_run_rebuild` also don't, so these paths raise a traceback instead of printing a message. The PRD does not specify this case, and a test pins the behaviour. | src/engram/store.py:104 | Phase 1 lock | BLAKE |
| R19 | [1/4] | ⚪ | The tests add several cases beyond the PRD's named symbols, for example process-level lock tests and a non-OS-error propagation test for the registry read. They are harmless extras, not new product features. | tests/test_write_lock.py | general | BLAKE |

## Alice

Implementation-aware consensus lens. Findings R1-R5, R14-R16 above.

R1: pass
R2: fail
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: fail
R10: pass
R11: pass
R12: pass
R13: fail

## Blake

Blind lens (PRD only, no diff). All seven PRD fixes verified present and matching the spec;
only low-severity deviations (R17-R19, plus agreement on R1 and R2).

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

Doubt lens + de-slop (codex). FIX bucket: R1, R2, R6, R7, R3, R8. VERIFY: (none). KNOWN: (none).

R1: fail
R2: fail
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: fail
R10: fail
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
generalist). Findings R1, R9, R10, R11, R12, R13 and the hedged rebuild test above.

R1: pass
R2: fail
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: fail
R10: pass
R11: pass
R12: pass
R13: fail

Verdict: 19 findings
Tests: 1345 passed, 0 failed, 0 skipped (reused from last-verification.json at 90d530f)
