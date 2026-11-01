---
prd: 00001-engram-core-v1
cycle: 5
date: 2026-08-02
head_sha: c8d7cc9b464334611716832d3711271514ff540a
codex_thread_id: 019fc06e-a3cc-7df0-99b9-76cfbb9e1d81
reviewers: alice,blake,bob,carl
---

# Review: PRD 00001 Engram Core — Cycle 5 (incremental, TERMINAL cap cycle)

Diff range: ba9f7ab82b7bc68b6b02eddc24712dfc7b10555c..c8d7cc9b464334611716832d3711271514ff540a (cycle-4 rework: D4 task 22 — route `_run_query`'s scope-None branch through `_repo_scope_error_msg()` + 2 tests + CHANGELOG line)

codex_rung_guard: not fired

## Reviewers that ran

- **Alice** (consensus, Claude subagent) — ran, ✅ 0 findings. Verified the task-22 fix at cli.py:81 routes through `_repo_scope_error_msg()`, both branches (missing registry vs unregistered repo) covered by the two new tests asserting on the distinguishing message text, no regression, sizes within limits. R1-R4, R6-R13 all pass.
- **Blake** (blind, PRD-only Claude subagent) — ran, 7 findings. All are either settled deferrals (goldset 3/4, extra CLI flags, `--alias`, `_write_pinned`) or pre-existing code OUTSIDE the cycle-5 diff (corpora `_unmapped`, indexer transient-prune, chunker non-UTF-8). None is a regression from the task-22 rework. R1/R6/R7/R16/R17 fail — map to settled/pre-existing items.
- **Bob** (doubt, codex; resumed thread 019fc06e) — ran, 2 ⚪ findings (CHANGELOG "every scope" overclaim; cannot-statically-verify pytest). Doubt rubric R1-R5 all pass.
- **Carl** (UI/design, gemini/copilot) — ran, ✅ 0 findings. R1-R4, R6-R13 all pass. Engram has no web/UI surface; reviewed as generalist.
- **Quinn** (qwen, advisory) — **SKIPPED (failed)**. Preflight passed on provider `llamacpp8001` (port 8001) but the pi review agent reached `localhost:8080` and got `fetch failed` — the same deterministic 8001/8080 config gap as cycles 1-4. Advisory weight only; no retry, no consensus impact.

## Verified facts (orchestrator checks, not reviewer claims)

- **The cycle-4 `_run_query` misleading-message finding is RESOLVED** — cli.py:81 now calls `_repo_scope_error_msg()` (was `print(_NOT_IN_REPO_MSG, ...)`). A missing `~/.config/gita/repos.csv` under `engram query --scope repo` now emits the "repos.csv not found" message; a present-but-unregistered repo still emits "not inside a registered repo". Both branches are bound by the two new tests (`test_query_repo_scope_fails_loud_with_repos_csv_message_when_registry_missing`, `test_query_repo_scope_reports_not_in_registered_repo_when_repos_csv_present_but_repo_unregistered`), which assert on the distinguishing message text, not just the exit code. This completes the bug-fix-discipline "same bug elsewhere" fix begun in D3 for `_run_index`/`_run_status`.
- **Full suite: 142 passed, 0 failed, 0 skipped** (`uv run pytest -q`, this cycle) — dismisses Bob's ⚪ cannot-statically-verify note.
- **The deferred redirect fixture-size item (task 23) was NOT re-flagged this cycle** — tests/test_client.py is outside the incremental diff (ba9f7ab..HEAD), so no reviewer scoped to the diff saw the fixture. It remains a settled deferral in the batch deferred JSON, unchanged.

## Decision (Phase 5, cycle 5 == cap 5, TERMINAL, loop mode)

Cycle 5 equals the rework cap (5), and unresolved findings remain, so no rework is dispatched. No finding is CRITICAL or security/data-loss, so this is a **loop-mode cap-out → converged-with-deferrals**, not a stall. Four genuinely-new unresolved findings are deferred as `cap-overflow` to the batch deferred JSON (202608012229); the settled items were already deferred in prior cycles.

### Deferred this cycle (cap-overflow)

- 🟡 Memory-corpus repo attribution is always `_unmapped` (corpora.py: slug `repo_path.replace("/","-")` never replaces `.`, so `github.com`→`github-com` project dirs never match; the unit test masks it) — pre-existing (task 5), outside the cycle-5 diff. NEW blind-lens catch. Follow-up candidate.
- 🟡 Portfolio `engram index` prunes a transiently-missing repo dir's chunks with no warning (indexer.py) — pre-existing (task 6), outside the cycle-5 diff. NEW blind-lens catch. Follow-up candidate.
- ⚪ Chunker `path.read_text()` has no per-file guard; a non-UTF-8 `.md` aborts the whole `index` run (chunker.py) — pre-existing (task 4), outside the cycle-5 diff. NEW blind-lens catch.
- ⚪ CHANGELOG overclaims missing repos.csv fails "under every scope"; `query --scope portfolio` never consults the registry at query time (Bob, in-scope — the CHANGELOG line was edited this diff). Doc-accuracy nit.

### Deferred earlier, re-surfaced (settled — no new action)

- 🟠 Gold set covers 3 of 4 corpora / `load_goldset` doesn't enforce four-corpus coverage — settled cycles 0-4 (no `decisions.md` exists portfolio-wide; `load_goldset` requires `expected_path` to exist, so a decision entry is structurally impossible today).
- 🟡 Extra CLI flags (`-k/--k`, `index --rebuild/--scope/--corpus`) — settled cycles 1-4 (scope call for the human; `--rebuild` design-authorized).
- ⚪ `llama-server --alias <id>` deviation — settled (design-authorized).
- ⚪ `_write_pinned` no-op when `[pinned]` has no `id` line — settled cycle 2 (accepted by-design; cannot occur with the frozen config schema).

## Consolidated findings (script output, exact-match consensus)

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [1/4] | 🟠 | Gold set covers only 3 of 4 corpora; `decision` corpus empty (SETTLED) | eval/goldset.yaml | Phase 2 | BLAKE |
| [1/4] | 🟡 | CLI flags beyond PRD contract: `-k/--k`, `index --rebuild/--scope/--corpus` (SETTLED) | src/engram/cli.py | Phase 2 | BLAKE |
| [1/4] | 🟡 | Memory-corpus repo attribution always `_unmapped` (`.` not replaced in slug) (DEFERRED cap-overflow) | src/engram/corpora.py | Phase 1 | BLAKE |
| [1/4] | 🟡 | Portfolio `index` prunes a transiently-missing repo dir's chunks (DEFERRED cap-overflow) | src/engram/indexer.py | Phase 1 | BLAKE |
| [1/4] | ⚪ | `_write_pinned` no-ops when `[pinned]` has no `id` line (SETTLED, cannot occur w/ frozen schema) | src/engram/harness.py | Phase 2 | BLAKE |
| [1/4] | ⚪ | Cannot statically verify `uv run pytest` exits 0 (runtime; verified 142 pass) | N/A | 22 | BOB |
| [1/4] | ⚪ | Chunker `read_text()` no per-file guard; non-UTF-8 `.md` aborts `index` (DEFERRED cap-overflow) | src/engram/chunker.py | Phase 1 | BLAKE |
| [1/4] | ⚪ | CHANGELOG overclaims "every scope"; `query --scope portfolio` never reads the registry (DEFERRED cap-overflow) | CHANGELOG.md | 22 | BOB |
| [1/4] | ⚪ | `llama-server --alias <id>` deviation from PRD-literal command (SETTLED, design-authorized) | src/engram/client.py | Phase 0 | BLAKE |

## Alice (consensus)

✅ No issues found. R1-R4, R6-R13 all pass. Verified the task-22 fix resolved (cli.py:81 → `_repo_scope_error_msg()`), both message branches tested on their distinguishing text, no regression, cli.py 182 lines / test_cli.py 597 lines / new test functions ~19 lines each (within limits).

## Blake (blind, PRD-only)

7 findings; R1/R6/R7/R16/R17 fail. Every finding maps to a settled deferral (goldset four-corpus, extra flags, `--alias`, `_write_pinned`) or pre-existing code outside the cycle-5 diff (corpora `_unmapped`, indexer transient-prune, chunker non-UTF-8). None is a regression from the task-22 rework. The `_unmapped`, indexer-prune, and chunker-UTF-8 items are genuinely-new blind-lens catches on pre-existing code — deferred as cap-overflow follow-up candidates.

## Bob (doubt, codex)

Doubt rubric: R1: pass, R2: pass, R3: pass, R4: pass, R5: pass. 2 ⚪ findings: (1) CHANGELOG "every scope" overclaim — `query --scope portfolio` never consults the registry at query time (deferred, doc-accuracy nit); (2) cannot statically verify `uv run pytest` exits 0 — runtime limitation, orchestrator verified 142 pass.

## Carl (UI/design, gemini)

✅ No issues found. R1-R4, R6-R13 all pass. Engram has no web/UI surface; reviewed as generalist against the shared checklist; the task-22 diff is a clean helper-routing fix plus its tests.

Verdict: 9 findings
Tests: 142 passed, 0 failed, 0 skipped
