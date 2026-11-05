# Project Capsule: engram

Updated: 2026-11-05, after the separate file-held-out probe.

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
