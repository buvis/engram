---
prd: dev/local/prds/wip/00004-engram-review-packs-v1.md
review: 1
date: 2026-08-03
head_sha: 4faab3b31307f60192e451c76c7570424f07ce48
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

Diff range: `7d949f2cde8f9721269238819f9181920a945958..4faab3b31307f60192e451c76c7570424f07ce48` (engram, tasks 1-6)
Diff range: `773b91e57^..ecbf89a76` (buvis bare repo, `~/.claude` tree, tasks 7-9)

codex_rung_guard: fired (2 codex-implemented task(s))

## Review Summary

Reviewed: 9 completed tasks
PRDs checked: 00004-engram-review-packs-v1

### Agent Status

- Alice (Claude, consensus): ✅ Available — 20 findings
- Blake (Claude, blind/PRD-only): ✅ Available — 16 findings
- Bob (codex, consensus + doubt): ✅ Available — 14 findings, D1-D5 all pass
- Carl (gemini/copilot, UI+generalist): ✅ Available — 15 findings
- Eve (Fable 5, doubt): ✅ Available — 13 FIX, 1 VERIFY, 4 KNOWN, D1-D5 all pass
- Quinn (local qwen, advisory): ⚠️ Unavailable: `pi` reported `[llama-cpp] failed to reach http://localhost:8080/v1/models: fetch failed` on both the initial dispatch and its one retry, despite `qwen-run.sh --preflight --approved-only` passing twice on provider `llamacpp8001` and the retry forcing `-P llamacpp8001`. Backend healthy; `pi` ignores the resolved provider and probes :8080. Advisory lens only — no findings lost from the consensus table.

Tests: 626 passed, 0 failed, 0 skipped

Test breakdown, all run live in the foreground this cycle, zero skips:
- `uv run --project <engram> pytest <engram>/tests -q` → **357 passed**
- `uv run --project <engram> pytest ~/.claude/skills/review-work-completion/scripts/ -q` → **184 passed**
- `node --test ~/.claude/workflows/*.test.mjs` → **85 passed**

⚠️ These commands are **improvised from the manifest, not project-documented**. engram's `pyproject.toml` declares no `[tool.pytest]` and no `[tool.ruff]`; `pytest` is not on the mise `python3`. There is no lint gate in this repo.

### Cycle degradations (fail loud)

1. **No engram context pack this cycle.** `engram pack --cycle 00004-c1` exits 1 with `not inside a registered repo; pass --scope portfolio instead`, because `/Users/bob/git/src/github.com/buvis/engram` is absent from `~/.config/gita/repos.csv`. Retried once, identical. `{PACK_FILE}` and `{PACK_FINDINGS}` were substituted with the literal `(no pack available this cycle)` sentinel in every prompt that takes them. **The feature under review could not be dogfooded on its own review cycle** — this is finding C1 below, not merely a staging hiccup.
2. **Consolidation was model-side, not `consolidate-findings.sh`.** The script exited 1 with `line 140: severity_by_key[$key]: unbound variable` after emitting 5 rows. Cause: its dedup key is `normalize(desc)|normalize(file_path)`, containing a literal `|`, which the `IFS='|' read -r count sev_num key` read-back then splits at, truncating the key so the array lookup misses. Not a fixable invocation problem, so per SKILL.md step 6 the fallback applied: findings were grouped model-side by same-issue-same-file across reviewers, consensus = count of distinct reviewers, sorted by consensus then severity. The script is not in this PRD's diff — recorded as an orchestrator observation, not a finding against 00004.
3. **The Watcher's readiness probe is satisfied by a stale non-empty file.** Quinn's retry wrote to a path that already held his first-run error text, so `await_reviewer_outputs.py` returned `DONE` in 37s without the retry having produced anything. Also out of this PRD's diff scope; recorded so the next cycle does not trust a fast `DONE` on a re-dispatch.
4. **Carl could not read `/Users/bob/.claude`** (`Permission denied` on every attempt) and could not run any test suite. He reviewed the engram diff plus the staged buvis diff file, which is why tasks 7-9 are still in his findings. His R-verdicts on test execution are therefore weaker evidence than Alice's or Eve's.

## Consolidated Findings

35 distinct findings after model-side grouping. Consensus is out of 5 reviewers (Quinn excluded — he produced no output).

### Full / near-full consensus

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [5/5] | 🟠 | `diff_path` (both `--cycle` and `--diff` branches) and `build()`'s default `out_dir` resolve against the invocation cwd, while `repo_root` anchors to the git toplevel. From a subdirectory, `--cycle` crashes on a file that exists at the root and `--diff` writes stray `<subdir>/dev/local/tmp/` trees. The subdirectory test masks this by monkeypatching `build` and asserting only `repo_root`. | src/engram/cli.py:263,285; src/engram/pack.py:231 | 5 | Alice, Blake, Bob, Carl, Eve |
| [4/5] | 🟠 | Task-prose "related memories" are retrieved by embedding `id_` — the cycle id (`00004-c1`) or a range slug (`abc123--def456`) — not the PRD title the design specifies. Neither the BM25 leg nor the vector leg can relate that token to the diff, so KNN still injects up to 2 arbitrary memories into every pack as noise. No test seeds the memory corpus at all. | src/engram/pack.py:152-158 | 4 | Alice, Blake, Bob, Eve |
| [4/5] | 🟠 | PRD success metric 1 (≥3 historical commit ranges, each pack containing ≥1 retrieved item absent from the diff) and the Phase 1 exit criteria were never executed and are recorded nowhere. Every pack test is a synthetic fixture with monkeypatched `index` and `embed`; the `--diff` CLI tests fake `git diff` output entirely. | tests/test_pack.py | general | Alice, Blake, Bob, Eve |
| [4/5] | 🟡 | No workflow test asserts victor's `skepticPrompt` carries the pack line — the new cases cover `dims` and `rubricPrompt` only. Victor gets it today solely because `skepticPrompt` shares the same `context` string, so a refactor decoupling it drops pack access for the refutation persona with every test still green. `assembleWith` already returns `skepticPrompt`, so the assertion is one line. | ~/.claude/workflows/registry-parity.test.mjs:125-131 | 9 | Alice, Bob, Carl, Eve |
| [4/5] | ⚪ | SKILL.md step 5's `pack_path` args row never says to omit the arg when pack generation fails, so the literal `(no pack available this cycle)` sentinel the step-3 fallback prescribes can be passed as a path and reach all seven dimension personas as "read (no pack available this cycle) before judging". | ~/.claude/skills/review-work-completion/SKILL.md:245 | 9 | Alice, Bob, Carl, Eve |

### Majority consensus

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [3/5] | 🟠 | Three new functions exceed the 50-line limit: `pack.build` (131), `cli._run_pack` (94), `diffmap.changed_symbols` (74). Carl adds `client.load_config` (64), also grown by this diff. Each splits along an existing seam. | src/engram/pack.py; src/engram/cli.py; src/engram/diffmap.py; src/engram/client.py | 4, 5, 1, 3 | Alice, Bob, Carl |
| [3/5] | 🟠 | `tests/test_pack.py` ships at 818 lines, over the 800-line limit. Alice adds that this diff pushed `tests/test_cli.py` from 1073 to 1611, with the self-contained pack CLI block at 1077-1611. | tests/test_pack.py; tests/test_cli.py | 4, general | Alice, Bob, Carl |
| [3/5] | 🟠 | The PRD's named error case ("missing `review-diff-{id}.diff` → loud failure naming the expected staging path, no empty pack written") has no handler and no test. `_run_pack` never checks existence; `build()` runs the full reindex FIRST (real embed traffic), then `changed_symbols` dies in an uncaught `FileNotFoundError` traceback. `_run_index` catches `FileNotFoundError` explicitly; `_run_pack` does not. | src/engram/cli.py:263 | 5 | Alice, Blake, Eve |
| [3/5] | 🟠 | **C1** — `engram pack` cannot run in a repo absent from gita's `repos.csv`, and its error names a flag the verb does not have: `--scope portfolio` then exits 2 `unrecognized arguments` (the pack subparser defines only `--cycle`/`--diff`/`--prd`/`--capsule`). This is exactly why this review cycle has no pack, and why the feature cannot be dogfooded in its own repo. | src/engram/cli.py:28,247 | 5 | Alice, Bob, Eve |
| [3/5] | ⚪ | `eve.md`'s new paragraph claims precedent-weighing governs "the rubric verdicts", but sits under `## Two lenses` while D1-D5 grade FIX/VERIFY/KNOWN bucket integrity, not precedent. Fix: drop "and the rubric verdicts". | ~/.claude/agents/eve.md:24 | 8 | Bob, Carl, Eve |

### Minority

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [2/5] | 🟠 | Eve's own dispatch path never substitutes `{PACK_FINDINGS}`. `agent-invocation.md` dispatches `subagent_type: eve` with raw `eve.md` as the system prompt and still lists only "the same three appended inputs", so the literal token ships in her system prompt. The design named this file an edit target and it was not touched. **Live proof: this cycle's orchestrator had to hand-resolve the placeholder in Eve's appended message.** This breaks the wiring on the one path where "doubt gets findings only" is actually enforceable. | ~/.claude/skills/review-work-completion/references/agent-invocation.md:79-96 | 8 | Alice, Eve |
| [2/5] | 🟠 | A wrong or unreadable `--prd`/`--capsule` path is swallowed silently: `_task_prose_entries` catches `OSError`, drops the entry, renders no note, exits 0. The design required "omitted, noted in the rendered pack", so a typo silently thins every reviewer's Task prose. | src/engram/pack.py:188 | 4 | Alice, Eve |
| [2/5] | 🟠 | Unsanitized `--cycle` permits staging-path traversal: it is interpolated raw into `dev/local/tmp/review-diff-{id}.diff` and `engram-pack-{id}.md`, while the `--diff` branch slugs its id with `re.sub(r"[^A-Za-z0-9_-]", "-", ...)`. `--cycle ../../x` escapes `out_dir` and makes `mkdir(parents=True)` create a literal `engram-pack-..` directory. | src/engram/cli.py:255 | 5 | Alice, Bob |
| [2/5] | 🟠 | `git diff <range>` and `git show <ref>:<path>` interpolate user-controlled values with no `--` separator, so a range starting with `-` is parsed as a git option (`--output=` writes files). argv lists block shell injection but not argument injection. | src/engram/cli.py | 5 | Alice, Bob |
| [2/5] | 🟡 | Task-prose entries carry no origin labels. `_render_pointer` labels code/findings hits, but prose renders via `lambda text: text`, so PRD text, capsule extract and memory bodies concatenate with no marker. PRD: "every item labeled with its origin". | src/engram/pack.py:133 | 4 | Blake, Bob |
| [2/5] | 🟡 | Self-match exclusion rests on raw string path equality (`hit.path == span_path`) with no canonicalization, though the design explicitly mandated it. Symbol paths come from `git rev-parse --show-toplevel`, stored chunk paths from the gita `repos.csv` spelling; any symlink/`/private`/trailing-slash difference silently disables the exclusion and the pack echoes the diff's own symbols back as "similar code" — the ≥1-item-beyond-diff metric fails silently. The harvest verb canonicalizes; this does not. | src/engram/pack.py | 4 | Alice, Blake |
| [2/5] | 🟡 | Git C-quoted non-ASCII paths are knowingly left undecoded, producing incorrect symbol paths and defeating both source reads and self-match exclusion. Alice separately flags that the deferral shipped as a `ponytail:` mode-name comment reading as unfinished work. | src/engram/diffmap.py:37 | 1 | Alice, Bob |
| [1/5] | 🔴 | **Blake (blind)**: the doubt lens receives the FULL pack, violating the PRD's "Findings-precedent section ONLY prepended to the doubt lens". SKILL.md names Bob the doubt lens and `bob.md` frontmatter says "Also carries the doubt lens every cycle", yet `bob.md:9` reads "Read {PACK_FILE} and treat its full content as prepended context". Findings-only isolation is enforced only on Eve, who is opt-in. Blake adds that the skill's own test file re-labels Bob as consensus to make the assertion pass. | ~/.claude/agents/bob.md | 8 | Blake |
| [1/5] | 🟠 | The PRD's own per-section caps are unimplementable as config. The spec says 1,500 (similar); the default is 1400, and writing the spec's exact table into `config.toml` is **verified rejected**: `ValueError: [pack] section caps plus framing overhead (4100) exceed hard_cap_tokens (4000)`. The PRD calls retuning "a config change, not a code change" — its own numbers cannot be configured. | src/engram/client.py | 3 | Blake |
| [1/5] | 🟠 | The first `engram pack` in any repo triggers a full repo-wide code index on the review critical path: `build()` calls `index(...)` before anything else and `store.known_sources` is empty for the code corpus, so every tracked file gets its own `embed()` call — the exact request-volume failure PRD 00002 measured. The design's "bounded by however many files the diff touched" holds only *after* a first successful index. | src/engram/pack.py | 4 | Alice |
| [1/5] | 🟠 | Fail-open path defeats "no empty pack written": `gather-context.sh:115` writes a `_No diff available_` sentinel into `$DIFF_FILE` on git failure, so the staged file exists holding non-diff text. diffmap then finds zero `diff --git` sections, zero symbols, zero retrievals, and `pack.build` writes a fully empty pack with exit 0 — the reviewer sees a valid-looking artifact. | ~/.claude/skills/review-work-completion/scripts/gather-context.sh | 1 | Blake |
| [1/5] | 🟠 | **Eve, reproduced live**: the grammarless/module-level fallback emits one file-level `Symbol` **per added line**, not one per file (design contract: "one file-level Symbol for that file"). A 20-line `CHANGELOG.md` edit yields 20 symbols, so a docs-heavy diff (CHANGELOG sorts first) burns the 40-symbol cap on junk single-line queries and crowds real code symbols out of `all_symbols[:MAX_SYMBOLS_PER_PACK]`. | src/engram/diffmap.py:95 | 1 | Eve |
| [1/5] | 🟠 | Pre-pack reindex covers only repo scope, but the PRD's stated inputs are "Current repo + portfolio index state" and Reuse precedent is served from portfolio scope. Every pack ships a hardcoded `Portfolio freshness: NOT refreshed this cycle (PRD 00002 pending)` string constant. | src/engram/pack.py | 4 | Blake |
| [1/5] | 🟡 | The BM25 half of every pack query is dead by construction: the query text is a whole symbol body, and `Store.search_bm25` quotes each token and lets FTS5 AND them, so a multi-token body matches no chunk. RRF fusion silently degenerates to KNN-only for all four retrieval calls. | src/engram/pack.py | 4 | Alice |
| [1/5] | 🟡 | A three-dot range `a...b` passes the `".." in range_str` check and produces `source_ref=".b"`; every `git show` then fails and the whole mapping silently degrades to per-line file-level symbols with `"kind name"` query texts. | src/engram/cli.py:268-276 | 5 | Eve |
| [1/5] | 🟡 | Reuse precedent can be starved by design: the portfolio query returns only the top k=5 fused hits and the own-repo filter runs *after* truncation. The local repo is normally its own best match, so foreign precedent is crowded out of the pool before the filter sees it. | src/engram/pack.py | 4 | Blake |
| [1/5] | 🟡 | Findings items are labeled `findings:<path>` with no repo or scope, so repo-scope and portfolio-scope findings are indistinguishable. PRD: "Findings precedent both scopes, labeled". **Eve refutes**: the design contradicts itself (its step-10 render spec says `corpus:path`, matching the PRD's literal "repo + file:line or corpus"), so this is a design-doc inconsistency, not an implementation defect. | src/engram/pack.py | 4 | Alice (refuted by Eve) |
| [1/5] | 🟡 | Neither declared export matches the PRD's signature: spec says `changed_symbols(diff_path)` and `build(cycle_id \| diff_range)`; the code has `changed_symbols(diff_path, repo_root, source_ref=None)` and a `build()` with six required positionals, none of them a cycle id or diff range. (The design deliberately redefined both — see Adjudication.) | src/engram/pack.py | general | Blake |
| [1/5] | ⚪ | `MAX_SYMBOLS_PER_PACK = 40` and `RETRIEVAL_K = 5` ship as module constants while the PRD says caps are config. Neither appears in the PRD nor in the `[pack]` table; the 40-cap silently drops changed symbols past the 40th from retrieval. | src/engram/pack.py | general | Blake |
| [1/5] | ⚪ | Config validation failures reach the user as tracebacks: `load_config()` raises `ValueError` and all four verbs call it outside any try block, so a mistuned `[pack]` table bricks every command with a stack dump. | src/engram/cli.py | 3 | Blake |
| [1/5] | ⚪ | Scope creep in the CLI: `--prd`/`--capsule` auto-discovery and `--diff` leaving `engram-pack-diff-{id}.diff` behind with no cleanup. (The design specified the defaults — see Adjudication.) | src/engram/cli.py | 5 | Blake |
| [1/5] | ⚪ | Wiring landed in SKILL.md step 3, not in the `references/agent-invocation.md` staging steps the PRD names, and the PRD's `agent-prompts.md` / `blind-lens-prompt.md` do not exist. The premise re-check the PRD mandated ("skip and report on material drift") produced no visible report. | ~/.claude/skills/review-work-completion/SKILL.md | general | Blake |
| [1/5] | ⚪ | `_render_pointer` emits `- {origin}\n  {body}` with only the first body line indented and no code fence, so every multi-line code chunk breaks out of the markdown list after line one. | src/engram/pack.py | 4 | Alice |
| [1/5] | ⚪ | `build(store, config, ...)` leaves its two most important params untyped where every sibling (`query`, `index`, `harvest`) annotates `store: Store, config: EngramConfig`. | src/engram/pack.py:220-222 | 4 | Eve |
| [1/5] | ⚪ | The Reuse-precedent self-repo filter is behavior beyond the design with no test pinning it: the scope-filter test asserts the foreign chunk appears in Reuse but never asserts the local chunk is absent. | src/engram/pack.py | 4 | Alice |
| [1/5] | ⚪ | De-slop: the no-pack test's two `/pack/i` `doesNotMatch` assertions are fully subsumed by the byte-identity golden equality on the next line, and will false-fail on innocent future wording ("package") in any persona body. | ~/.claude/workflows/registry-parity.test.mjs:150,161 | 9 | Eve |

### Out of scope (carried, confirmed real, not this PRD's diff)

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [2/5] | 🟡 | The codex no-edit probe uses an invocation-cwd-relative pathspec, so for any task whose files sit outside that cwd it matches nothing and false-latches `codex_no_edit: true`. **Eve confirms it is real but out of scope**: the file is not in this PRD's diff range (verified via `git --git-dir=/Users/bob/.buvis diff --stat`); it belongs to the work skill and needs its own fix. | ~/.claude/skills/work/SKILL.md:440 | 7 | Bob, Carl (scoped out by Eve) |

### Advisory (local model, unconfirmed)

- (none — Quinn was unavailable; see Agent Status)

## Adjudication of design-gate-accepted items

Blake is blind by construction and cannot know what the design gate accepted. Three of his findings land on deliberately-accepted decisions and are recorded here rather than silently dropped:

1. **🔴 doubt lens gets the full pack.** Accepted at the design gate with explicit reasoning (design doc, Interfaces "Claude lens wiring, precisely — and its one honest limitation", and Alternatives #6): Bob is ONE dispatch reading ONE assembled prompt, so `{PACK_FINDINGS}`'s placement signals emphasis and cannot make `{PACK_FILE}` invisible in the same call. True isolation is only achievable for Eve's separate dispatch. Eve independently placed this in her KNOWN bucket with the same reasoning. **However**, Blake's second half is NOT covered by that acceptance: he reports the skill's own test re-labels Bob as consensus to make the assertion pass, and finding [2/5] above shows Eve's dispatch — the one path where the guarantee is real — never substitutes `{PACK_FINDINGS}` at all. So the accepted limitation is wider in practice than the gate assumed.
2. **🟠 pre-pack reindex is repo-scope only.** Accepted (design Alternatives #5 and Risks): a portfolio reindex would immediately retrigger PRD 00002's measured embedding-backend crash, so the design chose loud disclosure over the attempt. Blake's "permanent stale-data disclaimer wired in as a string constant" is a fair characterization of the accepted trade, not a new defect.
3. **🟡 export signatures / ⚪ CLI scope creep.** The design deliberately redefined `changed_symbols` and `build` signatures (threading `repo_root`/`source_ref` was a blocker fix in dispatch 2) and deliberately added `--prd`/`--capsule` with convention defaults (also a blocker fix — Task prose would otherwise always render empty). Both are documented deviations, not drift.

Blake's remaining findings — the unconfigurable PRD caps, the missing-diff error case, and the `gather-context.sh` fail-open — are NOT covered by any gate acceptance and stand.

## Alice

20 findings, listed in the consolidated tables above. Full raw output: `dev/local/tmp/alice-output-00004-c1.txt`.

R1: fail
R2: pass
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

## Blake

16 findings including the cycle's only 🔴, listed above. Blind lens: PRD + rubric only, no diff, no context file, no design doc, no pack. Full raw output: `dev/local/tmp/blake-output-00004-c1.txt`.

B1: fail
B2: fail
B3: fail
B4: fail
B5: fail
B6: fail
B7: pass
B8: pass
B9: pass
B10: fail
B11: pass
B12: pass
B13: pass
B14: fail
B15: fail
B16: fail
B17: pass
B18: pass
B19: pass

## Bob

14 findings plus FIX/VERIFY/KNOWN buckets, listed above. Static analysis only (sandbox); he correctly emitted `Cannot statically verify` for test execution. Full raw output: `dev/local/tmp/bob-output-00004-c1.txt`.

R1: fail
R2: pass
R3: pass
R4: fail
R6: pass
R7: fail
R8: fail
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

15 findings, listed above. Could not read `/Users/bob/.claude` (permission denied) and could not execute any test suite; reviewed the engram diff plus the staged buvis diff file. No frontend surface in this change — he reviewed as a generalist, correctly declining to invent UI findings. Full raw output: `dev/local/tmp/carl-output-00004-c1.txt`.

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

## Quinn

⚠️ Unavailable. Both the initial dispatch and the one permitted retry failed with `[llama-cpp] failed to reach http://localhost:8080/v1/models: fetch failed`, while `qwen-run.sh --preflight --approved-only` passed twice on provider `llamacpp8001` and the retry forced `-P llamacpp8001`. The backend is healthy; `pi` ignores the resolved provider and probes :8080. Advisory weight only, so no follow-up tasks are lost.

## Eve

13 FIX, 1 VERIFY, 4 KNOWN. She independently verified the suites live and confirmed that the scope-filter, exclusion-union, batching, determinism, hard-cap and blind-lens metrics **are** genuinely pinned by tests — then found what the confident pass missed, including the per-added-line symbol explosion she reproduced live. Full raw output: `dev/local/tmp/eve-output-00004-c1.txt`.

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

Verdict: 35 findings
