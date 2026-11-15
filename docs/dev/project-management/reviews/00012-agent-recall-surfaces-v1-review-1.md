---
prd: docs/dev/project-management/prds/wip/00012-agent-recall-surfaces-v1.md
review: 1
date: 2026-11-15
head_sha: 15820a30e93cdc05382d5f1de65c849e955dc4ca
codex_thread_id: 01a1e0ac-858d-7f40-b3af-9bb93f3e4702
reviewers: alice,blake,bob,carl
agents:
  alice: available
  blake: available
  bob: available
  carl: available
dispatch_rows:
  bob: 83c23c96
  carl: 2310aa22
---

# Review: 00012-agent-recall-surfaces-v1

Diff range: `16ff0b3774bdc89607b1e0265b0221809a05c721..15820a30e93cdc05382d5f1de65c849e955dc4ca`

codex_rung_guard: not fired

pack: ok

## Review Summary

Reviewed: 4 completed tasks
PRDs checked: 00012-agent-recall-surfaces-v1

### Agent Status

- Alice: ✅ Available (Claude subagent, consensus lens)
- Blake: ✅ Available (Claude subagent, blind/PRD-only lens)
- Bob: ✅ Available (codex, doubt lens D1-D5 + de-slop)
- Carl: ✅ Available (gemini CLI, frontend/design + generalist)

Consolidation note: `consolidate_findings.py` merged row R1's citations after
suffix stripping (`src/engram/cli.py:601` ~ `src/engram/cli.py:123`), folding
Blake's low-severity argparse-exit note into Alice's untested-`reconfigure`
row. The merged row's defect is the untested `reconfigure` branch, which Bob
independently raises as R5; Blake's argparse note is a separate ⚪ observation
recorded here rather than in its own row.

No mechanical test-check findings: the tautological-shape block and the
fail-first replay block produced no `[MECH]` lines (the four new test files
could not be collected against the pre-change code, as expected for new files).

## Consolidated Findings

| Ref | Consensus | Severity | Issue | File | Task | Found By |
|-----|-----------|----------|-------|------|------|----------|
| R1 | [2/4] | 🟡 | New behavior in `main`, the `sys.stdin.reconfigure(errors="replace")` call in the `mcp` branch, has no test. Both CLI tests replace stdin with `StringIO` or `_LiveStdin`, neither of which has `reconfigure`, so the branch never runs. Add one test that feeds `cli.main(["mcp"])` an `io.TextIOWrapper` over invalid UTF-8 bytes and asserts the ping reply plus a -32700 reply for the bad line. | src/engram/cli.py:601 | 3 | ALICE, BLAKE |
| R2 | [1/4] | 🟡 | Breadth rule differs from the spec when `cwd` is not inside a git repository. The spec says a search is broad only when a path's repo root differs from `cwd`'s root, and two missing roots are equal. The code instead treats any path outside `cwd` as broad (`os.path.commonpath([p, cwd]) != cwd`), even when neither has a repo. A search of `/tmp/x` from a non-repo `cwd` nudges, where the spec says no. Test test_judges_breadth_from_cwd_outside_repo pins this behaviour (tests/test_nudge_detection.py:262). | src/engram/nudge.py:155 | 1 | BLAKE |
| R3 | [1/4] | 🟡 | Catching a failed stdout flush does not guarantee exit 0: buffered output can be retried during interpreter shutdown, producing exit 120 on a closed pipe. Handle BrokenPipeError by preventing the shutdown retry; add a subprocess regression with a closed output pipe. | src/engram/nudge.py:251 | 2 | BOB |
| R4 | [1/4] | 🟡 | json.loads accepts NaN and Infinity, so invalid JSON can receive successful replies instead of -32700. Reject these constants with parse_constant and test that the next valid request still succeeds. | src/engram/mcp_server.py:198 | 1 | BOB |
| R5 | [1/4] | 🟡 | The new stdin decoding recovery branch has no test: CLI tests use StringIO or _LiveStdin, neither exercises reconfigure. Add a TextIOWrapper over invalid UTF-8 bytes followed by a valid ping; assert error recovery and continued serving. | tests/test_mcp_server.py:627 | 3 | BOB |
| R6 | [1/4] | ⚪ | `_grep_search` can return an empty explicit pattern (`rg -e '' /other`) and `find_broad_search` then returns `""` instead of `None`, which breaks the "pattern or None" contract. `run_nudge` copes only because `build_recall_query("")` is empty. A `if explicit == "": return None` guard, or a test pinning the current result, would make it explicit. | src/engram/nudge.py:112 | 2 | ALICE |
| R7 | [1/4] | ⚪ | `_git_log_pattern` accepts any git command where the bare token `log` appears anywhere in the arguments. The spec says `git ... log`. For example, `git commit -S -m log` or `git -C log status -G x` would be treated as a log pickaxe. The result is only a spurious recall query, never a failure. | src/engram/nudge.py:72 | 1 | BLAKE |
| R8 | [1/4] | ⚪ | The operator-token check cuts the command at any token made only of operator characters. A quoted pattern such as `rg ';' /other` is therefore truncated. This matters only for patterns made entirely of `;<>|&`, and the query builder would drop them anyway. | src/engram/nudge.py:171 | 1 | BLAKE |
| R9 | [1/4] | ⚪ | Small additions beyond the spec, all harmless: JSON-RPC `-32602` for an unknown tool, `-32600` for a non-object message, `-32603` for an unexpected exception; blank stdin lines skipped; the nudge expands `~` and `$VAR` in paths; `sys.stdin.reconfigure(errors="replace")` runs before serving MCP; `egrep` and `fgrep` are also detected; a `find` path scan skips leading `-H`, `-L` and `-P` flags and stops at `(` or `!`. These are defensible hardening and not feature creep. | src/engram/mcp_server.py:169 | general | BLAKE |
| R10 | [1/4] | ⚪ | Copilot payload documentation assigns the object-or-JSON-string alternatives to toolArgs.command. Those alternatives apply to toolArgs; command must be a string. Correct the sentence so consumers construct valid payloads. | README.md:201 | 4 | BOB |

## Alice

Findings: R1 (🟡 untested `reconfigure` branch), R6 (⚪ empty explicit grep pattern).

Verified with no defect found:
- 304 passed over `tests/test_mcp_server.py`, `tests/test_mcp_server_search.py`, `tests/test_nudge.py`, `tests/test_nudge_detection.py`, `tests/test_cli.py`.
- `mcp_server.py` and `nudge.py` match the design contract, including the planning refinements (tokenizer punctuation, `\n` cut, `commenters=""`, `expandvars`, cwd outside a repo, `lexists`, closing the store, `RecursionError` handling, `stdout.flush()` inside the try).
- `engram query` prints through `format_pointer_lines`; existing query tests still pass.
- New tests are not tautological; no skipped/xfail tests; no stray `print()` in `mcp_server.py`; no TODOs.
- README and CHANGELOG entries match the PRD; the spike directory is deleted.
- Function sizes within 50 lines; no file over 800 lines (largest: `tests/test_mcp_server.py` at 685).
- No secrets, no subprocess or shell execution; MCP arguments validated before any search.

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

No Critical or High issues. The implementation matches the spec. A narrow run of the nudge and MCP test files passed: 287 passed. The full suite was not rerun (the staged test-gate block supplied it).

Findings: R2 (🟡 breadth rule when `cwd` has no repo), R7, R8, R9 (⚪), plus a ⚪ note that an invalid `--host` argument to `engram nudge` makes argparse exit 2 before the nudge runs (acceptable: the spec's "exits 0 on every input" covers payload and query failures; a misconfigured hook fails loudly and blocks nothing).

Spec checks that held up:
- Eligibility: `Adoption decision: proceed` present at docs/dev/project-management/reviews/2026-11-10-agent-session-evaluation-protocol.md:63; spike directory gone; `git diff --check` clean; both Phase 2 `rg -c` acceptance checks satisfied.
- MCP loop: `initialize` echoes the client's `protocolVersion` (default `2025-06-18`), returns the exact `instructions` text; `ping` returns `{}`; notifications get no reply; `-32601` for unknown methods; `-32700` carries `id: null`; EOF returns 0; each reply flushed per line.
- `engram_query`: `scope` and `k` validated (1-20, booleans rejected); query runs in-process; mismatch, embedding and preflight errors return `isError` and the server keeps serving.
- Nudge payloads: reads `tool_input` and `toolArgs` (object or string), falls back to process `cwd`; an unreadable or missing command prints one stderr line and exits 0.
- Nudge options: `ENGRAM_NUDGE=off` returns before stdin is read; query splits on `[^A-Za-z0-9_-]` keeping words of 3+ characters; scope `portfolio`, `k=3`; `ENGRAM_PACK_FILE` drops hits whose path occurs in the file, and an unreadable pack file is tolerated.
- Nudge output: header, footer, line format and the claude/codex/copilot/plain formats match the spec.
- Dependencies: none added; no MCP SDK in pyproject.toml.
- Required tests: every test the spec names exists.

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

Doubt lens (D1-D5) plus de-slop, codex, static-only sandbox with the full context and diff inlined.

FIX: R3 (🟡 BrokenPipeError on shutdown flush retry), R4 (🟡 `json.loads` accepts NaN/Infinity), R5 (🟡 untested stdin decoding recovery branch), R10 (⚪ copilot payload documentation).

VERIFY: (none)

KNOWN: (none)

R1: fail
R2: pass
R3: pass
R4: pass
R6: pass
R7: fail
R8: pass
R9: fail
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

Backend: gemini CLI (native `gemini`). Carl read the context, diff, pack, PRD, the four new test files and the CLI dispatch site. His attempt to run pytest was refused by the sandbox approval check (no interactive approver), so he judged tests from the staged test-gate line and the test sources.

[CARL] ✅ No issues found

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

Verdict: 10 findings
Tests: 1205 passed (suite run this cycle; counts read from gate log, autopilot verify could not parse the pytest summary)
