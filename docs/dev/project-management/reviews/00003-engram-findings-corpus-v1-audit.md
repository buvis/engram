# Decision Audit Log: 00003-engram-findings-corpus-v1

PRD: `00003-engram-findings-corpus-v1.md`
Started: 2026-08-02T20:56:52Z
Completed: 2026-08-03T03:59:35Z
Autonomous: 7  |  Deferred: 23  |  Doubts: 0

### [autonomous] 2026-08-02T20:56:52Z

**Decision**: Whether to proceed with PRD 00003 given the capsule's known 00002 task-5 client.py embedding-batching defect that will likely also block 00003's own index/harvest execution task.

**Recommendation**: Proceed - schema/logic tasks deliver value independent of the blocker, and the loop-mode stall procedure handles a recurrence at the execution task without wasting the batch.

**Choice**: Proceeded with PRD 00003.

**Rationale**: Schema/logic tasks (parser, store, retrieval, CLI verb) do not depend on a working embedding client; only the execution/index task does, and that task already has a stall procedure to fall back on.

### [autonomous] 2026-08-02T20:56:52Z

**Decision**: Design for PRD 00003 - how findings records are stored and reused against the existing chunks schema.

**Recommendation**: Reuse the existing chunks table (corpus=findings) with atomic replace-on-re-harvest via a new `Store.replace_chunks_for_source`, keyed on (corpus, path) per the PRD dedup contract.

**Choice**: Adopted the reuse design; ran 3 adversarial review dispatches (claude, codex, codex-verification), fixing 2 cardinal-sins and 19 blockers (rebuild data-loss, missing main() dispatch branch, missing imports, incomplete parser contract check, path-canonicalization dedup bug, findings unretrievable after source-file trash, purge_devlocal.py control-flow/timeout/ledger-ordering bugs).

**Rationale**: Reusing the existing corpus/chunks mechanism avoids a new storage layer for a data shape (findings) that fits the existing schema; the adversarial dispatches surfaced concrete data-loss and control-flow defects before implementation, cheaper to fix at design time than after code exists. Non-blocking items carried into planning: `Store.status()` false-staleness for findings rows, `EMBED_MAX_CHARS` truncation (pre-existing system-wide), claude-home not repo-scope-queryable (pre-existing limitation), and an unresolved tmp/-scope question for catchup opportunistic harvest.

### [autonomous] 2026-08-02T20:56:52Z

**Decision**: Task 1 scope boundary and `Record.heading`/severity/consensus-tag semantics, left as example wording ("e.g. finding title, or section heading") in the PRD/design rather than a precise contract, while real review files use white-circle (LOW) severity heavily and mix bulleted findings with and without a `[n/m]` consensus tag.

**Recommendation**: Scope task 1 to FINDINGS_CORPUS + Record + parse() only (upsert() belongs to task 2); pin heading = table Issue-column cell / first bold span on a bullet / nearest preceding markdown heading for unstructured lines (empty string if none); widen the severity emoji set to include white circle; treat the consensus tag as optional; unstructured fallback emits one Record per non-blank unmatched body line.

**Choice**: Implemented task 1 per this pinned interpretation.

**Rationale**: The PRD/design text was illustrative, not a precise contract, and real review files (the actual input corpus) needed a concrete rule to parse correctly - the assumption was the simplest one consistent with both the design's stated intent and the observed file shapes.

### [autonomous] 2026-08-02T20:56:52Z

**Decision**: The design doc logged catchup's `tmp/` scope as an unresolved question for `/plan-tasks` or the PRD author, and neither resolved it - which files should the catchup opportunistic harvest step match?

**Recommendation**: Resolve from the PRD's Inputs line, which is explicit for catchup (unlike the purge sweep): reviews satellites + `dev/local/tmp` review outputs, narrowed to a `*review*.md` pattern.

**Choice**: Catchup harvests `dev/local/reviews/*.md` plus `dev/local/tmp/*review*.md`. Purge-side scope (task 5) left unchanged: `reviews/` only, per the design.

**Rationale**: A bare `*review*` glob also matches non-markdown artifacts (e.g. `review-diff-<epoch>-<pid>.diff`) that `engram harvest` cannot parse, which would fail on every catchup run - the `.md` extension filter is a necessary narrowing the PRD text did not spell out but the Inputs line supports.

### [autonomous] 2026-08-02T21:24:45Z

**Decision**: Cycle-1 review decision gate: how to route 10 consolidated findings (all mechanical or additive, none modifying a public signature or schema).

**Recommendation**: Classify all 10 as AUTO-FIX and queue them as [D1] rework tasks: (1) Store.status findings exemption; (2) move the --rebuild preservation block inside the rebuild error boundary; (3) an end-to-end zero-loss test; (4) findings.parse decomposition plus _is_separator_row extraction; (5) one embed-text projection helper for all three call sites; (6) _harvest_path extraction plus type annotations; (7) process_store untangling in purge-devlocal; (8) real-review-file parser fixtures plus dead-import removal; (9) OSError catch in _resolve_repo_for_path plus consolidation with cli._resolve_repo_name; (10) explicit OSError/yaml.YAMLError catch replacing a bare except Exception.

**Choice**: Queued all 10 as rework tasks 7-16.

**Rationale**: None modified a public signature or schema; items 9 and 10 in particular restore behavior the approved design specified but the implementation dropped, making them clear-cut fixes rather than judgment calls. Full detail in `dev/local/reviews/00003-engram-findings-corpus-v1-review-1.md`.

### [autonomous] 2026-08-02T21:24:45Z

**Decision**: Cycle-2 review-decision gate: how to handle 30 unresolved findings when cycle 2 == rework_cap 2, with no reviewer rating anything CRITICAL.

**Recommendation**: Cap-out - defer all 30 as `cap-overflow` and hand off to finalize as converged-with-deferrals, rather than stalling the PRD, since the loop-mode cap-out branch only stalls on an unresolved CRITICAL.

**Choice**: Deferred all 30 findings to the batch deferred JSON with full reproduction detail; PRD marked converged-with-deferrals, not stalled.

**Rationale**: The two highest-severity items (a claude-home index regression from task 15, and the still-unproven purge-to-query zero-loss chain from task 9) are both high, not critical, and both are fully recorded with reproduction steps in `dev/local/reviews/00003-engram-findings-corpus-v1-review-2.md` and the deferred JSON - nothing is silently dropped. Continued polishing past the rework cap is not the loop's job; escalation to the human batch-end review is.

### [autonomous] 2026-08-02T21:24:45Z

**Decision**: Quinn (local qwen, advisory weight) failed cycle 1 with a connection error against port 8080 while the preflight passed against provider `llamacpp8001` - how to spend cycle 2's one retry.

**Recommendation**: Pin the retry to the preflight-validated provider (`-P llamacpp8001`) instead of re-running the identical failing command, rather than burning the retry on an exact repeat.

**Choice**: Ran the pinned retry; it failed identically, then Quinn was marked unavailable for the cycle.

**Rationale**: Cycle 1 had already spent its retry on an identical re-dispatch with an identical failure, leaving the cause open. Amending the invocation is what the retry policy permits, and it converted a recurring mystery into a diagnosed tooling defect (the model id is registered under both providers in models.json, so `pi` resolves by id and ignores the `-P` pin). Quinn is advisory weight, so no consensus finding was lost.

### [deferred] 2026-08-02T21:24:45Z (cycle 1)

**Decision**: Cycle-1 decision gate deferred 21 findings for PRD 00003 to batch-end review (full detail in `dev/local/autopilot/deferred/202608012229-deferred.json`). Two CRITICAL (deferred per the framework rule that critical severity always defers): (a) `no_repo` is a terminal harvest outcome so an unregistered repo never gets its review satellites trashed, forever, and the obvious fix (exit 0 on `no_repo`) would cause the exact data loss the PRD prevents; (b) the pre-trash sweep selects candidates by path shape rather than review-file-contract shape, making non-contract markdown in `reviews/` permanently un-GC-able. Five requirements-ambiguity or deployment items: the PRD-vs-design Record field contract, record granularity vs. the top-5 retrieval success metric, `engram` absent from PATH making both Phase 2 integrations inert as deployed, the claude-git-ferry release flow never running, and blind-lens-flagged scope creep on the design-mandated query/rebuild changes. One PRD-authoring gap (the PRD 00002 section that never existed), confirmed by four lenses. Plus 12 scope-overflow items past the top-10 rework cap and one reviewer-unavailable note for Quinn.

**Recommendation**: Human call needed on both criticals (fix direction is not obvious - see the two options above); the requirements-ambiguity items need a human to choose between PRD text and the approved design; the scope-overflow items are queued for the next touch past the cap.

**Choice**: Deferred to batch-end review.

**Rationale**: Critical severity always defers per `references/decision-framework.md`; the ambiguity items are PRD-vs-design divergences only a human can resolve; the scope-overflow items exceeded the loop-mode top-10 rework cap.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: REGRESSION - task 15's resolver consolidation gave `cli._resolve_repo_name` the claude-home sentinel, which the approved design explicitly ruled out of scope; `engram index` from inside `~/.claude` now silently exits 0 instead of failing loudly.

**Recommendation**: In `_run_index`, reject a repo scope that resolved to the claude-home sentinel with the existing portfolio hint; keep the sentinel for query/status where it is correct.

**Choice**: Deferred to batch-end review (high severity / cap-overflow, 1/5 consensus). Found by Eve (Fable doubt lens) - the only lens that caught it.

**Rationale**: Cycle 2 was at the rework cap with no CRITICAL findings, so this high-severity regression was recorded with full reproduction detail (cli.py:32, cli.py:176) rather than triggering a third rework cycle.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: Task 9 did not close its cycle-1 finding - the new test replaces the purge leg with `review_path.unlink()` and never executes purge_devlocal.py, so the purge-to-real-harvest-to-deletion-to-query chain has still never run as one sequence, leaving the PRD's headline exit criterion unproven.

**Recommendation**: Run purge_devlocal.py --apply against a fixture repo with an aged review satellite, a real engram on PATH and llama-server reachable; assert the satellite landed in .trash and a portfolio query returns the finding.

**Choice**: Deferred to batch-end review (high severity / cap-overflow, 3/5 consensus). Found by Bob, Alice, Eve.

**Rationale**: Same cap-out reasoning as above - high, not critical, fully documented for the human review.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: Task 8 fixed one of two rebuild error-boundary leaks - the first boundary (`open_store(tmp_path)` + `index()`) still returns 1 without closing `tmp_store.conn` or unlinking `.rebuild-tmp`, six lines above the boundary it did fix.

**Recommendation**: Mirror the second boundary's cleanup: pre-bind `tmp_store = None`, close if bound, unlink with `missing_ok=True`.

**Choice**: Deferred to batch-end review (medium severity / cap-overflow, 3/5 consensus). Found by Alice, Blake, Eve.

**Rationale**: Cap-out; recorded for the next touch.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: `process_store()` came down to 55 lines after extraction - genuinely improved nesting (6 to 3 levels) but still over the 50-line limit the task existed to clear.

**Recommendation**: Extract the summary/verbose reporting block into a `_print_store_report` helper.

**Choice**: Deferred to batch-end review (medium severity / cap-overflow, 2/5 consensus). Found by Alice, Bob.

**Rationale**: Cap-out; small remaining extraction.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: Task 15's consolidation reaches across modules for a private name and fabricates a synthetic path (`Path.cwd() / "_"`) to fit the existing signature, needing a 3-line comment to explain it; the design contract specified `cwd=path.parent` or the path itself if a directory.

**Recommendation**: Make the resolver public and directory-oriented (`resolve_repo_for_dir(dir_path)`); harvest passes `path.parent`, cli passes `Path.cwd()`.

**Choice**: Deferred to batch-end review (medium severity / cap-overflow, 2/5 consensus). Found by Alice, Eve.

**Rationale**: Cap-out; a clean refactor queued for the next touch.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: Task 15 did not close its cycle-1 finding either - `read_repos_csv` guards only `FileNotFoundError`, so a sibling `PermissionError` escapes uncaught, and `_harvest_path` calls the resolver outside any try, aborting the whole batch with a traceback (also affects `engram query --scope repo`).

**Recommendation**: Widen the guard to `except OSError: return None`.

**Choice**: Deferred to batch-end review (medium severity / cap-overflow, 1/5 consensus). Found by Alice.

**Rationale**: Cap-out; per-file isolation contract still not fully closed.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: Task 16 did not fully close its cycle-1 finding - the blank-reviewers check stringifies a whole collection (`str(reviewers or "").strip()`), so `reviewers: ["   "]` becomes `"['   ']"` and passes, while the scalar case is correctly rejected.

**Recommendation**: Validate scalar and collection members individually and require at least one non-blank reviewer.

**Choice**: Deferred to batch-end review (medium severity / cap-overflow, 1/5 consensus). Found by Bob.

**Rationale**: Cap-out; collection-case gap remains.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: Task 13's two style commits reformat ~60 lines the untangle never needed, and the argparse expansion pushes `main()` from 36 to 52 lines - a new 50-line breach introduced by formatting, not the fix itself.

**Recommendation**: Revert the unrelated reformatting or split main()'s argparse block into a `_build_parser` helper.

**Choice**: Deferred to batch-end review (medium severity / cap-overflow, 1/5 consensus). Found by Alice.

**Rationale**: Cap-out; formatting-caused regression.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: Task 15 adds 68 lines and a duplicate `_init_git_repo` helper to `tests/test_cli.py`, which cycle 1 already flagged as over the 800-line file limit and deferred.

**Recommendation**: Move the resolver tests to a focused module or reuse the existing `test_harvest.py` helper.

**Choice**: Deferred to batch-end review (medium severity / cap-overflow, 1/5 consensus). Found by Bob.

**Rationale**: Cap-out; compounds the already-deferred file-size finding.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: The consolidated resolver compares the git toplevel to the raw repos.csv string with `==` and no normalization, so a non-canonical registration (trailing slash, symlink, `~`-relative path) silently yields `no_repo`, indistinguishable from "not a git repo."

**Recommendation**: Normalize both sides with `Path.resolve()` before comparing.

**Choice**: Deferred to batch-end review (medium severity / cap-overflow, 1/5 consensus). Found by Blake (blind lens).

**Rationale**: Cap-out; normalization gap.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: `index --rebuild` reads findings from the live DB, re-embeds them, then `os.replace`s the whole database - check-then-act with no lock and no `busy_timeout`; a concurrent harvest committing inside that window is silently lost, and findings are the one corpus whose source file is already trashed.

**Recommendation**: Consider a lock file or a store-level guard around rebuild; compounds the deferred no-`busy_timeout` finding.

**Choice**: Deferred to batch-end review (medium severity / cap-overflow, 1/5 consensus). Found by Blake (blind lens); new this cycle.

**Rationale**: Cap-out; a data-loss window worth human attention but not CRITICAL by itself.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: `store.status()` gained the findings exemption, but the PRD's Structural Decomposition scopes store.py edits narrower than what shipped - the change itself is right, but the PRD text was never updated to sanction it.

**Recommendation**: Amend the PRD's Structural Decomposition at batch end; not a code defect.

**Choice**: Deferred to batch-end review (medium severity / cap-overflow, 1/5 consensus). Found by Blake (blind lens).

**Rationale**: PRD-authoring gap, documentation-only.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: Simplification opportunity - `_harvest_path` stages `path.resolve()` in a local and reassigns `path` on the next line, rather than assigning directly.

**Recommendation**: One-line cleanup.

**Choice**: Deferred to batch-end review (medium severity / cap-overflow, 1/5 consensus). Found by Carl.

**Rationale**: Cap-out; trivial style nit.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: The new OSError catch discards its cause - the resolver returns bare `None`, so `_harvest_path` reports `no_repo` with `error=None`, indistinguishable from an unregistered path in both the CLI summary and the purge WARN.

**Recommendation**: Surface the caught exception string in `FileHarvestResult.error`; compounds the deferred cycle-1 finding that `no_repo` results carry no error text.

**Choice**: Deferred to batch-end review (low severity / cap-overflow, 2/5 consensus). Found by Alice, Eve.

**Rationale**: Cap-out; compounding with an existing deferred item.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: The CHANGELOG overclaims task 16 - it says only OSError/yaml.YAMLError count as parse failures, but every contract violation (missing frontmatter, blank reviewers, missing Verdict:/Tests:) also raises ValueError and reports parse_failed.

**Recommendation**: Reword the CHANGELOG bullet to distinguish contract ValueError failures from exceptions newly converted to ValueError.

**Choice**: Deferred to batch-end review (low severity / cap-overflow, 2/5 consensus). Found by Alice, Bob.

**Rationale**: Cap-out; documentation wording fix.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: Task 7's exemption adds a third hardcoded "findings" literal beside prune()'s existing check and `findings.FINDINGS_CORPUS`, so the corpus name now lives in three places and two break silently if the constant changes.

**Recommendation**: Eve rates this KNOWN/out-of-scope (relocating the constant reshapes 00001 module boundaries); fold into the existing deferred duplicate-corpus-name finding.

**Choice**: Deferred to batch-end review (low severity / cap-overflow, 2/5 consensus). Found by Alice, Eve.

**Rationale**: Cap-out; overlaps an already-deferred item.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: `findings.parse` is still exactly 50 lines after decomposition, and the three extracted helpers each mutate the caller's records list while returning a different undocumented control value.

**Recommendation**: Move the frontmatter+Verdict+Tests checks into a `_validate_contract` helper and document each helper's return.

**Choice**: Deferred to batch-end review (low severity / cap-overflow, 1/5 consensus). Found by Alice.

**Rationale**: Cap-out; readability improvement only.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: NEW this cycle - `findings.parse` does an unguarded `path.read_text()` with no size cap, on paths supplied by the purge sweep and catchup globs, loading the whole file before any contract check.

**Recommendation**: Cap the read or stat the file first.

**Choice**: Deferred to batch-end review (medium severity / cap-overflow, 1/5 consensus). Found by Blake (blind lens).

**Rationale**: Cap-out; new finding at cap, recorded rather than triggering a third cycle.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: NEW this cycle - the purge sweep's 300s per-file subprocess timeout can be exceeded by a cold `engram harvest` that spawns llama-server and downloads a GGUF model; the spawned server is never stopped, and a cold machine can time out on every review file.

**Recommendation**: Consider a longer first-run budget or a pre-warm step; the design justified 300s specifically to cover cold start, but a first-ever model download can still exceed it.

**Choice**: Deferred to batch-end review (medium severity / cap-overflow, 1/5 consensus). Found by Blake (blind lens).

**Rationale**: Cap-out; deployment/ops consideration.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: NEW this cycle - the PRD success metric "a precedent query for a known past finding's pattern returns its record in top-5" is unmeasured; there is no goldset entry for corpus=findings and no rank assertion in any test.

**Recommendation**: Add a goldset entry for corpus=findings with a rank assertion - the one PRD success metric with no evidence either way.

**Choice**: Deferred to batch-end review (medium severity / cap-overflow, 1/5 consensus). Found by Blake (blind lens).

**Rationale**: Cap-out; the shipped 79-line fixture yields 45 records (28 noise), all competing in the same hybrid ranking - worth measuring before trusting the metric.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: Blake's cycle-2 blind pass independently re-derived 10 findings that cycle 1 had already deferred, being blind by construction and unable to know what was already deferred.

**Recommendation**: No new tasks - recorded as corroboration that a second independent lens reached the same conclusions from the spec alone.

**Choice**: Logged as blind-corroboration, no action.

**Rationale**: Strengthens the case for fixing the originals rather than adding duplicate tracking.

### [deferred] 2026-08-02T21:24:45Z (cycle 2)

**Decision**: Root cause found for the cycle-1 Quinn (local qwen) dispatch failure - the model id is registered under both `llamacpp` (not live) and `llamacpp8001` (live) providers in `~/.pi/agent/models.json`, so `pi` resolves by model id and ignores the `-P` provider pin regardless of preflight result.

**Recommendation**: Fix in use-qwen - de-duplicate the model id across providers, or teach `qwen-run.sh` to pass an explicit baseUrl rather than a provider name.

**Choice**: Logged as reviewer-unavailable (tooling defect), no PRD-scoped action; supersedes the cycle-1 open record.

**Rationale**: Quinn is advisory weight, so no consensus finding was lost in either cycle - this is an infrastructure fix outside the PRD's scope.
