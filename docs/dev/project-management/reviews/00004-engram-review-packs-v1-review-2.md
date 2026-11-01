---
prd: dev/local/prds/wip/00004-engram-review-packs-v1.md
review: 2
date: 2026-08-03
head_sha: 38f1f4ef4164490dcb87712f5f450a15b8e58010
codex_thread_id: 019fc774-96cd-7460-9352-ea7d4fbba63b
reviewers: alice,blake,bob,carl,eve
agents:
  alice: available
  blake: available
  bob: available
  carl: available
  quinn: unavailable
  eve: available
---

# Review: 00004-engram-review-packs-v1

Diff range: `4faab3b31307f60192e451c76c7570424f07ce48..38f1f4ef4164490dcb87712f5f450a15b8e58010` (engram, tasks 10-15 and 17-19)
Diff range: `6cae52b7f^..40afd5a2e` (buvis bare repo, `~/.claude` tree, task 16)

codex_rung_guard: fired (2 codex-implemented task(s))

## Review Summary

Reviewed: 19 completed tasks (incremental scope: the ten `[D1]` rework tasks 10-19)
PRDs checked: 00004-engram-review-packs-v1

This is an **incremental** cycle. Cycle 1 reviewed the full implementation and
produced 35 findings; the top 10 became rework tasks 10-19, and that rework is
this cycle's diff. Bob resumed his cycle-1 codex thread
(`019fc774-96cd-7460-9352-ea7d4fbba63b`), so his verification is continuous with
his own prior critique rather than a fresh read.

### Agent Status

- Alice (Claude, consensus): ✅ Available — 6 findings
- Blake (Claude, blind/PRD-only): ✅ Available — 25 findings
- Bob (codex, consensus + doubt): ✅ Available — 7 findings, D1-D5 all pass, thread resumed
- Carl (gemini/copilot, UI+generalist): ✅ Available — 2 findings
- Eve (Fable 5, doubt): ✅ Available — 9 FIX, 1 VERIFY, 5 KNOWN, D1-D5 all pass
- Quinn (local qwen, advisory): ⚠️ Unavailable: the `qwen-run.sh --preflight --approved-only` probe PASSED at step 1 (`provider 'llamacpp8001', model 'unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q6_K_XL'`), but by dispatch time the backend was gone — both the initial run and the one permitted retry exited 1 with `preflight failed (endpoint_unreachable): no llama-server responding on any provider in /Users/bob/.pi/agent/models.json`. Advisory weight only, so no consensus finding and no follow-up task is lost. Note this is a **different** failure from cycle 1, where the backend was healthy and `pi` probed the wrong port.

Tests: 657 passed, 0 failed, 0 skipped

Test breakdown — **run live in the foreground by the orchestrator this cycle**, not taken on a reviewer's word, zero skips:
- `uv run --project <engram> pytest <engram>/tests -q` → **387 passed**
- `uv run --project <engram> pytest ~/.claude/skills/review-work-completion/scripts/ -q` → **185 passed**
- `node --test ~/.claude/workflows/*.test.mjs` → **85 passed**

⚠️ Two reporting discrepancies worth recording rather than smoothing over:
1. Alice, Blake and Eve each independently reported **384** engram tests earlier in this same cycle; my own run minutes later, with no intervening commit, collected **387**. I have not explained the delta. 387 is the measured number and all three suites are green either way, but do not treat 384/387 as an audited figure.
2. Alice reported "17 node workflow tests (7 args + 10 registry-parity)" — that is **wrong**; she ran a subset. Eve's 85 matches my run. Alice's other counts matched mine.

There is no lint gate in this repo: `pyproject.toml` declares only
`[tool.hatch.build.targets.wheel]`. `pytest` is not on the mise `python3` and
`engram` is not on PATH, so the `uv run --project` form is mandatory.

### Cycle degradations (fail loud)

1. **No engram context pack this cycle — for the second cycle running.**
   `engram pack --cycle 00004-c2` exits 1 with `not inside a registered repo;
   register it in /Users/bob/.config/gita/repos.csv`, on both the initial run and
   the retry. `{PACK_FILE}` and `{PACK_FINDINGS}` took the literal
   `(no pack available this cycle)` sentinel in every prompt that carries them,
   and cycle 1's ten findings were passed as the findings-precedent substitute.
   **Task 13 fixed the error message only** — it no longer advises the
   nonexistent `--scope portfolio` flag, which is a genuine, verified
   improvement — but the root cause is untouched and the feature under review
   still cannot be dogfooded on its own review cycle. Registering the repo was
   deferred to the user at cycle 1 and was deliberately not done autonomously
   here either.
2. **Consolidation was model-side, on top of the script's output.**
   `consolidate-findings.sh` **ran successfully this cycle** (exit 0) — cycle 1's
   `unbound variable` crash did not recur. But its output was unusable as-is on
   two counts, so it was regrouped by hand:
   - It scored **every** finding `[1/5]`, including the four independent reports
     that `pack.build` is still 54 lines. Its normalisation matches on
     file+description and these reviewers worded the same defect differently.
   - It parsed **zero** findings from Eve. Her persona contract emits
     FIX/VERIFY/KNOWN prose, not `[EVE] {emoji} … | File: … | Task: …` lines, and
     the script silently drops everything that is not an issue line. Her entire
     lens would have vanished from the table.
   The consolidated table below is therefore grouped model-side by same-issue,
   with consensus = the count of distinct reviewers that raised it. This is a
   hand-rolled consolidation and must not be read as the script's.
3. **Carl could not read `/Users/bob/.claude`** again (`Permission denied` on
   both the scripts directory and the test suite there), so he reviewed the
   engram diff plus the staged buvis diff file and ran only the engram suite.
   He also left four scratch files (`count_lines.py`, `get_test_count.py`,
   `added_tests.txt`, `deleted_tests.txt`) plus a `.coverage` artifact in the
   repo root; these were deleted after his run.
4. **The first Watcher returned `WAITING` after its full 30-run budget (~52 min)
   with all three CLI reviewers pending.** This was *not* a stall: Quinn had
   already died without writing a file (so his path could never go `done`), and
   Bob and Carl finished shortly afterwards. A second Watcher scoped to Bob and
   Carl returned `DONE` in 4 runs. Recorded because a `WAITING` return is
   documented as grounds to mark a reviewer failed, and doing so here would have
   discarded two complete reviews. **Including a path that may never be written
   in the Watcher's argument list poisons the whole batch's readiness signal.**

## Verification of the ten cycle-1 rework tasks

The point of this cycle. Verdicts are the consolidated position across reviewers.

| Task | Cycle-1 finding | Verdict |
|------|-----------------|---------|
| 10 | `diff_path`/`out_dir` resolved against the invocation cwd | **Closed for the CLI path, residual on `build()`** — the CLI now passes an explicitly rooted directory, but `build()`'s own default `out_dir=Path("dev/local/tmp")` is still cwd-relative (finding 3) |
| 11 | Memory retrieval keyed on the cycle id, not the PRD title | **Half closed** — the key is fixed and pinned, but the finding's "no test seeded the memory corpus" clause is still open (finding 7), and two new residuals appeared (findings 4, 12) |
| 12 | Missing staged diff not handled loudly before the reindex | **Closed**, with a TOCTOU window left behind (finding 16) |
| 13 | Unregistered-repo error naming a flag the verb lacks | **Closed** — verified live this cycle; the error no longer mentions `--scope portfolio`. Root cause remains (degradation 1) |
| 14 | Four functions over the 50-line limit | **Not closed** — `pack.build` is still 54 lines (finding 1). The other three are now under |
| 15 | Two test files over the 800-line limit | **Not closed** — the split produced `test_cli_pack.py` at 851 lines, and `test_diffmap.py` crossed the limit in the same cycle (finding 2) |
| 16 | `{PACK_FINDINGS}` unsubstituted on Eve's dispatch path | **Not closed** — Eve received the literal token again this cycle (finding 5) |
| 17 | `--cycle` traversal + git option injection | **Closed on both named halves**, verified by Alice against the tests; two residuals remain (findings 15, 21) |
| 18 | Unreadable PRD/capsule swallowed silently | **Closed**, with a budget interaction left behind (finding 13) |
| 19 | One file-level symbol per added line | **Closed** — Alice and Eve both confirm one symbol per file, pinned by test |

**8 of 10 substantially closed; tasks 14, 15 and 16 did not meet their own bar.**
Independent test-loss audits by Alice (AST comparison of every test function name
and body across the range: 340 → 367, zero lost) and Eve (all 74 pre-split names
survive, 93 now) agree the task-15 split lost no coverage.

## Consolidated Findings

21 distinct findings after model-side grouping. Consensus is out of 5 reviewers
(Quinn excluded — he produced no output).

### Full / near-full consensus

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [4/5] | 🟡 | **Task 14 did not close its own finding.** `pack.build` is still 54 lines against the 50-line limit the task existed to enforce. The overrun is pure formatter reflow — three call sites each span 8-10 lines for 5-8 arguments; collapsing them to single lines fits in 88 columns and lands the function near 35. `cli._run_pack`, `diffmap.changed_symbols` and `client.load_config` ARE now under the limit. | src/engram/pack.py:456-509 | 14 | Alice, Bob, Carl, Eve |
| [4/5] | 🟡 | **Task 15 recreated its own violation.** The split produced `tests/test_cli_pack.py` at 851 lines (over 800), and `tests/test_diffmap.py` grew 596 → 822 in the same cycle from task 19's tests plus reflow, newly crossing the limit. Both split cleanly on existing section banners. | tests/test_cli_pack.py; tests/test_diffmap.py | 15 | Alice, Bob, Carl, Eve |

### Majority consensus

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [3/5] | 🟠 | **Task 10 left the exact anchor its [5/5] finding named.** `build()`'s default `out_dir=Path("dev/local/tmp")` is still cwd-relative. It is unused by the CLI (which passes a rooted directory), and the `is_absolute()` guard in `_publish_pack` exists only to rescue it. The new test only verifies the CLI's behaviour, not `build()`'s default. Fix: make `out_dir` required — every caller and test already passes it — and delete the guard. | src/engram/pack.py:465-466, 400-401 | 10 | Bob, Eve, Blake |
| [3/5] | 🟡 | **Dead parameter chain left by task 11's fix.** `id_` is threaded `build` → `_build_pack_sections` (:353, forwarded at :381) → `_task_prose_entries` (:167) but is never read there; `_prd_query_text(prd_text, prd_path)` replaced it. Drop it from both signatures (`build` still needs it for `_publish_pack`) and update the three positional callers in `test_pack_regressions.py:509,533,555`. | src/engram/pack.py:167,353 | 11 | Alice, Bob, Eve |

### Minority

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [2/5] | 🟠 | **Task 16 is not closed, with live proof for the second cycle running.** The literal `{PACK_FINDINGS}` token still ships in Eve's native-dispatch system prompt — she received it verbatim again this cycle. Nothing can substitute into `agents/eve.md` when the harness uses it as a Task-subagent system prompt; `agent-invocation.md:79` papers over this by claiming the fourth appended input "fills the `{PACK_FINDINGS}` placeholder in her persona body", which is false, and `eve.md:14-17` still lists only three appended inputs. The commit changed the documentation, not the mechanism. Fix: reword `eve.md:24` to reference the appended Findings-precedent input generically, add the fourth input to eve.md's input list, correct the false sentence, and **test the assembled prompt rather than the documentation text**. | ~/.claude/agents/eve.md:24; ~/.claude/skills/review-work-completion/references/agent-invocation.md:79 | 16 | Bob, Eve |
| [2/5] | 🟠 | **Root cause of cycle-1's C1 is still open.** engram is absent from `/Users/bob/.config/gita/repos.csv` (verified independently by both reviewers), so `engram pack` cannot run in its own repo. Two consecutive review cycles have now run with no pack. One-line fix, but deliberately left to the user. | /Users/bob/.config/gita/repos.csv | 13 | Blake, Eve |
| [2/5] | 🟡 | **Task 11's test clause remains open.** No test anywhere seeds a memory-corpus chunk into a real store and asserts its body reaches Task prose. All three new tests monkeypatch `engram.pack.query` to return `[]` and call the private `_task_prose_entries` directly, so `include_body=True`, the `[:2]` cap and the `hit.body` guard are all unpinned — dropping `include_body` would silently empty memories with the suite green. Coverage confirms `pack.py:197-198` are the only never-executed lines on the Task-prose path. | tests/test_pack_regressions.py:491-557 | 11 | Alice, Eve |
| [2/5] | ⚪ | Stale fail-first docstring shipped with task 16's test: it still reads "Today the section still claims she receives only the same three appended inputs…", which described the pre-fix state and now reads as false. The assertion messages below it are correctly phrased. | ~/.claude/skills/review-work-completion/scripts/test_agent_registry.py:391-395 | 16 | Alice, Eve |
| [1/5] | 🟠 | **NEW — `engram pack` mutates and prunes the shared store on the review critical path.** `index()` calls `store.prune(scope, corpus, active_sources)`, and `symbols.enumerate` merely `continue`s past a repo whose `git ls-files` exits non-zero. One transient git failure during a pack build therefore deletes every non-findings chunk for that repo. No lock, no dry-run, no confirmation. See the severity note below — this is recorded as a robustness defect, not a batch-halting data-loss risk. | src/engram/indexer.py | P1-verb | Blake |
| [1/5] | 🟠 | Task 11 residual: memory retrieval still fires with a junk query when the PRD is unreadable or carries a blank `# ` heading — it falls back to the filename stem or an empty string rather than skipping the query. | src/engram/pack.py:132 | 11 | Bob |
| [1/5] | 🟠 | Task 18 residual: the omission disclosures it added are themselves uncapped, so with a valid small hard cap the all-sections-empty render can still exceed it and `_finalize_pack` exits its loop without satisfying its postcondition. Needs a small-cap, long-path regression test. | src/engram/pack.py:216 | 18 | Bob |
| [1/5] | 🟡 | **NEW — unguarded path traversal from diff content.** `_section_file_identity` strips `b/` and joins `repo_root / rel_path` with no containment check; `diffmap._read_content` and `pack._symbol_query_text` then `read_text()` that path. A crafted or corrupted staged diff (`+++ b/../../../etc/passwd`) makes engram read arbitrary files and POST their contents to the embedding endpoint. See the severity note below. | src/engram/diffmap.py | P0-diffmap | Blake |
| [1/5] | 🟡 | Task 17 residual on the derived-`source_ref` path: `--diff a..` (empty head) passes validation and `git diff a..` diffs to HEAD, but `source_ref=""` makes every `_symbol_query_text`/`_read_content` call run `git show :rel_path` — silently reading the **index**, not HEAD. Treat an empty head as `HEAD` or reject the range, plus a pinning test. | src/engram/cli.py:281-288 | 17 | Eve |
| [1/5] | 🟡 | Task 12 residual — check-then-act on the staged diff: `_resolve_pack_diff` calls `diff_path.exists()`, then `build()` runs the full reindex (minutes, real embedding traffic) before `changed_symbols` finally calls `read_text()`. A file removed in that window raises an uncaught `FileNotFoundError` instead of the loud, path-naming failure the PRD requires. | src/engram/cli.py | 12 | Blake |
| [1/5] | 🟡 | Hard-cap overflow trims the **largest** section (`_largest_section`), not "the offending section" the PRD names, so a section comfortably under its own cap can be gutted because another section's framing pushed the total over. | src/engram/pack.py | P1-budget | Blake |
| [1/5] | 🟡 | `_run_pack` catches only `StoreModelMismatchError`. Embedding spawn/network failures (`EmbeddingPreflightError`, `EmbeddingServerError`), `load_config`'s `ValueError` on a mistuned `[pack]` table, and `FileNotFoundError` all surface as raw tracebacks. `_run_index` catches `FileNotFoundError` explicitly; `_run_pack` does not. | src/engram/cli.py | P1-verb | Blake |
| [1/5] | ⚪ | The `--diff` id slug collides: `re.sub(r"[^A-Za-z0-9_-]", "-", …)` maps both `a..b` and `a--b` to `a--b`, so two different ranges overwrite one pack. The materialized `engram-pack-diff-{id}.diff` is also never cleaned up. | src/engram/cli.py | P1-verb | Blake |
| [1/5] | ⚪ | Phase 2 acceptance requires the `~/.claude` edits committed via buvis by explicit path, but `test_agent_registry.py` carries an uncommitted working-tree modification (formatter reflow) in the buvis bare repo. | ~/.claude/skills/review-work-completion/scripts/test_agent_registry.py | P2-templates | Blake |
| [1/5] | ⚪ | Task 17's `--` terminator in `pack._symbol_query_text` has zero coverage (pack.py:48-60 reports as missing); the twin change in `diffmap._read_content` IS covered. No test anywhere asserts `--` reaches any git argv. Low because the up-front dash rejection is the real fix and the CHANGELOG is honest that `--` is defence-in-depth. | src/engram/pack.py:50 | 17 | Alice |

### Criticals — both adjudicated, neither a defect of this rework

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [1/5] | 🔴 | The doubt lens receives the FULL pack, not findings-only. `bob.md:9` gives Bob `{PACK_FILE}`, and SKILL.md stamps `doubt` = Bob; the skill's own test re-labels Bob as consensus so the assertion passes. | ~/.claude/agents/bob.md | P2-lenses | Blake |
| [1/5] | 🔴 | Three of the pack's four sections are empty in the deployed store: `~/.local/share/engram/engram.db` holds only `memory`, `prd`, `discovery`, `transcripts` — zero `code` and zero `findings` rows. Similar code, Reuse precedent and Findings precedent all render empty, so Success Metric 1 (">=1 retrieved item absent from the diff") is unmeetable in production today. | ~/.local/share/engram/engram.db | general | Blake |

**Adjudication — why neither critical stalls this PRD.** Blake is blind by
construction and cannot know what the design gate accepted.

1. The **full-pack doubt lens** was accepted at the design gate with written
   reasoning (design doc, Interfaces "Claude lens wiring, precisely — and its one
   honest limitation", and Alternatives #6): Bob is ONE dispatch reading ONE
   assembled prompt, so `{PACK_FINDINGS}`'s placement signals emphasis and cannot
   make `{PACK_FILE}` invisible in the same call. Cycle 1 adjudicated this
   identically and deferred it; it is already in the batch deferred record. It is
   resolved-by-decision, not unresolved. **But note it is now worse than the gate
   assumed**: finding 5 shows Eve's dispatch — the one path where the guarantee is
   real — still never substitutes `{PACK_FINDINGS}` at all, for the second cycle.
2. The **empty store** is caused by PRD 00002's stalled code corpus, which this
   PRD declares as a dependency and whose blocker is recorded at
   `dev/local/reviews/00002-task2-null-embedding-blocker.md`. This design doc
   pre-declares the exact condition ("today's store holds **zero** code chunks
   portfolio-wide"). 00004's code is complete; its success metric cannot be
   *measured* until its declared upstream dependency lands. That is a delivery
   record, not a code defect.

**Severity calls I made that a reader should be able to overturn** (both are
judgement, not fact):

- The **store-pruning** finding was NOT treated as the "detected data-loss risk"
  that halts a batch. Reasoning: `engram.db` is a derived, rebuildable embedding
  index (`engram index --rebuild` reconstructs it), not user data; the mechanism
  (`indexer.index` + `store.prune`) predates this PRD, which only adds a new
  caller; and the code corpus it would delete is already empty. If you consider a
  wipe of the shared store unacceptable regardless, this is the finding to
  escalate.
- The **path-traversal** finding was NOT treated as a security-critical halt.
  Reasoning: the diff file is generated locally by `gather-context.sh` from a repo
  the user is already reviewing, the "exfiltration" target is a localhost
  llama-server, and engram is a personal CLI with no multi-tenant surface. It is a
  real bug worth a containment check; it is not a secret being exposed or a
  vulnerability shipping to third parties.

### Blake's re-raises of already-deferred cycle-1 findings

Recorded, not re-deferred — these are the same findings cycle 1 already logged,
independently reconfirmed by a blind reviewer: the unconfigurable PRD section
caps; the `gather-context.sh` fail-open sentinel; self-match exclusion resting on
uncanonicalized path equality; the repo-scope-only pre-pack reindex and its
hardcoded freshness string; Reuse-precedent starvation by post-truncation
filtering; Task-prose entries carrying no origin labels; the two export
signatures not matching the PRD; the BM25 half of every query being dead by
construction; the two PRD-named wiring files not existing; `MAX_SYMBOLS_PER_PACK`
and `RETRIEVAL_K` shipping as module constants; `--prd`/`--capsule` as CLI flags
beyond the spec; `_render_pointer`'s broken markdown indentation; and the
unvalidated `pack_path` sentinel in the fanout workflow.

**No rework commit in this cycle regressed any deferred finding** — Alice checked
this explicitly. Task 16 partially *improves* the deferred 🔴 by closing the half
Blake named at cycle 1, even though it did not close its own.

### Advisory (local model, unconfirmed)

- (none — Quinn was unavailable; see Agent Status)

## Alice

6 findings, listed in the consolidated tables above. She ran all three suites and
performed the AST-level test-loss audit for task 15 (340 → 367 tests, zero lost,
9 bodies changed, all expected from task 10's re-anchoring). She confirmed task
17's injection hole is closed on both the whole-range and derived-`source_ref`
paths, with two tests asserting `diff_calls == []`. Full raw output:
`dev/local/tmp/alice-output-00004-c2.txt`.

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
R12: fail
R13: fail

## Blake

25 findings including both of the cycle's 🔴, listed above. Blind lens: PRD +
rubric only, no diff, no context file, no design doc, no pack. He located the
code in both repos himself and ran the engram and registry suites. He scored B17
`pass` as vacuously satisfied, noting the PRD has no Phase 3 — and said so rather
than silently failing it. Full raw output:
`dev/local/tmp/blake-output-00004-c2.txt`.

B1: fail
B2: fail
B3: fail
B4: fail
B5: fail
B6: fail
B7: fail
B8: pass
B9: pass
B10: pass
B11: pass
B12: fail
B13: pass
B14: fail
B15: fail
B16: fail
B17: pass
B18: pass
B19: pass

## Bob

7 findings plus FIX/VERIFY/KNOWN buckets, listed above. Resumed his cycle-1 codex
session, so his verification of the ten fixes is continuous with his own prior
critique. Static analysis only (sandbox); he correctly emitted `Cannot statically
verify` for test execution rather than guessing. Full raw output:
`dev/local/tmp/bob-output-00004-c2.txt`.

R1: fail
R2: fail
R3: pass
R4: fail
R6: pass
R7: pass
R8: pass
R9: fail
R10: pass
R11: fail
R12: fail
R13: fail

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Carl

2 findings, listed above. Could not read `/Users/bob/.claude` (permission denied)
and so could not run the review-skill suite; he reviewed the engram diff plus the
staged buvis diff file and ran the engram suite. No frontend surface in this
change — he reviewed as a generalist, correctly declining to invent UI findings.
His two findings are the same two the full panel converged on. Full raw output:
`dev/local/tmp/carl-output-00004-c2.txt`.

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
R12: fail
R13: fail

## Quinn

⚠️ Unavailable. The step-1 preflight passed cleanly on provider `llamacpp8001`,
but by dispatch time no llama-server was responding on any provider in
`~/.pi/agent/models.json`; the one permitted retry failed identically. Advisory
weight only, so no follow-up task is lost. Distinct from cycle 1's failure mode
(healthy backend, `pi` probing the wrong port) — this time the backend genuinely
went away between preflight and dispatch, which means **the preflight's freshness
is not a guarantee at dispatch time**.

## Eve

9 FIX, 1 VERIFY, 5 KNOWN. She verified all three suites live, audited the task-15
split for name-level test loss (all 74 pre-split names survive, 93 now), and
produced the cycle's sharpest finding by observing her **own** system prompt:
task 16 is not closed because the literal `{PACK_FINDINGS}` token reached her
again. She correctly bucketed the foreign `client.py` commit and the four
already-deferred cycle-1 findings as KNOWN rather than re-raising them. Full raw
output: `dev/local/tmp/eve-output-00004-c2.txt`.

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Cycle outcome

`state.cycle` (2) has reached `state.rework_cap` (2) and the review did not
converge, so **no third rework cycle is dispatched**. Running unattended, the
cap-out defers rather than pauses: every unresolved finding above is appended to
the batch deferred record as `cap-overflow` and the PRD proceeds to the finalize
hand-off as converged-with-deferrals.

Neither 🔴 is an unresolved defect of this work (see Adjudication), so the
`cap_critical` stall does not apply. The two severity calls behind that judgement
are stated explicitly above so they can be overturned at batch-end review.

Verdict: 21 findings
