---
prd: 00001-engram-core-v1
cycle: 3
date: 2026-08-02
head_sha: caa3a00fbefdfdfd9c1ac19b458146b66fd23f81
codex_thread_id: 019fc06e-a3cc-7df0-99b9-76cfbb9e1d81
reviewers: alice,blake,bob,carl
---

# Review: PRD 00001 Engram Core — Cycle 3 (incremental)

Diff range: 1c9a3196644ba81483b8d490b0137315637a84ae..caa3a00fbefdfdfd9c1ac19b458146b66fd23f81 (cycle-2 rework: 5 commits, D2 tasks 17-19 — cli.py + client.py hardening and their tests)

codex_rung_guard: not fired

## Reviewers that ran

- **Alice** (consensus, Claude subagent) — ran, 1 finding (⚪). Verified every cycle-2 D2 fix resolved in source; all production functions under 50 lines (R12 pass); suite 137 green. R13 fail (test_client.py 1045 lines).
- **Blake** (blind, PRD-only Claude subagent) — ran, 2 findings; R7/R16 fail (both are the settled deferrals: extra CLI flags, Phase-2 four-corpus acceptance). Found nothing new.
- **Bob** (doubt, codex; resumed cycle-2 thread 019fc06e) — ran, 4 findings (1 🟠, 2 🟡/⚪ test-quality, 1 "cannot statically verify"), doubt rubric R1-R5 all pass.
- **Carl** (UI/design, gemini/copilot) — ran, 2 findings (both 🟡, R12/R13 size limits on the test file). Engram has no web/UI surface; reviewed as generalist. Cycle-2 R12 miscount noted and corrected — counted carefully this cycle.
- **Quinn** (qwen, advisory) — **SKIPPED (failed)**. Same reviewer-tooling gap as cycles 1-2: preflight passed on provider `llamacpp8001` (port 8001) but the pi review agent reached `localhost:8080` and got `fetch failed`. Deterministic config gap (not transient), advisory weight only — no retry, no consensus impact.

Consensus scores in the table below are the `consolidate-findings.sh` exact-string match, so the two semantically-identical test_client.py >800-line findings (Alice + Carl) show as separate `[1/4]` rows. The real consensus by theme is in "Consensus themes".

## Verified facts (orchestrator checks, not reviewer claims)

- **Bob's 🟠 (repos.csv under default/repo scope) is REAL** — traced cli.py: `_resolve_scope("repo")` → `_resolve_repo_name()`, which returns `None` when `GITA_REPOS_CSV` does not exist (cli.py:32-33). `_run_index`/`_run_status` then print `_NOT_IN_REPO_MSG` ("not inside a registered repo; pass --scope portfolio instead") and return 1 — the D2 `except FileNotFoundError` repos.csv message (cli.py:136-138, 158-162) is only reached under `--scope portfolio`. So the cycle-2 fail-loud fix is incomplete for the default scope, and the misleading hint misdirects the user to portfolio scope (which also fails on the same missing repos.csv). New tests cover only `--scope portfolio`. Effective severity 🟡 Medium (it does fail loud with nonzero exit; the remediation message is wrong).
- **All cycle-2 D2 fix targets verified resolved** (Alice, against the code): repos.csv fail-loud on both `status` and `index` (portfolio path), `_parse_vector_item` non-mapping rejection + honest `list[Vector]` return, `-k` `return 1`, `_print_missing` corpus scoping, `--rebuild` tmp_store close before `os.replace`, loopback-redirect e2e via `_OPENER`, heading+body embed cardinality, tautological smoke assert removed. No regressions.
- **Full suite: 137 passed, 0 failed, 0 skipped** (`uv run pytest`, this cycle).
- **test_client.py is 1045 lines** — over the 800-line limit; Alice notes ~932 pre-diff, so the R13 violation predates cycle 2 (cycle 2 added +113).

## Consensus themes (semantic grouping)

- **test_client.py exceeds the 800-line limit (R13)** — ALICE (⚪), CARL (🟡) (**2/4**). Real; pre-existing (932 before cycle-2's +113). **AUTO-FIX (D3)** — split the embedding-response tests into a sibling module.
- **repos.csv missing gives a misleading message under default/repo scope** — BOB (🟠, verified 🟡). Cycle-2 fix covered only the portfolio path. **AUTO-FIX (D3, Protocol B proceed)** — check `GITA_REPOS_CSV.exists()` in the command path and emit the repos.csv message before `_NOT_IN_REPO_MSG`; add index+status repo/default-scope tests.
- **loopback-redirect test quality (R2 intent-binding)** — BOB (🟡 + ⚪). The `::1` integration test frames a loopback host as "off-machine" (confusing, though the fail-closed assertion itself is correct); the old private-handler test still accepts any `Exception` and is now redundant with the e2e test. The e2e function is also 83 lines (CARL 🟡, R12). **AUTO-FIX (D3, de-slop)** — remove the redundant old test, reframe the `::1` test naming, extract the dual-server setup to a helper to get the function under 50 lines.

## Deferred (settled — carried in the batch deferred JSON, NOT reworked)

- **Gold set covers 3 of 4 corpora (no `decision` entries)** — BLAKE (🟡, R16). Requirements ambiguity settled cycles 0/1/2: no `decisions.md` exists portfolio-wide and `load_goldset()` requires `expected_path` to exist, so a decision entry is structurally impossible today. **DEFERRED.**
- **Extra CLI flags beyond the PRD interface** (`-k/--k`, `--rebuild`) — BLAKE (⚪, R7). `--rebuild` is design-authorized as the "full re-embed" recovery path; `-k` is a scope call for the human. Settled cycles 1/2. **DEFERRED.**

## Accepted / not a defect

- **Bob "cannot statically verify `uv run pytest` exits 0"** (⚪) — sandbox runtime limitation, not a defect. Orchestrator verified 137 passed this cycle.

## Consolidated findings (script output, exact-match consensus)

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [1/4] | 🟠 | `index`/`status` give a misleading "not inside a registered repo" message (not the repos.csv message) under default/repo scope; new tests cover only `--scope portfolio` | src/engram/cli.py | 17 | BOB |
| [1/4] | 🟡 | test_client.py is 1045 lines, exceeding the 800-line limit | tests/test_client.py | 19 | CARL |
| [1/4] | 🟡 | test_post_embeddings_refuses_redirect_to_reachable_off_machine_loopback_host is 83 lines, exceeding the 50-line limit | tests/test_client.py | 19 | CARL |
| [1/4] | 🟡 | Gold set covers 3 of 4 corpora; Phase-2 "all four corpora" unmet (SETTLED) | eval/goldset.yaml | 9 | BLAKE |
| [1/4] | 🟡 | e2e redirect test frames IPv6 `::1` (a loopback host) as "off-machine"; confusing naming, binds to the hostname allowlist | tests/test_client.py | 19 | BOB |
| [1/4] | ⚪ | Cannot statically verify: `uv run pytest` exits 0 (runtime; verified 137 pass) | N/A | 19 | BOB |
| [1/4] | ⚪ | Extra CLI flags beyond PRD interface (-k/--rebuild) (SETTLED) | src/engram/cli.py | general | BLAKE |
| [1/4] | ⚪ | test_client.py 1045 lines > 800 (pre-diff ~932); split embedding-response tests into a module | tests/test_client.py | 19 | ALICE |
| [1/4] | ⚪ | Old private-handler redirect test remains, still accepts any `Exception`, now redundant with the e2e test | tests/test_client.py | 19 | BOB |

## Alice (consensus)

R1-R4, R6-R12 pass; R13 fail (test_client.py 1045 lines). 1 ⚪ finding. Verified every cycle-2 D2 fix resolved in source; production functions all under 50 lines; suite 137 green, no refactor regressions.

## Blake (blind, PRD-only)

R7 fail (extra flags), R16 fail (Phase-2 four-corpus) — both settled deferrals. All other rules pass (auth/rate-limit/migration rules vacuous for a local single-user tool). 2 findings, nothing new.

## Bob (doubt, codex)

Doubt rubric: R1: pass, R2: pass, R3: pass, R4: pass, R5: pass. 4 findings incl. 1 🟠 (repos.csv message incomplete under default/repo scope — verified real, effective 🟡) and 2 loopback-redirect test-quality findings (::1 framing, redundant old test) plus 1 "cannot statically verify" (runtime, not a defect).

## Carl (UI/design, gemini)

R1-R11 pass; R12 fail (83-line test function), R13 fail (1045-line test file). 2 findings, both test-size limits. Engram has no web/UI surface; reviewed as generalist. Cycle-2 R12 miscount corrected.

Verdict: 9 findings
Tests: 137 passed, 0 failed, 0 skipped
