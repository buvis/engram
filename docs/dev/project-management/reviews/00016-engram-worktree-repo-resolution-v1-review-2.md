---
prd: docs/dev/project-management/prds/wip/00016-engram-worktree-repo-resolution-v1.md
review: 2
date: 2026-11-16
head_sha: 1af23eb25083197fc672ab8be73dcd1e27328029
codex_thread_id: 01a1e550-e216-7943-b29b-ef3d01ffbea3
reviewers: alice,blake,bob,carl
agents:
  alice: available
  blake: available
  bob: available
  carl: available
dispatch_rows:
  bob: ec9a23af
  carl: 121ac727
---

# Review: 00016-engram-worktree-repo-resolution-v1 (cycle 2)

Diff range: `54f51429ef9f3012860269731ca0eb6c90388a06..1af23eb25083197fc672ab8be73dcd1e27328029`
(incremental: the rework commits since cycle 1)

codex_rung_guard: not fired

## Review Summary

Reviewed: 8 completed tasks (4 original + 4 cycle-1 rework)
PRDs checked: 00016-engram-worktree-repo-resolution-v1.md
Engine: legacy consensus (Alice as a single subagent); pack: ok
Incremental review with Bob's codex thread resumed from cycle 1.

### Agent Status

- Alice: ✅ Available (claude subagent, implementation-aware consensus)
- Blake: ✅ Available (claude subagent, blind lens, PRD-only)
- Bob: ✅ Available (codex, doubt lens D1-D5 + de-slop, resumed thread)
- Carl: ✅ Available (gemini via copilot backend, frontend/design specialist)
- Eve: ⏸️ Disabled (doubt_reviewer is codex and no codex-implemented task exists, so the roster guard did not fire)

Mechanical checks: 0 tautological test shapes across 42 test functions in 3
files; the fail-first replay collected nothing (all 3 touched test files fail to
collect at the cycle-1 base, which is expected for an incremental range). No
`[MECH]` finding this cycle, and no prior verification-check queue to carry
forward (cycle 1 wrote none).

### Prior-cycle findings: all resolved

R1 (test file over 800 lines) → worktree tests moved to
`tests/test_pack_worktree.py`; R2 (`_worktree_pack` 51 lines) → helpers
extracted, now 32; R3/R8 (combined rev-parse, unsafe `splitlines()`) →
`_resolve_main_checkout` runs only on the no-match path with its own error
handling; R4/R10 (missing `index_root.resolve() != repo_root.resolve()` guard) →
guard added; R5 (bare-repo worktree add) → `-c safe.bareRepository=all` pinned.
The cycle-1 single-voice and computed-fact discards were not re-raised.

## Consolidated Findings

| Ref | Consensus | Severity | Issue | File | Task | Found By |
|-----|-----------|----------|-------|------|------|----------|
| R1 | [2/4] | 🟡 | Dead import: the move to `tests/test_pack_worktree.py` removed the only `pytest` uses from `tests/test_pack_regressions.py` (the `parametrize` calls). `import pytest` at line 1 is now unused (F401). Delete it. | tests/test_pack_regressions.py:1 | 5 | ALICE, BOB |
| R2 | [2/4] | 🟡 | Phase 1 acceptance command `pytest -q tests/test_pack_regressions.py -k main_checkout` selects zero tests (exit 5, "no tests ran"). The required test `test_pack_in_worktree_excludes_changed_spans_indexed_under_main_checkout` lives in tests/test_pack_worktree.py:106, not in tests/test_pack_regressions.py. rg finds no "main_checkout" or "worktree" in test_pack_regressions.py. The test exists and passes, but the PRD's literal acceptance command and file mapping are not met. | tests/test_pack_worktree.py | 1 | BLAKE, BOB |
| R3 | [1/4] | 🟡 | The rework added behavior that no test covers. Neither test file has a test with a non-registered or failing `git rev-parse --git-common-dir`, which is the PRD Test Strategy's "Error case ... Expected: None, no crash". The `except (CalledProcessError, OSError)` branch in `_resolve_main_checkout` is unexercised. The new `except ValueError: continue` branch for a symbol path outside `repo_root` is also unexercised. | src/engram/harvest.py:46 | 7 | ALICE |
| R4 | [1/4] | 🟡 | The new `except ValueError: continue` silently omits a main-checkout exclusion when a symbol path cannot be made relative to `repo_root`, allowing publication with incomplete self-match filtering. Remove the silent catch; normalize supported path aliases or fail explicitly. | src/engram/pack.py:301 | 8 | BOB |
| R5 | [1/4] | ⚪ | src/engram/pack.py:296-302 wraps `Path(s.path).relative_to(repo_root)` in try/except ValueError and skips spans that do not fit. The spec shows an unguarded `relative_to`. This is safer and benign, but it silently drops the second exclusion span for a symbol path outside `repo_root`. | src/engram/pack.py | 1 | BLAKE |
| R6 | [1/4] | ⚪ | Extra tests beyond the named ones are present: tests/test_cli_pack.py:715 and tests/test_cli_pack.py:739, and the parametrized tests at tests/test_pack_worktree.py:183 and tests/test_pack_worktree.py:208. The extra tests are harmless and add no production scope. | tests/test_cli_pack.py | 2 | BLAKE |

No 🔴 CRITICAL and no 🟠 HIGH finding this cycle.

## Alice

Implementation-aware consensus lens, incremental. She verified every cycle-1
finding resolved in the code (see "Prior-cycle findings" above) and reviewed the
rework diff for regressions. Her two new findings are rows R3 (untested new
error branches) and R1 (dead `import pytest`). She confirmed the new test module
imports resolve, every helper and function is within 50 lines per the computed
facts, both test files are under 800 lines, and `_resolve_main_checkout`'s result
is canonicalized the same way as the toplevel lookup. She did not rerun the full
suite, per the test gate.

R1: fail
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

Blind lens, PRD only, no diff and no review history. He found no Critical or High
issue and traced every PRD requirement to code: the main-checkout fallback order,
`registry_root`, the `index_root.resolve() != repo_root.resolve()` guard, the
`_run_pack` wiring, the other repo-scoped commands, README and CHANGELOG, and the
five named tests. His three findings are rows R2 (the PRD's literal Phase 1
acceptance command now selects zero tests after the test move), R5 and R6. He ran
a narrow selection (17 passed, 39 deselected) and did not rerun the full suite,
per the test gate; he did not verify the fail-first claims.

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
B15: fail
B16: pass
B17: pass
B18: pass
B19: pass

## Bob

Doubt lens (codex, static-only sandbox, inlined prompt, cycle-1 thread resumed).

FIX: rows R4 (silent `except ValueError` dropping an exclusion span), R2 (the PRD
acceptance command now selects no tests), R1 (unused `import pytest`).

VERIFY: (none) — no verification-check queue was written for this cycle.

KNOWN: (none).

R1: fail
R2: pass
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: fail
R10: fail
R11: pass
R12: pass
R13: pass

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Carl

Backend: gemini-run.sh via copilot, exit 0, non-empty review text.

`[CARL] ✅ No issues found`. His sandbox could not read the repo files directly
(shell and read approvals denied with no interactive user) and the context and
diff files were too large for a single read, so he reviewed them in chunks plus
the pack. His verdict is therefore the weakest-evidence lens this cycle; it adds
no finding and contradicts none.

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

Verdict: 6 findings
Tests: 1452 passed, 0 failed, 0 skipped (suite run this cycle)
