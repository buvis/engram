---
prd: docs/dev/project-management/prds/wip/00010-repo-memory-corpus-v1.md
review: 2
date: 2026-11-10
head_sha: e7aaa3ae85562abc908402e97068c71e46449ef9
codex_thread_id: 01a1c471-ebfe-7790-9ba2-4791e23df699
reviewers: alice,blake,bob,carl
agents:
  alice: available
  blake: available
  bob: available
  carl: available
dispatch_rows:
  bob: 971f1ebf
  carl: df115b50
---

# Review: 00010-repo-memory-corpus-v1

Diff range: `32c8d95c4501d59c20572b264d71990aa6e61b21..e7aaa3ae85562abc908402e97068c71e46449ef9`

codex_rung_guard: not fired

## Review Summary

Reviewed: 6 completed tasks (incremental review, cycle 2, since cycle-1 head `32c8d95`)
PRDs checked: 00010-repo-memory-corpus-v1

- Consensus engine: legacy (single Alice subagent).
- pack: ok (`docs/dev/tmp/engram-pack-c2-00010.md`).
- Bob resumed codex thread `01a1c471-ebfe-7790-9ba2-4791e23df699` on the inlined prompt (178,874 bytes).
- Mechanical test checks: no `[MECH]` rows.
- Consolidation: script (`consolidate_findings.py`), with ledger `--ledger-dismiss BLAKE` (3 Blake rows auto-dismissed, listed below).
- The incremental diff also carries the user's engram-plugin spike commits (`c2313d2`, `1ef1340`, `e7aaa3a`) under `docs/dev/project-management/spikes/`. These are throwaway work outside this PRD; Bob's R1-R3 say so.
- Process note: Alice got one needless retry asking for an `R5` verdict. The consensus rubric has no R5. Her first output is the one consolidated; the retry's meta-line about the missing rule was dropped as an orchestrator artifact.
- Test gate: `review-stage` and `autopilot verify` (exit 3) both ran the suite (exit 0) but could not parse pytest's plain `680 passed` summary. The `Tests:` line below is read from `docs/dev/tmp/gate-e7aaa3a.log` line 11; `last-verification.json` was not written.

Prior-finding status: R2 (yaml `ValueError` crash) resolved by `8e0617f` with a regression case (Alice verified, 50 passed on the narrow selector). R4/R13 and every other cycle-1 row are settled in the ledger.

### Agent Status

- Alice (Claude, consensus): ✅ Available - 0 findings
- Blake (Claude, blind/PRD-only): ✅ Available - 5 findings (3 auto-dismissed by ledger)
- Bob (codex, consensus + doubt): ✅ Available - 3 KNOWN findings (spike only), D1-D5 all pass
- Carl (copilot, model gemini-3.8-flash, UI + generalist): ✅ Available - 0 findings (his pytest attempt was denied by the copilot sandbox; he reviewed statically)

## Consolidated Findings

| Ref | Consensus | Severity | Issue | File | Task | Found By |
|-----|-----------|----------|-------|------|------|----------|
| R1 | [1/4] | 🟡 | The spike MCP server terminates on `k: "invalid"`, a missing executable, or a query timeout: conversion and subprocess exceptions escape the request loop. These failure paths have no regression tests. Outside PRD 00010 because this server is explicitly a throwaway prototype. | docs/dev/project-management/spikes/engram-plugin/engram/server/engram_mcp.py:39 | general | BOB |
| R2 | [1/4] | 🟡 | The nudge’s “always exits 0” promise does not hold when an existing pack cannot be read or a query result lacks the expected TSV columns. Both exceptions escape `main`. Outside PRD 00010; address these failure paths if the prototype graduates. | docs/dev/project-management/spikes/engram-plugin/engram/nudge/engram_nudge.py:97 | general | BOB |
| R3 | [1/4] | 🟡 | Plugin delivery remains incomplete: several hook commands contain literal `<PLUGIN_ROOT: placeholder name unverified>` paths, and the manifest references an absent `dev.kiro/hooks.json`. This is an acknowledged prototype limitation, outside the repository-memory PRD. | docs/dev/project-management/spikes/engram-plugin/engram/plugin.json:14 | general | BOB |
| R4 | [1/4] | ⚪ | `memory_files` and `redact` are extra public helpers beyond the listed exports. Module-level side-channel lists (`repo_memory_dirs`, `legacy_shadowed`) carry state from `enumerate_corpora` to `_run_status`. This works and is tested, but it is hidden coupling. | src/engram/corpora.py:16 | 2 | BLAKE |
| R5 | [1/4] | ⚪ | `memory check` without PATH runs `subprocess.run(["git", ...])` without catching `FileNotFoundError`. A missing git binary gives a traceback instead of exit 1 with a hint. | src/engram/cli.py:123 | 3 | BLAKE |

### Auto-dismissed (ledger)

- [BLAKE] 🟡 Credential pattern for `sk-` deviates from the spec. The code uses a negative lookbehind `(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}`, but the spec gives `sk-[A-Za-z0-9_-]{20,}`. A token glued to an alphanumeric prefix (for example `xsk-<20+ chars>`) is not flagged. This was a deliberate narrowing and has its own test. | File: src/engram/memory.py:21 — settled design decision (cycle 0 autonomous_decisions): sk- pattern left-anchored as the only PRD amendment, after measured false positives on words like task-.
- [BLAKE] ⚪ `memory_files` and the legacy-skip predicate use `is_file()`, which follows symlinks. A symlinked `*.md` in the memory directory is indexed and read even when its target is outside the repository. | File: src/engram/memory.py:51 — single-voice
- [BLAKE] ⚪ `memory\tinvalid=<n>` counts distinct invalid files, and `MEMORY.md` counts as a file. The spec does not define what n counts. A missing-index-entry violation is attributed to the memory file, not to the index. | File: src/engram/cli.py:388 — single-voice

## Alice

No issues found (raw: `docs/dev/tmp/alice-output-c2-00010.txt`). Verified R2 resolved; no regression in the rework diff. Rubric: all pass.

## Blake

5 findings, 3 auto-dismissed by the ledger (raw: `docs/dev/tmp/blake-output-c2-00010.txt`). Narrow run of `tests/test_repo_memory.py` and `tests/test_memory_attribution.py`: 134 passed. Rubric: B1 fail, B10 fail, all others pass.

## Bob

3 KNOWN findings, all in the out-of-scope spike (raw: `docs/dev/tmp/bob-output-c2-00010.txt`). FIX and VERIFY buckets empty, so no checks were queued. Rubric: R1, R4, R7, R10, R11 fail; others pass.

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Carl

No issues found (raw: `docs/dev/tmp/carl-output-c2-00010.txt`). Backend copilot, model gemini-3.8-flash. Rubric: all pass.

Verdict: 5 findings
Tests: 680 passed (suite run this cycle; counts read from gate log, autopilot verify could not parse the pytest summary)
