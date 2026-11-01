---
prd: 00001-engram-core-v1
cycle: 1
date: 2026-08-02
head_sha: e5e9e62e8e49a4b8202a63fe8423204c1908c5b3
codex_thread_id: 019fc06e-a3cc-7df0-99b9-76cfbb9e1d81
reviewers: alice,blake,bob,carl
---

# Review: PRD 00001 Engram Core — Cycle 1

Diff range: d5eb18b41768fc37e0e1db9630ca0686898e1a78..e5e9e62e8e49a4b8202a63fe8423204c1908c5b3 (whole PRD work range)

codex_rung_guard: not fired

## Reviewers that ran

- **Alice** (consensus, Claude subagent) — ran, 9 findings.
- **Blake** (blind, PRD-only Claude subagent) — ran, 7 findings.
- **Bob** (doubt, codex) — ran, 19 findings, rubric R1-R5 all pass.
- **Carl** (UI/design, gemini/copilot) — ran, 7 findings.
- **Quinn** (qwen, advisory) — **SKIPPED (failed)**. Preflight passed on provider
  `llamacpp8001` (port 8001), but the pi review agent reached `localhost:8080`
  and got `fetch failed`. Advisory lens only; graceful degradation, no impact on
  consensus. (Reviewer-tooling gap: preflight probes 8001, review dispatch hits
  8080 — worth fixing in the qwen wrapper, not an engram code finding.)

Consensus scores below are from `consolidate-findings.sh` (exact-string match, so
semantically-equivalent findings across reviewers each show `[1/4]`). The real
multi-reviewer consensus, by theme, is called out in "Consensus themes".

## Consensus themes (semantic grouping)

- **status/index never surfaces missing corpus dirs and never fails loud** —
  flagged by BLAKE (×2), CARL, BOB, ALICE (**4/4 reviewers**). HIGH. PRD:
  "status shows per-corpus staleness ... fail loud" and "Missing dirs are
  skipped and counted in status." `_run_index` discards `IndexReport.corpora_missing`;
  `_run_status` only reads DB rows (no filesystem enumeration); `status` always
  exits 0.
- **Gold set covers 3 of 4 corpora (no `decision` entries)** — BLAKE (HIGH),
  BOB (HIGH/known-limitation), ALICE (LOW/settled) (**3/4**). PRD Phase-2
  acceptance: "covering all four corpora." Structurally unmeetable as written:
  no `decisions.md` exists portfolio-wide, and `load_goldset()` requires
  `expected_path` to exist. Already settled at cycle 0 (state.autonomous_decisions,
  assumed-ambiguity). **Deferred** — requirements ambiguity.
- **`_score_candidate` leaks `store.conn`** — CARL, ALICE, BOB (**3/4**). MEDIUM.
  Previously deferred at task-10 per-task review; promoted to fix given 3/4 consensus.
- **Functions exceed the 50-line limit** — ALICE, CARL (**2/4**). MEDIUM (R12 fail):
  upsert_chunks (92), chunk_markdown (81), enumerate_corpora (62), index (59),
  embed (58).

## Bob's unique HIGH/MED correctness findings (single-reviewer but real)

- **HIGH — `index()` skips model-mismatch validation when all sources are
  unchanged.** All chunks skip, `upsert_chunks()` is never called, so a re-index
  succeeds against a DB recorded for a *different* embedding model. Directly
  undermines the PRD success metric "A DB whose recorded embedding model
  mismatches the configured one fails loud."
- **HIGH — rg baseline swallows return codes other than 0/1.** An rg error can
  silently zero the baseline, so engram falsely "beats baseline" → false-positive
  eval gate (a PRD success metric).
- **HIGH — loopback enforcement doesn't validate redirect targets.** `urllib`
  follows redirects; `_post_embeddings()` never re-checks the final URL, so a
  loopback endpoint that 302s off-machine defeats the zero-off-machine-network
  invariant. (Requires a misbehaving local server; hardening, not an exposed vuln.)
- MED — indexer embeds only `Chunk.body`, not `heading` → heading-only sections
  get empty-text vectors; hurts KNN recall (relevant to the >=80% gate).
- MED — harness prints only aggregate hit rate; `per_corpus_hit_rate` computed
  but never emitted (PRD: "per-model, per-corpus top-5 hit rates").
- MED — `ensure_served` readiness loop catches only `EmbeddingPreflightError`;
  an `EmbeddingModelIdentityError` leaks the spawned process.
- MED — `embed()` response validation assumes `data` is iterable of mappings;
  `data: null`/scalar leaks raw `TypeError` instead of `EmbeddingPreflightError`.
- MED — `load_config()` accepts empty embeddings / a pinned id absent from the
  shortlist → later `IndexError`/`StopIteration`/`KeyError` instead of a clear error.
- MED — `-k` accepts negative values; `[:k]` then returns almost the whole pool.

## Consolidated findings (script output, exact-match consensus)

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [1/4] | 🟠 | status not wired to CLI output: `_run_index` discards IndexReport, `_run_status` reads only DB rows; missing corpus dirs never shown | src/engram/cli.py | 8 | BLAKE |
| [1/4] | 🟠 | engram status unconditionally returns 0, not failing loud on stale files / dead rows | src/engram/cli.py | 8 | CARL |
| [1/4] | 🟠 | index() never validates configured model when every source unchanged — indexes against a DB recorded for another model | src/engram/indexer.py | 6 | BOB |
| [1/4] | 🟠 | status derives corpora only from DB rows; never consumes corpora.missing_dirs; CLI discards IndexReport.corpora_missing | N/A | general | BOB |
| [1/4] | 🟠 | loopback enforcement validates only the configured URL; urllib follows redirects, final URL never validated | src/engram/client.py | 2 | BOB |
| [1/4] | 🟠 | rg return codes other than 0/1 silently ignored → baseline may zero → false-positive eval gate | src/engram/harness.py | 10 | BOB |
| [1/4] | 🟠 | Gold set covers only 3 of 4 corpora; `decision` absent, violates Phase-2 "all four corpora" | eval/goldset.yaml | 9 | BLAKE |
| [1/4] | 🟠 | Gold set no decision entries — four-corpus acceptance unmet; needs a real decision artifact or PRD amendment | eval/goldset.yaml | 9 | BOB |
| [1/4] | 🟡 | _score_candidate opens a sqlite store per model without closing store.conn | src/engram/harness.py | 10 | CARL |
| [1/4] | 🟡 | engram index discards IndexReport; corpora_missing never shown; index prints nothing on success | src/engram/cli.py | 8 | ALICE |
| [1/4] | 🟡 | engram status never exits nonzero; prints only stale=/dead= counts | src/engram/cli.py | 8 | BLAKE |
| [1/4] | 🟡 | No test for re-indexing a CHANGED file (add-new + prune-old in one index() call) | tests/test_indexer.py | 6 | ALICE |
| [1/4] | 🟡 | Extra CLI flags beyond PRD interface: -k/--k on query, --rebuild on index | src/engram/cli.py | 8 | BLAKE |
| [1/4] | 🟡 | Five functions exceed 50-line limit (upsert_chunks, chunk_markdown, enumerate_corpora, index, embed) | N/A | general | ALICE |
| [1/4] | 🟡 | _score_candidate() opens one SQLite store per model, never closes the connection | src/engram/harness.py | 10 | BOB |
| [1/4] | 🟡 | -k accepts negative values; [:k] returns nearly the entire fused pool | src/engram/query.py | 7 | BOB |
| [1/4] | 🟡 | ensure_served readiness loop catches only EmbeddingPreflightError; identity error leaks the process | src/engram/client.py | 2 | BOB |
| [1/4] | 🟡 | load_config accepts empty embeddings / pinned id absent from shortlist → IndexError/StopIteration/KeyError later | src/engram/client.py | 2 | BOB |
| [1/4] | 🟡 | embed response validation assumes data iterable of mappings; data:null leaks TypeError | src/engram/client.py | 2 | BOB |
| [1/4] | 🟡 | indexer embeds only Chunk.body, excluding heading; heading-only sections get empty-text vectors | src/engram/indexer.py | 6 | BOB |
| [1/4] | 🟡 | harness prints only aggregate hit rate; per_corpus_hit_rate never emitted | eval/harness.py | 10 | BOB |
| [1/4] | 🟡 | Pinned-entry selection block duplicated verbatim in query.py and indexer.py | src/engram/query.py | 7 | ALICE |
| [1/4] | 🟡 | Pointer scores printed as raw floats; misaligns columns; format to fixed precision | src/engram/cli.py | 8 | CARL |
| [1/4] | 🟡 | test_status... asserts exit 0 despite staleness (binds to behavior, not PRD intent) | tests/test_cli.py | 8 | CARL |
| [1/4] | ⚪ | _baseline_hit_rate dead code: `if not tokens: continue` | src/engram/harness.py | 10 | CARL/ALICE |
| [1/4] | ⚪ | _write_pinned silently no-ops if config lacks [pinned] section | src/engram/harness.py | 10 | BLAKE |
| [1/4] | ⚪ | hit_map: dict[int, object] loses SearchHit type | src/engram/query.py | 7 | ALICE |
| [1/4] | ⚪ | index --rebuild doesn't delete leftover <db>.rebuild-tmp before open_store | src/engram/cli.py | 8 | ALICE |
| [1/4] | ⚪ | IndexReport.chunks_updated is dead API, permanently zero | src/engram/indexer.py | 6 | BOB |
| [1/4] | ⚪ | smoke test `assert engram is not None` is tautological | tests/test_smoke.py | 1 | BOB |
| [1/4] | ⚪ | three gold-set validation tests use pytest.raises(Exception), not ValueError | tests/test_harness.py | 10 | BOB |
| [1/4] | ⚪ | query() throws cryptic error if config.embeddings is empty | src/engram/query.py | 7 | CARL |
| [1/4] | ⚪ | Spawn adds --alias <id> beyond PRD exact spawn command (design-authorized) | src/engram/client.py | 2 | BLAKE |
| [1/4] | ⚪ | Success metrics (>=80%, beats baseline) only runtime-verifiable | src/engram/harness.py | 10 | BLAKE |
| [1/4] | ⚪ | Bob: 4× "cannot statically verify" (pytest exit, uv tool install, harness gate, egress trace) | N/A | general | BOB |

## Alice (consensus)

R1: fail (a critical incremental path — changed-file re-index — has no test). R12: fail (five functions >50 lines). All other rubric rules pass. 9 findings — see table.

## Blake (blind, PRD-only)

R1: fail, R7: fail (extra flags -k/--rebuild), R16: fail (Phase-2 four-corpus acceptance). Others pass (R9/R11/R13 vacuous for a local single-user tool). 7 findings — see table.

## Bob (doubt, codex)

Rubric: R1: pass, R2: pass, R3: pass, R4: pass, R5: pass. 19 findings incl. 5 HIGH and 4 "cannot statically verify" (runtime checks, not defects) — see table and the "Bob's unique HIGH/MED" section.

## Carl (UI/design, gemini)

R2: fail, R9: fail, R12: fail (per Carl's own rubric variant). 7 findings — see table.

Verdict: 35 findings
Tests: 104 passed, 0 failed, 0 skipped
