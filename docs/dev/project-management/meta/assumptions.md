# Implementor assumptions ledger — PRD 00002 (engram heavy corpora v1)

Historical build ledger. PRD 00002 was finalized on 2026-11-01; current evidence
is in its done PRD and review 3. The task-4 assumption that `symbols.chunk()`
must swallow read/parser failures is superseded: those failures now propagate
to the indexer's per-file guard so the empty-source cache cannot remember them.
The release and installation holds below describe past sessions, not current
instructions.

Per-plan ledger of assumptions the implementors made where the task, tests, or
listed files were silent. Input to the review phase. Replaced at the first
completed task of a full-plan pass (the prior contents belonged to PRD 00004,
whose ledger is preserved in that PRD's review trail).

## 3: [D1] Gate the harness on the PRD's per-class thresholds and stop pinning on a failed gate (review cycle 1 rework)

Tess (test author):
- Used `str.removeprefix` (Python 3.12+ per `pyproject.toml`, so safe) to derive per-query hit/miss indices in the scripted query stubs, following the file's existing text-prefix-based scripted-query pattern.
- Picked concrete hit-rate numbers not specified verbatim in the brief (5/4/21-entry splits yielding 0.60/0.75/1.0) rather than reproducing the exact 0.864/0.750/0.600 real-run figures, keeping the qualitative shape (global passes, two classes fail) with round fractions for exact `pytest.approx` assertions.
- Assumed `_write_config_toml`'s always-empty `id = ""` pinned section is an acceptable "before" state for the Defect B unchanged-config test, since no helper exists to seed a non-empty prior pin.
- Used distinct new port numbers (8140-8145) purely for uniqueness; functionally inert since networking is mocked.

Ivan (implementation):
- none.

Orchestrator (main session):
- Discarded unreported formatter reflow Ivan's tree carried across five unrelated regions of `tests/test_harness.py` (absent from its `FILES_TOUCHED`). Judged out of scope: it is review finding T22 recurring, and committing it would have left the file split across two formatting conventions.

## 4: [D1] Stop one bad file or one failed repo from aborting or silently pruning an index run (review cycle 1 rework)

Tess (test author):
- Assumed the fix adds an `IndexReport.files_skipped: int` field with a default, so the existing `IndexReport(...)` construction test keeps working. The field did not exist; it was a guess at the interface the "surface the skipped count" criterion implies. Ivan implemented it as guessed.
- Assumed the Defect A fix keys off the `f"code:{name}"` entries already appended to `corpora.missing_dirs`, and wrote the fakes to reproduce that exact contract rather than mocking a different signal.
- Monkeypatched `symbols.process` to simulate a tree-sitter parse failure, since real grammars emit ERROR nodes rather than raising.
- For the guard test, picked corpus `"memory"` arbitrarily; any of memory/prd/decision/discovery routes through `chunk_markdown` identically.

Ivan (implementation):
- `files_skipped` sums two sources (a local dispatch-skip counter plus the `symbols.skipped_files` delta), because `symbols.chunk()` must keep swallowing its own exceptions to satisfy an existing test and so never raises to the outer guard.
- Placed the `try/except` at the call site of `_chunk_file()` inside `index()`'s loop rather than inside `_chunk_file()` itself.
- Used a bare `except Exception:` to match the existing convention in `symbols.py`, though general style guidance prefers naming the exception.

Orchestrator (main session):
- Discarded unreported formatter reflow from Ivan's first pass across all three test files (absent from `FILES_TOUCHED`). Second consecutive task where this happened.
- Chose to fix Pat's re-review MEDIUM (the new dispatch guard had no test) rather than defer it as the step-5.7 MEDIUM rule allows, because the guard is the mechanism fixing a HIGH finding and narrowing it later would silently restore the bug with all tests still green.

## 5: [D1] Make engram status enumerate transcripts and replace the false-coverage test (review cycle 1 rework)

Tess (test author):
- Assumed the fix would reach the producer via a module-qualified `transcripts.enumerate()` (mirroring the existing `symbols.count_skipped()` call in `_run_status`), so patched the `engram.transcripts` module attribute directly rather than a dotted string through `engram.cli` - which could not resolve until the import existed. Ivan implemented it that way.
- Assumed "loud failure" means non-zero exit plus the producer's raised message verbatim on stderr, matching the existing `enumerate_corpora` handling.
- Chose to RENAME rather than delete the false-coverage test, on the grounds that it covers real verbatim-message passthrough for the repos.csv producer and was only mislabelled as the cellar case.

Ivan (implementation): none.

Orchestrator (main session):
- Discarded a formatter reflow that appeared in `tests/test_indexer.py`, a file this task never touched. Third consecutive task with an unrequested reflow.
- Applied Pat's MEDIUM directly instead of deferring it: `list(transcripts.enumerate())` walked ~1,845 cellar files on every `status` call just to probe the root, and catchup calls `status` every run. Verified `transcripts.py:35-39` puts the `is_dir()` guard first in the generator body, so `next(..., None)` raises identically without the walk.

## 6-11: [D1] remaining review-cycle-1 rework

**6 (catchup skill hardening, claude-git-ferry).** Orchestrator: implemented directly rather than via Tess/Ivan - the work skill skips test authoring and per-task review for documentation-only tasks, and this is prose instructing an agent with no test surface. The unreleased `Added` CHANGELOG entry was amended rather than a `Fixed` entry added, since the bug never shipped. `dev/bin/release` deliberately NOT run (held pending `/warden:allow engram`).

**7 (stop every lease).** Orchestrator: inverted `test_run_harness_stops_every_lease_except_the_winners` rather than adding a parallel test, because the old assertion pinned the leak itself; recorded via rename, inline comment, commit message and attempt log rather than a quiet flip.

**8 (rg baseline tie-break).** Tess: asserted only that the two path spellings produce the SAME rate, not which value the fix converges on, since the requirement is invariance rather than a particular verdict. Orchestrator: chose to admit the whole tie band at the 5th-best match count. rg reports a count and nothing else, so it has no signal that can order a tie; the old code invented one (the path string). Effect: the baseline reads slightly higher and is stable, which makes the gate's floor stricter, not laxer.

**9 (stream score lines).** Tess: read "match the line format `format_report` uses" as the headline `{model_id}\t{hit_rate:.3f}` line only, not the per-corpus sub-lines, since that is the line signalling a model finished. Orchestrator: accepted that each model's lines now appear twice on a successful run (once streamed, once in the summary) because the task required the summary block stay unchanged for anything parsing it.

**10 (inline `_pid_to_release`).** No assumptions. The aegis fact-forcing gate blocked the first edit and was satisfied by stating importers, affected public surface, and config structure.

**11 (error_patterns in config).** Tess: drove `_load_error_patterns` directly rather than through `chunk()`'s implicit path, because that default argument binds `client.DEFAULT_CONFIG_PATH` at import time and she was forbidden from risking a touch to the real config - so the test proves the loader caches, not that `chunk()`'s call site benefits. Orchestrator: wrote the in-code defaults verbatim into the live `~/.local/share/engram/config.toml`, having first checked that `harness._write_pinned` is line-preserving so a future pin will not drop the table; verified the loaded result compares equal to `DEFAULT_ERROR_PATTERNS`, so it is behaviour-preserving.

## 1: Run the initial full portfolio index and prove incrementality

Tess (regression tests):
- Used `set(...)` equality (matching the existing `test_enumerate_yields_corpusfile_per_tracked_file_and_resets_skipped_files` pattern) rather than order-sensitive comparison, since `enumerate()`'s output order is not part of the contract under test.
- Did not call `symbols.skipped_files.clear()` at the start of either test; the assertion is `not in`, which holds regardless of prior state, matching the two enumerate tests immediately above.

Ivan (implementation):
- none.

Orchestrator (main session):
- The task's acceptance says the second run "embeds 0 chunks". Measured: `memory`, `prd`, `discovery` and `code` all reported `stale=0` with unchanged chunk counts (zero re-embeds), but `transcripts` gained 14 chunks because cellar session JSONL files are appended live while the index runs — including this autopilot session's own transcript. Read as "zero re-embeds for every corpus whose files are not being written during the run"; `transcripts` cannot reach `stale=0` while any Claude session is active.
