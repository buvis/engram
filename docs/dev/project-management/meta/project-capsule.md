# Project Capsule: engram

Updated: 2026-11-10, after Session 7 was redefined around agent sessions.

## Key Invariants

- Standalone uv-managed Python CLI, not a Claude plugin.
- Local llama-server embedding endpoints; engram owns its embedding config.
- Queries require explicit repo or portfolio scope. Query `-k`/`--k` and index
  `--rebuild` are supported interfaces (user decision, 2026-11-01).
- Model/dimension mismatches fail loud. Production remains pinned to
  `ggml-org/bge-m3-Q8_0-GGUF:Q8_0`; never repin or rebuild without explicit request.
- Equal harness scores keep the current pin. The harness pins only on a passing gate.
- Retrieval returns source pointers; findings additionally carry their durable body.
- Index commits per file. Unchanged sources are not re-embedded.
- Read/parser failures are retried, not stored as successful empty sources.
- Project documents live under `docs/dev/project-management/`; transient packs
  live under globally ignored `docs/dev/tmp/`.

## Component Boundaries

- `client.py`: config, model identity, server leases, context budgets, embeddings.
- `store.py`: SQLite/FTS5/sqlite-vec, source caches, scopes, model checks.
- `corpora.py`, `chunker.py`, `transcripts.py`, `symbols.py`: enumeration and chunking.
- `indexer.py`: incremental indexing and pruning; `query.py`: hybrid retrieval.
- `findings.py`, `harvest.py`: durable review records.
- `diffmap.py`, `pack.py`: review context packs; `cli.py`: CLI entry points.
- `harness.py`, `eval/`: candidate scoring, gold set, and rg baseline.

## Active Work

### Batch 202611100725
- [x] 00010-repo-memory-corpus-v1 (2 cycles)
- [x] 00011-memory-migrate-command-v1 (3 cycles)
- [ ] 00012-agent-recall-surfaces-v1 (backlog, skipped: needs "Adoption decision: proceed" in the agent-session evaluation review)

Observations: 00010 shipped `src/engram/memory.py`, repo memory enumeration and
legacy skip in `corpora.py`, `engram memory check`, and status lines. Cycle 1
fixed a `yaml.safe_load` `ValueError` crash on invalid dates. The `sk-`
credential pattern is left-anchored (measured false positives in legacy
memory). `tests/test_repo_memory.py` exceeds 800 lines on purpose: PRD
acceptance commands pin that one file. The `enforce_prd_location.py` hook blocks
real `docs/dev/project-management/memory/` writes, which 00011 must account for.

Earlier: PRDs 00001–00007 are in `done/`. Symbol
lookup, audit harvesting, and meaningful status shipped and the installed CLI
was verified against the checkout. The speculative anonymous-symbol percentage
target was replaced with user-approved behavioral criteria. See
`reviews/2026-11-09-backlog-delivery.md`; do not reopen its resolved installation
or acceptance items.

PRD 00002's historical gate used 52 entries: all candidates scored 0.962 versus
rg 0.519. bge-m3 scored transcripts 1.000 and code 0.800. The unchanged portfolio
index took 12.6 seconds. Catchup integration shipped in git-ferry 0.3.0.
See the done PRD's Completion section and review 3 for evidence and limitations.

The gold set has 55 entries, including three decision queries. The November 9
closeout replaced one unavailable transcript under a pre-scoring sampling policy.
Historical scores apply to their original labels, not the revised set. The fresh
assessment found another missing transcript; see Project Health below.

Completion review fixed a regression that cached parser/read failures as empty.
The next normal index invalidates old empty-code markers once and reparses those
sources; later unchanged runs retain the cache. Existing embedded chunks remain.

The requested PRD 00001 follow-ups are triaged in
`reviews/2026-11-01-follow-ups.md`. Older findings from other PRDs remain separate.
Autopilot runtime state remains local and ignored; retain its unresolved ledger.

The follow-up fixes and code re-embedding migration shipped in `f8c2434` and
`ecbbe72`; do not repeat that work. The local model campaign is committed in
`f25ac54`. The fusion and fixed-fusion reranker probes are committed in `9ee1f73`.
Read `reviews/2026-11-03-probe-rerank-fixed.md` for results, limitations, and the
production-database timestamp observation. Intakes 00008 and 00009 contain the
updated reranker and fusion evidence. No production retrieval change or model
switch was made by these probes.

The separate file-held-out probe is recorded in
`reviews/2026-11-05-probe-heldout.md`: ten agent-authored questions, ten passage
labels including two transcripts. OR alone does not reproduce the earlier MRR
gain; OR plus reranking reaches 10/10 files and 7/10 passages. Independent human
questions and broader transcript labels remain necessary. Persistent reranker latency/fallback and Qwen3-0.6B embeddings on the full
snapshot remain later probes. Preserve the production pin, config, index, and
retrieval code; production changes and rebuilds require the user's authorization.

## Project Health

`master` tracks `origin/master` at `ba912d5`, initially clean. Run the main and
eval suites separately:
`.venv/bin/python -m pytest -q --ignore=eval` and
`PYTHONPATH=src:. .venv/bin/python -m pytest -q eval`.
Fresh verification: **501 main tests passed, one failed; 30 eval tests passed**.
`test_real_goldset_loads_clean_and_covers_transcripts_and_code` now fails on
`cellar/.claude/projects/-Users-bob-git-src-github-com-buvis-gems/c0e70656-a139-4b1b-8407-f8989807631e.jsonl`.
This is a different source from the repaired closeout anchor. Cellar still tracks
the blob in HEAD, but its worktree reports a deletion; this assessment did not
restore or otherwise change it. Exactly one of the 55 current gold paths is
missing. Stabilize evaluation-source availability rather
than repeatedly relabeling disappearing transcripts; preserve historical freezes.

Current memory enumeration maps **all 295 files to `_unmapped`**. In
`corpora.py`, registry paths replace `/` but retain `.`, whereas actual Claude
project directory names use `github-com`. This old deferred defect still affects
repo-scoped memory recall and should be fixed before memory-source expansion.

Portfolio status exits 1: **7,072 dead rows** (6,597 transcript, 168 PRD,
7 discovery, 300 code), plus 11 stale memory files, 6 stale transcripts,
3 stale code files, and missing required `code:herdr-plugins`. Its registered
directory does not exist. Reconcile that registry entry/source before an ordinary
incremental portfolio refresh; a model switch or full rebuild is unnecessary.
Engram itself is now registered, so the historical own-repo pack blocker is stale.

Review-pack correctness debt remains visible in current source: unreadable PRDs
still trigger filename-based memory queries; omission notices can exceed the
hard cap after all section items are removed; an empty `--diff` head is passed
as an empty source ref; reuse filtering occurs after top-five retrieval. Triage
the retained PRD 00003/00004 findings against current code rather than treating
every historical finding as unresolved. The catchup harvest succeeded for 14
supported review/audit files and rejected 13 ordinary reports for missing
frontmatter; the broad review glob still mixes supported and unsupported inputs.

No extra worktree or executed plan belongs to this assessment. The prior stash
archive and intentional database rollback backups remain retained.

The requested redacted index audit found fixtures/examples and prose among the
checked credential patterns, with no plausible live credential identified.
See the follow-up note for scope, evidence, and the unchanged `0644` file mode.

## Next Work

1. Fix memory repo attribution and stabilize the missing gold-source fixture.
2. Reconcile the missing registered source and refresh the stale portfolio index.
3. Verify and fix the remaining review-pack correctness findings; review dependency
   PR #2 with parser/index regression checks. Add repeatable CI coverage.
4. Collect independent retrieval questions using
   `reviews/2026-11-05-independent-evaluation-protocol.md` (20–30 total; start
   with 5–10 actual questions). Freeze labels before comparing fusion variants
   and the 0.6B reranker; measure persistent latency/fallback only if gains hold.
5. Specify intake 00010's repository-owned shared memory contract, including
   path/format, evidence, migration, scope, and host integration. This work can
   proceed while independent questions accumulate. Intakes 00008/00009 remain
   evidence-gated; no embedding migration is justified by current measurements.

## Related context

Topic (2026-11-10, PRD 00011): "Memory migrate command". Repo and portfolio
queries both returned only the PRD itself
(`prds/wip/00011-memory-migrate-command-v1.md`: 7-10, 153-162, 183-187, 28-34,
114-122; top score 0.0328); no prior related work indexed. Reuse targets are
known directly: `src/engram/memory.py` (`parse_memory`, `check_directory`,
`memory_dir`, credential guard) from PRD 00010.

Staleness (`engram status --scope portfolio`, exit 1, 2026-11-10): memory
stale=7, transcripts stale=3 dead=859, prd stale=1 dead=68, code stale=33
dead=133. Harvest: 18 review files upserted, 14 missing frontmatter (known).

## GitHub State

Remote: `https://github.com/buvis/engram`. No open PRs (PR #2 closed). Only open
issue: Dependency Dashboard #3. No releases. Workflow "Test" on master: last 5
runs success (2026-11-10), so `c220c4d` CI did reach GitHub.

## Project Memories

Engram remains a standalone CLI, not a plugin. It owns embedding configuration
and bare llama-server lifecycle; host chat model registries are separate.

## Historical External Follow-up

- The earlier capsule records an unrelated merge conflict in `buvis/home`;
  its current status was not checked in this assessment.

## Session 1 complete: memory attribution (2026-11-09)

This session supersedes earlier memory-attribution observations for the checkout.
The live baseline was reproduced: all 295 enumerated files and all 330 indexed
memory chunks (270 files) were `_unmapped`. Claude encodes dots, underscores,
spaces, and other non-ASCII-alphanumeric characters as hyphens; enumeration now
matches complete registry paths using that encoding. Collisions remain unmapped
regardless of row order, including different names for the same path. Duplicate
identical registrations are harmless. Unknown paths and subdirectories are not
assigned by prefix or basename. Current enumeration maps 162 files to **22**
registered repositories; 133 files have no exact registry match.

Migration was verified on a disposable SQLite backup of the existing production
index, using the pinned BGE-M3 server on port 8083. A memory-only portfolio pass
scanned 295 files, added 234 chunks, pruned 209, and reported no failed/skipped
sources. The resulting 355 memory chunks cover 294 files, plus one empty source.
All 177,152 unrelated chunks and vectors, 16,664 unrelated empty-source records,
and all model/cache metadata had identical before/after fingerprints. BM25,
vector, and hybrid recall remained isolated in all 22 mapped repository scopes.
The repeat pass added/pruned zero chunks. SQLite and FTS integrity checks passed.

The production database and configuration remain unchanged. No full rebuild,
model switch, historical snapshot edit, or server shutdown occurred. The temporary
database was removed; existing rollback backups were preserved. The installed
CLI is still the previously verified version: **Session 3 must install this fix
before refreshing the live index**. Its planned portfolio refresh will migrate
memory attribution; alternatively, the documented memory-only portfolio command
migrates just memory. A repo-only pass cannot prune legacy `_unmapped` rows.

Verification: **69 focused tests passed; 517 main tests passed, one failed;
30 evaluation tests passed**. The sole main-suite failure remains the missing
gems gold-source transcript
`cellar/.claude/projects/-Users-bob-git-src-github-com-buvis-gems/c0e70656-a139-4b1b-8407-f8989807631e.jsonl`,
reserved for Session 2. Sixteen new
regressions cover path encoding, ambiguous/unknown mappings, scoped recall,
migration of chunks and empty sources, isolation, and idempotence. Fail-first
testing reproduced the defects. Diff review checked collision handling, migration
scope, and the change that skips unrelated code enumeration on memory-only runs.
Black, Ruff correctness rules (`E4,E7,E9,F`), and `git diff --check` passed.
The broad global Ruff profile retains style debt; its isolated checks also report
the same two pre-existing indexer findings as HEAD (`PLR0402`, `BLE001`).

Next: **Session 2, stabilize evaluation sources**. Preserve Cellar's unrelated
working-tree deletion and recover private evidence without changing gold labels.
Sessions 2–8 remain pending in `plans/2026-11-09-engram-next-work.md`. This was a
bounded repair session, not new PRD execution; PRDs 00001–00007 and the previous
global installation remain complete.
No session worktree or scratch file remains.

## Session 2 complete: evaluation sources (2026-11-10)

This section supersedes earlier source-availability observations. The assessment
baseline remains **501 main passed, one failed; 30 eval passed**. At session start,
after Session 1, verification reproduced **517 main passed, one failed; 30 eval
passed**, with the same missing gems transcript. Cellar had since committed the
deletion in `eda46f05ef5ea06d19d470e7a2f04024255265b3` (November 9, 23:37 CET).
The exact 558,897-byte source was recovered privately from
`e2bc3d7b30027e542dd894db0f774e315c6baf0c`, blob
`6e0a164b6d8508b6eee1a7403dbc93a89d5de1fd`; its SHA-256 is
`40071e87472d4d7d2e9f63ffb4fef9d0685b8e6ad6d93fb20748507f5f2f2c32`.
Its retained turns contain the rebase, GPG, signing-key, and SSH incident evidence.
Cellar's worktree and index were not changed.

`eval/sources.json` now pins the gold-set fingerprint, resolved scoring identities,
source hashes/sizes, and available Git revisions. All **55 unchanged labels**
have their **53 distinct sources** retained under
`~/.local/share/engram/eval/sources/` (9,951,037 bytes, directories `0700`, files
`0600`). Source bodies remain outside Git. Thirty-two sources have matching
Cellar revisions; 21 require private backup if their live sources disappear.
`PYTHONPATH=src:. .venv/bin/python -m eval.sources validate` verifies the archive;
`restore` recovers missing copies only from matching live bytes or pinned Git
history. Capture refuses overwrite; validation rejects missing/corrupt sources,
label drift, and incomplete manifests. Frozen symlink identities survive source
retargeting/deletion, including restoration through the original resolved path.

New comparison preparation chunks retained bytes while preserving original
scoring/embedding paths and records the manifest hash in its snapshot identity.
All sources chunk successfully (**729 chunks**); all **eight passage-label
queries** still match. No new campaign was prepared or scored. Gold queries,
target labels, corpus labels, and passage labels are unchanged. The shipped-set
test now explicitly validates retained private evidence. The live harness remains
strict and still rejects the absent live gems transcript; this repair does not
claim live portfolio coverage or a new retrieval score.

Verification: **63 focused tests, 519 main tests, and 47 evaluation tests passed**.
Black on changed code, isort on new modules, Ruff correctness rules (`E4,E7,E9,F`),
and `git diff --check` passed. The full `tests/test_harness.py` formatting check
retains the same three unrelated differences verified against HEAD.
Eighteen additional regressions cover exact Git recovery,
deletions, corruption, labels, overwrite refusal, permissions, symlink identities,
original embedding/scoring paths, and read-only snapshot preparation. Fail-first
checks reproduced the missing retained-source API, snapshot integration, and
symlink restoration defects.

Doubt review completed two passes: **ten doubts, four fixed, three verified,
three known**. Fixes froze symlink identities, restored via their frozen origins,
preserved parser basenames while removing an unused helper argument, and made
gold loading a single pass instead of resolving identities twice. Verification
covered full source/passage coverage, strict live validation, and unchanged labels
and protected artifacts. Known limits: 21 sources depend on private backups;
private acceptance is not portable CI coverage (Session 5 owns that separation);
the three pre-existing test-formatting differences remain outside this repair.

SHA-256 and modification-time comparisons confirmed no changes to the production
database/configuration, three historical comparison snapshots, or their two
campaign pointers. The production embedding model, rollback backups, and servers
were untouched. No global installation, full index rebuild, frozen-repository
work, or fresh PRD execution occurred. No session scratch files or worktrees
remain. Pre-existing unrelated capsule edits are preserved outside this commit.

Next: **Session 3, restore portfolio index health**. Investigate `herdr-plugins`,
preserve/back up the live index, install the tested fixes through the established
process, and refresh incrementally. Session 1's live memory migration remains
assigned there. Sessions 3–8 remain pending; stop after this completed session.

## Session 3 complete: portfolio index maintenance (2026-11-10)

This section supersedes earlier installation and portfolio-health observations.
`herdr-plugins` was deliberately retired on November 9, not moved. Its retained
session `cd12c6d6-df15-4cf5-b982-b4b6029877cc` and the Pluck reference README
confirm retirement. The complete archive at
`~/.local/share/archive/herdr-plugins.bundle` verifies at `4362ef4`.
Warrant `d4c165e06b6611f16d5182d147ec42ec` removed only its stale gita row;
byte comparison confirmed all other registry rows were preserved. Every remaining
registered directory exists. Its three retained memory files remain searchable
in portfolio scope as `_unmapped`; its 410 obsolete repository rows were pruned.

Pre-maintenance SQLite backup:
`~/.local/share/engram/backups/session3-20261110/engram.db`, 1,554,391,040 bytes,
SHA-256 `fc45ad9183cc4c8dea6efce8591dbce4748d2a59fae791783d15f7c80ddbf124`.
Integrity passed; all 177,482 original chunks/vectors were preserved. Before
refresh, every database byte after the SQLite header matched the backup.
The same private directory retains registry/config backups, constraints,
installation receipt, protected-file fingerprints, and maintenance logs.
Existing rollback backups remain untouched.

Installation warrant `ad9e2dd9b263e61c1fccf3ff35f3c082` was refused because
mise-managed uv is outside trusted executable roots. The user completed the
exact installation in a host terminal; no wrapper or warrant policy change was
used. All **15 installed modules** match the tested checkout. Managed Python
3.14 and all four dependency versions remain as constrained by `uv.lock`.

`engram index --scope portfolio` succeeded in **163.94 seconds**: 12,281 new
chunk IDs and 9,198 pruned old IDs. Fresh pre-maintenance status had **7,142 dead
rows**, versus November 9's 7,072, and stale files: 11 memory, 6 transcripts,
98 code. After refresh, **dead rows are zero** and no required source is missing.
An **8.89-second** catch-up pass reconciled changes made by other active sessions;
both index runs exited 0 with no failed-source or failed-code-enumeration reports.
Final counts: memory 355, transcripts 34,306, findings 57,535, PRD 15,653,
discovery 770, code 71,925, decision 29 (**180,573 total**).

Final CLI status deliberately remains **exit 1**: one stale code file,
`claude-agoge/skills/run-agoge/scripts/target_snapshot.py`, was edited at
00:33:31 CET, after the catch-up pass finished around 00:33:09. One transcript
was in flight; no transcript, memory, PRD, discovery, or decision was stale.
No failure was suppressed or configuration relaxed. The 2,449 unsupported-code
files, 6,897 excluded files, and absent optional document corpora remain reported.
Concurrent edits require a later ordinary incremental refresh; this session does
not freeze other sessions or claim a permanently clean portfolio.

All **295 memory files** are represented (294 chunked, one empty): 159 map to
21 repositories; 136 have no registered project mapping. BM25, vector, and hybrid
recall passed repository-isolation checks across all 21 mapped scopes. All
**57,535 findings and their vectors** are unchanged. SQLite and FTS external-
content integrity passed; vector coverage and attribution were checked. Model,
dimension, and cache metadata are unchanged. All 15 protected artifacts retain
their hashes and mtimes, including configuration, the retirement archive, three
historical snapshots, two campaign pointers, and evaluation labels/results.

Verification: **85 focused tests passed against the installed Python 3.14 runtime;
519 main tests and 47 evaluation tests passed**. All 55 labels and 53 private
sources validate; `git diff --check` passed. Doubt review covered seven doubts:
one fixed by the catch-up pass, five verified, and one retained limitation for
continued concurrent edits. The second pass confirmed that limitation rather
than starting an unbounded refresh loop. No production source change, model
switch, complete rebuild, unrelated server shutdown, or fresh PRD execution
occurred. Only the pinned BGE-M3 endpoint on 8083 was started.

Next: **Session 4, repair review-pack correctness**. Stop after Session 3.
The active multi-session plan remains; no session scratch files or worktrees
were created. Unrelated working-tree capsule edits remain outside this commit.

## Session 4 complete: review-pack correctness (2026-11-10)

This section supersedes earlier review-pack observations. Current source reproduced
all four named defects before repair: a 204-token hard cap emitted 437 estimated
tokens from framing/omission notices alone; `HEAD~1..` read the staged function
instead of committed HEAD; 25 local code candidates crowded foreign evidence out
of retrieval; unreadable, blank-title, and titleless PRDs queried filenames or an
empty string. Two-dot and three-dot open-ended ranges now read HEAD. Explicit
three-dot heads also map the correct symbols and embedding text.

Reuse exclusion is applied in both BM25 and sqlite-vec searches before their
20-candidate limits and the fused top five. Other queries retain their existing
scope/ranking behavior. Memory retrieval requires a readable, nonblank first H1;
available PRD prose still renders without a title. Real-store coverage verifies
memory bodies reach Task prose with its two-hit limit. Long omission notices
collapse to a counted disclosure before trimming content. The pack keeps all
four headings and symbol-omission counts; an impossible programmatic cap fails
without overwriting an existing pack. Normal budgets retain unreadable paths.

Adjacent repairs: reject absolute/traversing paths and symlinks escaping the
repository; read/map the diff before reindexing; reject empty or sentinel-only
non-diffs; refuse pack publication when reindexing reports failed sources or the
current repository's unavailable code corpus. CLI filesystem, configuration,
registry, embedding-server/preflight, and model-identity failures now exit 1 with
diagnostics. Existing model-mismatch guidance remains. The freshness disclosure
now says only the current repository was refreshed, removing the obsolete claim
that PRD 00002 is pending. Binary/mode-only diff sections remain supported.

PRD 00003/00004 triage against current source and retained reviews:

- Closed or superseded: failed code enumeration already preserves indexed rows
  (`indexer.py` and its two repository-enumeration regressions); findings parsing
  already catches only expected read/YAML errors and has real review fixtures;
  the missing memory-body regression is now covered. Prior installation,
  registration, corpus population, and git-ferry release blockers remain resolved
  by the completed delivery and Sessions 1–3, not reopened here.
- Unsupported as stated: SQLite does not fail instantly merely because no explicit
  timeout is supplied. A disposable current store reports `busy_timeout=5000`.
  PRD/export-signature, findings origin-label, and full-pack doubt-lens disputes
  retain their recorded design adjudications; they are not newly proven defects.
- Confirmed separate findings/harvest debt: collection-valued blank reviewers
  still pass validation; registry resolution retains raw path equality and catches
  only `FileNotFoundError`; the `claude-home` resolver fallback remains shared with
  indexing. Rebuild's first error boundary still lacks cleanup, and concurrent
  harvest/rebuild replacement is not coordinated. Findings fields/granularity and
  retrieval-quality evidence need their own work, not a pack repair or rebuild.
- Separate pack debt: Git C-quoted paths, canonical self-match exclusion, direct
  `build()`'s cwd-relative default output, slug collisions/generated diff retention,
  prose origins/multiline pointer formatting, dead argument threading, and
  size/style findings remain. Section-cap/spec inconsistencies and the largest-
  section trimming policy remain documented. Long symbol queries can weaken AND
  lexical retrieval; changing fusion stays evidence-gated in Sessions 7–8.
- External review/purge dispatch, sentinel consumers, prompt substitutions, and
  cross-project lifecycle tests remain with their owning skills/plugins. Their
  historical paths were not treated as current proof or edited. The local pack
  now rejects the non-diff sentinel; no claim is made about the external producer.

The November 9 catchup harvest mismatch remains **14 supported files succeeded,
13 ordinary reports lacked required frontmatter**. A fresh read-only parse census
of all 27 current review/audit files reproduces **14 supported / 13 missing
frontmatter**. No live harvest or embedding ran; repairing the producer's broad
glob remains separate. Parser rejection is legitimate and was not suppressed.

Verification: **130 focused, 547 main, and 47 evaluation tests passed**. The main
suite ran with `--ignore=eval`; evaluation ran separately with `PYTHONPATH=src:.`.
Twenty-eight new cases cover the repairs and adjacent boundaries. Fail-first
checks reproduced the defects; Git fixtures deliberately differ between HEAD,
the index, and the worktree. Black passed on changed code, isort on the new test
module, Ruff correctness rules (`E4,E7,E9,F`), and `git diff --check` passed.
Unrelated pre-existing Black differences in the two old pack test modules remain.

Two-pass doubt review: **10 doubts, 4 fixed, 4 verified, 2 known**. Fixes compacted
notices before discarding evidence, covered registry/model-identity error paths,
removed unnecessary conditional keyword dictionaries, and removed duplicate
titleless-test coverage. Verified both retrieval limits, Git source selection and
containment, real memory-body inclusion, and additive/default query behavior.
Known limits are the separate triaged debt above and deployment: the global CLI
remains the verified Session 3 installation; this session's source repairs are
not yet installed. No fresh PRD execution or completion-review gate was entered.

The production model/configuration/index, historical evaluation artifacts, and
rollback backups were not changed. No model servers were started/stopped, no
complete index rebuild ran, and the frozen repository was not accessed. No session
scratch files or worktrees remain. Unrelated capsule edits are preserved unstaged.
The multi-session plan is retained and Session 4 is marked complete.

Next: **Session 5, review dependencies and establish portable CI**, preserving
private-source acceptance checks. Stop after this completed Session 4.

## Session 5 complete: dependencies and portable CI (2026-11-10)

This section supersedes earlier dependency and CI observations. PR #2
(Renovate, `tree-sitter-language-pack` 1.14.0 → 1.25.0) was tested on current
master in an isolated worktree, not merged as-is. Its relevant breaking changes:
`process()` raises typed `Error` subclasses instead of `RuntimeError` (no engram
caller catches `RuntimeError` from it; the indexer catches `Exception` and
retries), and since 1.20 `str()` of an `Other` structure kind is JSON. Grammars
download lazily into a per-version cache (`~/Library/Caches/tree-sitter-language-pack/vX/`);
the 1.14.0 cache held 43 grammars, 1.25.0 starts empty. Linux and macOS 15+
wheels exist; the host and `ubuntu-latest` qualify.

A read-only census chunked the whole portfolio code corpus under both versions:
**21,250 files**, identical enumeration, **6,907 identical exclusions**,
identical language detection (2,450 unsupported), **zero parse errors** in
18,800 parsed files. Chunks rose 71,955 → 73,004 and anonymous headings fell
17,793 → 17,294. **760 files** changed chunks: JS/TS/TSX arrow functions
mostly gained names (one JS file lost some), Swift structs stop reading as
classes, C headers gained 875 constants, 123 macros, and 95 types. Those 1,093
`Other` symbols rendered as `{"Other":"Constant"}` in doc types, headings, and
diff symbols. Fixed with `symbols.kind_name()` (the kind payload); fail-first
regressions in `test_symbols.py` and `test_diffmap.py`. Two Python diffs in
the census were concurrent file edits, not parser changes.

`4eb8af5 fix(symbols): adopt tree-sitter-language-pack 1.25.0` is pushed to
`origin/master` with the six earlier session commits (`ba912d5..4eb8af5`).
PR #2 is superseded; Renovate should close it on its next run. The dev `.venv`
now has 1.25.0. **The installed global CLI still has 1.14.0** and lacks the
Session 4 and 5 fixes. After a future installation the first index downloads
1.25.0 grammars, and unchanged code sources keep their 1.14.0 chunks until
edited (hash cache); no re-chunk or rebuild was run or is required.

CI: `.github/workflows/test.yml` runs both suites on `ubuntu-latest`, Python
3.12 and 3.14, with SHA-pinned actions matching buvis/gems, ripgrep, and
`uv sync --locked`. The `private` pytest marker (registered with
`--strict-markers`) tags `test_real_goldset_loads_clean_and_covers_transcripts_and_code`;
CI deselects it with `-m "not private"`. Local default runs still include it.
README and eval README state that green CI does not validate private evidence.
An empty-`HOME` simulation found four status tests reading the real Cellar
checkout; the file's autouse fixture now stubs that producer. Only the private
test fails without private state.

**Commit `c220c4d ops(ci): …` is not pushed.** The agent PAT lacks the
`workflow` scope, so GitHub refused the workflow file. The user must push from
a host terminal. CI has therefore never run on GitHub; only the local
simulation passed.

Verification: 120 focused tests passed; CI simulation (empty `HOME`, minimal
`PATH`, worktree cwd) **548 main passed, 1 deselected; 47 eval passed**; full
local **549 main and 47 evaluation tests passed**, including the private test.
`uv lock --check`, Ruff correctness rules, Black on changed modules, and
`git diff --check` passed. The production model, configuration, index,
historical snapshots, and rollback backups were untouched; no servers were
started or stopped. The session worktree, branch, and scratch files were removed.

Next: **Session 6, specify shared project memory**. Stop after Session 5.

## Session 6 complete: shared project memory spec (2026-11-10)

Intake 00010 was elicited at comprehensive depth and moved to
`intake/processed/00010-shared-project-memory/` (`discovery.md` beside
`idea.md`). User decision: repository memory must be **public-safe**, because
28 of 29 `buvis` repositories are public (only `cellar` is private).
Host-private, personal, and secret facts stay in host-global memory.

The contract has six parts:

- **Path and format.** Memory lives in `docs/dev/project-management/memory/`,
  one `<slug>.md` file per fact. Each file has frontmatter `name`, which must
  equal the file stem, `description`, `type`
  (`project`/`feedback`/`reference`, `user` refused; Claude `metadata.type`
  accepted), `source`, and a non-empty `evidence` list. Git records the author,
  the date, and every revision.
- **Index.** `MEMORY.md` is sorted, limited to 200 lines and 25 KB, and marked
  `merge=union` in `.gitattributes`.
- **Changes.** A correction edits the file; a retraction deletes it. Each change
  is its own `docs(memory): <verb> <slug>` commit. Incremental indexing prunes
  deleted memories.
- **Scope.** New memory goes to the current repository. Recall defaults to repo
  scope; portfolio scope is explicit. Callers enforce blind-role exclusion.
- **Hosts.** `AGENTS.md` carries a "Project memory" section for all hosts. For
  Claude, the repository sets `autoMemoryEnabled: false` and `CLAUDE.md` adds
  `@docs/dev/project-management/memory/MEMORY.md`. Native Codex and Copilot
  memory was not verified (2026-11-10 docs check), so it is not used.
  `autoMemoryDirectory` was rejected: only absolute and `~/` paths are
  documented. A probe could not run, because nested `claude` failed OAuth in
  the sandbox.
- **Migration.** 159 mapped legacy files across 21 repositories; the 136 unmapped
  files, including 80 in the `~/.claude` project, stay in Claude auto-memory.

Two backlog PRDs. Both passed the grounding gate with 0 blocking findings:

- `00010-repo-memory-corpus-v1`: `src/engram/memory.py` validator,
  repository memory enumeration, legacy-skip for repositories with repository
  memory, `engram memory check`, and the status lines `invalid` (exit 1) and
  `legacy-shadowed`.
- `00011-memory-migrate-command-v1`: `engram memory migrate --from --to
  [--apply]`, a dry-run TSV report, conversion that writes no absolute host
  path, idempotent wiring (`.gitattributes`, `AGENTS.md`, `CLAUDE.md`,
  `.claude/settings.json`), and no commit or push. It becomes eligible after
  00010 is done.

The rollout is attended, not a PRD. For each repository: dry run, public-safe
review, apply, `engram memory check`, one commit. Push only after the user
approves the batch. Then update `~/.claude/rules/memory.md` and
`~/.claude/AGENTS.md` to say that project facts go to repository memory.

**Blocker found.** The installed autopilot `enforce_prd_location.py` hook
(0.10.0, source only in frozen `claude-autopilot`) rejects writes to
`docs/dev/project-management/memory/`. It also rejects `meta/` subdirectories.
Agents cannot write repository memory until the companion change ships.

Companion work:

- agent-plugins intake 00065 (`b91f37b`): layout vocabulary and blind-role
  recall exclusion.
- agent-skills intake 00176: catchup `load-memories.sh` (its `tr '/.' '-'`
  repeats the Session 1 encoding bug), distil-memory writes, promote-memories,
  layout.md, and brush. A concurrent 00135 autopilot session swept this staged
  file into its commit `982c885`. The content is intact; history was not
  rewritten.

Observed separate debt: stray `pytest-of-bob-…test_cli_clean_exit_for_ordina0`
project directories (runs 718–725) under `~/.claude/projects` show that some
test suite writes into the real Claude projects directory. No source under
`~/git/src` matched, so the origin is unknown.

Verification: documentation and specification only. No production code
changed, so the test suites were not rerun. `git diff --check` passed. The
production model, configuration, index, snapshots, and backups were untouched.
No servers were started. Probe scratch files were removed.

Next: **Session 7, collect independent retrieval evidence** (needs genuine user
questions). PRDs 00010 and then 00011 can run through `/autopilot:run-autopilot`
independently. Stop after Session 6.

## Session 7 redefined: agent adoption and evidence (2026-11-10)

Not complete. The session changed direction on a user decision: Engram serves
agents, so evidence comes from agent sessions, not from user-written questions.

- **Adoption measured.** Claude sessions modified since 2026-11-01, this
  repository excluded: 364 sessions, 40 projects. 14 sessions (4%) called
  Engram, all through the catch-up skill, in 4 projects (33 query, 22 status,
  20 index, 19 harvest, 0 lookup). 212 sessions ran 5,671 ad-hoc searches.
  `engram pack` runs from scripts and is invisible to this scan. Nothing in
  `AGENTS.md` names Engram.
- **Pilot.** Eight random sessions held 91 search bursts. Most were lookups in
  a known file; a minority were cross-repo, history, or decision questions.
- **New protocol.** `reviews/2026-11-10-agent-session-evaluation-protocol.md`:
  mine search bursts, label from the files the agent settled on, exclude each
  question's own transcript from its pool. The 2026-11-05 human protocol is now
  a secondary set of five private questions; `a30de13` recorded its ledger.
  Two of those answers live only in non-indexed sources (BIM vault, a project
  capsule): corpus coverage gaps, not ranking misses.
- **Adoption design (user-approved order).** 1. agent-session evaluation;
  2. orchestrator injection of Engram context into autopilot phase prompts
  (agent-plugins intake 00066); 3. an Engram plugin: portable skill and MCP
  server, plus per-host hooks.
- **Spike.** `spikes/engram-plugin/` (throwaway, never merges). One plugin
  directory passes the agent-plugins validator; a stdlib MCP server answers
  `initialize`, `tools/list`, `tools/call`; one host-neutral nudge core emits
  the documented post-tool output for Claude, Codex, Gemini, Copilot, and Kiro;
  `ENGRAM_NUDGE=off` and `ENGRAM_PACK_FILE` keep it clear of orchestrator
  injection. Run `python3 docs/dev/project-management/spikes/engram-plugin/demo.py`.
  Later rounds verified the nudge live in Claude Code, Codex 0.167.0 (config-level
  hook only; a repository `.codex/hooks.json` did not fire), and Copilot CLI
  1.0.108. Pi is unrun, Kiro untested, and Gemini CLI cannot authenticate here.
- **Graduated (user decision).** Engram PRD `00012-agent-recall-surfaces-v1`
  (backlog): `engram mcp` and `engram nudge <host>`, so hooks call a bare
  command and need no plugin-root path. Its `eligibility` check waits for
  `Adoption decision: proceed` in the agent-session protocol. agent-plugins PRD
  `00067-engram-plugin-v1` (backlog, unpushed there): skill, `mcp.json`, and
  per-host hook files; eligible once `engram nudge --help` works. Both passed
  the grounding gate with 0 blocking rows. Delete the spike when 00012 lands.

Verification: documentation and a throwaway spike only. No production or
evaluation code changed, so the suites were not rerun. `git diff --check`
passed. Production model, configuration, index, snapshots, and backups were
untouched; no servers were started beyond Engram's own on-demand query serving.

Next: execute redefined **Session 7** (build the miner under `eval/`, freeze,
score). Then set the protocol's `Adoption decision:` line from the hit rate;
that line releases PRD 00012, and intake 00066 is decided from the same result.
