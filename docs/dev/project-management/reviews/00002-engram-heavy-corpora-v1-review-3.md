---
prd: docs/dev/project-management/prds/done/00002-engram-heavy-corpora-v1.md
review: 3
date: 2026-11-01
head_sha: 1a3b49fb840dbf5341192638777d44a7e9653109
reviewers: alice,blake,bob,sonnet
agents:
  alice: available
  blake: available
  bob: available
  sonnet: available
  carl: unavailable
---

# Review: 00002 finalization

Diff range: `7610ef534d8f6be61f5cd1dbe54c195d14c16b6b..1a3b49fb840dbf5341192638777d44a7e9653109`

codex_rung_guard: not fired

Fresh standalone review after the Kiro build handoff. The user's explicit target
includes `18913f4` through `1a3b49f`; base `7610ef5` includes all seven commits.
The done PRD is authoritative. No active state/tasks existed; no tasks were
fabricated, and the old review-2 thread was not resumed across this explicit range.

## Outcome

The new empty-source cache incorrectly remembered symbol read/parser failures.
Fixed in `ce71263`, with red/green regressions through the real symbol chunker
and one-time invalidation of legacy empty-code records. Also fixed capsule
selection residue, duplicate capsule tests, the enlarged harness function,
missing cache-failure coverage, self-derived token-budget assertions, stale
capsule text, and gold-set labeling/provenance. The requested PRD 00001
follow-ups are recorded in `2026-11-01-follow-ups.md`.

This is acceptance after adjudication, not a claim of unanimous clean review.
Pre-existing spec gaps and structural debt remain explicitly deferred below.
No production repin, live rebuild, or full harness rerun occurred. The historical
52-entry gate is unchanged evidence; three new decision entries are load-checked,
not retrieval-scored.

## Reviewer execution and limitations

- Alice and Blake ran as separate native Claude CLI sessions through
  `use-sonnet`, alias `sonnet`, effort `high`. Session records identify
  `claude-sonnet-5-5`. Blake received the PRD/rubric and test result, without
  the diff, implementation history, or other reviewers' findings.
- Bob's Codex CLI helper refused nested dispatch with exit 3. The prescribed
  Claude fallback ran separately at Sonnet/high and is named **Sonnet** below.
  A fresh native Codex subagent subsequently ran Bob's identical inlined
  snapshot to retain an independent OpenAI voice. Its exact host-selected model
  identifier is not exposed; no CLI restriction was disabled or bypassed.
- Both doubt reviews include the full de-slop lens and D1–D5 (the current names
  for the older doubt R1–R5 rubric). All expected R/B/D verdict lines are present.
- Carl's Gemini helper also refused nested dispatch, exit 3. No model inference
  ran. Optional Carl is unavailable; there is no false all-reviewers-pass claim.
- `review-stage` succeeded; its engram context pack failed because the installed
  CLI could not resolve this repo. The failure sentinel was carried into prompts.
- The stage's first fail-first replay could not find the worktree-relative venv.
  An absolute interpreter alone then imported the editable HEAD package, yielding
  an invalid all-pass replay. That result is discarded. The corrected replay set
  `PYTHONPATH=src`, selecting each temporary base worktree's source: 38 touched
  tests ran, 24 failed against base and 14 passed. The four MECH rows below retain
  every passing group. Replay worktrees were removed by the runner.
- The stage ran the full suite: 446 passed at the reviewed revision. Its parser
  expects PASS/FAIL/SKIP/EXIT summaries, so it could not parse pytest's native
  summary; the actual pytest log supplies the counts. No verification record was
  hand-written. A first `autopilot verify` on the repair tree correctly refused
  uncommitted source changes. After commit, native pytest passed but the wrapper
  returned exit 3 for its unsupported summary. A temporary adapter then emitted
  measured pytest counts in the required format; `autopilot verify` returned 0
  and recorded 453 passed, 0 failed, 0 skipped at `ce71263`.
- The wrapper's standalone dispatch rows were absent; the review records the
  actual backends, raw outputs, exit-3 refusals, and native subagent recovery here.

## Consolidated Findings

| Ref | Consensus | Severity | Issue | File | Task | Found By |
|-----|-----------|----------|-------|------|------|----------|
| R1 | [2/4] | 🟡 | Other function-size violations predate this change: index measures 84 lines after this diff, ensure_served 68, _baseline_hit_rate 58, and pack.build 54. | src/engram/indexer.py:23 | general | BOB, SONNET |
| R2 | [2/4] | ⚪ | `_max_chars_for` no longer caches a `/props` miss. An endpoint that never serves `/props` now gets one extra failed HTTP request on every `embed()` call, which is once per file during indexing. It is cheap, but it is a cost the old code avoided. | src/engram/client.py:355 | general | ALICE, SONNET |
| R3 | [1/4] | 🟠 | `symbols.chunk` catches parse and read errors and returns `[]`, so the new `indexer.index` memo records those files as empty and never retries them. The CHANGELOG says "A chunker failure is still retried", which is false for the common failure. A tree-sitter exception or a transient `OSError` stays unindexed until the file's content changes. | src/engram/symbols.py:52 (memo written at src/engram/indexer.py:83) | general | ALICE |
| R4 | [1/4] | 🟠 | Error-bearing tool results are kept as chunks with an empty body. `chunk()` builds the body only from `text` blocks, so the traceback or error text is never embedded or searchable. The spec asks for "error-bearing tool results" to be recalled, and the test pins `body=""` as intended. | src/engram/transcripts.py:119 | 1 | BLAKE |
| R5 | [1/4] | 🟠 | Unchanged transcripts are re-read on every run. `hash_source` reads full file bytes for each of the ~1,700 files (~900MB) to compute the blob hash. The spec says "unchanged transcripts are never re-read" and cites git blob-hash incrementality, which `git ls-files -s` would give without reading. The 12.6 s run met the 60 s bound only because of the OS page cache. | src/engram/indexer.py:66 | general | BLAKE |
| R6 | [1/4] | 🟠 | Parser failures become permanently cached empty sources: index() records every empty chunk result, but symbols.chunk() swallows parsing exceptions and records skips. An unchanged file is therefore never retried after parser recovery. The new retry test bypasses this boundary by making _chunk_file raise. | src/engram/indexer.py:84 | general | BOB |
| R7 | [1/4] | 🟠 | The gold set swaps five `prd` entries and one `discovery` entry for new queries and anchors (for example calcard-mcp 00032/00036, gems 00071/00045, gems discovery 00062 are gone). Only the transcript block records a selection protocol. Without a recorded reason that each old anchor vanished, the swap reads as re-picking entries after scoring, which this file says never to do. | eval/goldset.yaml:77 | general | SONNET |
| R8 | [1/4] | 🟡 | `IndexReport.files_skipped` counts only `symbols.skipped_files` appended during the run. Memoized grammarless and unparseable files are no longer chunked, so an unchanged re-run reports 0 skipped where the first run reported thousands. | src/engram/indexer.py:105 | general | ALICE |
| R9 | [1/4] | 🟡 | `test_chunker_failure_is_retried_not_recorded_as_empty` stubs `_chunk_file` to raise, which the real `symbols.chunk` never does for parse or read failures. The test also passes against the pre-change code, where nothing is memoized and the chunker simply runs twice. It does not pin the new behavior or the CHANGELOG claim. A test that runs the real `symbols.chunk` with a failing `process` would fail today and expose the finding above. | tests/test_indexer.py:1004 | general | ALICE |
| R10 | [1/4] | 🟡 | `index()` is 84 lines, over the 50-line limit, and this diff added about 14 of them. Extracting the per-file diff/chunk/embed loop body (for example `_index_file`) would also remove the `active_*` bookkeeping from the main flow. | src/engram/indexer.py:23 | general | ALICE |
| R11 | [1/4] | 🟡 | This diff grows `tests/test_indexer.py` and `tests/test_harness.py` past the 800-line limit. Both were already over it. | tests/test_indexer.py:1 | general | ALICE |
| R12 | [1/4] | 🟡 | The file path is not embedded in code symbol chunks. The spec says "signature + docstring + file path embedded". `text_for_embedding` is `"{Kind} {name}\n{body}"`, so the path never enters the embedded text and path-based "have I built X" cues are lost. | src/engram/symbols.py:65 | 4 | BLAKE |
| R13 | [1/4] | 🟡 | `engram status` reads whole files once per chunk row, not once per path. Each file is re-read and re-hashed for every chunk it produced (about 98k reads of large files). This works against the incremental/seconds goal and makes the freshness check slow. | src/engram/store.py:473 | 3 | BLAKE |
| R14 | [1/4] | 🟡 | Tool-result content that arrives as a list of blocks is ignored by the error filter. `_has_error_match` only inspects string `content`, so list-form errors are silently dropped from the "error-bearing" start set. | src/engram/transcripts.py:81 | 1 | BLAKE |
| R15 | [1/4] | 🟡 | Capsule discovery retains a one-element fallback loop after removing every fallback; replace it with one candidate path and an existence check. | src/engram/cli.py:329 | general | BOB |
| R16 | [1/4] | 🟡 | The capsule migration makes two tests equivalent: both create only the canonical capsule and assert that pack selects it. Their former distinction depended on the removed stale-root fixture. Consolidate them. | tests/test_cli_pack.py:779 | general | BOB |
| R17 | [1/4] | 🟡 | run_harness now measures 58 lines, exceeding the mandatory 50-line limit; isolate winner selection and tie preference in a focused helper. | src/engram/harness.py:302 | general | BOB |
| R18 | [1/4] | 🟡 | The capsule default is a `for` loop over a one-element tuple, left behind when the root-path fallback was removed. Assign the path and test `.exists()` directly. | src/engram/cli.py:329 | general | SONNET |
| R19 | [1/4] | 🟡 | The new carry-over of empty-source markers for repos whose `git ls-files` failed (`active_empty` seed, `key[0] == "code" and key[1] in failed_code_repos`) has no test. Deleting it would let a transient git failure drop the markers and re-parse about 16k files on the next run, with the suite still green. | src/engram/indexer.py:58 | general | SONNET |
| R20 | [1/4] | 🟡 | This diff grows `tests/test_harness.py` (~1966 lines, several new tests 65-100+ lines) and `tests/test_indexer.py` (~941 lines), both far past the 800-line limit. Split along the existing section banners. | tests/test_harness.py:1966 | general | SONNET |
| R21 | [1/4] | 🟡 | The broad `except Exception` around `_chunk_file` still swallows the failure without recording the path or exception. The new comment says it is retried, but a run that fails on thousands of files exits 0 with only a count nothing reads. | src/engram/indexer.py:78 | general | SONNET |
| R22 | [1/4] | 🟡 | The new `Store` methods `mark_empty_source` and `prune_empty_sources` execute DML with no visible commit. `prune_empty_sources` runs after `store.prune`, so its deletes may roll back on connection close. The new tests share one connection, so they cannot see this. | src/engram/store.py:356 | general | SONNET |
| R23 | [1/4] | 🟡 | The code-seed entries now sit under the `# --- transcripts corpus` header because the `# --- code corpus` header was deleted with the old transcript block. The file's own `Corpora present` convention is now misleading. | eval/goldset.yaml:126 | general | SONNET |
| R24 | [1/4] | 🟡 | Unrelated formatter reflow is committed. In `test_harvest.py` the import blocks are reordered and several signatures re-wrapped. In `test_corpora.py` two test signatures are re-wrapped. In `test_cli_pack.py` an import blank line is dropped. None of it traces to the request. | tests/test_harvest.py:3 | general | SONNET |
| R25 | [1/4] | 🟡 | The token-density fix (0.75 to 1.0, minified JS measured at 0.81) ships without a test that pins the value. The new test derives its expectation from `WORST_CASE_TOKENS_PER_CHAR`, so reverting the constant to 0.75 still passes. Add a case asserting that a 0.81 tokens/char text at the budget fits a 2048-token context. | tests/test_client_embed.py:401 | general | SONNET |
| R26 | [1/4] | ⚪ | `test_resolve_repo_for_path_maps_claude_project_management_to_claude_home` passes against the old `harvest.py`, since `target` sits under `~/.claude` and the old code accepted that too. It only covers the simplification, not new behavior. | tests/test_harvest.py:151 | general | ALICE |
| R27 | [1/4] | ⚪ | `_enumerate_repo_corpora` and the `pack` defaults drop the `dev/local` fallback with no migration guard. A registered repo not yet on `docs/dev/project-management/` now lands in `missing_dirs`, and the next index prunes its prd, decision and discovery chunks. This is deliberate per the CHANGELOG, but worth confirming that all 26 portfolio repos are migrated. | src/engram/corpora.py:42 | general | ALICE |
| R28 | [1/4] | ⚪ | The code enumerator uses `git ls-files` (the index), not HEAD as the spec says. Staged-but-uncommitted paths are included, and tracked-but-deleted paths are filtered only by `is_file()`. | src/engram/symbols.py:23 | 5 | BLAKE |
| R29 | [1/4] | ⚪ | `SCAFFOLDING_PREFIXES` is hardcoded in the module. The spec says the filter pattern list lives in config, though it names only the error patterns. The `isMeta` and `isSidechain` exclusions are also extras beyond the spec's turn filter. | src/engram/transcripts.py:34 | 1 | BLAKE |
| R30 | [1/4] | ⚪ | `index` enumerates transcripts even for `--scope repo`. A missing cellar path therefore makes every repo-scoped `engram index` fail, including the one catchup runs in each repo. This is loud, as the spec wants, but it couples all repos to cellar. | src/engram/indexer.py:30 | general | BLAKE |
| R31 | [1/4] | ⚪ | Existing test modules exceed the 800-line limit: the supplied AST inventory extends test_cli_pack.py beyond 858, test_indexer.py beyond 914, and test_harness.py beyond 1920. | tests/test_harness.py:1920 | general | BOB |
| R32 | [1/4] | ⚪ | The "deleted file gets pruned on next index()" banner now labels the zero-chunk tests, and it is repeated before `test_deleted_file_is_pruned_on_next_index`. | tests/test_indexer.py:108 | general | SONNET |
| R33 | [1/4] | ⚪ | The committed `meta/project-capsule.md` and `meta/assumptions.md` still describe 00002 as parked or in wip, with 395 tests and an open gate blocker. `engram pack` reads the capsule by default (`cli.py:329`), so this stale text becomes reviewer Task prose. | docs/dev/project-management/meta/project-capsule.md:3 | general | SONNET |
| R34 | [1/4] | ⚪ | `hash_source` still reads every transcript and code file on each run (689 MB of transcripts), contradicting the PRD line "unchanged transcripts are never re-read". The 13 s run time hides this. | src/engram/corpora.py:106 | general | SONNET |
| R35 | [1/4] | ⚪ | The tie rule fixes only the equal-score case. A strictly better non-pinned model still repoints `config.toml` away from the live index's model and breaks every query until a rebuild, with no warning in the harness output. | src/engram/harness.py:331 | general | SONNET |
| R36 | [1/4] | ⚪ | Review-2 finding C22 (credential-shaped strings in the 0644 index file) is still unresolved. Verify whether any of the `ghp_`, `AKIA` and `Bearer` matches are live and rotate them if so. | N/A | general | SONNET |
| R37 | [1/4] | 🟡 | One migrated pack source-ref test passes at base. | tests/test_cli_pack.py | general | mech-check |
| R38 | [1/4] | 🟡 | Six unchanged corpus contracts pass at base. | tests/test_corpora.py | general | mech-check |
| R39 | [1/4] | 🟡 | Six unchanged harvest contracts pass at base. | tests/test_harvest.py | general | mech-check |
| R40 | [1/4] | 🟡 | The generic chunker-exception retry test passes at base. | tests/test_indexer.py | general | mech-check |

## Adjudication

Every table row has a disposition. The script's conservative merge leaves some
same-issue rows separate; the shared resolutions below make those duplicates
explicit. Findings were reported here, not written as autopilot tasks.

- **R1, R10, R11, R20, R31 — deferred structural debt.** Index and the large
  test modules already exceeded the limits at base. New regression coverage is
  in small separate files. A broad module split is outside this finalization;
  the newly enlarged harness function is addressed under R17.
- **R2 — accepted tradeoff.** Retrying `/props` is required to recover from a
  loading-time miss. A permanently unsupported endpoint incurs one extra GET.
- **R3, R6, R9 — fixed together.** Symbol read/parse exceptions now reach the
  indexer's existing per-file guard. Real-boundary failures are not recorded as
  empty; recovery with unchanged bytes embeds the source. Legacy code markers
  invalidate once. Tests cover read failure, parser failure, and reopen behavior.
- **R4, R14 — deferred pre-existing transcript extraction defects.** Confirmed
  in `_extract_text`/`_has_error_match`; no transcript code changed in this range.
  Retained in the follow-up note and earlier review trail.
- **R5, R34 — deferred pre-existing hashing contract gap.** The implementation
  reads file bytes. The measured 12.6 seconds establishes latency, not literal
  compliance with never reading unchanged transcripts. No unsupported assertion
  about cache-cold timing is adopted.
- **R7 — provenance repaired; scoring-manipulation allegation unproven.** Four
  PRD queries and one discovery query changed, not five PRDs. Three basenames
  are absent; calcard 00036 moved to unindexed intake/new and gems 00062 to
  unindexed research. The old dev/local material was ignored, leaving no tracked
  deletion history. Recorded in goldset comments. No queries were tuned here;
  historical scores are explicitly specific to the revised set.
- **R8 — rejected as a total-population requirement.** `files_skipped` counts
  work skipped in this invocation; memoized sources perform no parse work.
  `status` independently enumerates grammarless files with `count_skipped`.
  The actual cached-parser-error defect is fixed under R3/R6.
- **R12 — deferred pre-existing embedding contract gap.** Symbol text omits
  paths; review 2 C18 already records it. Changing embedded text and rebuilding
  the production corpus is outside this incremental finalization.
- **R13 — deferred pre-existing status inefficiency.** Per-chunk rehashing is
  unchanged; review 2 C19 and the follow-up note retain it.
- **R15, R18 — fixed.** Replaced the one-candidate loop with one path check.
- **R16 — fixed.** Removed the now-identical old capsule-precedence test;
  the canonical selection and absent-capsule tests remain.
- **R17 — fixed.** Winner/tie selection is a 10-line helper; `run_harness`
  is 42 lines. Existing winner, tie, gate, and lease tests still pass.
- **R19 — fixed.** Added a regression preserving empty-code markers when
  enumeration reports `code:repo` as failed.
- **R21 — deferred pre-existing error reporting.** Failure counts/path reporting
  and preservation of old rows after failed changed-file chunking need separate
  work; they are not hidden by the empty-source fix.
- **R22 — rejected with evidence.** `open_store` uses `isolation_level=None`;
  each statement commits automatically. Reopen tests also demonstrate that new
  valid empty records persist. The explicit migration transaction is atomic.
- **R23, R32 — fixed.** Restored code/transcript headings and corrected the
  zero-chunk test banner.
- **R24 — retained historical formatting only.** Reversing already committed
  whitespace would add unrelated churn without changing behavior. This session
  introduces no formatter sweep; pre-existing formatter stashes stay untouched.
- **R25 — fixed.** Both small-context tests assert an independent 2048-character
  bound. Reverting the ratio to 0.75 would fail these assertions.
- **R26, R37, R38, R39 — accepted behavior-preserving coverage.** These tests
  retain contracts across a path migration/simplification; they are not claimed
  as fail-first proof of the new cache or tie rule. The corrected replay fails
  the actual migration regressions and new functional regressions against base.
- **R27 — settled migration.** The user explicitly made the docs path migration
  final. Missing corpora are reported. Do not restore obsolete fallbacks as part
  of this review; unmigrated external corpora remain a separate migration concern.
- **R28 — retained prior convention.** `git ls-files` is both the named enumerator
  and the existing behavior; the HEAD/index wording discrepancy predates this
  deduplication fix (review 2 C37).
- **R29 — rejected config-scope inference.** The configurable list is the error
  pattern set; scaffold/meta exclusions remove non-conversation records and
  already predate this range. No new hardcoded error patterns were introduced.
- **R30 — deferred pre-existing producer coupling.** Missing cellar disables
  unrelated index scopes; review 2 C30 and the follow-up note retain it.
- **R33 — fixed.** Replaced stale capsule state and marked assumptions historical,
  explicitly superseding the swallowing-errors assumption.
- **R35 — out of scope/settled selection behavior.** Strictly better model
  selection is the existing harness contract; the requested change is tie
  stability. Production was neither repinned nor rebuilt during this review.
- **R36 — retained old unverified security finding.** No secret values were
  inspected, disclosed, or verified in this work. Earlier review 2 C22 and the
  follow-up note preserve the concern; do not invent a confirmed exposure.
- **R40 — superseded by stronger coverage.** The generic exception retry test
  is a backfill and legitimately passes on base. The new real-parser/read-error
  regressions fail on the reviewed revision and pass after R3/R6's repair.

## Validation

Before fixes: three cache regressions and four CLI error regressions failed.
After fixes: 454 tests passed. The duplicate-test removal and harness
extraction then passed all 68 focused harness/CLI-pack tests. The final full
suite passed 453 tests in 35.03 seconds at `ce71263`. `load_goldset` accepts all 55
entries; `git diff --check` passes.

## Alice

Original review output for the pre-fix snapshot:

```text
[ALICE] 🟠 `symbols.chunk` catches parse and read errors and returns `[]`, so the new `indexer.index` memo records those files as empty and never retries them. The CHANGELOG says "A chunker failure is still retried", which is false for the common failure. A tree-sitter exception or a transient `OSError` stays unindexed until the file's content changes. | File: src/engram/symbols.py:52 (memo written at src/engram/indexer.py:83) | Task: general
[ALICE] 🟡 `IndexReport.files_skipped` counts only `symbols.skipped_files` appended during the run. Memoized grammarless and unparseable files are no longer chunked, so an unchanged re-run reports 0 skipped where the first run reported thousands. | File: src/engram/indexer.py:105 | Task: general
[ALICE] 🟡 `test_chunker_failure_is_retried_not_recorded_as_empty` stubs `_chunk_file` to raise, which the real `symbols.chunk` never does for parse or read failures. The test also passes against the pre-change code, where nothing is memoized and the chunker simply runs twice. It does not pin the new behavior or the CHANGELOG claim. A test that runs the real `symbols.chunk` with a failing `process` would fail today and expose the finding above. | File: tests/test_indexer.py:1004 | Task: general
[ALICE] 🟡 `index()` is 84 lines, over the 50-line limit, and this diff added about 14 of them. Extracting the per-file diff/chunk/embed loop body (for example `_index_file`) would also remove the `active_*` bookkeeping from the main flow. | File: src/engram/indexer.py:23 | Task: general
[ALICE] 🟡 This diff grows `tests/test_indexer.py` and `tests/test_harness.py` past the 800-line limit. Both were already over it. | File: tests/test_indexer.py:1 | Task: general
[ALICE] ⚪ `test_resolve_repo_for_path_maps_claude_project_management_to_claude_home` passes against the old `harvest.py`, since `target` sits under `~/.claude` and the old code accepted that too. It only covers the simplification, not new behavior. | File: tests/test_harvest.py:151 | Task: general
[ALICE] ⚪ `_enumerate_repo_corpora` and the `pack` defaults drop the `dev/local` fallback with no migration guard. A registered repo not yet on `docs/dev/project-management/` now lands in `missing_dirs`, and the next index prunes its prd, decision and discovery chunks. This is deliberate per the CHANGELOG, but worth confirming that all 26 portfolio repos are migrated. | File: src/engram/corpora.py:42 | Task: general
[ALICE] ⚪ `_max_chars_for` no longer caches a `/props` miss. An endpoint that never serves `/props` now gets one extra failed HTTP request on every `embed()` call, which is once per file during indexing. It is cheap, but it is a cost the old code avoided. | File: src/engram/client.py:355 | Task: general

I did not run tests myself; the 446 passed is the verified result from the prompt. The fail-first replay in the context did not run (missing `.venv/bin/python`), so the "passes pre-change" claims come from reading the code, not from a run.

R1: pass
R2: fail
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: pass
R10: fail
R11: pass
R12: fail
R13: fail
```

## Blake

Original review output for the pre-fix snapshot:

```text
[BLAKE] 🟠 Error-bearing tool results are kept as chunks with an empty body. `chunk()` builds the body only from `text` blocks, so the traceback or error text is never embedded or searchable. The spec asks for "error-bearing tool results" to be recalled, and the test pins `body=""` as intended. | File: src/engram/transcripts.py:119 | Task: 1
[BLAKE] 🟠 Unchanged transcripts are re-read on every run. `hash_source` reads full file bytes for each of the ~1,700 files (~900MB) to compute the blob hash. The spec says "unchanged transcripts are never re-read" and cites git blob-hash incrementality, which `git ls-files -s` would give without reading. The 12.6 s run met the 60 s bound only because of the OS page cache. | File: src/engram/indexer.py:66 | Task: general
[BLAKE] 🟡 The file path is not embedded in code symbol chunks. The spec says "signature + docstring + file path embedded". `text_for_embedding` is `"{Kind} {name}\n{body}"`, so the path never enters the embedded text and path-based "have I built X" cues are lost. | File: src/engram/symbols.py:65 | Task: 4
[BLAKE] 🟡 `engram status` reads whole files once per chunk row, not once per path. Each file is re-read and re-hashed for every chunk it produced (about 98k reads of large files). This works against the incremental/seconds goal and makes the freshness check slow. | File: src/engram/store.py:473 | Task: 3
[BLAKE] 🟡 Tool-result content that arrives as a list of blocks is ignored by the error filter. `_has_error_match` only inspects string `content`, so list-form errors are silently dropped from the "error-bearing" start set. | File: src/engram/transcripts.py:81 | Task: 1
[BLAKE] ⚪ The code enumerator uses `git ls-files` (the index), not HEAD as the spec says. Staged-but-uncommitted paths are included, and tracked-but-deleted paths are filtered only by `is_file()`. | File: src/engram/symbols.py:23 | Task: 5
[BLAKE] ⚪ `SCAFFOLDING_PREFIXES` is hardcoded in the module. The spec says the filter pattern list lives in config, though it names only the error patterns. The `isMeta` and `isSidechain` exclusions are also extras beyond the spec's turn filter. | File: src/engram/transcripts.py:34 | Task: 1
[BLAKE] ⚪ `index` enumerates transcripts even for `--scope repo`. A missing cellar path therefore makes every repo-scoped `engram index` fail, including the one catchup runs in each repo. This is loud, as the spec wants, but it couples all repos to cellar. | File: src/engram/indexer.py:30 | Task: general

B1: fail
B2: pass
B3: pass
B4: pass
B5: pass
B6: pass
B7: pass
B8: pass
B9: pass
B10: pass
B11: pass
B12: pass
B13: pass
B14: pass
B15: fail
B16: pass
B17: pass
B18: pass
B19: pass
```

## Bob

Original review output for the pre-fix snapshot:

```text
[BOB] 🟠 Parser failures become permanently cached empty sources: index() records every empty chunk result, but symbols.chunk() swallows parsing exceptions and records skips. An unchanged file is therefore never retried after parser recovery. The new retry test bypasses this boundary by making _chunk_file raise. | File: src/engram/indexer.py:84 | Task: general
[BOB] 🟡 Capsule discovery retains a one-element fallback loop after removing every fallback; replace it with one candidate path and an existence check. | File: src/engram/cli.py:329 | Task: general
[BOB] 🟡 The capsule migration makes two tests equivalent: both create only the canonical capsule and assert that pack selects it. Their former distinction depended on the removed stale-root fixture. Consolidate them. | File: tests/test_cli_pack.py:779 | Task: general
[BOB] 🟡 run_harness now measures 58 lines, exceeding the mandatory 50-line limit; isolate winner selection and tie preference in a focused helper. | File: src/engram/harness.py:302 | Task: general
[BOB] ⚪ Other function-size violations predate this change: index measures 84 lines after this diff, ensure_served 68, _baseline_hit_rate 58, and pack.build 54. | File: src/engram/indexer.py:23 | Task: general
[BOB] ⚪ Existing test modules exceed the 800-line limit: the supplied AST inventory extends test_cli_pack.py beyond 858, test_indexer.py beyond 914, and test_harness.py beyond 1920. | File: tests/test_harness.py:1920 | Task: general

FIX:

- Parser failures cached as empty — src/engram/indexer.py:84 — Distinguish successful empty chunking from producer-reported failure before writing empty_sources. Preserve retry behavior for failures. Add an integration regression that makes symbols.process fail once, then recover without changing source bytes; assert the second index parses and embeds the file. Evidence: the supplied assumptions ledger explicitly says symbols.chunk swallows exceptions and reports them through symbols.skipped_files; the new test instead patches _chunk_file to raise.
- Single-candidate fallback loop — src/engram/cli.py:329 — Assign the canonical capsule path directly and retain the existing existence check.
- Duplicate capsule tests — tests/test_cli_pack.py:779 — Keep one canonical-path selection test; remove the redundant former-precedence test.
- Newly oversized harness function — src/engram/harness.py:302 — Extract model winner selection, including the pinned-model tie rule, into a focused helper. Preserve the existing gate and config-write behavior.

VERIFY:

- (none)

KNOWN:

- Other function-size violations — src/engram/indexer.py:23 — The supplied diff and mechanical inventory show pre-existing oversized functions; broad restructuring of indexing, server lifecycle, baseline scoring, and pack construction is outside this incremental fix.
- Oversized test modules — tests/test_harness.py:1920 — These modules already exceeded 800 lines before the small additions and path migration; splitting the existing suites is separate structural cleanup.

R1: fail
R2: pass
R3: pass
R4: fail
R6: pass
R7: pass
R8: pass
R9: fail
R10: fail
R11: pass
R12: fail
R13: fail

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass
```

## Sonnet

Original review output for the pre-fix snapshot:

```text
[BOB] 🟡 The capsule default is a `for` loop over a one-element tuple, left behind when the root-path fallback was removed. Assign the path and test `.exists()` directly. | File: src/engram/cli.py:329 | Task: general
[BOB] 🟡 The new carry-over of empty-source markers for repos whose `git ls-files` failed (`active_empty` seed, `key[0] == "code" and key[1] in failed_code_repos`) has no test. Deleting it would let a transient git failure drop the markers and re-parse about 16k files on the next run, with the suite still green. | File: src/engram/indexer.py:58 | Task: general
[BOB] 🟡 `indexer.index` is now 84 lines and `harness.run_harness` 58 (mechanical facts). This diff added about a dozen lines to the first and 9 to the second. Extract the empty-marker bookkeeping and the tie-break into helpers. | File: src/engram/indexer.py:23 | Task: general
[BOB] 🟡 This diff grows `tests/test_harness.py` (~1966 lines, several new tests 65-100+ lines) and `tests/test_indexer.py` (~941 lines), both far past the 800-line limit. Split along the existing section banners. | File: tests/test_harness.py:1966 | Task: general
[BOB] 🟡 The broad `except Exception` around `_chunk_file` still swallows the failure without recording the path or exception. The new comment says it is retried, but a run that fails on thousands of files exits 0 with only a count nothing reads. | File: src/engram/indexer.py:78 | Task: general
[BOB] 🟡 The new `Store` methods `mark_empty_source` and `prune_empty_sources` execute DML with no visible commit. `prune_empty_sources` runs after `store.prune`, so its deletes may roll back on connection close. The new tests share one connection, so they cannot see this. | File: src/engram/store.py:356 | Task: general
[BOB] 🟡 The code-seed entries now sit under the `# --- transcripts corpus` header because the `# --- code corpus` header was deleted with the old transcript block. The file's own `Corpora present` convention is now misleading. | File: eval/goldset.yaml:126 | Task: general
[BOB] ⚪ The "deleted file gets pruned on next index()" banner now labels the zero-chunk tests, and it is repeated before `test_deleted_file_is_pruned_on_next_index`. | File: tests/test_indexer.py:108 | Task: general
[BOB] 🟡 Unrelated formatter reflow is committed. In `test_harvest.py` the import blocks are reordered and several signatures re-wrapped. In `test_corpora.py` two test signatures are re-wrapped. In `test_cli_pack.py` an import blank line is dropped. None of it traces to the request. | File: tests/test_harvest.py:3 | Task: general
[BOB] 🟠 The gold set swaps five `prd` entries and one `discovery` entry for new queries and anchors (for example calcard-mcp 00032/00036, gems 00071/00045, gems discovery 00062 are gone). Only the transcript block records a selection protocol. Without a recorded reason that each old anchor vanished, the swap reads as re-picking entries after scoring, which this file says never to do. | File: eval/goldset.yaml:77 | Task: general
[BOB] ⚪ The committed `meta/project-capsule.md` and `meta/assumptions.md` still describe 00002 as parked or in wip, with 395 tests and an open gate blocker. `engram pack` reads the capsule by default (`cli.py:329`), so this stale text becomes reviewer Task prose. | File: docs/dev/project-management/meta/project-capsule.md:3 | Task: general
[BOB] 🟡 The token-density fix (0.75 to 1.0, minified JS measured at 0.81) ships without a test that pins the value. The new test derives its expectation from `WORST_CASE_TOKENS_PER_CHAR`, so reverting the constant to 0.75 still passes. Add a case asserting that a 0.81 tokens/char text at the budget fits a 2048-token context. | File: tests/test_client_embed.py:401 | Task: general
[BOB] ⚪ Not caching a `/props` miss means an endpoint that never serves `/props` pays an extra failing GET on every `embed()` call. Per-file indexing calls `embed()` once per file. | File: src/engram/client.py:358 | Task: general
[BOB] ⚪ `hash_source` still reads every transcript and code file on each run (689 MB of transcripts), contradicting the PRD line "unchanged transcripts are never re-read". The 13 s run time hides this. | File: src/engram/corpora.py:106 | Task: general
[BOB] ⚪ The tie rule fixes only the equal-score case. A strictly better non-pinned model still repoints `config.toml` away from the live index's model and breaks every query until a rebuild, with no warning in the harness output. | File: src/engram/harness.py:331 | Task: general
[BOB] ⚪ Review-2 finding C22 (credential-shaped strings in the 0644 index file) is still unresolved. Verify whether any of the `ghp_`, `AKIA` and `Bearer` matches are live and rotate them if so. | File: N/A | Task: general

FIX:
- The one-element tuple loop in the capsule default — src/engram/cli.py:329 — assign the path and test `.exists()` directly.
- The empty-marker carry-over for failed repos is untested — src/engram/indexer.py:58 — add a test where `symbols.enumerate` records `code:repo` as missing and asserts the markers survive.
- `index` is 84 lines and `run_harness` 58 — src/engram/indexer.py:23 — extract the empty-source bookkeeping and the pinned-tie selection.
- Test files over 800 lines — tests/test_harness.py, tests/test_indexer.py — split along existing section banners.
- The blanket `except Exception` hides the failing path — src/engram/indexer.py:78 — record the path and exception and surface them in the index summary.
- Code seeds under the transcripts header — eval/goldset.yaml:126 — restore the `# --- code corpus ---` header.
- The duplicated "deleted file" banner — tests/test_indexer.py:108 — move or remove the first copy.
- Unrelated formatter reflow — tests/test_harvest.py, tests/test_corpora.py, tests/test_cli_pack.py — revert the reflow hunks.
- The stale capsule and assumptions files — docs/dev/project-management/meta/ — update them to the done state or drop them from the tree.
- The density constant is unpinned — tests/test_client_embed.py:401 — add a hard-coded 0.81 tokens/char fits-in-context assertion.

VERIFY:
- Whether `mark_empty_source` and `prune_empty_sources` commit — check that `Store.prune` and `Store.upsert_chunks` commit. Then run `engram index` twice as separate processes after deleting a zero-chunk file. Confirm the second run's `empty_sources` table no longer holds it.
- Whether the replaced gold anchors are truly gone — for each removed `expected_path` (calcard-mcp 00032/00036, gems 00071/00045, gems discovery 00062), run `git log --diff-filter=D` and `rg --files` in that repo. Confirm none exists at any path, then note the result in the goldset header.

KNOWN:
- Extra `/props` GET per `embed()` for endpoints without it — it is cheap, and only non-llama endpoints hit it.
- `hash_source` rereads all files each run — it predates this diff (review-2 C20) and the 12.6 s run meets the 60 s bound.
- A strictly better candidate still repoints the pin — rebuild-on-model-change is the designed recovery. Warning text is a separate change.
- Credential-shaped strings in the index — hardening is out of scope for this diff. It is recorded in review-2 C22.

R1: fail
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

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass
```

Verdict: 40 findings
Tests: 453 passed, 0 failed, 0 skipped (repair commit ce71263; suite run this cycle)
