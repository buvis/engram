---
prd: dev/local/prds/wip/00003-engram-findings-corpus-v1.md
review: 1
date: 2026-08-03
head_sha: 6400947947b896b42ba7165f34aad8b87ba06eaa
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

Diff range: `fd1b727a2a7f902117da579e802b4e5e6624496e..6400947947b896b42ba7165f34aad8b87ba06eaa`
(engram, tasks 1-4). The change also spans two external repos, both reviewed:
task 5 = `79a068ac^..04802395` in the `~/.buvis` bare repo
(`~/.claude/skills/purge-devlocal/`); task 6 = commit `658a607` in
`claude-git-ferry`. All three were concatenated into
`dev/local/tmp/review-diff-all-00003-c1.diff` and handed to every lens.

codex_rung_guard: fired (1 codex-implemented task(s))

## Review Summary

Reviewed: 6 completed tasks
PRDs checked: 00003-engram-findings-corpus-v1

### Agent Status

- Alice (consensus, Claude): ✅ Available
- Blake (blind, PRD-only): ✅ Available
- Bob (doubt + de-slop, codex): ✅ Available
- Carl (UI/generalist, gemini via copilot): ✅ Available
- Eve (doubt, Fable 5): ✅ Available — activated by the codex doubt-roster guard
- Quinn (local qwen, advisory): ⚠️ Unavailable: dispatch failed twice with
  `[llama-cpp] failed to reach http://localhost:8080/v1/models: fetch failed`.
  The step-1 preflight passed against provider `llamacpp8001`, so the preflight
  probe and the dispatch target disagree on port. One retry was spent per the
  retry policy and failed identically; Quinn is advisory weight, so no finding
  was lost from the consensus set.

### Consolidation note (fail-loud)

`consolidate-findings.sh` ran successfully (exit 0) over ALICE, BLAKE, BOB and
CARL — the four reviewers whose output uses the `[AGENT] {emoji} … | File: … |
Task: …` issue-line contract. **Its output is not usable as a consensus signal
and is not reproduced as the headline table.** The script keys duplicate
detection on the exact normalized description text, and the five lenses phrase
the same defect differently, so it emitted 62 rows every one of which scored
`[1/4]` — including defects that four independent reviewers raised. The raw
script output is preserved in the per-agent files under `dev/local/tmp/`.

The Consolidated Findings below are therefore a **model-side semantic merge**
of the same four outputs plus Eve's, grouping findings that name the same
defect regardless of wording. Consensus is `N/5` over the five reviewers that
ran (Quinn excluded — he produced no output).

Eve is counted in the denominator but was NOT passed to
`consolidate-findings.sh`: her lens emits the doubt contract (FIX / VERIFY /
KNOWN + `D{n}` verdicts), not issue lines, so the script would have parsed zero
findings from her file while still inflating the denominator to 5 — deflating
every score. Her findings are merged by hand below and reproduced in full in
her own section.

## Consolidated Findings

| Consensus | Severity | Issue | File | Task | Found By |
|-----------|----------|-------|------|------|----------|
| [3/5] | 🔴 | `no_repo` is a terminal harvest outcome that makes `engram harvest` exit nonzero, and purge treats every nonzero as failure — so a review file in a repo absent from gita's `repos.csv` is never trashed and warns on every run, forever. Verified: engram's own repo is not in `~/.config/gita/repos.csv`. The PRD mandates a nonzero exit only "if any file failed to parse entirely". | src/engram/harvest.py + purge_devlocal.py | 4, 5 | Blake, Alice, Eve |
| [1/5] | 🔴 | The pre-trash sweep selects files by path shape (`rel.parts[0] == "reviews"` and `.md`) instead of "files matching the review-file contract" as the PRD requires, so non-contract markdown in `reviews/` fails harvest and becomes permanently un-GC-able. Verified against two real files in this repo (`00001-engram-core-v1-audit.md`, `00002-task5-index-blocker.md`), both of which parse-fail and are trash candidates today. | ~/.claude/skills/purge-devlocal/scripts/purge_devlocal.py | 5 | Blake |
| [4/5] | 🟠 | `Store.status()` reports every findings row stale while its source review file exists and dead once it is trashed, because findings `content_hash` is a sha1 of the record body while `status()` recomputes a git-blob hash of the whole file. `engram status` therefore exits 1 permanently in this PRD's designed steady state. `prune()` got a findings exemption; `status()` did not. Confirmed by two independent live runs (`stale_files=[review.md]` before deletion, `dead_rows` after). | src/engram/store.py | 2 | Alice, Blake, Bob, Eve |
| [4/5] | 🟠 | The `--rebuild` findings-preservation block sits outside the `try/except` that guards the rebuild, so an `embed()` or store failure there escapes as a raw traceback instead of the branch's own "rebuild failed: …" message, and leaks `tmp_store.conn` / the `.rebuild-tmp` file. | src/engram/cli.py | 4 | Alice, Bob, Carl, Eve |
| [4/5] | 🟠 | Nothing tests the PRD's headline exit criterion end-to-end. The purge tests stub `subprocess.run` with a fake completed process and the engram tests stub `embed()`, so no test ever runs purge → real `engram harvest` → source deletion → query. "Trash and invoke" is proven; queryability after the trash is not. | N/A (cross-repo) | general | Alice, Blake, Bob, Eve |
| [3/5] | 🟠 | Durable records omit the PRD's stated record fields. The PRD's Outputs contract is "Records: severity, file, pattern/description, verdict, PRD id, repo, date"; `Record` carries only `heading`, `body`, `line_start`, `line_end`, `structured`. Severity, file, verdict, PRD id and date survive only as raw text inside `body`, so findings cannot be filtered or ranked, and the future distill consumer must re-parse record text. | src/engram/findings.py | 1 | Alice, Blake, Bob |
| [2/5] | 🟠 | The unstructured fallback is line-granular, so one real review file yields 104 records of which 69 are context-free single lines (shortest body 8 chars). Across 5 real review files that is 363 records, 262 unstructured — each its own embedded chunk competing in hybrid retrieval, directly against the success metric "a precedent query … returns its record in top-5". | src/engram/findings.py | 1 | Alice, Blake, Eve |
| [1/5] | 🟠 | `engram` is not on PATH (absent from `uv tool list` and `~/.local/bin`), so both Phase 2 integrations are inert in the deployed environment: purge prints one warning and trashes satellites unharvested; catchup skips. The zero-loss metric does not hold as deployed. | N/A (environment) | 5, 6 | Blake |
| [4/5] | 🟡 | `findings.parse` is ~107 lines at 5 levels of nesting, over both the 50-line and 4-level limits, and the table-separator test is written twice verbatim (lines 65-67 and 71-74). | src/engram/findings.py | 1 | Alice, Bob, Carl, Eve |
| [4/5] | 🟡 | The embed-text projection `f"{c.heading}\n{c.body}" if c.heading else c.body` is now written three times — `indexer.py:90` (pre-existing), `findings.py:166` and `cli.py:168-170` (both added here). Three copies of the store's embedding convention will drift. | N/A (cross-module) | general | Alice, Bob, Carl, Eve |
| [4/5] | 🟡 | `harvest()` is 59 lines with untyped `store` and `config` parameters, against the design contract `harvest(store: Store, config: EngramConfig, …)`. | src/engram/harvest.py | 4 | Alice, Bob, Carl, Eve |
| [4/5] | 🟡 | `process_store()` grew to ~70 lines at 6 nesting levels; the harvest-failure `detail` local shadows an unrelated `detail` later in the same function; the `# unchanged, fire-and-forget` comment documents diff history rather than behavior. | ~/.claude/skills/purge-devlocal/scripts/purge_devlocal.py | 5 | Alice, Bob, Carl, Eve |
| [4/5] | 🟡 | Parser fixtures are hand-synthesized 5-12 line strings, but the PRD states "Fixtures are copies of real review files". Nothing binds the parser to real reviewer output; real files behave very differently (104 records, only 35 structured). | tests/test_findings.py | 1 | Alice, Blake, Bob, Eve |
| [3/5] | 🟡 | `_resolve_repo_for_path` duplicates `cli._resolve_repo_name` and has already diverged (one uses `corpora.read_repos_csv`, the other a hand-rolled `csv.reader`; only the harvest copy knows the `claude-home` sentinel), and it lets `PermissionError` and other `OSError` subclasses escape — violating harvest's per-file isolation contract, which the design explicitly specified catching. | src/engram/harvest.py | 4 | Bob, Carl, Alice, Eve |
| [2/5] | 🟡 | `findings.parse` ends with a bare `except Exception` re-raised as `ValueError(f"unable to parse {path}")`, so a genuine programming error is reported as a routine `parse_failed` and the original cause never reaches `FileHarvestResult.error`. Contract validation also accepts whitespace-only `reviewers` values. The design specified catching `OSError` and `yaml.YAMLError` explicitly. | src/engram/findings.py | 1 | Alice, Bob |
| [3/5] | 🟡 | Catchup's globs are unreliable: without `nullglob` an unmatched pattern is passed through literally and parse-fails, and `dev/local/tmp/*review*.md` selects reviewer prompts and context dumps rather than review outputs (all 58 matches in this repo fail `findings.parse`). The step exits nonzero on essentially every real run. | claude-git-ferry skills/catchup/SKILL.md | 6 | Alice, Blake, Bob |
| [1/5] | 🟡 | Phase 2 acceptance requires a claude-git-ferry release commit carrying the CHANGELOG entry; the entry sits under `[Unreleased]` and HEAD is the feature commit, so the release flow never ran. | claude-git-ferry CHANGELOG.md | 6 | Blake |
| [1/5] | 🟡 | Scope creep beyond the PRD text: `engram query` now prints stored record bodies for findings hits, and `index --rebuild` re-embeds and carries findings forward. Both were mandated by the approved design (as cardinal-sin fixes), but neither is in the PRD. | src/engram/cli.py | general | Blake |
| [1/5] | 🟡 | `open_store` sets no SQLite `busy_timeout`, so a harvest concurrent with `engram index` or another harvest fails instantly with "database is locked" → `upsert_failed` → nonzero → purge keeps the file. Phase 2 makes this newly reachable by turning harvest into an externally triggered multi-process write path. | src/engram/store.py | 2 | Blake |
| [1/5] | 🟡 | Review-contract files under `dev/local/tmp/` are trashed by the stale-tmp rule with no harvest gate, and a test locks that behavior in. Combined with the catchup glob failing on tmp files, a contract-shaped review output in `tmp/` is lost at GC. | ~/.claude/skills/purge-devlocal/scripts/purge_devlocal.py | 5 | Blake |
| [1/5] | 🟡 | `_run_index` grew from ~38 to 62 lines, crossing the 50-line limit. | src/engram/cli.py | 4 | Alice |
| [1/5] | 🟡 | `tests/test_cli.py` now exceeds the 800-line limit. | tests/test_cli.py | general | Bob |
| [3/5] | ⚪ | Dead import: `from engram import findings` at `tests/test_findings.py:6` is never used. | tests/test_findings.py | 1 | Alice, Carl, Eve |
| [2/5] | ⚪ | The corpus name is defined twice: `FINDINGS_CORPUS` in `findings.py` and a hardcoded `'findings'` literal in the new `prune()` exemption SQL (a circular import forced it), so the exemption silently breaks if the constant changes. | src/engram/store.py | 2 | Blake, Eve |
| [1/5] | ⚪ | `Record.structured` is computed but never persisted or read — `upsert` maps only heading/body/lines into `Chunk`, so no consumer can distinguish a parsed finding from fallback prose. | src/engram/findings.py | 1 | Blake |
| [1/5] | ⚪ | Module export signatures deviate from the PRD's Structural Decomposition: `upsert(records)` is `upsert(store, config, repo, path, records)`; `harvest(paths)` is `harvest(store, config, paths)`. | src/engram/findings.py | general | Blake |
| [1/5] | ⚪ | purge-devlocal's SKILL.md never mentions the new pre-trash harvest sweep or its keep-on-failure rule, so an operator seeing "WARN harvest failed … not trashing this run" has no documented explanation. | ~/.claude/skills/purge-devlocal/SKILL.md | 5 | Blake |
| [1/5] | ⚪ | An unterminated frontmatter block surfaces the raw `"'---' is not in list"` from `lines.index` as the purge WARN detail. | src/engram/findings.py | 1 | Eve |
| [1/5] | ⚪ | `no_repo` results carry no `error` text, so a purge-kept file's WARN cannot distinguish "repo not gita-registered" from "repos.csv missing". | src/engram/harvest.py | 4 | Eve |
| [1/5] | ⚪ | The diff carries unrelated autoformat churn (trailing commas, re-wrapped arguments) through store.py, cli.py and test_cli.py, mixing style-only lines into a feature diff. | N/A | general | Alice |
| [4/5] | ⚪ | PRD-authoring gap, flagged as the design instructed: the PRD claims task 6 "extends the claude-git-ferry SKILL.md section added by PRD 00002", but 00002 stalled at task 5 of 7 and that section never existed. The design's pre-authorized fallback was correctly taken; the PRD text remains wrong. | claude-git-ferry skills/catchup/SKILL.md | 6 | Alice, Blake, Bob, Eve |
| [1/5] | ⚪ | Cannot statically verify: reported test suites execute and pass in all three repositories (sandbox constraint). | N/A | general | Bob |

### Advisory (local model, unconfirmed)

- (none — Quinn was unavailable this cycle; see Agent Status.)

## Alice

Consensus lens, implementation-aware. 20 findings: 4 🟠, 8 🟡, 8 ⚪. Full output:
`dev/local/tmp/alice-output-00003-c1.txt`.

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
himself across all three repos. 18 findings: 2 🔴, 4 🟠, 7 🟡, 5 ⚪. Full output:
`dev/local/tmp/blake-output-00003-c1.txt`.

Blake independently verified several claims against the live environment
(gita `repos.csv` membership, `engram` absence from PATH, a live `status` run
before and after deleting a source file, and a real-review-file parse producing
104 records). He is the only lens that rated anything Critical.

Per-rule verdicts:

B1: fail
B2: fail
B3: fail
B4: pass
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
B16: pass
B17: fail
B18: pass
B19: pass

## Bob

Doubt + de-slop lens (codex, static-only sandbox). 15 findings: 3 🟠, 10 🟡,
2 ⚪, plus the FIX/VERIFY/KNOWN buckets. Full output:
`dev/local/tmp/bob-output-00003-c1.txt`.

Per-rule verdicts (consensus rubric):

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

Doubt-rubric verdicts:

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Carl

Generalist lens (gemini via copilot). No frontend surface in this change, so
reviewed against the shared checklist. 9 findings: 1 🟠, 7 🟡, 1 ⚪. Full output:
`dev/local/tmp/carl-output-00003-c1.txt`.

Per-rule verdicts:

R1: pass
R2: pass
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: pass
R10: fail
R11: pass
R12: fail
R13: pass

## Eve

Doubt lens (Fable 5), activated by the codex doubt-roster guard. 13 FIX, 2
VERIFY, 4 KNOWN. Eve ran both test suites herself (engram 266 passed,
purge-devlocal 29 passed) and reproduced the `status` defect live. Full output:
`dev/local/tmp/eve-output-00003-c1.txt`.

Doubt-rubric verdicts:

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Quinn

⚠️ Unavailable. Dispatch and its one retry both exited 1 with
`[llama-cpp] failed to reach http://localhost:8080/v1/models: fetch failed`,
while the step-1 preflight had passed against provider `llamacpp8001`. Advisory
weight only; no follow-up task would have been created from a Quinn-only
finding.

## Follow-up Tasks Created

Safety check fired: the review yielded far more than 10 actionable follow-ups.
Per the loop-mode rule the top 10 by severity became rework tasks; the remainder
were deferred to batch end as `scope-overflow`. Trivial one-line fixes were
grouped into the task that already touches their file rather than deferred
separately.

1. [D1] Exempt the findings corpus from `Store.status()` staleness and dead-row accounting (M) — 🟠 [4/5]
2. [D1] Move the `--rebuild` findings-preservation block inside the rebuild error boundary (S) — 🟠 [4/5]
3. [D1] Add the end-to-end zero-loss test: purge → real harvest → source deletion → query (L) — 🟠 [4/5]
4. [D1] Decompose `findings.parse` and extract `_is_separator_row` (M) — 🟡 [4/5]
5. [D1] Extract one embed-text projection helper and use it in all three call sites (S) — 🟡 [4/5]
6. [D1] Extract `_harvest_path` from `harvest()` and annotate its public boundary (M) — 🟡 [4/5]
7. [D1] Untangle `process_store()`: extract the harvest gate, early-continue, rename the shadowed local, drop the diff-history comment (M) — 🟡 [4/5]
8. [D1] Replace synthetic parser fixtures with copies of real review files; drop the dead import (M) — 🟡 [4/5]
9. [D1] Catch `OSError` in `_resolve_repo_for_path` and consolidate it with `cli._resolve_repo_name` (M) — 🟡 [3/5]
10. [D1] Replace `findings.parse`'s bare `except Exception` with explicit `OSError`/`yaml.YAMLError`; reject whitespace-only `reviewers` (S) — 🟡 [2/5]

Deferred to batch end (not reworked this cycle): both 🔴 findings, the
PRD-vs-design record-fields and record-granularity questions, the `engram`-not-
on-PATH deployment gap, the claude-git-ferry release gap, the scope-creep
question, and 12 `scope-overflow` items. See
`dev/local/autopilot/deferred/202608012229-deferred.json`.

Verdict: 32 findings
Tests: 266 passed, 0 failed, 0 skipped
