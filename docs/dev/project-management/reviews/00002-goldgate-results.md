# PRD 00002 gold-set gate — results

Two runs. Run 1's numbers are **void** (scoring bug). Run 2 is the real measurement.

Class sizes in `eval/goldset.yaml`: memory 20, prd 13, code 5, transcripts 4,
discovery 2 (44 total).

## Verdict against the PRD's two success metrics: BOTH FAIL

This is the headline, and it is **not** what the harness's own `gate_passed` line says.

| PRD success metric | threshold | winner (bge-m3) | verdict |
|---|---|---|---|
| transcript past-incident paraphrase in top-5 | >= 0.80 | **0.750** (3/4) | **FAIL** |
| cross-repo "have I built X" seed in top-5 | >= 0.80 | **0.600** (3/5) | **FAIL** |

`gate_passed True` in run 2 is a **global** >=0.80 across all 44 entries, strictly
beating the rg baseline. The PRD gates **per class**. The two gated classes are the
two smallest in the gold set (4 and 5 entries), and the winner misses both. No
single model meets both: `nomic` is the only model to reach code 0.800, and it
scores transcripts 0.500.

PRD 00002's Phase 1 exit criterion ("Both success-metric retrieval thresholds met at
the harness") is therefore **not met**. Goldset queries were not tuned to close the
gap, and should not be.

## Run 2 (valid) — 2026-08-04, code at `997944d`

```
Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0       0.682   code 0.600  discovery 1.000  memory 0.750  prd 0.615  transcripts 0.500
nomic-ai/nomic-embed-text-v1.5-GGUF:Q8_0  0.795   code 0.800  discovery 1.000  memory 0.900  prd 0.692  transcripts 0.500
ggml-org/bge-m3-Q8_0-GGUF:Q8_0            0.864   code 0.600  discovery 1.000  memory 1.000  prd 0.769  transcripts 0.750
winner       ggml-org/bge-m3-Q8_0-GGUF:Q8_0
baseline     0.068
gate_passed  True
```

bge-m3 wins on every class except `code`, where it ties Qwen at 0.600 and loses to
nomic's 0.800.

**Sample sizes are tiny.** transcripts moves in steps of 0.25, code in steps of 0.20.
One gold entry either way flips a class across the threshold. Treat every per-class
number here as directional, not precise. The honest read is "the two new corpora are
near but under the bar on a handful of queries", not "retrieval is 15% short".

## Run 1 (VOID) — and the bug that voided it

Run 1 reported `gate_passed False` with a 0.409 winner and `memory 0.000` for all
three models. The memory class was zero **structurally**, not because retrieval
failed:

- `~/.claude/projects` is a **symlink** to
  `/Users/bob/git/src/github.com/buvis/cellar/.claude/projects`.
- `corpora._enumerate_memory_corpora` yielded the **unresolved** path, and
  `indexer.index` stores it verbatim (`key = (file.repo, str(file.path), h)`).
  Confirmed against the live index: `select min(path) from chunks where
  corpus='memory'` → `/Users/bob/.claude/projects/-Users-bob--claude-plugins/memory/MEMORY.md`.
- `harness.load_goldset` calls `.resolve()` on every `expected_path`, producing the
  cellar path.
- The hit test is an exact string compare (`g.expected_path in seen`), so no memory
  entry could ever match.

20 of 44 gold entries (45%) were unhittable, which invalidated the overall hit rate,
the winner selection, and the gate verdict. Only memory was affected — transcripts
already stored real cellar paths, which is why they scored normally in both runs.

Fixed in `997944d` (`md_file.resolve()` at enumeration), pinned by
`test_memory_corpus_paths_are_symlink_resolved_when_projects_dir_is_a_symlink`.
Memory went 0.000 → 0.750 / 0.900 / 1.000 across the three models, which is what
confirms the diagnosis.

**The fix did not move the two gated classes**, and was never expected to: memory
chunks always competed in the ranking, only the hit *comparison* was broken. Run 2's
transcripts and code numbers are byte-identical to run 1's.

## Findings for the review

1. **`_write_pinned` repoints production on a FAILED gate.** `run_harness` calls it
   unconditionally, so run 1 — a failed run, on invalid numbers — rewrote
   `~/.local/share/engram/config.toml` to bge-m3 while the live index was Qwen-built.
   Every `engram query` then died with `vector model ... does not match indexed model
   ...`. An eval that did not pass should not repoint production.
2. **The rg baseline is unstable.** It fell 0.205 → 0.068 between runs on a change
   that only altered *path spelling* for one corpus. `_baseline_hit_rate` ranks by
   `(-match_count, path)`, so with many tied match counts the top-5 is decided by
   alphabetical order of the path string; resolving memory paths reshuffled the tie
   break. A comparator that swings 3x on a path rename is weak evidence for "engram
   beats grep", even though the gate clears it either way.
3. **`run_harness`'s cleanup leaks servers on the crash path.** The `finally` stops a
   lease only `if lease.entry.id != winner_id`; when the run dies before a winner is
   chosen (`winner_id is None`), it reaps nothing. It also deliberately leaves the
   winner's server running on success — which then gets leased as unspawned by the
   next run, losing the degraded-server recycle path. Killing the leftover bge-m3
   server on 8083 was a manual step before run 2.
4. **`format_report` prints only at the very end**, after all candidates *and* the rg
   baseline. Any late failure discards a full ~40-minute scoring run with zero
   output. This is what made run 1's ARG_MAX crash so expensive.
5. **The `code` corpus indexes archived transcript payloads as portfolio source.**
   `min(path)` for `corpus='code'` is
   `.../cellar/.claude/projects-archive/.../workflows/scripts/deep-research-wf_*.js`.
   Archived session artifacts are not portfolio code, and the code corpus is the
   larger of the two classes that missed its threshold (41,716 chunks, 3,267 files
   skipped for want of a grammar). Worth checking whether this noise is part of why
   code sits at 0.600.
6. **Stale memory rows after the fix.** The live index held 192 memory rows under the
   old unresolved path. Those paths still resolve on disk, so they are not "dead" by
   `engram status`'s definition — a plain reindex would likely have *added* 192
   resolved-path rows and kept the old ones, double-counting the corpus. The full
   `--rebuild` performed after run 2 sidesteps this, but the pruning rule is worth a
   look before the next incremental reindex.
