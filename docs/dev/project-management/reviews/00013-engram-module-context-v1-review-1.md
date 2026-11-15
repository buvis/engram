---
prd: docs/dev/project-management/prds/wip/00013-engram-module-context-v1.md
review: 1
date: 2026-11-15
head_sha: 02924186cd3176f5a80d730efc23a01cc04e6acf
codex_thread_id: 01a1e124-1ba5-7723-9b1c-ce433d564296
reviewers: alice,blake,bob
agents:
  alice: available
  blake: available
  bob: available
  carl: unavailable
dispatch_rows:
  bob: 9231c1ca
  carl: b56f9668
---

# Review: 00013-engram-module-context-v1

Diff range: `2cca6f28df718be1b246a060eef9eacaa1cc49d3..02924186cd3176f5a80d730efc23a01cc04e6acf`

codex_rung_guard: not fired

pack: ok

## Review Summary

Reviewed: 3 completed tasks
PRDs checked: 00013-engram-module-context-v1

### Agent Status

- Alice: ✅ Available (Claude subagent, consensus lens)
- Blake: ✅ Available (Claude subagent, blind/PRD-only lens)
- Bob: ✅ Available (codex via agent-skills `codex-run.sh -y`, doubt lens D1-D5 + de-slop)
- Carl: ⚠️ Unavailable: copilot backend exit 1, `Model "gemini-3.1-pro-preview" is not available`; retry on the native gemini backend exit 1, `IneligibleTierError: This client is no longer supported for Gemini Code Assist for individuals`. Both are runtime exit 1 (the agent-skills runner has no exit-4 classification), so Carl was not latched as batch-unavailable. Consensus counts N=3.

Consolidation note: `consolidate_findings.py` left Alice's and Bob's `_context_chunks` simplification (src/engram/symbols.py:157 and :159, same defect, same fix) as two single-voice rows. They were merged by hand into R2 with consensus 2 of 3. Every other row is the script's output.

Blake's raw output named U+2028 and U+2029 as literal characters, which split his first finding across lines; they were rewritten as `U+2028`/`U+2029` text before consolidation. No finding text was otherwise changed.

Mechanical test checks: no `[MECH]` lines. The fail-first replay was skipped (`.venv/bin/python` absent in the base worktree), so no replay evidence exists this cycle.

Orchestrator check of R1: confirmed by reading src/engram/symbols.py:113-134. `chunk` slices symbol bodies and context runs from `source.splitlines()`, which also breaks at `\x0b`, `\x0c`, `\x1c`-`\x1e`, `\x85`, U+2028 and U+2029, while tree-sitter spans count `\n` rows only.

## Consolidated Findings

| Ref | Consensus | Severity | Issue | File | Task | Found By |
|-----|-----------|----------|-------|------|------|----------|
| R1 | [1/3] | 🟠 | Form-feed and other Unicode line separators (\x0c, \x0b, \x1c-\x1e, \x85, U+2028, U+2029) break the "every nonblank line once" guarantee. `chunk` splits with `str.splitlines()` (src/engram/symbols.py:114), but tree-sitter counts lines at \n only, so the parser's spans and `lines[]` indexes disagree. I ran `chunk` on `import os\n\x0c\nX = 1\n\ndef f():\n    return 2\n\nTAIL = 3\n`. The function chunk came out as lines 5-6 with body '\ndef f():'. The tail context chunk came out as lines 7-9 with body '    return 2\n\nTAIL = 3'. The file has only 8 \n lines, so 9 is past the end. `return 2` appears in the tail chunk and is missing from the function chunk, and the context line numbers point past the end of the file. The skewed symbol bodies already existed in the code. The new gap logic turns them into duplicated or misattributed context lines and wrong line_start/line_end values. Form feeds do occur in GNU C and older Python sources. The fix is to split on \n only, for example `source.split("\n")` with CRLF handling. A test with a form-feed fixture would catch it. | src/engram/symbols.py:114 | 1 | BLAKE |
| R2 | [2/3] | 🟡 | `_context_chunks` builds a list of line numbers per run, then filters it again for non-blank lines (`runs: list[list[int]]`, then `kept`). One pass would do: track the run start and the first and last non-blank line, and emit when a covered line or EOF ends the run. Same output, no per-run int lists. Behavior-preserving, so Medium. | src/engram/symbols.py:157 | 1 | ALICE, BOB |
| R3 | [1/3] | 🟡 | The final assertion checks only locally constructed `expected` records, so it cannot detect an implementation defect. Remove it; the preceding lookup-result equality assertions already enforce exclusion. | tests/test_module_context.py:625 | 2 | BOB |
| R4 | [1/3] | ⚪ | `chunk` is now exactly 50 lines (mechanical facts, up from 48 before this diff). It sits at the limit. Any later addition to `chunk` needs the context gate pulled out into a helper. | src/engram/symbols.py:100 | 1 | ALICE |
| R5 | [1/3] | ⚪ | `test_chunk_gives_symbolless_python_file_one_context_chunk` re-types the whole `CONTEXT_LANGUAGES` literal and compares it to the production constant. That pins the contract, but any later widening of the set (the design calls this a one-line change) needs a matching edit here. Separately, it hides an unrelated allowlist check in a test named for a single-chunk case. | tests/test_module_context.py:383 | 1 | ALICE |
| R6 | [1/3] | ⚪ | The diff replaces the whole PRD 00012 assumptions ledger with the PRD 00013 one (37 lines removed). Git history keeps the old text. If the autopilot convention is one ledger per PRD, this is expected. If not, append instead of overwriting. | docs/dev/project-management/meta/assumptions.md:1 | general | ALICE |
| R7 | [1/3] | ⚪ | The fail-first replay was skipped (no `.venv/bin/python` in the base worktree), so I checked by reading. These tests would pass against the pre-change code and so don't pin the change by themselves: `test_lookup_by_path_returns_context_rows_with_file_symbols`, `test_lookup_leaves_context_row_body_searchable_by_bm25`, the blank/unsupported file test, the parser-failure test and the symbol-less non-context-language test. The PRD acceptance criteria explicitly require each of them as a compatibility or boundary guard, and the others in the file (the `_service`-based index tests, the lookup exclusion tests, and the `chunk` context tests) fail without the change. Informational, not a defect. | tests/test_module_context.py:862 | 2 | ALICE |
| R8 | [1/3] | ⚪ | The gap-coverage scan builds a `covered` set of line numbers and loops over all lines in Python (src/engram/symbols.py:156-164). Cost is linear in file size and acceptable under the 1000-character line cap. A giant, deeply covered file only costs memory. No action is needed. | src/engram/symbols.py:156 | 1 | BLAKE |
| R9 | [1/3] | ⚪ | The README documents the None-heading migration exception: an unchanged legacy file is re-chunked once and so gains context (README.md:174-176). That matches the unchanged indexer migration path (src/engram/indexer.py:83-112) and the "keep legacy-anonymous migration" requirement. It is accurate but goes beyond the PRD's wording, so keep it if intended. | README.md:174 | 3 | BLAKE |

## Alice

Raised R2, R4, R5, R6 and R7 (raw: `docs/dev/tmp/alice-output-00013c1.txt`).

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

## Blake

Raised R1, R8 and R9. Checked as compliant: chunking rules, the 14-language allowlist, lookup exclusion on exact, prefix and fallback matching, the unfiltered `lookup_by_path`, the unchanged indexer, and the README/CHANGELOG. He ran tests/test_module_context.py, tests/test_symbols.py, tests/test_indexer.py and tests/test_empty_sources.py: 81 passed.

B1: fail
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

Raised R2 and R3 (FIX bucket); VERIFY and KNOWN empty.

R1: pass
R2: fail
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

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Carl

Did not run (see Agent Status).

Verdict: 9 findings
Tests: 1244 passed (suite run this cycle; counts read from gate log docs/dev/tmp/gate-00013c1.log: 1191 passed, 1 deselected non-eval + 53 passed eval; review-stage could not parse the two-command summary)
