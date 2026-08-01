# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **client**: local embedding client - loopback-only config with default shortlist, real-call preflight, on-demand `llama-server` spawn/stop, and batched OpenAI-compatible embedding with model-identity verification
- **store**: sqlite-vec + FTS5 scoped store - model-versioned (fail-loud on model/dim mismatch before any write), scoped BM25 and vector KNN via vec0 partition keys, incremental prune, and per-corpus status (stale/dead detection)
