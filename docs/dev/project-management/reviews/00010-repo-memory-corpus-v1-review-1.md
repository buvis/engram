---
prd: docs/dev/project-management/prds/wip/00010-repo-memory-corpus-v1.md
review: 1
date: 2026-11-10
head_sha: 32c8d95c4501d59c20572b264d71990aa6e61b21
codex_thread_id: 01a1c471-ebfe-7790-9ba2-4791e23df699
reviewers: alice,blake,bob,carl
agents:
  alice: available
  blake: available
  bob: available
  carl: available
dispatch_rows:
  bob: b3df40fe
  carl: 69297064
---

# Review: 00010-repo-memory-corpus-v1

Diff range: `ee254a34dcc3803bc9e1adfb844e06fb1fffeac7..32c8d95c4501d59c20572b264d71990aa6e61b21`

codex_rung_guard: not fired

## Review Summary

Reviewed: 5 completed tasks (full review, cycle 1)
PRDs checked: 00010-repo-memory-corpus-v1

- Consensus engine: legacy (single Alice subagent).
- pack: ok (`docs/dev/tmp/engram-pack-c1-00010.md`).
- Mechanical test checks: 93 test functions checked, no tautological shapes; fail-first replay ran 0 touched tests (the new test file cannot be collected at base, so its tests fail there by construction). No `[MECH]` rows.
- Consolidation: script (`consolidate_findings.py`); no ledger (cycle 1).
- Test gate: `review-stage` and `autopilot verify` both ran the suite (exit 0) but could not parse pytest's plain `679 passed` summary. The `Tests:` line below is read from the gate log `docs/dev/tmp/gate-32c8d95.log` line 11, not from a parsed verification record; `last-verification.json` was not written.

### Agent Status

- Alice (Claude, consensus): ✅ Available - 6 findings
- Blake (Claude, blind/PRD-only): ✅ Available - 5 findings
- Bob (codex, consensus + doubt): ✅ Available - 4 findings, D1-D5 all pass
- Carl (copilot, model gemini-3.8-flash, UI + generalist): ✅ Available - 2 findings (his pytest attempt was denied by the copilot sandbox; he reviewed statically)

## Consolidated Findings

| Ref | Consensus | Severity | Issue | File | Task | Found By |
|-----|-----------|----------|-------|------|------|----------|
| R1 | [3/4] | 🟡 | tests/test_repo_memory.py is 1424 lines, above the 800-line file limit. It splits cleanly into three files: validator tests (schema, index, credential), enumeration and legacy tests, and cli_check/status tests. The `-k` selectors in the PRD acceptance still work after the split. | tests/test_repo_memory.py:1 | general | ALICE, BOB, CARL |
| R2 | [2/4] | 🟠 | `yaml.safe_load` can raise `ValueError` (not `yaml.YAMLError`) for date-shaped scalars such as `source: 2026-13-45` or `name: 0000-00-00`. I reproduced it: `yaml.safe_load('x: 2026-13-45')` raises `ValueError: month must be in 1..12`. `_split_frontmatter` catches only `yaml.YAMLError`, so one such memory file crashes `engram memory check` with a traceback instead of `frontmatter<TAB>unparseable`. It also crashes `engram status` through `check_directory`, which turns one bad memory file into a failure of the whole status run. The PRD makes unparseable frontmatter a reported violation. Fix: catch `(yaml.YAMLError, ValueError)` at src/engram/memory.py:163 and add a regression test for an invalid calendar date. | src/engram/memory.py:163 | 1 | ALICE, BOB |
| R3 | [1/4] | 🟡 | An unrelated formatter reflow is committed. `raise FileNotFoundError(f"...")` in `read_repos_csv` was re-wrapped onto three lines, and nothing in the task touches that function. This repeats the finding precedent (review-3 R24). Drop the hunk. | src/engram/corpora.py:102 | 2 | ALICE |
| R4 | [1/4] | 🟡 | In `_enumerate_memory_corpora`, the existing local `memory_dir = project_dir / "memory"` now shadows the newly imported function `memory_dir` in the same module. It is harmless today, but a later edit that calls `memory_dir(...)` in that function would break. Rename the local, for example to `legacy_memory`. | src/engram/corpora.py:51 | 2 | ALICE |
| R5 | [1/4] | 🟡 | The `sk-` credential pattern adds a negative lookbehind `(?<![A-Za-z0-9])` that the spec does not have. The spec pattern is `sk-[A-Za-z0-9_-]{20,}`. The guard is therefore weaker than specified: a token glued to a preceding alphanumeric (for example `xsk-<20+ chars>`) is not flagged. This looks deliberate, to avoid false positives like `task-…`. It is still an unrequested change to a pattern the PRD listed verbatim, and it is a fail-open path in the credential guard. | src/engram/memory.py:21 | 1 | BLAKE |
| R6 | [1/4] | 🟡 | Tabs or newlines in YAML mapping keys enter forbidden-key diagnostics unchanged, breaking the promised three-column, one-line output. Escape control characters in dynamic key paths and filenames before formatting; test both cases. | src/engram/memory.py:82 | 1 | BOB |
| R7 | [1/4] | 🟡 | The capsule newly presents slash-only slug encoding and entirely unmapped memory as current defects, although the supplied base and revised code both replace every non-alphanumeric character. Mark these observations historical and remove the resolved attribution fix from Next Work. | docs/dev/project-management/meta/project-capsule.md:94 | general | BOB |
| R8 | [1/4] | ⚪ | Status tests that stub `enumerate_corpora` (`tests/test_backlog_delivery.py`) do not reset the new `corpora.repo_memory_dirs` and `corpora.legacy_shadowed` globals. The reset lives only in `tests/test_cli_index_status.py:24`. The suite passes in default alphabetical order, but a randomized or xdist order could read stale entries from an earlier real-enumeration test. The design's own review log suggested a `tests/conftest.py` autouse reset covering `missing_dirs`, `repo_memory_dirs` and `legacy_shadowed`. | tests/test_cli_index_status.py:24 | 4 | ALICE |
| R9 | [1/4] | ⚪ | The `git rev-parse --show-toplevel` subprocess block is now copied a third time. The design chose the copy on purpose. A small shared helper that `_resolve_pack_repo` and `_run_memory_check` both call would remove the duplication. | src/engram/cli.py:123 | 3 | ALICE |
| R10 | [1/4] | ⚪ | `MEMORY.md` is also scanned for credentials, which the spec does not ask for ("Full file text" refers to memory files). `redact` and `memory_files` are public helpers beyond the listed exports. Both are harmless. | src/engram/memory.py:55 | 1 | BLAKE |
| R11 | [1/4] | ⚪ | `memory_files` uses `iterdir()` and `is_file()`, which follow symlinks, and has no `OSError` guard. A symlinked `*.md` pointing outside the repo would be indexed as repository memory. An unreadable memory directory would raise out of `enumerate_corpora`, and `memory check` has the same exposure. | src/engram/memory.py:44 | 2 | BLAKE |
| R12 | [1/4] | ⚪ | `memory\tinvalid=<n>` counts distinct violating paths, so `MEMORY.md` index violations count as an "invalid file". The spec does not say whether index-level problems count. A directory with no `MEMORY.md` and no memory files passes `memory check` with exit 0, because the index check only fires per file. This is defensible but unspecified. | src/engram/cli.py:388 | 3 | BLAKE |
| R13 | [1/4] | ⚪ | `_enumerate_memory_corpora` shadows the imported `memory_dir` with a local variable. It is functionally harmless but fragile. | src/engram/corpora.py:51 | 2 | BLAKE |
| R14 | [1/4] | ⚪ | Unrelated Session 7 evaluation protocol updates committed in PRD 00010 diff | docs/dev/project-management/reviews/2026-11-05-independent-evaluation-protocol.md:1 | general | CARL |

R4 and R13 describe the same shadowing defect at the same line; the script did not merge them because the reviewers gave different severities. The decision gate treats them as one.

## Alice

6 findings (raw: `docs/dev/tmp/alice-output-c1-00010.txt`). Rubric: R10 fail, R13 fail, all others pass.

## Blake

5 findings (raw: `docs/dev/tmp/blake-output-c1-00010.txt`). Ran `tests/test_repo_memory.py` and `tests/test_memory_attribution.py` narrowly: 133 passed. Rubric: B1 fail, B10 fail, all others pass.

## Bob

4 findings (raw: `docs/dev/tmp/bob-output-c1-00010.txt`). VERIFY and KNOWN buckets empty, so no checks were queued. Rubric: R1, R7, R9, R10, R13 fail; others pass.

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Carl

2 findings (raw: `docs/dev/tmp/carl-output-c1-00010.txt`). Backend copilot, model gemini-3.8-flash. Rubric: R13 fail, all others pass.

Verdict: 14 findings
Tests: 679 passed (suite run this cycle; counts read from gate log, autopilot verify could not parse the pytest summary)
