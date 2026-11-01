---
prd: 00001-engram-core-v1
cycle: 2
date: 2026-08-02
head_sha: 1c9a3196644ba81483b8d490b0137315637a84ae
codex_thread_id: 019fc06e-a3cc-7df0-99b9-76cfbb9e1d81
reviewers: alice,blake,bob,carl
---

# Review: PRD 00001 Engram Core — Cycle 2 (incremental)

Diff range: e5e9e62e8e49a4b8202a63fe8423204c1908c5b3..1c9a3196644ba81483b8d490b0137315637a84ae (cycle-1 rework: 13 commits, D1 tasks 11-16)

codex_rung_guard: not fired

## Reviewers that ran

- **Alice** (consensus, Claude subagent) — ran, 3 findings (all ⚪), rubric R1-R13 all pass; verified every cycle-1 finding resolved, no regressions in the refactors.
- **Blake** (blind, PRD-only Claude subagent) — ran, 7 findings; R1/R7/R16 fail (all three are the settled deferrals: goldset decision corpus, extra CLI flags, Phase-2 four-corpus acceptance).
- **Bob** (doubt, codex; resumed cycle-1 thread) — ran, 10 findings (1 🟠, 3 🟡, rest ⚪ incl. 2 "cannot statically verify"), doubt rubric R1-R5 all pass.
- **Carl** (UI/design, gemini/copilot) — ran, 6 findings; R1/R12 fail. **Note: Carl's R12 fail is a miscount** — see "Verified facts" below.
- **Quinn** (qwen, advisory) — **SKIPPED (failed)**. Same reviewer-tooling gap as cycle 1: preflight passed on provider `llamacpp8001` (port 8001) but the pi review agent reached `localhost:8080` and got `fetch failed`. Advisory lens only; graceful degradation, no impact on consensus.

Consensus scores in the table below are the `consolidate-findings.sh` exact-string
match, so semantically-equivalent findings each show `[1/4]`. The real
multi-reviewer consensus by theme is in "Consensus themes".

## Verified facts (orchestrator checks, not reviewer claims)

- **`_heading_delimited_chunks` is 44 lines (36-79), NOT 58** — Carl's R12 fail on
  this function is a miscount. Alice's R12 pass is correct.
- **`_parse_batch_vectors` is exactly 50 lines (262-311)** — borderline the
  "under 50" limit. Carl's "51" is close; the substantive issue is the incomplete
  item-mapping validation (below), whose fix will require a small extraction to
  stay under 50.
- **Full suite: 131 passed, 0 failed, 0 skipped** (`uv run pytest`, this cycle).
- **All 20 cycle-1 fix targets verified resolved** (Alice + Bob, against the code):
  status/index fail-loud + missing-dir surfacing, unconditional model-mismatch
  validation on unchanged reindex, rg return-code guard, loopback redirect handler,
  scorer conn close, heading+body embedding, per-corpus rate emission, wrong-model
  reap, non-list `data` guard, load_config validation, `-k` rejection, extracted
  `resolve_pinned_entry`, `dict[int, SearchHit]` typing, five functions split, real
  smoke tests, `:.4f` scores, dead `if not tokens` branch removed, nonzero-exit test.
  No behavior regressions in the store/corpora/chunker/indexer/client splits.

## Consensus themes (semantic grouping)

- **Missing `~/.config/gita/repos.csv` handled inconsistently** — flagged by BOB
  (🟠), BLAKE (🟡), ALICE (⚪) (**3/4**). `_run_status` catches `FileNotFoundError`
  and `pass`es (exits 0 with incomplete output — violates PRD "status ... fail
  loud"), while `engram index` dies with an uncaught traceback on the same
  condition. **AUTO-FIX (D2)** — both paths should fail loud with a clear message.
- **`_parse_batch_vectors` response hardening incomplete** — BOB (🟡), ALICE (⚪),
  CARL (⚪, return type) (**3/4**). `data` is guarded as a list, but each `item` is
  assumed to be a mapping; `item.get("index")` on a `[null]`/`[1]` element raises
  raw `AttributeError` instead of `EmbeddingPreflightError`. The helper also returns
  a `list[Vector | None]` typed value as `list[Vector]`. **AUTO-FIX (D2)** — additive
  boundary validation + tighten the return type.
- **`-k` uses `sys.exit(1)` inside a return-code-based `_run_query`** — CARL (🟡),
  ALICE (⚪), BOB (⚪) (**3/4**). Inconsistent control flow; the test cements it.
  (Cycle-1 discarded this once as "correct per SystemExit test"; re-raised by 3
  reviewers.) **AUTO-FIX (D2)** — low, use `return 1` and adjust the test.
- **`_print_missing` prints out-of-scope missing-dir warnings** — BOB (🟡), CARL
  (🟡, missing test) (**2/4**). `index --corpus prd` prints missing-dir warnings for
  every corpus because `_print_missing` filters by repo only; the cycle-1 rework
  made previously-hidden out-of-scope warnings user-visible. **AUTO-FIX (D2)** —
  scope the warnings to the active `--corpus`, add the missing test.
- **Weak tests (R2 intent-binding)** — BOB (🟡/⚪). The loopback-redirect regression
  test invokes a private handler and accepts any `Exception` (passes even if
  `_post_embeddings` stops using `_OPENER` — does not protect the contract); the
  heading-embedding test only checks the heading appears "somewhere"; the smoke
  suite retains `assert callable(main)`. **AUTO-FIX (D2, de-slop)**.

## Deferred (settled — carried in the batch deferred JSON, NOT reworked)

- **Gold set covers 3 of 4 corpora (no `decision` entries)** — BLAKE (🟠, R16),
  requirements ambiguity settled cycle 0: no `decisions.md` exists portfolio-wide
  and `load_goldset()` requires `expected_path` to exist, so a decision entry is
  structurally impossible today. **DEFERRED.**
- **Extra CLI flags beyond the PRD interface** (`-k/--k`, `--rebuild`, `--scope`/
  `--corpus` on index/status) — BLAKE (🟡, R7), scope call for the human at
  batch-end. `--rebuild`/`--alias` are design-authorized. **DEFERRED.**
- **Phase-2 eval-gate outcome unverifiable from the codebase** — BLAKE (🟠). The
  gate (top-5 >=80% AND > rg baseline) is runtime-only, pinned into the runtime
  `config.toml`, never in the repo; overlaps Bob's 2 "cannot statically verify".
  Not a code defect — runtime verification, out of static-review scope. **KNOWN.**

## Accepted / known (low, not reworked)

- `_write_pinned` missing-`id` edge (BOB 🟡, 1/4): cannot occur with the frozen
  config schema (`[pinned]` always carries `id = ""`). **ACCEPT.**
- `IndexReport.chunks_updated` vestigial (permanently 0) (BLAKE ⚪): cycle-1
  deferred; low-value dead field. **DEFER (low de-slop).**
- `corpora.py` module-global `missing_dirs` (BLAKE ⚪): design-intentional
  (module-level counter reset per call, single-user CLI, not thread-relevant).
  **ACCEPT (by design).**
- `tmp_store` not closed before `os.replace` in `--rebuild` (CARL ⚪): POSIX
  `os.replace` over an open SQLite handle is safe on macOS/Linux; folded into the
  D2 cli.py task as cheap hygiene. **AUTO-FIX (D2).**
- Server spawn `--alias` deviation from the verbatim PRD spawn command (BLAKE ⚪):
  design-authorized (pins `/v1/models` identity for the preflight check). **ACCEPT.**

## Consolidated findings (script output, exact-match consensus)

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [1/4] | 🟠 | status --scope portfolio swallows a missing repos.csv, exits 0 instead of failing loud | src/engram/cli.py | 11 | BOB |
| [1/4] | 🟠 | goldset.yaml 36 entries but zero decision-corpus; Phase-2 "all four corpora" unmet (SETTLED) | eval/goldset.yaml | 9 | BLAKE |
| [1/4] | 🟠 | Phase-2 eval-gate outcome unverifiable from codebase (runtime-only) | src/engram/harness.py | 10 | BLAKE |
| [1/4] | 🟡 | Extra CLI flags beyond PRD interface (-k/--rebuild/--scope/--corpus) (SETTLED) | src/engram/cli.py | 8 | BLAKE |
| [1/4] | 🟡 | _write_pinned checks [pinned] exists, not that exactly one id replaced (cannot occur w/ frozen schema) | src/engram/harness.py | 14 | BOB |
| [1/4] | 🟡 | index --corpus X prints missing-dir warnings for every corpus; _print_missing filters by repo only | src/engram/cli.py | 11 | BOB |
| [1/4] | 🟡 | response hardening incomplete: data elements not validated as mappings → AttributeError; Optional return type | src/engram/client.py | 13 | BOB |
| [1/4] | 🟡 | redirect regression test invokes private handler, accepts any Exception; doesn't protect the contract | tests/test_client.py | 13 | BOB |
| [1/4] | 🟡 | enumerate_corpora reads repos.csv with no existence guard; index dies uncaught | src/engram/corpora.py | general | BLAKE |
| [1/4] | 🟡 | -k sys.exit(1) circumvents main() return flow; use return 1 | src/engram/cli.py | 15 | CARL |
| [1/4] | 🟡 | (MISCOUNT) _heading_delimited_chunks "58 lines" — actually 44 (36-79); R12 pass | src/engram/chunker.py | 16 | CARL |
| [1/4] | 🟡 | _parse_batch_vectors ~50 lines (borderline); real issue is item-mapping validation | src/engram/client.py | 16 | CARL |
| [1/4] | 🟡 | Missing test for repo-scoped missing-corpus filtering in _print_missing | src/engram/cli.py | 11 | CARL |
| [1/4] | ⚪ | _parse_batch_vectors item-mapping unvalidated → raw AttributeError (partial cycle-1 fix) | src/engram/client.py | 13 | ALICE |
| [1/4] | ⚪ | -k rejects non-positive via sys.exit(1) while siblings use return 1 | src/engram/cli.py | 15 | ALICE |
| [1/4] | ⚪ | _run_status swallows FileNotFoundError while index crashes uncaught | src/engram/cli.py | 11 | ALICE |
| [1/4] | ⚪ | Cannot statically verify: uv run pytest exits 0 (runtime) | N/A | 16 | BOB |
| [1/4] | ⚪ | Cannot statically verify: harness gate (>=80%, beats baseline) (runtime) | N/A | 14 | BOB |
| [1/4] | ⚪ | corpora.py module-global missing_dirs (by design) | src/engram/corpora.py | general | BLAKE |
| [1/4] | ⚪ | heading-embedding test only checks heading appears "somewhere" | tests/test_indexer.py | 12 | BOB |
| [1/4] | ⚪ | -k validation deslop: sys.exit inside return-based function; test cements it | src/engram/cli.py | 15 | BOB |
| [1/4] | ⚪ | smoke suite retains assert callable(main) (framework-verification) | tests/test_smoke.py | 16 | BOB |
| [1/4] | ⚪ | IndexReport.chunks_updated vestigial (permanently 0) | src/engram/indexer.py | general | BLAKE |
| [1/4] | ⚪ | _parse_batch_vectors return type list[Vector|None] violates list[Vector] | src/engram/client.py | 13 | CARL |
| [1/4] | ⚪ | tmp_store connection not closed before os.replace in rebuild | src/engram/cli.py | 11 | CARL |
| [1/4] | ⚪ | Server spawn --alias deviation from verbatim PRD spawn command (design-authorized) | src/engram/client.py | 2 | BLAKE |

## Alice (consensus)

R1-R13 all pass. 3 ⚪ findings (repos.csv inconsistency, _parse_batch_vectors item-mapping partial hardening, -k sys.exit). Verified all cycle-1 findings resolved; no regressions in the refactors. See table.

## Blake (blind, PRD-only)

R1 fail (goldset decision corpus), R7 fail (extra flags), R16 fail (Phase-2 four-corpus) — all three are the settled deferrals. Other rules pass (R9/R11/R13 vacuous for a local single-user tool). 7 findings — see table.

## Bob (doubt, codex)

Doubt rubric: R1: pass, R2: pass, R3: pass, R4: pass, R5: pass. 10 findings incl. 1 🟠 (status swallows repos.csv) and 2 "cannot statically verify" (runtime checks, not defects) — see table and "Consensus themes".

## Carl (UI/design, gemini)

R1 fail (test coverage), R12 fail — **R12 fail is a miscount** (`_heading_delimited_chunks` is 44 lines, not 58; `_parse_batch_vectors` is 50, borderline). 6 findings — see table. Engram has no web/UI surface; reviewed as generalist.

Verdict: 26 findings
Tests: 131 passed, 0 failed, 0 skipped
