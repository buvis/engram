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

### Fixed

- **cli**: `status` exits nonzero on staleness (stale files or dead rows) and lists missing corpus dirs; `index` reports missing corpora instead of discarding them; query scores print at fixed precision; `-k` rejects non-positive values; `index --rebuild` clears a leftover temp DB before building
- **indexer**: fail loud on a configured/recorded embedding-model mismatch even when every source is unchanged; embed the heading together with the body so heading-only sections get non-empty vectors
