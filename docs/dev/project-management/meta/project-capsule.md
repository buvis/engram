# Project Capsule: engram

Updated: 2026-11-10, after Session 2 evaluation-source retention.

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

PRDs 00001–00004 are in `done/`; no PRD or plan is active. Backlog 00005–00007
requires a new user request.

PRD 00002's historical gate used 52 entries: all candidates scored 0.962 versus
rg 0.519. bge-m3 scored transcripts 1.000 and code 0.800. The unchanged portfolio
index took 12.6 seconds. Catchup integration shipped in git-ferry 0.3.0.
See the done PRD's Completion section and review 3 for evidence and limitations.

The gold set now has 55 entries, including three decision queries. These were
validated by `load_goldset`; the expensive live harness was not rerun for them.
Its historical gate score must not be presented as a score for the enlarged set.

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

Local `master`; no remote or CI. Run the main and eval suites separately:
`.venv/bin/python -m pytest -q --ignore=eval` and
`PYTHONPATH=src:. .venv/bin/python -m pytest -q eval`.
The installed implementation matches the checkout after the approved warrant
installation of the production fixes; later evaluation tools remain in the repo.
Verification on 2026-11-05: main suite 467 passed, 1 failed; eval suite 30 passed.
`test_real_goldset_loads_clean_and_covers_transcripts_and_code` fails because a
live transcript target is missing:
`/Users/bob/git/src/github.com/buvis/cellar/.claude/projects/-Users-bob-git-src-github-com-buvis-agent-skills/5a656567-eccb-474e-833a-8ca6a7601e5a.jsonl`.
Cellar commit `ba64775dd` deleted this transcript on November 3; no relocation
was found. The new probe uses frozen sources, without replacing historical labels.
Resolve source availability before a new live-source evaluation; preserve the
historical development labels and frozen campaign results when investigating.
Both stashes were inspected: formatting/import cleanup only, no unfinished logic.
Both were dropped with user authorization after a verified recovery bundle was saved.
Exact hashes and the archive path are in the follow-up note.
No extra worktree or executed plan belongs to this session.

The completion review's context-pack command could not resolve engram in the
installed registry. This is already recorded in the PRD 00004 review; no registry
configuration was changed here.

The requested redacted index audit found fixtures/examples and prose among the
checked credential patterns, with no plausible live credential identified.
See the follow-up note for scope, evidence, and the unchanged `0644` file mode.

## User Decisions Still Open

- Resolve the unrelated merge conflict in `buvis/home`.

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

## Session 3 checkpoint: awaiting warrant (2026-11-10)

`herdr-plugins` was deliberately retired, not moved. Its retained session
`cd12c6d6-df15-4cf5-b982-b4b6029877cc` records deletion on November 9;
`~/.claude/docs/dev/project-management/discovery/00185-pluck-reference/README.md`
confirms the replacement references. The complete archive at
`~/.local/share/archive/herdr-plugins.bundle` verifies at `4362ef4`.
Only its stale gita registration remains unavailable. Removing that row retains
its three memory files as `_unmapped` for portfolio recall.

Fresh status exits 1: **7,142 dead rows** (6,663 transcripts, 168 PRD,
7 discovery, 304 code); stale files: **11 memory, 6 transcripts, 98 code**.
No portfolio refresh has run. The production index, configuration, and historical
snapshots remain unchanged. Only the pinned BGE-M3 endpoint was started (8083).
No unrelated server was stopped; no model change or full rebuild occurred.

Verified SQLite backup: `~/.local/share/engram/backups/session3-20261110/engram.db`,
1,554,391,040 bytes; SHA-256
`fc45ad9183cc4c8dea6efce8591dbce4748d2a59fae791783d15f7c80ddbf124`.
Integrity passes; all 177,482 chunks/vectors, including 410 retired-repository
rows, are preserved. The same directory retains registry/config backups,
protected-file fingerprints, source hashes, installation receipt, and constraints.
Existing rollback backups and unrelated working-tree capsule edits are retained.

Verification: **85 focused, 519 main, and 47 evaluation tests passed**;
`git diff --check` passed. Installed `corpora.py`, `indexer.py`, and `harness.py`
still differ from tested source. Installation request
`ad9e2dd9b263e61c1fccf3ff35f3c082` awaits host warrant approval.
Seatbelt denied the registry write; removal request
`d4c165e06b6611f16d5182d147ec42ec` also awaits approval. Neither was bypassed.
Next: finish **Session 3**, verify both receipts and installed modules, refresh
incrementally, inspect portfolio status, and verify memory attribution/findings
and protected artifacts. Do not start Session 4. No session scratch or worktree
was created; the multi-session plan remains active. No fresh PRD execution occurred.
