---
prd: dev/local/prds/wip/00003-engram-findings-corpus-v1.md
review: 2
date: 2026-08-03
head_sha: d04d02d7fec7222c39e6b3accfe45e9c128ba1ec
codex_thread_id: 019fc52b-032f-7c23-9815-c8e55514fa69
reviewers: alice,blake,bob,carl,eve
agents:
  alice: available
  blake: available
  bob: available
  carl: available
  eve: available
  quinn: unavailable
---

# Review: 00003-engram-findings-corpus-v1

Diff range: `6400947947b896b42ba7165f34aad8b87ba06eaa..d04d02d7fec7222c39e6b3accfe45e9c128ba1ec`
(engram, the ten `[D1]` rework tasks 7-16). Task 13 lives in the `~/.buvis` bare
repo: `048023953..e1e50a903` on `.claude/skills/purge-devlocal/`. Both were
concatenated into `dev/local/tmp/review-diff-all-00003-c2.diff` and handed to
every implementation-aware lens. claude-git-ferry has no new commits since
cycle 1, so no third range this cycle.

**Incremental review.** Cycle 1 reviewed the full implementation (tasks 1-6);
this cycle scopes to the rework and asks two questions per finding: is the
cycle-1 defect actually resolved, and did the rework regress anything.

codex_rung_guard: fired (1 codex-implemented task(s))

## Review Summary

Reviewed: 16 completed tasks (10 under review this cycle)
PRDs checked: 00003-engram-findings-corpus-v1

### Agent Status

- Alice (consensus, Claude): ✅ Available
- Blake (blind, PRD-only): ✅ Available
- Bob (doubt + de-slop, codex, resumed cycle-1 thread `019fc52b`): ✅ Available
- Carl (UI/generalist, gemini via copilot): ✅ Available
- Eve (doubt, Fable 5): ✅ Available — activated by the codex doubt-roster guard
- Quinn (local qwen, advisory): ⚠️ Unavailable — see below

### Quinn's failure, diagnosed (recurrence of the cycle-1 symptom)

Cycle 1 recorded Quinn failing twice with
`[llama-cpp] failed to reach http://localhost:8080/v1/models: fetch failed`
while the step-1 preflight passed against provider `llamacpp8001`, and left the
cause open. This cycle reproduced it and found the cause.

The retry was spent on `qwen-run.sh -P llamacpp8001` — pinning the provider the
preflight validated. It failed identically, and the run log shows why:

```
Using provider 'llamacpp8001' model 'unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q6_K_XL'
[llama-cpp] failed to reach http://localhost:8080/v1/models: fetch failed
```

`qwen-run.sh` resolves provider and model correctly, but the model id
`unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q6_K_XL` is registered under **both** providers
in `~/.pi/agent/models.json` — `llamacpp` (`baseUrl` `http://127.0.0.1:8080/v1`,
not live) and `llamacpp8001` (`http://127.0.0.1:8001/v1`, live). `pi` resolves
the model by id and takes the first provider listing it, so `-P` is overridden
by the duplicate registration. The preflight passes because it probes the
resolved *provider*; the dispatch fails because `pi` re-resolves by *model id*.

This is a tooling/registry defect, not an engram finding. It is recorded here so
the next cycle does not re-diagnose it: the fix is to de-duplicate that model id
across the two providers in `models.json` (or teach `qwen-run.sh` to pass an
explicit baseUrl). Quinn is advisory weight, so no consensus finding was lost.

### Consolidation note (fail-loud)

`consolidate-findings.sh` ran successfully (exit 0) over ALICE, BLAKE, BOB and
CARL — the four reviewers whose output uses the `[AGENT] {emoji} … | File: … |
Task: …` issue-line contract. **Its output is not usable as a consensus signal
and is not reproduced as the headline table.** As in cycle 1, the script keys
duplicate detection on exact normalized description text, so it emitted 33 rows
every one of which scored `[1/4]` — including the `process_store()` 55-line
finding that Alice and Bob both raised in nearly the same words, and the
CHANGELOG overclaim both also raised. The raw script output is reproducible from
the per-agent files under `dev/local/tmp/`.

The Consolidated Findings below are therefore a **model-side semantic merge** of
the same four outputs plus Eve's, grouping findings that name the same defect
regardless of wording. Consensus is `N/5` over the five reviewers that ran
(Quinn excluded — he produced no output).

Eve is counted in the denominator but was NOT passed to
`consolidate-findings.sh`: her lens emits the doubt contract (FIX / VERIFY /
KNOWN + `D{n}` verdicts), not issue lines, so the script would have parsed zero
findings from her file while still inflating the denominator — deflating every
score. Her findings are merged by hand below and reproduced in full in her own
section.

### Orchestrator verification

Three findings were checked directly against the source rather than taken on a
reviewer's word. All three confirmed:

- **Eve's `claude-home` regression** — `cli.py:32` returns the sentinel;
  `_resolve_scope` (`cli.py:35-41`) therefore returns `Scope("repo",
  "claude-home")` instead of `None`, so `_run_index`'s `scope is None` guard
  (`cli.py:176-179`) never fires and the command exits 0 having indexed nothing.
- **Alice's escaping `PermissionError`** — `harvest.py:57-60` guards
  `read_repos_csv` with `except FileNotFoundError` only; `PermissionError` is a
  sibling `OSError` subclass and escapes. `_harvest_path` calls the resolver
  outside any `try` (`harvest.py:80`).
- **Bob's whitespace-collection gap** — `findings.py:126-127` is
  `str(reviewers or "").strip()`, so `reviewers: ["   "]` stringifies to
  `"['   ']"` and passes the non-blank check.

## Consolidated Findings

### In scope — the rework itself (tasks 7-16)

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [1/5] | 🟠 | **Regression.** Task 15's resolver consolidation gave `cli._resolve_repo_name` the `claude-home` sentinel, which the design explicitly ruled out of scope ("Extending `_resolve_repo_name` with a matching fallback would be scope creep"). `engram index` (default or `--scope repo`) from inside `~/.claude` used to fail loudly with "not inside a registered repo; pass --scope portfolio instead" (exit 1); it now resolves to `Scope("repo", "claude-home")`, matches zero enumerated corpus files, prints nothing and exits 0 — a fake success. **Verified against source.** | src/engram/cli.py:32,176 | 15 | Eve |
| [3/5] | 🟠 | **Task 9 did not close its cycle-1 finding.** The new test replaces the purge leg with `review_path.unlink()` and never executes `purge_devlocal.py`, while the purge-side suite still monkeypatches `subprocess.run` at all 8 harvest call sites. The sequence the cycle-1 finding named — purge → real `engram harvest` → source deletion → query — has still never run as one chain, so the PRD's headline exit criterion remains unproven. | tests/test_harvest.py:568 + purge-devlocal test_purge_devlocal.py | 9 | Bob, Alice, Eve |
| [3/5] | 🟡 | **Task 8 fixed one boundary of two.** `_run_index --rebuild`'s first boundary (`open_store(tmp_path)` + `index()`) still returns 1 without closing `tmp_store.conn` or unlinking `.rebuild-tmp` — the exact leak class the task claimed to fix, six lines above the boundary it did fix. | src/engram/cli.py:156-161 | 8 | Alice, Blake, Eve |
| [2/5] | 🟡 | **Task 13 did not clear its limit.** `process_store()` came down from ~70 to 55 lines after `harvest_before_trash` was extracted (nesting genuinely fixed, 6 → 3 levels), but 55 is still over the 50-line limit the task was created to clear. | purge_devlocal.py:325-379 | 13 | Alice, Bob |
| [2/5] | 🟡 | Task 15's consolidation reaches across modules for a private name and fabricates a path to fit it: `cli` imports `_resolve_repo_for_path` from `harvest` and calls it as `_resolve_repo_for_path(Path.cwd() / "_")`, needing a 3-line comment to explain the synthetic filename. The design contract specified `cwd=path.parent` "or path itself if a directory"; implementing that branch and making the helper public removes both the private import and the fake path. | src/engram/cli.py:28-32 | 15 | Alice, Eve |
| [1/5] | 🟡 | **Task 15 did not close its cycle-1 finding either.** `corpora.read_repos_csv` calls `read_text()` after its `exists()` check, and the resolver guards it with `except FileNotFoundError` only — a sibling `PermissionError` escapes. `_harvest_path` calls the resolver outside any `try`, so one unreadable `repos.csv` aborts the whole batch with a traceback, which is precisely the per-file isolation contract the task existed to enforce. Also tracebacks `engram query --scope repo`. **Verified against source.** | src/engram/harvest.py:57-60,80 | 15 | Alice |
| [1/5] | 🟡 | **Task 16 did not fully close its cycle-1 finding.** The blank-reviewers check is `str(reviewers or "").strip()`, which stringifies a whole collection — so `reviewers: ["   "]` becomes `"['   ']"` and passes. The scalar case (`reviewers: "   "`) is correctly rejected; the collection case is not. **Verified against source.** | src/engram/findings.py:126-127 | 16 | Bob |
| [1/5] | 🟡 | Task 13's two style commits (`5c4b3dab`, `e1e50a90`) reformat ~60 lines the untangle never needed (`KEEP_NAMES`, `find_stores`, `classify_artifact`, `_dedup_dest`, `trash_file`, the argparse block, `re.M`→`re.MULTILINE`), and the argparse expansion pushes `main()` from 36 to 52 lines — a **new** 50-line breach introduced by formatting, not by the fix. | purge_devlocal.py:382-433 | 13 | Alice |
| [1/5] | 🟡 | Task 15 adds 68 lines and a duplicate `_init_git_repo` helper to `test_cli.py`, which cycle 1 already flagged as over the 800-line limit and deferred. Move the resolver tests to a focused module or reuse the `test_harvest.py` helper. | tests/test_cli.py:1028 | 15 | Bob |
| [1/5] | 🟡 | The resolver compares the git toplevel to the raw `repos.csv` string with `==` and no normalization, so a non-canonical registration (trailing slash, symlink, `~`-relative path) silently yields `no_repo`, indistinguishable from "not a git repo". | src/engram/harvest.py | 15 | Blake |
| [1/5] | 🟡 | `index --rebuild` reads findings from the live DB, re-embeds them, then `os.replace`s the whole database — check-then-act with no lock and no `busy_timeout`. A `harvest` committing inside that window (a full portfolio reindex plus a re-embed of every finding) is silently lost, and findings are the one corpus whose source file is already trashed. | src/engram/cli.py | 8 | Blake |
| [1/5] | 🟡 | `store.status()` gained the findings exemption, but the PRD's Structural Decomposition scopes store.py edits to "prune logic gains the findings prune-exemption" with "other 00001 modules unchanged". The change is right (it closes cycle-1's 🟠 [4/5] status finding); the PRD text was never updated to sanction it. | src/engram/store.py | 7 | Blake |
| [1/5] | 🟡 | Simplification: assign `path = path.resolve()` directly rather than staging it in `resolved_path` and reassigning on the next line. | src/engram/harvest.py:70-78 | 12 | Carl |
| [2/5] | ⚪ | The new `OSError` catch discards its cause — the resolver returns bare `None`, so `_harvest_path` reports `no_repo` with `error=None` and a permission failure is indistinguishable from an unregistered path in both the CLI summary and the purge WARN. The new test asserts `outcome`/`records_count` only, locking the silence in. (Contrast: the `path.resolve()` branch does populate `error`.) | src/engram/harvest.py:47-54 | 15 | Alice, Eve |
| [2/5] | ⚪ | The CHANGELOG overclaims task 16: "only an unreadable file (`OSError`) or malformed frontmatter (`yaml.YAMLError`) counts as a parse failure" — every contract violation (missing frontmatter, blank `reviewers`, missing `Verdict:`/`Tests:`) also raises `ValueError` and reports `parse_failed`. The bullet describes which foreign exceptions get converted, not which failures count. | CHANGELOG.md:38 | 16 | Alice, Bob |
| [2/5] | ⚪ | Task 7's exemption adds a third hardcoded `"findings"` literal (`if corpus != "findings":`) beside `prune()`'s `AND chunks.corpus != 'findings'` and `findings.FINDINGS_CORPUS`. Eve rates this KNOWN/out-of-scope: relocating the constant reshapes 00001 module boundaries and the literal matches the cycle-1-reviewed one in `prune`. | src/engram/store.py:427 | 7 | Alice, Eve |
| [1/5] | ⚪ | `parse` is still exactly 50 lines after decomposition, and the three extracted helpers each mutate the caller's `records` list while returning a different undocumented control value (issue column / next index / current heading). | src/engram/findings.py:117-166 | 10 | Alice |

### Re-raised cycle-1 deferrals — no new tasks

Blake is blind by construction: he gets the PRD and nothing else, so he cannot
know which findings cycle 1 deliberately deferred. These restate findings
already recorded in `dev/local/autopilot/deferred/202608012229-deferred.json`.
They are listed for completeness and create no tasks. Blake's independent
re-derivation of them from the spec alone is corroboration of the originals, not
new information.

| Severity | Issue | File | Found By |
|----------|-------|------|----------|
| 🟠 | `no_repo` is a terminal harvest outcome making `engram harvest` exit nonzero; purge reads that as failure and never trashes the satellite. Blake newly confirms the blast radius: engram itself, agoge-gym, calcard-mcp and claude-loupe are all absent from the 26-row `repos.csv`. | src/engram/harvest.py | Blake |
| 🟠 | Durable records omit every PRD-specified field but repo — severity, file, verdict, PRD id and date survive only as raw text inside `body`. | src/engram/findings.py | Blake |
| 🟠 | The pre-trash sweep selects by path shape (`reviews/*.md`) rather than by the review-file contract. | purge_devlocal.py | Blake |
| 🟠 | Phase 2 catchup acceptance unmet: no claude-git-ferry release commit; the CHANGELOG entry still sits under `[Unreleased]`. | claude-git-ferry skills/catchup/SKILL.md | Blake |
| 🟡 | Line-granular unstructured fallback: the shipped fixture (79 lines) yields 45 records, 28 of them noise rows. Blake adds a **new** observation — the "known finding returns in top-5" success metric is *unmeasured*: no goldset entry for `corpus=findings` and no rank assertion in any test. | src/engram/findings.py | Blake |
| 🟡 | *(New this cycle)* `findings.parse` does an unguarded `path.read_text()` with no size cap, on paths supplied by the purge sweep and catchup globs. | src/engram/findings.py | Blake |
| 🟡 | *(New this cycle)* The purge sweep's 300s per-file timeout can be exceeded by a cold `engram harvest`, which may spawn llama-server and download a model; the spawned server is never stopped. On a cold machine the first purge run can time out on every review file. | src/engram/client.py | Blake |
| ⚪ | Module export signatures deviate from the PRD's Structural Decomposition. | src/engram/harvest.py | Blake |
| ⚪ | `Record.structured` is computed and then discarded — `upsert` never persists it. | src/engram/findings.py | Blake |
| ⚪ | purge-devlocal's SKILL.md and module docstring never mention the harvest sweep or the "kept because harvest failed" outcome. | purge-devlocal/SKILL.md | Blake |
| ⚪ | Catchup passes relative globs while the harvest contract specifies absolute paths; an unmatched glob is passed through literally. | claude-git-ferry skills/catchup/SKILL.md | Blake |
| ⚪ | No SQLite `busy_timeout`, so a concurrent harvest surfaces as "database is locked", is swallowed into `upsert_failed`, and is never retried. | src/engram/store.py | Blake |
| ⚪ | Cannot statically verify: reported test suites execute and pass (codex sandbox constraint). Resolved by the orchestrator's own foreground run — 288 passed. | N/A | Bob |

### Advisory (local model, unconfirmed)

- (none — Quinn was unavailable this cycle; see Agent Status.)

## Alice

Consensus lens, implementation-aware. Ran the suite herself. 10 findings: 5 🟡,
5 ⚪. Full output: `dev/local/tmp/alice-output-00003-c2.txt`.

Alice's central point: four of the ten rework tasks (8, 9, 13, 15) fixed the
symptom their cycle-1 finding named but not the defect — the second `--rebuild`
boundary, the purge half of the zero-loss chain, the 50-line limit, and the
resolver's isolation contract each survive.

Per-rule verdicts:

R1: pass
R2: pass
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

## Blake

Blind lens — PRD only, no diff, no design doc, no review history; found the code
himself across all three repos and ran both suites (engram 288 passed,
purge-devlocal 29 passed). 16 findings: 4 🟠, 6 🟡, 6 ⚪. Full output:
`dev/local/tmp/blake-output-00003-c2.txt`.

Most of Blake's set restates cycle-1 deferrals he could not know about. His
genuinely new contributions: the `--rebuild` check-then-act race, the
unmeasured top-5 success metric, the unguarded `read_text()`, the cold-start
timeout, and the `==`-without-normalization defect in the consolidated resolver.

Per-rule verdicts:

B1: fail
B2: fail
B3: fail
B4: fail
B5: fail
B6: fail
B7: pass
B8: pass
B9: pass
B10: pass
B11: pass
B12: fail
B13: pass
B14: fail
B15: pass
B16: pass
B17: fail
B18: pass
B19: pass

## Bob

Doubt + de-slop lens (codex, static-only sandbox), resumed on his cycle-1 thread
`019fc52b-032f-7c23-9815-c8e55514fa69` so he verified fixes against his own
earlier critique rather than re-reviewing from zero. 6 findings: 1 🟠, 3 🟡,
2 ⚪, plus the FIX/VERIFY/KNOWN buckets. Full output:
`dev/local/tmp/bob-output-00003-c2.txt`.

Bob is the only lens that caught the whitespace-collection gap in task 16's
validation — a direct check of whether the task he critiqued in cycle 1 actually
closed.

Per-rule verdicts (consensus rubric):

R1: fail
R2: fail
R3: pass
R4: fail
R6: pass
R7: fail
R8: pass
R9: fail
R10: pass
R11: pass
R12: fail
R13: fail

Doubt-rubric verdicts:

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Carl

Generalist lens (gemini via copilot). No frontend surface in this change, so
reviewed against the shared checklist. 1 finding: 1 🟡. Full output:
`dev/local/tmp/carl-output-00003-c2.txt`.

Carl's pass was thin this cycle — one simplification nit and an otherwise clean
rubric. Recorded as-is; his single finding is valid and nothing in his output
contradicts another lens.

Per-rule verdicts:

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
R13: fail

## Eve

Doubt lens (Fable 5), activated by the codex doubt-roster guard. 4 FIX, 1
VERIFY, 2 KNOWN. Eve ran both suites herself and verified the fixture is a
byte-exact copy of the real review file. Full output:
`dev/local/tmp/eve-output-00003-c2.txt`.

Eve confirmed six of the ten rework tasks as genuinely complete (parser
decomposition parity, status exemption, embed-text consolidation, `_harvest_path`
extraction, exception narrowing, purge refactor) and localized the residue to
task 15 — the one task that never received a per-task patch review because a
context-cap rotation cut it mid-flight. She is the only lens that found the
`claude-home` index regression.

Doubt-rubric verdicts:

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Quinn

⚠️ Unavailable. Dispatch and its one retry both failed with
`[llama-cpp] failed to reach http://localhost:8080/v1/models: fetch failed`.
Root cause diagnosed this cycle — see "Quinn's failure, diagnosed" above: a
duplicate model-id registration across two providers in `~/.pi/agent/models.json`
makes `pi` ignore the `-P llamacpp8001` pin. Advisory weight only; no follow-up
task would have been created from a Quinn-only finding.

## Follow-up Tasks Created

None. **Cycle 2 is the rework cap** (`rework_cap: 2`), so no rework is
dispatched from this cycle and no follow-up tasks are created. Under autopilot
loop mode a cap-out with no unresolved CRITICAL finding defers rather than
pauses: all 30 findings above are recorded as `cap-overflow` in
`dev/local/autopilot/deferred/202608012229-deferred.json` and the PRD proceeds to
finalize as converged-with-deferrals.

No reviewer rated anything 🔴 Critical this cycle. The highest severities are two
🟠 High findings — the `claude-home` index regression and the still-unproven
zero-loss chain — both deferred, not silently dropped.

Verdict: 30 findings
Tests: 288 passed, 0 failed, 0 skipped
