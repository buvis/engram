# Project Capsule: engram

Updated: 2026-11-16. Trimmed to current facts; the session-by-session history
(Sessions 1-8, 2026-11-09 to 11-15) is in git history of this file before
commit "docs(meta): trim capsule to current facts".

## Key Invariants

- Standalone uv-managed Python CLI, not a Claude plugin.
- Local llama-server embedding endpoints; engram owns its embedding config.
- Queries require explicit repo or portfolio scope. Query `-k`/`--k` and index
  `--rebuild` are supported interfaces (user decision, 2026-11-01).
- Model/dimension mismatches fail loud. Production stays pinned to
  `ggml-org/bge-m3-Q8_0-GGUF:Q8_0` (endpoint port 8083). Never repin, switch
  models or run a full rebuild without the user's explicit authorization.
- Equal harness scores keep the current pin. The harness pins only on a passing gate.
- Retrieval returns source pointers; findings additionally carry their durable body.
  Findings are the one corpus that cannot be re-derived from sources.
- Index commits per file. Unchanged sources are not re-embedded or re-chunked
  (hash cache), so chunker changes reach only new or edited files.
- Read/parser failures are retried, not stored as successful empty sources.
- Project documents live under `docs/dev/project-management/`; transient packs
  live under globally ignored `docs/dev/tmp/`.
- `engram pack --cycle <id>` file names (`review-diff-{id}.diff`,
  `engram-pack-{id}.md`) are an external contract with autopilot's
  `review_stage.py` and the review-work-completion skill. Do not change them.
- Repository memory (`docs/dev/project-management/memory/`) must be
  public-safe: 28 of 29 buvis repos are public.

## Architecture Decisions

- Memory attribution matches Claude's project-dir encoding (every
  non-alphanumeric char becomes `-`) against complete registry paths. Ambiguous
  or unknown dirs stay `_unmapped`, portfolio-only.
- `symbols.chunk` is the single code emit site; module-context gap chunks
  (PRD 00013) append after it. Nested symbols overlap, so coverage is a union.
  `Store.lookup_by_name` is the only place the `module_context` doc type is
  filtered; a parser kind `module` stays a symbol.
- `symbols.kind_name()` unwraps tree-sitter-language-pack `Other` kinds (since
  1.20 their `str()` is JSON).
- `mcp_server.py` owns `search_pointers` and `format_pointer_lines`, shared by
  `engram query`, `engram mcp` and `engram nudge`.
- Pack reuse exclusion runs inside BM25 and sqlite-vec searches, before their
  candidate limits, not after the fused top five.

## Component Boundaries

- `client.py`: config, model identity, server leases, context budgets, embeddings.
- `store.py`: SQLite/FTS5/sqlite-vec, source caches, scopes, model checks.
- `corpora.py`, `chunker.py`, `transcripts.py`, `symbols.py`: enumeration and chunking.
- `indexer.py`: incremental indexing and pruning; `query.py`: hybrid retrieval.
- `findings.py`, `harvest.py`: durable review records.
- `memory.py`, `migrate.py`: repository memory check and Claude auto-memory migration.
- `mcp_server.py`, `nudge.py`: agent recall surfaces.
- `diffmap.py`, `pack.py`: review context packs; `cli.py`: CLI entry points.
- `harness.py`, `eval/`: candidate scoring, gold set, agent-session evaluation.

## Active Work

State 2026-11-16 (autopilot batch 202611161217):

- `00014-engram-findings-pack-correctness-v1` is in `wip/`, building now via
  `/autopilot:run-autopilot`: 7 verified defects in harvest, rebuild and pack,
  plus a harvest/rebuild advisory lock. `design: skip`, `default_model: opus`.
- Backlog, next in build order:
  - `00015-engram-module-context-backfill-v1`: `engram index --backfill-code`.
    Building it does not run it; the production run needs a backup and the
    user's OK.
  - `00016-engram-worktree-repo-resolution-v1`: linked worktrees resolve to
    their main checkout's registry entry (fixes `engram pack` in autopilot
    worktrees). Its `eligibility` waits for 00014 in `done/`.
- 13 PRDs done (00001-00013). Installed CLI matches master as of 2026-11-16
  (`engram nudge --help` works).
- agent-plugins PRD 00067 (engram plugin: skill, mcp.json, per-host nudge
  hooks) is building in agent-plugins. Intake 00066 there (orchestrator
  injection of engram context) is open.
- Intakes 00008 (Qwen3 reranker/embedding) and 00009 (fusion OR/tie-break)
  stay deferred in `intake/new/` until evidence justifies a spec.

## Evaluation

- Agent-session protocol: `reviews/2026-11-10-agent-session-evaluation-protocol.md`.
  Second set (judged relevance, 44 questions): 36/44 top-3 useful (81.8%);
  user spot check agreed 10/10. `Adoption decision: proceed` (2026-11-15).
  The first 24 questions are development data now.
- Exact-file measure stays low (10/44); wider pools find labels the reranker
  misses. OR alone does not reproduce earlier MRR gains.
- Gold set: 55 entries, 53 sources retained privately under
  `~/.local/share/engram/eval/sources/`, pinned by `eval/sources.json`.
  `PYTHONPATH=src:. .venv/bin/python -m eval.sources validate` checks it.
  21 sources exist only in that private backup.
- Tools: `eval/agent_session_mine.py`, `eval/agent_session_relevance.py`,
  `eval/agent_session_recall.py`.

## Project Health

- Tests: `.venv/bin/python -m pytest -q --ignore=eval` and
  `PYTHONPATH=src:. .venv/bin/python -m pytest -q eval`. Tests marked `private`
  need the private eval archive; CI deselects them with `-m "not private"`.
- CI: `.github/workflows/test.yml`, ubuntu, Python 3.12 and 3.14; green on master.
- Portfolio index (2026-11-16, after refresh): zero dead rows except 55
  transcript rows from 2 in-flight sessions. `engram status` exit 1 then was
  only those.
- Backups: `~/.local/share/engram/backups/session3-20261110/` (pre-maintenance
  DB, registry, config). Keep existing rollback backups.
- Known debt not in 00014: findings field granularity; `claude-home` resolver
  fallback shared with indexing; pack prose origins and multiline pointer
  formatting; section-cap spec inconsistencies; long symbol queries weaken AND
  lexical retrieval (fusion is evidence-gated, intake 00009).
- Catchup harvest: the broad review glob mixes supported reviews with ordinary
  reports that lack frontmatter; those rejections are legitimate.
- Some test suite somewhere writes `pytest-of-bob-…` dirs into the real
  `~/.claude/projects`; origin unknown, not in this repo.

## Related context

2026-11-16 (00014 catchup): topic "master 00014 Engram findings, harvest and
pack correctness". Top repo hits are the PRD itself and the harvest dedup
tests (`test_harvest_reharvesting_unchanged_file_twice_yields_one_record_set_no_duplicates`,
`test_findings_upsert_reharvest_dedup_and_replace_yields_one_record_set`) —
relevant because PRD defect 4 (findings race between copy and `os.replace`)
sits next to this existing dedup/replace behavior; nothing else ranked above
noise. Portfolio scope surfaced no additional repo. Staleness
(`engram status --scope portfolio`, exit 1): transcripts dead=543 (expected,
many repos never harvest transcripts), prd dead=32, memory stale=2, code
stale=1; findings/discovery/decision all stale=0 dead=0.

## GitHub State

Remote: `https://github.com/buvis/engram` (2026-11-16). No open issues, no
open PRs (#4 merged as `d580ff0`). No releases. Workflow "Test" on master:
green, latest 2026-11-16 (5 consecutive successes).

## Project Memories

- Engram is a standalone CLI, not a plugin; it owns embedding configuration and
  bare llama-server lifecycle. Host chat model registries are separate.
- External reviewers: codex needs `-y` inside the run-agent sandbox; nested
  claude needs the setup token exported from file.
- When the user must decide, ask one question at a time with good/bad/ugly per option.
