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
