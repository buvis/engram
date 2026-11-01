---
prd: 00001-engram-core-v1
cycle: 4
date: 2026-08-02
head_sha: ba9f7ab82b7bc68b6b02eddc24712dfc7b10555c
codex_thread_id: 019fc06e-a3cc-7df0-99b9-76cfbb9e1d81
reviewers: alice,blake,bob,carl
---

# Review: PRD 00001 Engram Core — Cycle 4 (incremental)

Diff range: caa3a00fbefdfdfd9c1ac19b458146b66fd23f81..ba9f7ab82b7bc68b6b02eddc24712dfc7b10555c (cycle-3 rework: D3 tasks 20-21 — cli.py repos.csv default-scope message + test_client.py split/de-slop)

codex_rung_guard: not fired

## Reviewers that ran

- **Alice** (consensus, Claude subagent) — ran, 1 finding (🟡). Verified test_client.py trimmed to 799 lines, pyflakes clean (no unused imports), all 4 moved embedding tests plus siblings landed in test_client_embed.py with none lost, redundant private-handler test dropped (redirect refusal still covered e2e), `::1` test renamed with allowlist-binding docstring, repos.csv disambiguation via `_repo_scope_error_msg()` correct and tested on both branches. R12 fail (redirect fixture 69 lines).
- **Blake** (blind, PRD-only Claude subagent) — ran, 8 findings. Mostly the settled deferrals (goldset 3/4, extra flags, eval-gate runtime, --alias, ensure_served race) which he cannot know are settled, plus one out-of-scope pre-existing item (CLI catches only StoreModelMismatchError). R1/R6/R7/R16 fail — all map to settled deferrals.
- **Bob** (doubt, codex; resumed thread 019fc06e) — ran, 3 findings (1 🟡 fixture-size concurring with Alice/Carl, 1 ⚪ test-fixture socket-leak nit, 1 ⚪ "cannot statically verify"), doubt rubric R1-R5 all pass.
- **Carl** (UI/design, gemini/copilot) — ran, 2 findings. Concurred on the fixture-size R12 violation (labeled 🔴, effective 🟡), and uniquely caught that `_run_query` still emits the misleading message (the task-20 fix was not applied to query). Engram has no web/UI surface; reviewed as generalist.
- **Quinn** (qwen, advisory) — **SKIPPED (failed)**. Preflight passed on provider `llamacpp8001` (port 8001) but the pi review agent reached `localhost:8080` and got `fetch failed` — the same deterministic config gap as cycles 1-3. Advisory weight only; no retry, no consensus impact.

Consensus scores in the consolidated table are the `consolidate-findings.sh` exact-string match, so the three semantically-identical fixture-size findings (Alice + Bob + Carl) show as separate `[1/4]` rows. The real consensus by theme is in "Consensus themes".

## Verified facts (orchestrator checks, not reviewer claims)

- **`_run_query` misleading-message finding (Carl) is REAL** — traced cli.py: `_run_query` (line 81) prints `_NOT_IN_REPO_MSG` directly on `scope is None`, whereas `_run_index` (line 132) and `_run_status` (line 153) were fixed in D3/task-20 to use `_repo_scope_error_msg()`. So when `~/.config/gita/repos.csv` is missing and the user runs `engram query --scope repo <text>`, `_resolve_scope("repo")` returns None (repos.csv absent) and the misleading "not inside a registered repo; pass --scope portfolio instead" hint surfaces — the exact bug cycle 3 fixed for index/status, left unfixed in query. Same root cause, incomplete fix. Effective 🟡 (query's `--scope` is required, so the trigger is explicit `--scope repo` + missing repos.csv, narrower than the default-scope index/status path).
- **Redirect fixture size finding (Alice/Bob/Carl) is REAL** — `_redirect_chain_to_reachable_off_machine_loopback` spans ~69-70 lines (lines ~590-659), over the 50-line limit. Task 21's stated acceptance was to extract the dual-server setup into a `<50`-line helper; the test function was brought under 50 but the bulk relocated into a 69-line fixture, so the task's own target is only partially met.
- **repos.csv disambiguation for index/status verified correct** (Alice, against code): `_repo_scope_error_msg()` returns the repos.csv-not-found message when `GITA_REPOS_CSV` is absent, else `_NOT_IN_REPO_MSG`; both `_run_index` and `_run_status` use it, and both branches are tested (test_cli.py adds 4 default-scope tests).
- **test module split verified** — embedding-response tests moved to `tests/test_client_embed.py`; shared helpers extracted to `tests/_embedding_server.py`; no test lost; both test files under 800 lines (test_client.py 799).
- **Full suite: 140 passed, 0 failed, 0 skipped** (`uv run pytest`, this cycle).

## Consensus themes (semantic grouping)

- **Redirect fixture exceeds the 50-line limit (R12)** — ALICE (🟡), BOB (🟡), CARL (🔴→🟡) (**3/4**). Real; task-21's own `<50`-line acceptance only partially met. **AUTO-FIX (D4)** — extract the two ad-hoc server-handler classes out of the fixture (module scope or a helper) so the fixture body is under 50 lines; keeps the suite green.
- **`_run_query` still emits the misleading repos.csv message** — CARL (⚪, verified 🟡). The task-20 fix was applied to index/status but not query. **AUTO-FIX (D4, bug-fix discipline — same bug elsewhere)** — route `_run_query`'s scope-None branch through `_repo_scope_error_msg()`; add a query default/repo-scope missing-repos.csv test.

## Deferred (settled — carried in the batch deferred JSON, NOT reworked)

- **Gold set covers 3 of 4 corpora** (+ `load_goldset` does not enforce four-corpus coverage) — BLAKE (🟠/🟡, R16/R1/R15). Requirements ambiguity settled cycles 0/1/2/3: no `decisions.md` exists portfolio-wide and `load_goldset()` requires `expected_path` to exist, so a decision entry is structurally impossible today. **DEFERRED.**
- **Extra CLI flags beyond the PRD interface** (`-k/--k`, `--rebuild`) — BLAKE (🟡/⚪, R6/R7). `--rebuild` is design-authorized recovery; `-k` is a scope call for the human. Settled cycles 1/2/3. **DEFERRED.**
- **Eval gate not demonstrably met from code** (`[pinned] id=""`, runtime-only) — BLAKE (🟡). Not a code defect; the gate is a runtime outcome on real corpora. **DEFERRED.**
- **`llama-server --alias <id>` deviation from the PRD-literal command** — BLAKE (⚪). Design-authorized (design doc: `--alias` makes the server's reported model id match `entry.id`). **DEFERRED.**
- **`ensure_served` check-then-act port race** — BLAKE (⚪). Tolerable for a single-user manual tool. **DEFERRED (accepted).**
- **`query`/`index` CLI let EmbeddingServerError/EmbeddingPreflightError escape as an uncaught traceback** — BLAKE (🟡). Pre-existing (not introduced by D3), out of the D3 incremental scope, and still "loud" (nonzero exit + the actionable message rides in the exception). **DEFERRED to batch end** as a UX-polish follow-up candidate.

## Accepted / not a defect

- **Bob "cannot statically verify `uv run pytest` exits 0"** (⚪) — sandbox runtime limitation, not a defect. Orchestrator verified 140 passed this cycle.
- **Bob ⚪ redirect fixture starts the reachable server before the `try/finally`** (socket/thread leak only if the *redirect* server then fails to construct) — test-only error path; folded into the D4 fixture rework (the extraction tightens setup/teardown).

## Consolidated findings (script output, exact-match consensus)

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [1/4] | 🔴→🟡 | `_redirect_chain_to_reachable_off_machine_loopback` fixture is 69 lines, over the 50-line limit | tests/test_client.py | 21 | CARL |
| [1/4] | 🟡 | Redirect fixture 69 lines (591-659), task-21 `<50` target only partially met | tests/test_client.py | 21 | ALICE |
| [1/4] | 🟡 | Redirect fixture 70 lines (590-659), over the `<50` target | tests/test_client.py | 21 | BOB |
| [1/4] | ⚪→🟡 | `_run_query` still prints `_NOT_IN_REPO_MSG` directly instead of `_repo_scope_error_msg()` (misleading hint when repos.csv missing) | src/engram/cli.py | 20 | CARL |
| [1/4] | 🟠 | Gold set covers 3 of 4 corpora; `decision` corpus empty (SETTLED) | eval/goldset.yaml | 9 | BLAKE |
| [1/4] | 🟡 | `load_goldset` never enforces four-corpus coverage (SETTLED) | eval/harness.py | 9 | BLAKE |
| [1/4] | 🟡 | Eval gate not demonstrably met from code (runtime-only) (SETTLED) | src/engram/client.py | 10 | BLAKE |
| [1/4] | 🟡 | `-k/--k` flag beyond PRD interface (SETTLED) | src/engram/cli.py | 8 | BLAKE |
| [1/4] | 🟡 | `query`/`index` catch only StoreModelMismatchError; endpoint-down/spawn escapes as traceback (pre-existing, DEFERRED) | src/engram/cli.py | 8 | BLAKE |
| [1/4] | ⚪ | `index --rebuild` flag not named in PRD (SETTLED) | src/engram/cli.py | 8 | BLAKE |
| [1/4] | ⚪ | `ensure_served` check-then-act port race (SETTLED, tolerable) | src/engram/client.py | 2 | BLAKE |
| [1/4] | ⚪ | `llama-server --alias <id>` deviation from PRD-literal command (SETTLED, design-authorized) | src/engram/client.py | 2 | BLAKE |
| [1/4] | ⚪ | Redirect fixture starts reachable server before `try/finally` (leak on redirect-server construction failure) | tests/test_client.py | 21 | BOB |
| [1/4] | ⚪ | Cannot statically verify `uv run pytest` exits 0 (runtime; verified 140 pass) | N/A | 21 | BOB |

## Alice (consensus)

R1-R4, R6-R11, R13 pass; R12 fail (redirect fixture 69 lines). 1 🟡 finding. Verified every cycle-3 D3 fix resolved in source (repos.csv disambiguation, module split, no test lost, no unused import, `::1` rename, redundant test dropped); suite 140 green, no refactor regressions.

## Blake (blind, PRD-only)

R1/R6/R7/R16 fail — all map to settled deferrals (goldset four-corpus, extra flags). All other rules pass (auth/rate-limit/migration/Phase-3 rules vacuous for a local single-user tool). 8 findings; the only non-settled one (CLI uncaught-traceback on endpoint-down) is pre-existing and out of the D3 scope — deferred.

## Bob (doubt, codex)

Doubt rubric: R1: pass, R2: pass, R3: pass, R4: pass, R5: pass. 3 findings: 1 🟡 (redirect fixture 70 lines — concurs with Alice/Carl), 1 ⚪ (fixture socket-leak on redirect-server construction failure — test error path), 1 ⚪ ("cannot statically verify" pytest — runtime, not a defect).

## Carl (UI/design, gemini)

R1-R11, R13 pass; R12 fail (69-line fixture). 2 findings: the fixture-size R12 violation (concurs), and the unique catch that `_run_query` still emits the misleading message (task-20 fix incomplete). Engram has no web/UI surface; reviewed as generalist.

Verdict: 14 findings
Tests: 140 passed, 0 failed, 0 skipped
