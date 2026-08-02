# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **client**: local embedding client - loopback-only config with default shortlist, real-call preflight, on-demand `llama-server` spawn/stop, and batched OpenAI-compatible embedding with model-identity verification
- **store**: sqlite-vec + FTS5 scoped store - model-versioned (fail-loud on model/dim mismatch before any write), scoped BM25 and vector KNN via vec0 partition keys, incremental prune, and per-corpus status (stale/dead detection)
- **chunker**: markdown heading chunker - flat heading-delimited chunks (heading + body with line spans and sequential ordinals), preamble captured, oversized sections kept whole
- **corpora**: corpus enumerators - walk registered repos (gita repos.csv) for prd/decision/discovery sources plus auto-memory dirs (slug-resolved repo, `_unmapped` fallback), git-blob content hashing, and missing-source tracking
- **indexer**: incremental indexer - enumerate and scope-filter corpora, skip unchanged files via content-hash diff, chunk/embed/upsert new and changed files, and prune vanished sources within the reindexed scope only
- **query**: hybrid retrieval - fuse scoped BM25 and vector KNN results via reciprocal rank fusion (RRF), returning ranked file:line pointers; propagates a model mismatch loudly
- **cli**: `engram query|index|status` command line - required-scope query printing file:line pointers, scoped or full `--rebuild` indexing (atomic temp-DB swap), per-corpus status, and a bare `engram` on PATH via `uv tool install`
- **eval**: model-selection harness - score each configured embedding model against a real gold set (top-5 hit rate, deduped by path), compare to an rg baseline, pin the winner into config.toml, and gate on >=80% hit rate strictly beating baseline
- **transcripts**: transcript corpus - enumerate cellar session JSONL and chunk one pointer-addressable turn per kept line, keeping user/assistant text turns plus error-bearing tool results (config-tunable error patterns); a missing cellar path fails loud instead of yielding an empty corpus
- **symbols**: code corpus - enumerate HEAD-tracked files across gita-registered repos (`git ls-files` per repo, missing repos tracked not raised) and chunk each into pointer-addressable symbols via tree-sitter (one whole-symbol chunk per function/class at every nesting depth, body by line span); files with no grammar are skipped and counted for `status`
- **corpora**: register the transcript and code corpora in the index/status/harness pipeline - `engram index` now enumerates and per-corpus dispatches chunking for cellar transcripts and repo code symbols; `engram status` reports the code corpus's grammarless skipped-file count; `index`/`status` surface the producing corpus's own missing-path message instead of a hardcoded repos.csv string; the eval harness accepts `transcripts`/`code` gold entries and includes their files in the rg baseline

- **findings**: review-file parser - extract durable records from review-contract files (frontmatter `reviewers:` plus `Verdict:`/`Tests:` lines), recognising Consolidated-Findings table rows and severity-emoji bullets with their continuation lines; any body line matching neither shape is kept as unstructured record text so no finding content is dropped, and an incomplete or unreadable file fails loud as a total parse failure rather than degrading to a partial record set

- **findings**: durable record store - findings persist as extracted records (`corpus=findings`) that survive their source file, via an atomic `replace_chunks_for_source` keyed on (corpus, path) so a re-harvest replaces a path's records in one transaction, embedding before deleting so a failed embed leaves the prior records intact; findings rows are exempt from reindex pruning and are carried forward (freshly re-embedded from their stored text) across `engram index --rebuild`, which would otherwise destroy them permanently

- **query**: findings hits carry their record text - a `Pointer` for a `findings` hit now exposes the stored record body (`engram query` prints it on its own line after the hit's summary line), so a harvested finding stays readable after its source review file is trashed; every other corpus keeps the pointer-only contract with `body` unset and byte-identical output

### Fixed

- **cli**: `status` exits nonzero on staleness (stale files or dead rows) and lists missing corpus dirs; `index` reports missing corpora instead of discarding them; query scores print at fixed precision; `-k` rejects non-positive values; `index --rebuild` clears a leftover temp DB before building; `query`, `status`, and `index` fail loud with a clear "repos.csv not found" message on a missing gita repos.csv under every scope, including the default/repo scope (which previously showed a misleading "not inside a registered repo" hint); `index --corpus` scopes missing-dir warnings to that corpus
- **indexer**: fail loud on a configured/recorded embedding-model mismatch even when every source is unchanged; embed the heading together with the body so heading-only sections get non-empty vectors
- **client**: size embedding requests by total characters, not a fixed text count, and pass `-c`/`-b`/`--ubatch-size` when spawning `llama-server` - a run of long, token-dense chunks (transcript error turns, minified code) previously built a request past the server's default batch, which closed the connection and killed the whole index run
- **client**: refuse off-machine HTTP redirects (preserving the loopback-only invariant); reject an empty embedding shortlist or an unknown pinned id at config load; raise a clear error on a non-list `data` response field or a non-mapping `data` element (instead of a raw `AttributeError`); reap the spawned server when it reports the wrong model
- **eval**: the rg baseline fails loud on an rg error instead of silently zeroing (no false-positive gate); emit per-model, per-corpus hit rates; the scorer closes its sqlite connection; pinning the winner fails loud when the config has no `[pinned]` section
