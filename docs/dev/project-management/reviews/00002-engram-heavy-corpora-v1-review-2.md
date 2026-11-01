---
prd: dev/local/prds/wip/00002-engram-heavy-corpora-v1.md
review: 2
date: 2026-08-04
head_sha: efc4d2fc3bb3311ac6dcca2e1d4717ebfada7d54
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

Diff range: `997944db1da140759d1e6b95ae588de62d8e7880..efc4d2fc3bb3311ac6dcca2e1d4717ebfada7d54`
Incremental review of the cycle-1 rework: 19 commits, 12 files, +1143/-39.
Second repo: `claude-git-ferry` `2131a62` (task 6's entire implementation; not in the range above).

codex_rung_guard: fired (1 codex-implemented task(s))

## Review Summary

Reviewed: 11 completed tasks (2 original-plan + 9 `[D1]` rework)
PRDs checked: 00002-engram-heavy-corpora-v1

### Agent Status

- Alice: ✅ Available (consensus lens; ran the suite and reproduced findings live)
- Blake: ✅ Available (blind lens, PRD-only; found the code himself, queried the live DB)
- Bob: ✅ Available (codex; doubt + de-slop lens; **resumed** cycle-1 thread `019fca1d-0a29-7143-9d07-f2e35034f9e3`)
- Carl: ✅ Available (gemini via copilot)
- Eve: ✅ Available (Fable 5, doubt lens — added by the codex doubt-roster guard)
- Quinn: ⚠️ Unavailable: local qwen backend unreachable, **identical failure to cycle 1**. `qwen-run.sh --preflight --approved-only` PASSED (provider `llamacpp8001`, model `unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q6_K_XL`, real 1-token completion), but the dispatch wrote only `[llama-cpp] failed to reach http://localhost:8080/v1/models: fetch failed`. Root cause confirmed this cycle by direct probe: `lsof` shows llama-server listening on `127.0.0.1:8001` and **nothing on :8080**, while `qwen-run.sh:468` does pass `--provider "$PROVIDER"` to `pi` — so `pi` is ignoring the flag and falling back to its own default provider. The one permitted retry was deliberately SKIPPED as deterministically pointless (cycle 1 already spent its retry on the `-P llamacpp8001` variant and failed identically). Quinn is advisory-weight, so no consensus finding was lost.

### Process notes (fail-loud)

- **The engram context pack could not be generated**, same deterministic cause as cycle 1: `engram pack` exits 1 with `not inside a registered repo; register it in /Users/bob/.config/gita/repos.csv`, and `engram` is still absent from that file (verified with `rg`, and the search pattern proved working against a control term). The retry was skipped as pointless. Every prompt received the sentinel `(no pack available this cycle)`; Blake never receives a pack by design. **The review is degraded by the missing retrieval context, not invalid.** This is cycle-1 finding T12, still open.
- **`gather-context.sh --since` produced a healthy 59,577-byte diff this cycle** — cycle 1's empty-diff trap (its merge-base range resolving to nothing on this `master`-only repo) did not recur, because `--since <head_sha>` bypasses the merge-base path. Verified non-empty before dispatch.
- **Two defects in the review tooling itself, surfaced rather than swallowed:**
  1. `qwen-run.sh` **exited 0** while writing only an error line to its `-o` file. A failed reviewer that reports success to its caller is how a lens silently drops; only the byte-count check caught it.
  2. `consolidate-findings.sh` again scored all 55 raw lines `[1/5]` despite heavy agreement — its matcher is exact string equality on file+description, and five reviewers described the same defect in five different sentences. **Consolidation below is therefore script-run then merged model-side**; consensus counts are distinct-reviewer counts per theme. Eve's output contributes no lines to the script at all (her contract is FIX/VERIFY/KNOWN, not the issue-line format), so a script-only reading would have dropped her entirely.
- **A formatter reflow of `tests/test_transcripts.py` (81 insertions, zero semantic change, 88-col against the repo's ~100-col committed style) was sitting uncommitted in the working tree at cycle start** and was discarded before review. Sixth occurrence. Cycle-1 finding T22, still recurring.

## Consolidated Findings

Five active reviewers. Consensus is `[n/5]`, counted per merged theme.

### Multi-reviewer themes

| Consensus | Sev | id | Issue | File |
|-----------|-----|----|-------|------|
| [4/5] | 🟠 | C1 | **T16 is still half-closed.** `hash_source(file.path)` runs BEFORE the guarded `_chunk_file` dispatch, so a file deleted or made unreadable between enumeration's `is_file()` and hashing still aborts the whole run (`PermissionError` escapes even the CLI's `FileNotFoundError` catch as a raw traceback). Blake frames it as a check-then-act race that is routine across 26 live repos and 636 continuously-appended transcripts, and can kill a 40-minute rebuild. No test covers it | src/engram/indexer.py |
| [4/5] | 🟠 | C2 | **The prune fail-open (T15) was closed only for the `code` corpus.** A repo whose checkout is transiently absent still records `prd:`/`decision:`/`discovery:` misses that are ignored, and those chunks are pruned; a missing `~/.claude/projects` makes `_enumerate_memory_corpora` return silently with **no `missing_dirs` marker at all**, pruning the entire memory class (20 of 44 gold entries) without a message. Blake adds a third variant: `transcripts.enumerate` raises only when the directory is *missing*, so an empty-or-unmounted `projects/` yields zero files and prunes all **18,981** transcript chunks — the same silent-empty-corpus failure the PRD forbids, one directory level down | src/engram/indexer.py, src/engram/corpora.py |
| [3/5] | 🟡 | C3 | `IndexReport.files_skipped` has **zero production consumers** (only tests read it), and the dispatch-level `except Exception` records neither the failing path nor the exception. A run that skipped 12,000 files looks identical to a clean run. The CHANGELOG's "the count is reported" oversells. Eve adds that the count also **conflates** benign no-grammar skips with genuine parse/read failures, so on a fresh code index real errors are buried under expected ones | src/engram/cli.py, src/engram/indexer.py |
| [2/5] | 🟠 | C4 | **The task-11 fix is defeated by the task-4 fix.** `index()`'s blanket `except Exception` swallows the new config-boundary `ValueError`: a bad regex in `[transcripts] error_patterns` is caught, the file is counted as skipped, and the run **exits 0 silently**. Alice reproduced it live (`IndexReport(files_scanned=1, chunks_added=0, files_skipped=1)`, no stderr). The CHANGELOG claim "fails at the config boundary, naming the offending pattern" is **false via `engram index`**. Bob adds that all transcript rows may then be pruned. Two fixes from the same cycle cancelling out is the highest-value finding of this review | src/engram/indexer.py |
| [2/5] | 🟠 | C5 | **The new per-class gate is vacuous for an absent class.** `per_corpus_hit_rate` is built only from goldset entries that exist, so `all(...)` passes over a partial dict and `gate_passed` can be True while the PRD's `code` or `transcripts` class is entirely unmeasured; `test_config_names_winner_after_gate_passes` enshrines this. **Eve dissents**, bucketing it KNOWN/out-of-scope on the grounds that the goldset is a committed, reviewed artifact and `load_goldset` enforces a floor | src/engram/harness.py |
| [3/5] | 🟡 | C6 | A non-string element in `[transcripts] error_patterns` (`["ERROR", 42]` is valid TOML) raises a bare `TypeError` from `re.compile`, bypassing the named-pattern-and-key contract the task exists to provide. Catch `(re.error, TypeError)` in the same clause, or validate `list[str]` | src/engram/transcripts.py |
| [3/5] | 🟡 | C7 | `known_code = store.known_sources(scope, "code")` runs a full code-corpus scan on **every** `index()` call even when `failed_code_repos` is empty (the common case). One-line, behavior-preserving fix: guard both statements on `if failed_code_repos:`. This was the build's own deferred LOW | src/engram/indexer.py |
| [3/5] | 🟡 | C8 | Each model's score block now prints **twice** on a successful harness run. **Reviewers disagree on the remedy:** Bob wants progress streamed to stderr with stdout reserved for the unchanged summary; Alice calls it defensible and idempotent for any parser keyed on the first field; Eve accepts it as a deliberate, recorded cost | src/engram/harness.py |
| [2/5] | 🟡 | C9 | **The task-8 control test cannot fail.** `test_baseline_rate_still_favors_a_file_that_matches_more_query_tokens` uses counts `[3,1,1,1,1,1,1]` → `cutoff = counts[4] = 1` → all 7 files are admitted, so the expected file "hits" regardless of implementation. Alice and Eve verified the arithmetic independently. It passes for an admit-everything baseline, and **nothing in the suite pins that the band ever excludes anything**. Its docstring's claim is false. This is a test that binds to nothing — the exact failure `rules/testing.md` forbids | tests/test_harness.py |
| [2/5] | 🟡 | C10 | Size ceilings breached **by this diff**: `tests/test_harness.py` 1739 lines (was 1151), `tests/test_indexer.py` 862 (was 655), `tests/test_cli_index_status.py` 847 (was 707) against the 800 max; `index()` is 72 lines and `_baseline_hit_rate` 58 against the 50-line rule. Several new gate tests are 65-70 lines of duplicated setup | tests/test_harness.py, src/engram/indexer.py |
| [2/5] | 🟡 | C11 | Pat's un-reworked cycle-1 MEDIUM still stands: `per_model[winner_id]` is indexed three times inside the gate expression; bind `winner_score` once | src/engram/harness.py |
| [2/5] | 🟡 | C25 | Naming and doc drift introduced by this cycle: `top5` now holds an unbounded tie band (measured 5-10 files per query), and `eval/harness.py`'s module docstring still says the winner is pinned unconditionally — which task 3 made false | src/engram/harness.py, eval/harness.py |
| [2/5] | 🟡 | C29 | `count_skipped()` reports grammarless *tracked* files, not files actually skipped during chunking, so it disagrees with `IndexReport.files_skipped`; it also **clears the shared `symbols.skipped_files` global as a side effect** | src/engram/symbols.py |

### PRD-completion criticals (both are cycle-1 deferrals resurfacing, exactly as predicted)

| Consensus | Sev | id | Issue | File |
|-----------|-----|----|-------|------|
| [2/5] | 🔴 | C12 | **Phase 1's exit criterion is unmet.** The only recorded harness run scores code **0.600** and transcripts **0.750** against the PRD's 0.80 per-class bar, and `config.toml` still pins that failing model as the live embedding model. Cycle-1 T2 | eval/goldset.yaml |
| [2/5] | 🔴 | C13 | **Phase 2's exit criterion is unmet and unreachable unattended.** The catchup CHANGELOG entry sits under `[Unreleased]`, the newest ferry tag is `v0.2.2` (predating all three engram commits), master is 3 commits unpushed, and **none of the 14 `project-capsule.md` files in the portfolio contains a `## Related context` heading** — so the section has never been produced end-to-end. Blocked on a user action: `/warden:allow engram`. Cycle-1 T4 | claude-git-ferry/CHANGELOG.md, claude-git-ferry/skills/catchup/SKILL.md |

### Single-reviewer findings that matter

| Consensus | Sev | id | Issue | File |
|-----------|-----|----|-------|------|
| [1/5] | 🟠 | C16 | **The `engram` on PATH predates the entire rework.** The uv-tool snapshot at `~/.local/share/uv/tools/engram/.../engram/cli.py` still has `_run_status` without the `transcripts.enumerate` probe — task 2 installed it *before* tasks 3-11 landed, and nobody reinstalled. Unattended catchup (Phase 2's exit criterion) would run a binary containing **none** of this cycle's fixes. One command fixes it: `uv tool install --reinstall .` (Eve) | ~/.local/share/uv/tools/engram/ |
| [1/5] | 🟠 | C14 | **New regression from task 4.** A *changed* file that fails chunking contributes no active source, so `prune()` deletes its last successfully indexed chunks — the guard that was added to stop data loss introduces a narrower version of it (Bob) | src/engram/indexer.py:68 |
| [1/5] | 🟠 | C15 | **T19 is only half-fixed.** Freshly generated configs still omit `[transcripts] error_patterns`, so every new installation runs the hardcoded fallback. Editing the live config by hand does not ship the requirement (Bob) | src/engram/client.py:41 |
| [1/5] | 🟠 | C17 | **42% of the code corpus has no symbol identity.** 17,449 of 41,716 code chunks carry the heading `Function None`/`Class None` because `item.name` is None and unguarded, so the only name signal in the embedded text is the word "None". Directly implicated in the code class scoring 0.600 (Blake) | src/engram/symbols.py |
| [1/5] | 🟠 | C18 | Symbol chunks do not embed "signature + docstring + file path" as the PRD specifies: the text is `"{Kind} {name}\n{entire raw body}"`, the path is never embedded, and `StructureItem.signature`/`doc_comment` **are populated in the pinned 1.14.0** contrary to the design doc's live probe; 687 code chunks exceed the 8000-char embed cap and are silently truncated (Blake). Cycle-1 T7, newly quantified and with the design premise contradicted | src/engram/symbols.py |
| [1/5] | 🟠 | C19 | `engram status` re-reads ~46 GB per invocation: `Store.status` reads and SHA-1s a file once per chunk row with no path dedup (18,981 rows over 636 files), plus `count_skipped()` re-runs `git ls-files` across 26 repos. **Measured 18.1s warm** — and catchup runs it every session (Blake) | src/engram/store.py |
| [1/5] | 🟠 | C20 | The PRD's "unchanged transcripts are never re-read" is violated: `hash_source` reads every byte of all 636 transcripts (**689 MB**) plus all 11,694 tracked code files on every index run; git blob hashes are never consulted despite the PRD naming them as the mechanism (Blake) | src/engram/corpora.py |
| [1/5] | 🟠 | C21 | T3's **wider half is unaddressed**: the eval harness still runs against the live `engram.db` and live `config.toml` rather than an isolated test database. Only the narrow "don't pin on a failed gate" half was fixed (Carl) | N/A |
| [1/5] | 🟡 | C22 | The new corpora copy raw session and source text into a single **0644 unencrypted** SQLite file with no redaction; scanning indexed bodies matched credential-shaped strings — 26 rows with `ghp_`, 6 with `AKIA`, 75 with `Bearer `. **Suspected, not confirmed as live secrets**, but no scrubbing exists either way (Blake) | ~/.local/share/engram/engram.db |
| [1/5] | 🟡 | C23 | Task 6's shell-safety fix uses a `topic='...'` variable assignment plus a multi-line block — which the user's own Bash rule explicitly forbids, because the assignment becomes the permission prefix and warden gates on the first token. The fix may itself be unrunnable unattended (Eve) | claude-git-ferry/skills/catchup/SKILL.md:56-61 |
| [1/5] | 🟡 | C24 | The new indexer tests append `"code:repoB"` to the real module-global `corpora.missing_dirs` and never restore it, leaking state into any later test whose stubs do not clear it (Eve) | tests/test_indexer.py:713,745 |
| [1/5] | 🟡 | C26 | The error matcher ignores list-form `tool_result` content (`isinstance(text, str)` only); **173 of 4,050** real tool_result blocks sampled from cellar carry their payload as a list, so those error turns can never match a pattern (Blake) | src/engram/transcripts.py |
| [1/5] | 🟡 | C27 | The code corpus ingests non-portfolio artifacts — cellar's `projects-archive` minified JS and generated game code (**bobiste alone contributes 13,140 chunks, 12,443 of them unnamed**), degrading the "have I built X" pool the PRD is measured on (Blake). Cycle-1 T8, newly quantified | src/engram/symbols.py |
| [1/5] | 🟡 | C28 | Nested symbols are double-indexed: `_walk` emits a class chunk containing every method body *and* each method separately, so identical text competes against itself in the same KNN pool (Blake). Cycle-1 T34 | src/engram/symbols.py |
| [1/5] | 🟡 | C30 | A missing cellar checkout disables indexing of **every unrelated corpus**: all three producers enumerate before the `--scope`/`--corpus` filter, so even `engram index --corpus prd` exits 1 on a machine without cellar (Blake) | src/engram/indexer.py |
| [1/5] | 🟡 | C31 | The staleness stamp is red by construction: the current session's own JSONL is always newer than the index, so `engram status` exits nonzero forever (observed `transcripts stale=1` during this review), training the capsule reader to ignore the signal (Blake). Cycle-1 T32 | src/engram/store.py |
| [1/5] | 🟡 | C32 | The gold set is too thin to carry the success metrics: 4 transcript entries (0.25 steps) and 5 code seeds (0.20 steps), and each code entry pins one canonical path rather than modelling the cross-repo *duplicate* the PRD describes (Blake). Cycle-1 T10 | eval/goldset.yaml |
| [1/5] | 🟡 | C33 | The "<60s unchanged reindex" success metric is asserted **nowhere** — no test, no harness timing, no recorded measurement in the repo. Blake's own probe of the enumerate+hash path is ~3.1s warm, so the bound is plausible but entirely unpinned and will drift | src/engram/harness.py |
| [1/5] | 🟡 | C34 | Module API deviates from the PRD's stated exports: both `enumerate()` functions return an `Iterator`, not `list[Entry]`, and both `chunk()` functions require `(path, repo, content_hash)` rather than the specified `chunk(path)` (Blake) | src/engram/transcripts.py |
| [1/5] | 🟡 | C35 | Blind-lens scope-creep flag: `findings.py`, `harvest.py`, `pack.py`, `diffmap.py`, the `engram harvest`/`engram pack` subcommands, a `findings` corpus and a `[pack]` config block all ship in the same tree, none named by this PRD (Blake). **Adjudication: not scope creep from this PRD** — that surface belongs to PRDs 00003/00004, which Blake cannot see by design. Recorded because a blind reviewer flagging it is working correctly | src/engram/cli.py |
| [1/5] | ⚪ | C36 | No test calls `transcripts.chunk()` with `error_patterns=None`, so the implicit loader seam and its caching are never exercised through the real path — the Tess flag carried from the build, still open (Alice) | tests/test_transcripts.py |
| [1/5] | ⚪ | C37 | `git ls-files` reads the index, not HEAD as the PRD states: staged-but-uncommitted files are included and staged deletions excluded (Blake) | src/engram/symbols.py |
| [1/5] | ⚪ | C38 | Cross-module state travels through mutable module globals (`symbols.skipped_files`, `corpora.missing_dirs`); correctness depends on `enumerate_corpora()` clearing before `symbols.enumerate()` appends within the same expression — load-bearing and undocumented (Blake) | src/engram/indexer.py |
| [1/5] | ⚪ | C39 | Untracked `.serena/` tool-cache junk left in the repo by the work session (Eve) | .serena/ |
| [1/5] | ⚪ | C40 | Catchup's topic hardening still relies on the model escaping a literal `'` inside a branch name or PRD title; adequate for an agent-executed skill, but it is the one residual injection surface (Alice) | claude-git-ferry/skills/catchup/SKILL.md |

### Advisory (local model, unconfirmed)

- (none — Quinn was unavailable this cycle)

## What the rework DID achieve

Recorded deliberately, because the finding count above understates it. Alice and Eve independently verified in the code that **every one of the 14 cycle-1 findings routed to rework is present and correct**: T1 (per-class gate), T3 narrow half (`_write_pinned` gated; it is the sole call site), T13, T14 (every lease stopped, including the crash-after-selection path Eve identified), T15 (for the code corpus), T16 (at the dispatch seam), T17 (status enumerates transcripts, honest test), T18/T27/T28 (verified in `claude-git-ferry`), T19/T20 (live config carries `[transcripts]`; Alice checked that `_write_pinned`'s line rewriter leaves the table intact because single-bracket headers reset its state), T29, T30. Eve's verdict: the corrections "are genuinely carried into the rework and their tests bind to intent."

The findings above are overwhelmingly **residue** — half-closed guards, an unshipped install, and defects the fixes newly exposed — not a failed rework.

## Alice

Implementation-aware consensus lens. 15 findings; ran the suite and reproduced the config-swallow defect live. Raw output: `dev/local/tmp/alice-output-00002-c2.txt`. Repro scripts: `~/.local/tmp/claude-dev/alice/`.

Her distinctive contribution is **C4** — the live reproduction proving task 11's config-boundary error is swallowed by task 4's guard, making a CHANGELOG claim false — and the numeric disproof of the task-8 control test (**C9**).

```
R1: fail
R2: fail
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: fail
R10: fail
R11: pass
R12: fail
R13: fail
```

## Blake

Blind lens — PRD only, no diff, no file list, no review history; found the code himself. 24 findings, again the largest yield, and again the only reviewer to reach the corpus-content defects. Raw output: `dev/local/tmp/blake-output-00002-c2.txt`.

Blake verified against the live system rather than the diff: he queried `~/.local/share/engram/engram.db` directly (producing the 17,449-of-41,716 unnamed-chunk count in **C17**, the 809 empty-body transcript chunks, and the credential-shaped-string scan in **C22**), timed `engram status` at 18.1s (**C19**), and checked `tree-sitter-language-pack==1.14.0`'s real API — finding that `signature`/`doc_comment` **are** populated, contradicting the design doc's recorded live probe (**C18**).

```
B1: fail
B2: fail
B3: fail
B4: fail
B5: pass
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
```

## Bob

Codex; doubt + de-slop lens, static analysis only (sandboxed, no execution). **Resumed his cycle-1 thread**, so he verified the fixes against his own prior critique rather than re-reviewing from zero. 14 findings. Raw output: `dev/local/tmp/bob-output-00002-c2.txt`.

Bob is the only reviewer to reach **C14** (a changed file that fails chunking loses its active source, so prune deletes its last good chunks — a narrower re-introduction of the very defect task 4 closed) and **C15** (freshly generated configs still omit the `[transcripts]` table, so T19 is only half-fixed for anyone who installs engram tomorrow). He correctly declined to assert the suite result, emitting a VERIFY line instead.

```
R1: fail
R2: fail
R3: pass
R4: fail
R6: pass
R7: fail
R8: pass
R9: fail
R10: fail
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

Gemini via copilot; reviewing as a generalist since the change has no UI surface. 2 findings, both substantive. Raw output: `dev/local/tmp/carl-output-00002-c2.txt`.

Carl held his cycle-1 altitude and re-raised the half of T3 nobody else tracked (**C21**): the narrow fix stopped the failed-gate pin, but the eval still mutates live production state instead of using an isolated test database. He also independently proposed the exact one-line guard for **C7**.

```
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
```

## Eve

Fable 5, doubt lens — added by the codex doubt-roster guard because task 1 was implemented by codex. 11 FIX / 2 VERIFY / 8 KNOWN. Raw output: `dev/local/tmp/eve-output-00002-c2.txt`.

Eve again audited the build's own self-report, as she did in cycle 1, and her distinctive contribution is **C16**: she read the *installed* CLI at `~/.local/share/uv/tools/engram/` and found it predates all 19 rework commits — task 2 installed engram before tasks 3-11 landed and nobody reinstalled. Every prior phase, both reviews, and the build's own verification missed it, because they all read the repo rather than the artifact the PRD actually ships. She also independently derived the same arithmetic Alice did for the vacuous control test (**C9**), and flagged that task 6's shell-safety fix may violate the user's own Bash rule (**C23**).

Her two VERIFY items name exact checks: run the SKILL.md block through warden with `WARDEN_UNATTENDED=1` to settle C23, and restore `harness.py` to `bfa74d6~1` to confirm task 3's "3 of 6 tests failed pre-fix" red-check claim.

```
D1: pass
D2: pass
D3: pass
D4: pass
D5: pass
```

## Follow-up Tasks Created

**None — deliberately.** This is cycle 2 of a cap-2 review loop, so no rework cycle will run to consume them, and the PRD is being stalled to `dev/local/prds/hold/` (see below). Creating 40 tasks that nothing will execute would put false in-flight work on the dashboard and collide with the fresh `TaskCreate` ids of whatever PRD runs next. The findings' durable home is this file plus the batch deferred record; a human who un-parks the PRD re-enters the build gate, which replans from scratch against this review.

## Decision gate outcome

`state.cycle` = 2, `state.rework_cap` = 2 → **the rework cap is reached** and the review did **not** converge. Loop mode is active (`$_AUTOPILOT_LOOP` set), so the cap-out branch applies: unresolved CRITICAL findings exist (**C12**, **C13**), which routes to the loop-mode stall procedure with `site: cap_critical` rather than a cap-pause. The PRD moves to `dev/local/prds/hold/` and the batch continues.

Both criticals are cycle-1 deferrals that were never rework-fixable, and the contract card written at the cycle-1 hand-off predicted exactly this:

- **C12 / T2** needs retrieval-quality iteration, not a code patch — and this cycle finally produced a concrete lead on *why* the code class scores 0.600: **C17** (42% of code chunks named `None`) and **C18** (no signature/docstring/path embedded, 687 chunks truncated). Those are the first actionable causes anyone has named.
- **C13 / T4** is blocked on a **user action**: `/warden:allow engram`. An agent must not self-grant through the security gate; the build agent correctly tried and was denied.

### The data-loss and security findings, and why neither is a batch halt

`decision-framework.md` sanctions halting the whole batch for a "detected data-loss risk" or a "security-critical finding". Three findings were weighed against those rules and **none** halts the batch:

- **C2 / C14** (prune deletes chunks on a transient enumeration or chunking failure) — the engram DB is **derived** data. Losing rows costs re-embedding time, not user content. Same judgement recorded in cycle 1 for T15, applied consistently.
- **C22** (credential-shaped strings in a 0644 SQLite file) — this is **not a new exposure created by this PRD**. The same strings already sit in plaintext in cellar's transcripts and in tracked source; engram copies local data into another local file on the same single-user machine, and nothing is published. It is a real hardening gap (no redaction exists), not a shipped vulnerability. **It does warrant a human eye**: if any of the 26 `ghp_` / 6 `AKIA` / 75 `Bearer ` matches is a live credential, the standing rule is to rotate it. Blake was explicit that these are suspected, not confirmed.

Verdict: 40 findings
Tests: 426 passed, 0 failed, 0 skipped
