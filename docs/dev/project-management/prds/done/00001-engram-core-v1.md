---
rework_cap: 3
---

# Engram Core: Scoped Hybrid Retrieval over Prose Corpora

Source: `~/.claude/dev/local/discovery/00090-engram-context-engine.md` (PRD A of A/B/C1/C2).

## Overview

### Problem Statement

Paraphrase queries over memories, PRDs, decisions, and discovery docs miss because
rg needs the exact token. Engram chunks, embeds, stores, and queries these corpora
with scoped hybrid retrieval. This PRD builds the core pipeline, CLI, and the eval
gate every later phase (transcripts, code symbols, capsule wiring, review packs)
builds on.

### Target Users

Claude Code agents (catchup, ad-hoc mid-task queries) and the user, single machine,
local only.

### Success Metrics

- Gold set (>=30 paraphrase query/answer pairs): right doc in top-5 for >=80%, and
  engram beats a scripted rg baseline on the same set.
- A query without `--scope repo|portfolio` is rejected with a usage error.
- Zero network calls off-machine at query/index/harness time (sole exception:
  first-ensure GGUF download of a model not yet cached).
- A DB whose recorded embedding model mismatches the configured one fails loud.

## Functional Decomposition

### Capability: Embedding Access

Client for llama-server-served local embeddings; engram spawns and ensures the
servers itself on demand (the discovery's never-launch constraint was reversed
at the 2026-08-01 backlog review: its LlamaBarn premise was dead, and
portability to fresh setups requires zero manual server management).

#### Feature: Embedding client
- **Description**: Batch text-to-vector via OpenAI-compatible endpoint.
- **Inputs**: Texts; endpoint + model id from the embedding entries in
  `~/.local/share/engram/config.toml` (engram-owned; `~/.pi/agent/models.json`
  stays chat-only).
- **Outputs**: Vectors (model id + dimension attached).
- **Behavior**: POST `/v1/embeddings` to the configured llama-server instance
  (Homebrew llama.cpp, one instance per model). No cloud keys, no Ollama.

#### Feature: Preflight
- **Description**: Prove the endpoint is really serving before any indexing run.
- **Inputs**: Endpoint config.
- **Outputs**: Pass, or loud failure naming the fix.
- **Behavior**: One real embedding call with a cold-load ceiling (`/v1/models` is
  false-healthy; mirror `qwen-run.sh --preflight`).

#### Feature: Server ensure
- **Description**: Spawn-on-demand lifecycle for embedding llama-servers.
- **Inputs**: Config entries (id, endpoint); `llama-server` binary on PATH.
- **Outputs**: A ready endpoint, or loud failure naming the fix.
- **Behavior**: Before any embedding call, probe the entry's endpoint; if dead,
  spawn `llama-server --embedding -hf <id> --port <port>` detached and wait for
  readiness via preflight (first spawn may download the GGUF - the sole
  off-machine network exception). Missing binary fails loud naming
  `brew install llama.cpp`. Missing config.toml is created with the default
  shortlist on first use.

### Capability: Prose Indexing

Corpora v1 minus transcripts, chunked and stored incrementally.

#### Feature: Heading chunker
- **Description**: Markdown heading-split chunking; no fixed-token windows.
- **Inputs**: Markdown file.
- **Outputs**: Chunks = heading + body, each carrying file path + line span.
- **Behavior**: Split at headings; oversized sections stay whole (pointer contract
  makes truncation safe at read time).

#### Feature: Corpus enumerators
- **Description**: Enumerate the v1 prose corpora across all registered repos.
- **Inputs**: `~/.config/gita/repos.csv` (repo list); filesystem.
- **Outputs**: (corpus, repo, path) triples.
- **Behavior**: auto-memories (`~/.claude/projects/*/memory/*.md`), plus per-repo
  patterns `dev/local/prds/**`, `dev/local/decisions.md`, `dev/local/discovery/*.md` <!-- link-ok: per-repo patterns, not local paths -->
  in every registered repo. Missing dirs are skipped and counted in `status`.

#### Feature: Scoped store
- **Description**: One sqlite-vec DB with FTS5, metadata, and model versioning.
- **Inputs**: Chunks + vectors.
- **Outputs**: DB at `~/.local/share/engram/`.
- **Behavior**: Metadata columns: corpus, repo, doc type, content hash, file:line.
  Store records embedding model id + dimension; on mismatch engram fails loud and
  requires a full re-embed.

#### Feature: Incremental indexer
- **Description**: Reindex only what changed; prune what vanished.
- **Inputs**: Enumerated files, store state.
- **Outputs**: Updated store.
- **Behavior**: Key = content hash (git blob hash for tracked files, `git
  hash-object` for untracked prose). Unchanged chunks are skipped. Rows whose source
  no longer exists are pruned. Trigger: manual `engram index` (later PRDs add
  consumers). No daemons, no git hooks.

### Capability: Retrieval

#### Feature: Hybrid query
- **Description**: BM25 + vector KNN fused via reciprocal rank fusion.
- **Inputs**: Query text; mandatory `--scope repo` (current repo) or
  `--scope portfolio`; optional corpus filter.
- **Outputs**: Pointers, one per line: rank, score, `file:line`, heading.
- **Behavior**: FTS5 BM25 and vector search run over the scope filter; RRF fuses.
  Unscoped invocation is an error. Results are pointers, never chunk bodies.

#### Feature: CLI
- **Description**: `engram query|index|status` entry points.
- **Inputs**: Subcommand + flags.
- **Outputs**: stdout results; nonzero exit on failure.
- **Behavior**: `status` shows per-corpus staleness (files newer than index, dead
  rows) - fail loud. Installed with `uv tool install .` so a bare `engram` sits on
  PATH; later PRDs' consumers (catchup, purge-devlocal, reviewer wiring) invoke it
  bare from other repos, never via `uv run`.

### Capability: Eval Gate

#### Feature: Gold set
- **Description**: Real query/answer pairs proving retrieval quality.
- **Inputs**: Auto-memory hook lines (query = hook line, answer = memory file) plus
  hand-written paraphrase queries for known PRDs/discovery docs.
- **Outputs**: `eval/goldset.yaml`, >=30 entries.
- **Behavior**: Each entry: query text, expected path, corpus.

#### Feature: Harness
- **Description**: Scores engram vs an rg baseline; selects the embedding model.
- **Inputs**: Gold set; the embedding entries in
  `~/.local/share/engram/config.toml` (endpoint + model id each, port-per-model;
  that configured set IS the shortlist - see the Precondition risk).
- **Outputs**: Report with per-model, per-corpus top-5 hit rates; pinned winner
  written back to the same config as the `pinned` entry.
- **Behavior**: Runs gold set through engram once per configured embedding entry
  (ensuring each entry's server on demand; stops the servers it started except
  the pinned winner's) and through a scripted rg baseline; pins the
  highest-scoring model. Gate: later PRDs may not wire engram into catchup
  until top-5 >=80% and engram > baseline.

## Structural Decomposition

### Repository Structure

```
pyproject.toml               # uv-managed single package
src/engram/
├── client.py                # Maps to: Embedding Access
├── chunker.py               # Maps to: Prose Indexing (heading chunker)
├── corpora.py               # Maps to: Prose Indexing (enumerators)
├── store.py                 # Maps to: Prose Indexing (scoped store)
├── indexer.py               # Maps to: Prose Indexing (incremental indexer)
├── query.py                 # Maps to: Retrieval (hybrid query)
└── cli.py                   # Maps to: Retrieval (CLI)
eval/
├── goldset.yaml             # Maps to: Eval Gate (gold set)
└── harness.py               # Maps to: Eval Gate (harness)
tests/
```

### Module: client
- **Maps to capability**: Embedding Access
- **Responsibility**: Endpoint resolution, preflight, batch embedding, server
  ensure.
- **Exports**:
  - `embed(texts) -> list[Vector]` - batch embedding with model metadata
  - `preflight()` - real-call health check, raises with actionable message
  - `ensure_served(entry)` - probe, spawn-if-dead, readiness-wait

### Module: store
- **Maps to capability**: Prose Indexing (scoped store)
- **Responsibility**: sqlite-vec + FTS5 schema, model versioning, scope filters.
- **Exports**:
  - `upsert_chunks(chunks)` / `prune(missing)` - write path
  - `search_bm25(q, scope)` / `search_knn(vec, scope)` - read path

### Module: indexing (chunker.py, corpora.py, indexer.py)
- **Maps to capability**: Prose Indexing
- **Responsibility**: Enumerate, chunk, hash, and incrementally sync corpora.
- **Exports**:
  - `index(corpora, scope) -> IndexReport` - incremental sync incl. pruning

### Module: query
- **Maps to capability**: Retrieval
- **Responsibility**: Hybrid RRF search returning pointers.
- **Exports**:
  - `query(text, scope, corpus=None) -> list[Pointer]`

### Module: cli
- **Maps to capability**: Retrieval (CLI)
- **Responsibility**: Argument parsing, scope enforcement, status rendering.
- **Exports**:
  - `main()` - `engram query|index|status`

### Module: eval
- **Maps to capability**: Eval Gate
- **Responsibility**: Gold-set scoring, baseline comparison, model selection.
- **Exports**:
  - `harness.py` (script) - report + model pinning

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **client**: Embedding vectors + preflight.
- **store**: Persistent scoped storage.

### Core Layer (Phase 1)
- **indexing**: Depends on [client, store].
- **query**: Depends on [client, store].

### Integration Layer (Phase 2)
- **cli**: Depends on [indexing, query, store].
- **eval**: Depends on [cli].

## Implementation Phases

### Phase 0: Foundation
**Goal**: Package skeleton, embedding client, versioned store.

**Tasks**:
- [ ] Scaffold uv package + pytest wiring (no deps) - Acceptance: `uv run pytest`
      exits 0 with a real smoke test.
- [ ] Embedding client + preflight + server ensure (no deps) - Acceptance:
      mocked-endpoint tests pass; with a dead endpoint, ensure spawns a stub
      llama-server from PATH and the call proceeds; with no binary on PATH,
      exits nonzero naming `brew install llama.cpp`; missing config.toml is
      written with the default shortlist; preflight failure names the endpoint.
- [ ] Store schema + model versioning (no deps) - Acceptance: pytest inserts chunks
      and asserts a mismatched model id raises before any write.

**Exit Criteria**: `uv run pytest` green; store round-trips chunks with metadata.

### Phase 1: Core
**Goal**: Corpora indexed incrementally; hybrid scoped retrieval works.

**Tasks**:
- [ ] Heading chunker (depends on: Phase 0) - Acceptance: fixture markdown yields
      expected chunks with line spans.
- [ ] Corpus enumerators (depends on: Phase 0) - Acceptance: fixture tree + fake
      repos.csv yields the expected (corpus, repo, path) set; missing dirs counted.
- [ ] Incremental indexer (depends on: chunker, enumerators) - Acceptance: reindex
      of unchanged fixture embeds 0 chunks; deleting a fixture file prunes its rows.
- [ ] Hybrid query (depends on: Phase 0) - Acceptance: with stub vectors, an
      exact-token query hits via BM25 and a synonym query via KNN; unscoped call
      errors.

**Exit Criteria**: Fixture corpora indexed and queryable through both retrieval
paths with correct scope filtering.

### Phase 2: Integration
**Goal**: CLI surface + eval gate passed.

**Tasks**:
- [ ] CLI verbs query|index|status (depends on: Phase 1) - Acceptance: `engram
      query --scope repo <q>` prints pointer lines; `status` lists per-corpus
      staleness; missing scope exits nonzero; `uv tool install .` puts a bare
      `engram` on PATH and `engram --help` runs from a directory outside this
      repo (consumers in later PRDs invoke it bare, never via `uv run`).
- [ ] Gold set (depends on: Phase 1) - Acceptance: `eval/goldset.yaml` schema-valid
      with >=30 entries covering all four corpora.
- [ ] Harness + model selection (depends on: CLI, gold set) - Acceptance: harness
      report shows per-model scores, pinned model recorded in
      `~/.local/share/engram/config.toml`, engram top-5 >=80% and above the rg
      baseline.

**Exit Criteria**: Eval gate met on real corpora with the pinned model; core is
ready for PRD 00002 (heavy corpora).

## Test Strategy

### Critical Scenarios
- **Happy path**: paraphrase of a memory hook line → Expected: that memory file in
  top-5 pointers.
- **Edge case**: unscoped query; unchanged reindex → Expected: usage error; zero
  re-embeds.
- **Error case**: endpoint down; model-id mismatch → Expected: loud preflight
  failure; refusal until full re-embed.

## Risks

- **Precondition**: `llama-server` on PATH (`brew install llama.cpp`) - the
  only manual setup. Servers and config are engram-managed: spawn-on-demand per
  entry (first spawn downloads the GGUF), default shortlist (qwen3-embedding,
  nomic-embed, bge-m3, ports 8081-8083) written to
  `~/.local/share/engram/config.toml` if absent. Frozen config schema (tests
  bind to it):

  ```toml
  [[embedding]]
  id = "<model id as the server reports it at /v1/models>"
  endpoint = "http://127.0.0.1:<port>/v1"

  [pinned]
  id = ""  # written by the eval harness
  ```

  Premise re-check: ensure + preflight per configured entry before the harness
  runs; an entry that cannot be spawned or served fails loud naming the fix,
  never silently shrinks the shortlist.
- **Embedding model quality**: eval harness decides from the configured
  shortlist, not vibes; GGUF availability constrains it.
- **Gate unmet (<80%)**: tune chunking/RRF weighting and re-run; catchup wiring
  (PRD 00002) stays blocked until met - fail loud, don't wire.
- **Cross-PRD contract drift**: this repo owns the CLI contract; later PRDs edit
  their own consumers, never this contract silently.
