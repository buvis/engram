---
prd: dev/local/prds/wip/00002-engram-heavy-corpora-v1.md
review: 1
date: 2026-08-04
head_sha: 997944db1da140759d1e6b95ae588de62d8e7880
codex_thread_id: 019fca1d-0a29-7143-9d07-f2e35034f9e3
reviewers: alice,blake,bob,carl,eve
agents:
  alice: available
  blake: available
  bob: available
  carl: available
  eve: available
  quinn: unavailable
---

# Review: 00002-engram-heavy-corpora-v1

Diff range: `3f99e4686ba142aebf06bfbb4b576cc859452e74..997944db1da140759d1e6b95ae588de62d8e7880`
Second repo: `claude-git-ferry` `d4eb2d2` (task 2's entire implementation; not in the range above)

codex_rung_guard: fired (1 codex-implemented task(s))

## Review Summary

Reviewed: 2 completed tasks
PRDs checked: 00002-engram-heavy-corpora-v1

### Agent Status

- Alice: ✅ Available
- Blake: ✅ Available (blind lens, PRD-only)
- Bob: ✅ Available (codex; doubt + de-slop lens)
- Carl: ✅ Available (gemini via copilot)
- Eve: ✅ Available (Fable 5, doubt lens — added by the codex doubt-roster guard)
- Quinn: ⚠️ Unavailable: local qwen backend unreachable. Preflight resolved provider `llamacpp8001` and passed a real 1-token completion, but both the dispatch and the one permitted retry (with `-P llamacpp8001` forced) failed with `[llama-cpp] failed to reach http://localhost:8080/v1/models: fetch failed` — `pi` dialled the default `:8080` provider regardless of the forced flag. Retry budget spent; graceful degradation, five reviewers proceeded. Quinn is advisory-weight, so no consensus finding was lost.

### Process notes (fail-loud)

- **The engram context pack could not be generated.** `engram pack` exits 1 with
  `not inside a registered repo; register it in /Users/bob/.config/gita/repos.csv` —
  engram itself is absent from `repos.csv` (26 repos, no engram row). Deterministic
  cause, confirmed by reading the file, so the one permitted retry was skipped as
  pointless. Every prompt received the sentinel `(no pack available this cycle)`.
  The review is degraded by the missing retrieval context, not invalid. This is
  also finding **T12** below, raised independently by four reviewers.
- **`gather-context.sh` produced an EMPTY diff** (0 bytes): its merge-base range
  resolved to nothing on this `master`-only repo. Detected before dispatch and
  regenerated over the correct `work_start_sha..HEAD` range (44,234 bytes, 7 files).
  A review of an empty diff would have been worthless; no reviewer ever saw one.
- **Consolidation was script-run, then merged model-side.** `consolidate-findings.sh`
  succeeded but its matcher is exact string equality on file+description, so it
  scored all 69 raw lines `[1/5]` despite heavy agreement (five reviewers described
  the same gate defect in five different sentences). Reporting that would have
  misrepresented consensus and misrouted the decision gate. The themes below are
  merged model-side; consensus counts are distinct-reviewer counts per theme.

## Consolidated Findings

Five active reviewers. Consensus is `[n/5]`.

### Full / near-full consensus

| Consensus | Sev | Theme | Issue | File |
|-----------|-----|-------|-------|------|
| [5/5] | 🔴 | T1 | The harness gate encodes only a GLOBAL `hit_rate >= 0.80` plus beats-baseline; it computes `per_corpus_hit_rate` but never gates on it, so it prints `gate_passed True` on a run that fails both PRD per-class thresholds, and `eval/harness.py` exits 0 | src/engram/harness.py:249-252 |
| [5/5] | 🔴 | T4 | Task 2 is unshipped and unattended-blocked: ferry `d4eb2d2` is unreleased (latest tag `v0.2.2`, both catchup entries still under `[Unreleased]`), `~/.claude/warden.yaml` has no `engram` rule, and no full catchup run was ever executed — so Phase 2's exit criterion and the "zero manual steps" metric are unproven and currently unreachable | claude-git-ferry/skills/catchup/SKILL.md |
| [4/5] | 🔴 | T2 | Both PRD per-class metrics miss: transcripts 0.750 (3/4), code 0.600 (3/5) vs >=0.80. Phase 1's exit criterion ("Both success-metric retrieval thresholds met at the harness") is not satisfied | dev/local/reviews/00002-goldgate-results.md |
| [4/5] | 🔴 | T3 | `run_harness` calls `_write_pinned` unconditionally, repointing the production `config.toml` even when `gate_passed` is False — a failed eval mutates live config against an index built with a different model (this is what broke every engram query after run 1). Carl frames it wider: the eval mutates live production state (`engram.db` and `config.toml`) instead of an isolated test DB | src/engram/harness.py:253 |
| [4/5] | 🟡 | T12 | `engram` is not registered in `~/.config/gita/repos.csv`, so engram's own source never enters the "have I built X" corpus it builds (and `engram pack` cannot run inside its own repo — see Process notes) | N/A |

### Majority / minority

| Consensus | Sev | Theme | Issue | File |
|-----------|-----|-------|-------|------|
| [3/5] | 🟠 | T10 | Gold-set class sizes make the gated metrics unmeasurable: 4 transcript entries (0.25 steps, so >=0.80 demands a perfect 4/4) and 5 code entries (0.20 steps). One entry flips a class either way — neither pass nor fail is a measurement | eval/goldset.yaml |
| [3/5] | 🟡 | T8 | The code corpus ingests build output, vendored third-party code and cellar session artifacts, all competing in RRF for the failing `code` metric. Quantified independently: 3,476/41,716 chunks (8.3%) from four `claude-warden/dist/*.cjs` bundles plus ~734 from `vendor/*.min.js` (Alice); 1,651 (~4%) from `.claude/` artifacts (Eve); no language allowlist, so `.txt`→vimdoc and `.md`→markdown pull in session dumps (Blake) | src/engram/symbols.py |
| [3/5] | 🟡 | T13 | `_pid_to_release` is a one-line single-caller dict lookup behind an 8-line docstring; inline into `stop_served` | src/engram/client.py:461 |
| [2/5] | 🔴 | T6 | Error-bearing tool_result turns are KEPT but chunked with an EMPTY body — `_extract_text` reads only `type=="text"` blocks, so the traceback/ERROR/exit-code text that qualified the turn is never embedded. 809 such rows live in the deployed index; they embed as the literal string "user turn". The PRD's error-recall class is structurally unretrievable, and `tests/test_transcripts.py:90` pins this as intended | src/engram/transcripts.py |
| [2/5] | 🟠 | T7 | Code chunks embed the whole symbol body and never the file path; the PRD specifies "signature + docstring + file path embedded" | src/engram/symbols.py |
| [2/5] | 🟠 | T9 | `transcripts.enumerate` globs one level, silently excluding every `*/subagents/*.jsonl` — 1,153-1,200 of ~1,830 cellar files. Even with a recursive glob those turns carry `isSidechain: true` and are filtered out. Only ~630 of the PRD's stated "~1,700 transcripts" are indexed | src/engram/transcripts.py |
| [2/5] | 🟠 | T18 | The catchup topic (branch name + PRD title) is interpolated into a double-quoted shell argument with no escaping; `"`, backticks or `$(` in repo-controlled text become command injection | claude-git-ferry/skills/catchup/SKILL.md:52 |
| [2/5] | 🟡 | T14 | `run_harness`'s `finally` stops a lease only `if lease.entry.id != winner_id`, so success deliberately leaks the winner's llama-server (manual kill was needed before run 2) and a crash after winner selection leaks it too | src/engram/harness.py:255-258 |
| [2/5] | 🟡 | T19 | The PRD requires the error-pattern list to live in config and be tuned against the harness; the deployed `config.toml` has no `[transcripts]` section, so hardcoded `DEFAULT_ERROR_PATTERNS` is what actually runs and no tuning pass was done | N/A |
| [2/5] | 🟡 | T20 | Config-supplied `error_patterns` bypass `load_config` validation and go straight to `re.search` with no compile check; an invalid regex aborts the index with a raw `re.error` | src/engram/transcripts.py |
| [2/5] | 🟡 | T21 | The capsule prints RRF scores (sums of `1/(60+rank)`) clustering 0.0164→0.0154; they read as confidence but only re-encode rank, so "scored hits" misleads a human reader | src/engram/query.py |
| [2/5] | 🟡 | T26 | The symlink fix is a spot fix: only `_enumerate_memory_corpora` resolves; prd/decision/discovery/transcripts/code still yield unresolved paths, so the identical silent 0/N class score returns the day a root becomes a symlink. Eve verified no root is symlinked today | src/engram/corpora.py |
| [2/5] | 🟡 | T27 | The catchup skill contradicts itself — the header says "skip on failure, note the gap", the template says "omit the section entirely" — and it drops the whole section when there is no topic (master with no single wip PRD, the common case), so an unattended warden denial degrades silently | claude-git-ferry/skills/catchup/SKILL.md |
| [2/5] | 🟡 | T29 | The rg baseline breaks equal-score ties alphabetically by path, so its rate moved 0.205 → 0.068 on a path-spelling-only change. Weak comparator | src/engram/harness.py:191 |
| [2/5] | 🟡 | T23 | Size ceilings: `tests/test_harness.py` 1151 lines and `tests/test_client.py` 1276 (limit 800; this diff added 316 and 57 to files already over); `transcripts.chunk` (51) and `indexer.index` (53) exceed the 50-line limit. The three new batching tests are 74-104 lines each with duplicated setup | tests/test_harness.py |
| [2/5] | ⚪ | T31 | Two claims in the build's own results write-up are wrong and will mislead follow-up: the `finally` crash path DOES stop every lease when `winner_id is None`, and `store.prune` would have removed the stale unresolved-path memory rows on the next index (live DB confirmed: 0 rows under `/Users/bob/.claude/%`) | dev/local/reviews/00002-goldgate-results.md |
| [1/5] | 🔴 | T5 | The gold gate measures a CONTAMINATED corpus: cellar transcripts include this PRD's own build and review sessions, which quote the gold queries verbatim. All 9 gated entries have 1-4 engram-session transcript turns in their top-5; for the "recurring reminder job" seed the entire top-8 is transcripts, rank 1 being the Pat-review prompt that lists the seed queries. The per-class numbers cannot be trusted in either direction | src/engram/harness.py |
| [1/5] | 🟠 | T15 | Fail-open destructive path: when `git ls-files` fails for a repo, `symbols.enumerate` records the miss and continues, so none of that repo's files reach `active_sources` and `store.prune` deletes every one of its code chunks in the same run. A transient failure (unmounted disk, moved checkout) silently wipes thousands of embedded rows | src/engram/indexer.py |
| [1/5] | 🟠 | T16 | Unguarded parse/read paths abort the whole index run: `symbols.chunk` calls `process(...)` with no exception guard, `transcripts.chunk` uses strict-UTF-8 `read_text()`, and `_run_index` catches only `StoreModelMismatchError`/`FileNotFoundError`. One bad file kills the run with a traceback | src/engram/symbols.py |
| [1/5] | 🟠 | T17 | The PRD's Test Strategy error case is not implemented: `engram status` never calls `transcripts.enumerate()`, so a missing cellar path reports nothing and exits 0 — the exact silent-empty-corpus outcome the PRD forbids. The test claiming to cover it stubs `engram.cli.enumerate_corpora` to raise, a producer that cannot raise for a missing cellar: false coverage | src/engram/cli.py |
| [1/5] | 🟠 | T11 | Portfolio-scope retrieval is drowned by transcripts — exactly the capsule leg the PRD ships. Verified live: "have I built a retry with exponential backoff" returns 5/5 transcript turns and zero code | src/engram/query.py |
| [1/5] | 🟡 | T22 | Three `style: apply formatter reflow` commits rewrap unrelated lines at a narrower width than the rest of the repo, which has no formatter config — scope creep against the surgical-changes rule, leaving two conventions in the tree | src/engram/harness.py |
| [1/5] | 🟡 | T24 | `engram index --rebuild` replaces the live DB via `os.replace` with no backup; if `_preserve_findings` misses rows the previous index is unrecoverable | src/engram/cli.py |
| [1/5] | 🟡 | T25 | Files that chunk to zero are never added to `active_sources`, so they are re-read and re-parsed every run — 8,576 of 12,635 files on an "unchanged" reindex, 14.5s of pure waste (the 60s bound still holds) | src/engram/indexer.py |
| [1/5] | 🟡 | T28 | Catchup runs a portfolio query but a repo-default `engram status`, so the staleness stamp cannot report portfolio freshness | claude-git-ferry/skills/catchup/SKILL.md:57 |
| [1/5] | 🟡 | T30 | `format_report` prints only at the very end, so a late failure discards a ~40-minute run (exactly what run 1's ARG_MAX crash did) | eval/harness.py |
| [1/5] | 🟡 | T32 | Phase 0's acceptance "engram status shows transcripts corpus fresh" is unattainable by construction: cellar JSONL is appended live, so status reports `stale=1` whenever any session runs. The catchup staleness stamp is therefore permanently nonzero | src/engram/store.py |
| [1/5] | 🟡 | T33 | "Install engram on PATH" leaves no repeatable record — no README or install doc, and `uv tool install .` froze a non-editable snapshot the released skill will call with no reinstall or version story | pyproject.toml |
| [1/5] | 🟡 | T34 | `_walk` emits every nested symbol as its own chunk while the parent chunk's body already contains it, so a class and each of its methods are embedded twice (2,306 class + 1,663 method chunks live) | src/engram/symbols.py |
| [1/5] | ⚪ | T35 | Misc: export signatures deviate from the PRD (`enumerate()` returns `Iterator[CorpusFile]`, `chunk()` needs 3-4 args, both shadow the `enumerate` builtin); enumerator output carries no content hash; `count_skipped()` ignores scope and re-runs `git ls-files` across 26 repos per status call; `_load_error_patterns` TOML-parses config once per transcript file (630 parses/run); `zip(chunks, vectors)` without `strict=True`; CHANGELOG overstates what shipped; `goldset.yaml` hardcodes `/Users/bob/...` absolute paths; `_has_error_match` skips list-shaped tool_result content (3 of 40 error results lost) | various |

### Advisory (local model, unconfirmed)

- (none — Quinn was unavailable this cycle)

## Alice

Implementation-aware consensus lens. 21 findings; ran the suite and independently reproduced the gate against the live index. Raw output: `dev/local/tmp/alice-output-00002-c1.txt`.

Her distinctive contribution is **T5** (corpus contamination), which no other reviewer caught and which undercuts the measurement in both directions, and the quantified **T8** correction: the write-up blames cellar `projects-archive` payloads (41 chunks, 0.1%) when the real bulk is `claude-warden/dist/*.cjs` (3,476 chunks, 8.3%).

Verification she actually ran: `uv run pytest -q` → 401 passed, 0 skipped, 0 xfail, 28.6s. Portfolio enumeration plus hashing of 12,635 files measured 2.4s warm, which makes the reported 14s incremental reindex credible — **that PRD metric holds**. Live-index reproduction of the gate: transcripts 3/4, code 3/5, matching harness run 2 exactly.

```
R1: fail
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
```

## Blake

Blind lens — PRD only, no diff, no file list, no implementation context; found the code himself. 31 findings, the largest yield of any reviewer, and the only one to reach **T6** (809 error-turn rows with empty bodies), **T15** (fail-open prune), **T16** (unguarded parse aborts the run) and **T17** (status never enumerates transcripts + the false-coverage test). Raw output: `dev/local/tmp/blake-output-00002-c1.txt`.

Blake's spec-compliance verdict is severe because he judged the PRD's full surface, not this diff: `transcripts.py` and `symbols.py` behaviour diverges from the spec in several named ways, and both Phase 1 and Phase 2 exit criteria are unmet.

```
B1: fail
B2: fail
B3: fail
B4: fail
B5: fail
B6: fail
B7: fail
B8: pass
B9: pass
B10: fail
B11: pass
B12: fail
B13: pass
B14: fail
B15: fail
B16: fail
B17: fail
B18: pass
B19: pass
```

## Bob

Codex; doubt + de-slop lens, static analysis only (sandboxed, no execution). 11 findings, each pre-bucketed FIX/VERIFY/KNOWN. Raw output: `dev/local/tmp/bob-output-00002-c1.txt`. Thread `019fca1d-0a29-7143-9d07-f2e35034f9e3` (cycle 2 resumes it).

Bob is the only reviewer to raise **T18** (shell injection through the catchup topic) and **T28** (repo-scoped status behind a portfolio query). He correctly declined to assert runtime facts, emitting a VERIFY line for the parts needing execution.

```
R1: fail
R2: fail
R3: pass
R4: fail
R6: pass
R7: fail
R8: fail
R9: fail
R10: pass
R11: pass
R12: fail
R13: fail
```

```
D1: pass
D2: pass
D3: pass
D4: pass
D5: pass
```

## Carl

Gemini via copilot; the panel's frontend/design specialist, reviewing as a generalist here since the change has no UI surface. 5 findings. Raw output: `dev/local/tmp/carl-output-00002-c1.txt`.

Carl's distinctive framing is the widest reading of **T3**: not just "`_write_pinned` fires on a failed gate" but "the eval harness mutates live production state (`engram.db` and `config.toml`) instead of using an isolated test database". He also raised the presentation finding **T21** (near-flat scores shown as confidence).

```
R1: pass
R2: fail
R3: pass
R4: fail
R6: pass
R7: pass
R8: pass
R9: fail
R10: pass
R11: pass
R12: pass
R13: pass
```

## Eve

Fable 5, doubt lens — added by the codex doubt-roster guard because task 1 was implemented by codex. 20 findings in 13 FIX / 2 VERIFY / 5 KNOWN. Raw output: `dev/local/tmp/eve-output-00002-c1.txt`.

Eve's distinctive contribution is **auditing the build's own self-report and correcting two of its claims** (T31), both verified against the code and the live DB:

- "the `finally` reaps nothing on a crash" is **wrong** — with `winner_id = None`, `lease.entry.id != winner_id` holds for every lease, so a pre-winner crash stops everything. The real leaks are the winner on success (pinned by `tests/test_harness.py:585`) and the winner after a post-selection crash.
- "a plain reindex would double-count the 192 stale memory rows" is **wrong** — `store.prune` is a set-difference on `(repo, path, hash)`, so those rows are pruned on the next index of their scope. Live DB confirmed 0 rows under `/Users/bob/.claude/%`.

She also names two tests that pin implementation against intent: `tests/test_harness.py:546` pins the unconditional `_write_pinned` (the behaviour that broke production), and `tests/test_transcripts.py:90` pins that an error-bearing tool_result is kept "with empty body".

Her verdict on the range itself is worth quoting: the eight commits are "honest, competent bug-fixing … What the range does not do is discharge the PRD, and one line it prints actively obscures that."

```
D1: pass
D2: pass
D3: pass
D4: pass
D5: pass
```

## Follow-up Tasks Created

9 tasks, grouped by theme (the finding→task mapping is explicit so grouping cannot hide a finding). Themes routed to rework are those fixable **without a full reindex** — anything that changes what gets embedded would leave the live index inconsistent mid-cycle and is deferred instead.

1. `[D1] Gate the harness on the PRD's per-class thresholds and stop pinning on a failed gate` (M) — 🔴 [5/5]+[4/5] — addresses T1, T3
2. `[D1] Stop one bad file or one failed repo from aborting or silently pruning an index run` (M) — 🟠 — addresses T16, T15
3. `[D1] Make engram status enumerate transcripts and replace the false-coverage test` (S) — 🟠 — addresses T17
4. `[D1] Harden the catchup skill: shell-safe topic, portfolio-scoped status, no silent section drop` (S) — 🟠 — addresses T18, T28, T27
5. `[D1] Stop every llama-server lease in run_harness, including the winner` (S) — 🟡 — addresses T14
6. `[D1] Make the rg baseline tie-break path-independent and pin rename invariance` (S) — 🟡 — addresses T29
7. `[D1] Stream per-model score lines instead of printing only at the end` (S) — 🟡 — addresses T30
8. `[D1] Inline _pid_to_release into stop_served` (S) — 🟡 — addresses T13
9. `[D1] Move error_patterns into config.toml and validate the regexes at the boundary` (S) — 🟡 — addresses T19, T20

## Deferred to batch end

Criticals defer by rule (`decision-framework.md`: "Critical severity, always"), except where the fix is additive-only and bounded — T1 and T3 met that carve-out and went to rework. The rest defer with reasons:

- **T2** 🔴 — Phase 1's metrics are unmet. Closing them is retrieval-quality iteration, not a review-time patch, and the gold-set queries must not be tuned to pass. The PRD stays open.
- **T4** 🔴 — needs a **user action**: `/warden:allow engram`. An agent must not self-grant through the security gate (the build agent correctly tried and was denied). The ferry release is blocked behind it.
- **T5** 🔴 — corpus contamination is a design decision (how should the harness exclude engram's own sessions?), and it invalidates the current numbers in both directions.
- **T6** 🔴, **T7** 🟠, **T8** 🟡, **T9** 🟠, **T12** 🟡 — all change what gets embedded and require a full reindex plus a re-gate (~40+ min) to take effect.
- **T10** 🟠, **T11** 🟠 — gold-set curation and a portfolio-scoping design decision.
- **T21**, **T22**, **T23**, **T24**, **T25**, **T26**, **T31**, **T32**, **T33**, **T34**, **T35** — quality and hygiene items below the rework cut.

### Two data-loss-flavoured findings, deliberately NOT treated as a batch halt

`decision-framework.md` sanctions a PAUSE for "detected data-loss risk". T15 (prune wipes a repo's code chunks on a transient `git ls-files` failure) and T24 (`--rebuild` replaces the live DB with no backup) both touch deletion, and both were weighed against that rule. Judgement: the engram DB is **derived** data — losing rows costs re-embedding time, not user content — so neither is the "detected data-loss risk" the halt rule protects against. T15 is routed into rework task 2; T24 defers. Recorded here rather than resolved silently.

Verdict: 33 findings
Tests: 401 passed, 0 failed, 0 skipped
