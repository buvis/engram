---
prd: docs/dev/project-management/prds/wip/00016-engram-worktree-repo-resolution-v1.md
review: 1
date: 2026-11-16
head_sha: 54f51429ef9f3012860269731ca0eb6c90388a06
codex_thread_id: 01a1e550-e216-7943-b29b-ef3d01ffbea3
reviewers: alice,blake,bob,carl
agents:
  alice: available
  blake: available
  bob: available
  carl: available
dispatch_rows:
  bob: eef0708d
  carl: b842b3e8
---

# Review: 00016-engram-worktree-repo-resolution-v1

Diff range: `4b25d374c0ba98bee088e5292bbf9c6c0060dc69..54f51429ef9f3012860269731ca0eb6c90388a06`

codex_rung_guard: not fired

## Review Summary

Reviewed: 4 completed tasks
PRDs checked: 00016-engram-worktree-repo-resolution-v1.md
Engine: legacy consensus (Alice as a single subagent); pack: ok

### Agent Status

- Alice: ✅ Available (claude subagent, implementation-aware consensus)
- Blake: ✅ Available (claude subagent, blind lens, PRD-only)
- Bob: ✅ Available (codex, doubt lens D1-D5 + de-slop)
- Carl: ✅ Available (gemini via copilot backend, frontend/design specialist)
- Eve: ⏸️ Disabled (doubt_reviewer is codex and no codex-implemented task exists, so the roster guard did not fire)

Note: the step-5.7 per-task reviews of tasks 2 and 3 failed in the build phase
with `auth_revoked` (use-sonnet OAuth token revoked for that session). This
cycle's four lenses are the first independent review those two tasks received.

## Consolidated Findings

| Ref | Consensus | Severity | Issue | File | Task | Found By |
|-----|-----------|----------|-------|------|------|----------|
| R1 | [3/4] | 🟠 | tests/test_pack_regressions.py is now 898 lines (was about 686), over the 800-line limit. This diff added about 212 lines. Move the worktree tests and helpers (`_write_files_diff`, `_worktree_pack` and the three tests) into a new module, e.g. tests/test_pack_worktree.py. | tests/test_pack_regressions.py:898 | 2 | ALICE, BOB, CARL |
| R2 | [2/4] | 🟡 | New helper `_worktree_pack` is 51 lines (716-767), over the 50-line limit. The per-chunk store seeding and the embed monkeypatching can be extracted. | tests/test_pack_regressions.py:716 | 2 | ALICE, BOB |
| R3 | [2/4] | 🟡 | Deviates from the PRD's Main checkout fallback and widens the blast radius. The PRD runs the toplevel lookup unchanged first and calls `git rev-parse --path-format=absolute --git-common-dir` only when no row matched. The diff adds `--path-format=absolute --git-common-dir` to the single primary call. On git older than 2.31 (no `--path-format`), every resolution now falls into the except branch and returns None or "claude-home", even for a registered main checkout. The PRD says main-checkout behavior must not change. The two-line unpack `toplevel_out, common_dir_out = result.stdout.strip().splitlines()` also raises an uncaught `ValueError` if git ever prints a different number of lines. Move the common-dir call into the no-match path with its own `CalledProcessError`/`OSError` handling that returns None. | src/engram/harvest.py:40 | 1 | ALICE, BOB |
| R4 | [2/4] | 🟡 | `_reindex_and_resolve_symbols` adds the second span set whenever `index_root` is not None. The spec says to add it only when `index_root.resolve() != repo_root.resolve()`. In a main checkout the extra spans are duplicates or equal, so this is harmless. There is also a small `relative_to` `ValueError` risk if a symbol path is not under `repo_root`, which `_run_pack` would turn into exit 1. `tests/test_pack_regressions.py:872` appears to cover the no-distinct-checkout case. | src/engram/pack.py:293 | 2 | BLAKE, BOB |
| R5 | [1/4] | 🟠 | Test fails with CalledProcessError because git worktree add on bare repo lacks -c safe.bareRepository=all | tests/test_harvest.py:618 | 1 | CARL |
| R6 | [1/4] | 🟡 | Unrequested churn in `_run_pack`. `config, store = load_config(), open_store()`, collapsing four `print` calls into two with `sep="\n"`, and deleting a blank line have nothing to do with `index_root`. They exist only to keep `_run_pack` at 50 lines, which is still not under 50 (mechanical facts: 50 lines). Revert them and extract a helper, e.g. `_print_pack_report`, if the length needs trimming. | src/engram/cli.py:602 | 3 | ALICE |
| R7 | [1/4] | 🟡 | Unrelated reformatting of `build()`'s calls to `_reindex_and_resolve_symbols`, `_retrieve_pack_hits` and `_build_pack_sections`, which collapses argument lists. This is style drift beyond the task, apparently made to hit the line limit. It also adds a redundant `Path(index_root)` wrap in `_reindex_and_resolve_symbols`, because `index_root` is already typed `Path`. | src/engram/pack.py:515 | 2 | ALICE |
| R8 | [1/4] | 🟡 | `_resolve_repo_for_path` runs one combined `git rev-parse --show-toplevel --git-common-dir` call before the registry lookup. The spec asks for the toplevel lookup first and a separate `--git-common-dir` call only when no row matches. Results are equivalent for the tested cases, but a git failure that affects only one of the two outputs would now fail both. The existing test mock in `tests/test_harvest_resolve.py` had to be changed to fit (commit 4290a35). | src/engram/harvest.py:40 | 1 | BLAKE |
| R9 | [1/4] | 🟡 | Mechanical replay identifies seven cases passing against the baseline: registered-worktree precedence, unregistered-repo rejection, four symlink-resolution cases, and unchanged exclusion without a distinct index root. These violate the literal fail-first metric but preserve explicitly required existing behavior; changing those expectations merely to fail the baseline would be outside the feature's intent. | N/A | general | BOB |
| R10 | [1/4] | 🟡 | Missing index_root.resolve() != repo_root.resolve() check before expanding changed_spans | src/engram/pack.py:293 | 2 | CARL |
| R11 | [1/4] | 🟡 | Function size of 51 lines exceeds the 50-line limit | src/engram/cli.py:585 | 3 | CARL |
| R12 | [1/4] | ⚪ | The PRD guard "only when `index_root.resolve() != repo_root.resolve()`" is not implemented. A second span is always added, which is harmless because `_exclude` compares canonical paths and the set absorbs duplicates. The test `test_pack_without_a_distinct_main_checkout_excludes_only_worktree_spans` therefore cannot observe the guard. Behavior is correct, so this is a note only. | src/engram/pack.py:293 | 2 | ALICE |
| R13 | [1/4] | ⚪ | The mech replay shows `test_resolve_repo_for_path_registered_worktree_keeps_its_own_name`, `test_resolve_repo_for_path_worktree_of_unregistered_repo_returns_none` and `test_pack_without_a_distinct_main_checkout_excludes_only_worktree_spans` passing against pre-change code. They are deliberate regression guards that the PRD names, so I do not treat them as tautological. The PRD success metric says every named test fails pre-change, which is unattainable for these three. | tests/test_harvest.py:672 | 1 | ALICE, mech-check |
| R14 | [1/4] | ⚪ | The commits include unrelated cosmetic rewrites. In `_run_pack`, `config, store = load_config(), open_store()` is merged onto one line, a blank line is dropped, and the four `print` calls are collapsed into two with `sep="\n"`. `build()` call arguments are also reformatted. These were done to get under a 50-line limit. Output is byte-identical but it is not in the spec's scope. | src/engram/cli.py:602 | 3 | BLAKE |
| R15 | [1/4] | ⚪ | The `CHANGELOG.md` entry is filed under the existing `### Fixed` list in `[Unreleased]`, which is correct. It lists `engram mcp` and `engram harvest` explicitly, and that wording is broader than the spec's single "cli" entry. | CHANGELOG.md:90 | 4 | BLAKE |
| R16 | [1/4] | 🟡 | 4 touched test(s) pass against the pre-change code: test_resolve_repo_for_path_matches_symlinked_registry_path | tests/test_harvest_resolve.py | general | mech-check |
| R17 | [1/4] | 🟡 | 1 touched test(s) pass against the pre-change code: test_pack_without_a_distinct_main_checkout_excludes_only_worktree_spans | tests/test_pack_regressions.py | general | mech-check |

## Alice

Alice ran the five touched test files (103 passed) and traced the PRD wiring end
to end: harvest fallback, `registry_root`, `build(index_root=...)`, the
`_run_pack` call, README and CHANGELOG. `ruff` is not installed in the venv, so
she ran no lint. Her findings are rows R1, R2, R3, R6, R7, R12, R13 above
(R1 🟠, four 🟡, two ⚪).

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
R12: fail
R13: fail

## Blake

Blind lens, PRD only. He found no Critical or High issue and judged the
implementation to do what the spec says, with three wording deviations at Medium
or Low (rows R8, R4, R14, R15). He ran the worktree-selected tests across the
four touched test modules (17 passed) and did not rerun the full suite, per the
Test gate block. He did not run the new tests against pre-change code, so the
PRD's fail-first metric is unchecked by him; the `eval` suite and
`git diff --check` are also unchecked by him.

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

Doubt lens (codex, static-only sandbox, inlined prompt).

FIX: rows R3 (combined rev-parse plus an unsafe `splitlines()` unpack), R4/R10
(missing `index_root.resolve() != repo_root.resolve()` guard), R2
(`_worktree_pack` at 52 lines by the supplied AST counts), R1
(test_pack_regressions.py over the 800-line limit).

VERIFY: (none) — no verification-check queue was written for this cycle.

KNOWN: row R9 (seven baseline-passing cases that preserve required existing
behavior).

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
R12: fail
R13: fail

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Carl

Backend: gemini-run.sh, exit 0, non-empty review text. Rows R5, R10, R3-adjacent
style rows: R5 (🟠), R10, R1 and R11.

Carl's R5 is environment-dependent and was re-measured by this session:
`uv run python -m pytest -q tests/test_harvest.py -k "worktree or registry_root"`
is 4 passed here, and the repo's full gate is 1399 passed, exit 0, at this
head_sha. `safe.bareRepository` is unset in this checkout's git config, so the
failure he saw came from his sandbox's own git config
(`safe.bareRepository is 'explicit'`). The defect is real as test portability —
`tests/test_harvest.py::_git` does not pin `-c safe.bareRepository=all`, so the
bare-repo worktree step breaks under that hardening — but it is not a failure of
this repo's suite as configured.

R1: pass
R2: pass
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: fail
R10: pass
R11: pass
R12: fail
R13: fail

Verdict: 17 findings
Tests: 1399 passed, 0 failed, 0 skipped (suite run this cycle)
