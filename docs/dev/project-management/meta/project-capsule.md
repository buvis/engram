# Project Capsule: engram

Updated: 2026-11-01, after PRD 00002 finalization and completion review.

## Key Invariants

- Standalone uv-managed Python CLI, not a Claude plugin.
- Local llama-server embedding endpoints; engram owns its embedding config.
- Queries require explicit repo or portfolio scope.
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

## Project Health

Local `master`; no remote or CI. Run `.venv/bin/python -m pytest -q`.
Two pre-existing formatter-only stashes remain untouched. No extra worktree or
executed plan belongs to this session.

The completion review's context-pack command could not resolve engram in the
installed registry. This is already recorded in the PRD 00004 review; no registry
configuration was changed here.

## User Decisions Still Open

- Keep or drop the extra query `-k`/`--k` and index `--rebuild` flags.
- Resolve the unrelated merge conflict in `buvis/home`.
