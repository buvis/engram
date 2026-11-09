# Engram Symbol Lookup and Code Corpus Hygiene

## Overview

### Problem Statement

Engram indexes 41,716 code chunks, and **17,449 of them (41.8%) carry the heading
`Function None`** - anonymous functions and callbacks with no name. A further
slice is vendored minified bundles: `easymde.min.js` contributes 496 chunks and
`highlight.min.js` 238, with sample headings reading `Function a`, `Function u`,
`Function s`. Of the 17,449 anonymous chunks, 12,772 are `.js`.

Two consequences. First, the `code` class scores **0.600** on the gold gate
against a 0.80 bar, the weakest of every corpus, and minified vendor code is
exactly the token-dense content that forced the embedding batch-size work.
Second, engram cannot answer the question serena answers instantly - "where is
`stop_served` defined" - even though the store already holds every symbol's name,
kind, path, and line span. It only reaches that data through ranked hybrid
retrieval, which needs a running embedding server and returns approximations
where an exact answer exists.

This PRD does not build reference finding. Import, alias, and inheritance
resolution needs a language server; serena owns that and engram will not compete
there (decided 2026-08-04, recorded in `README.md`).

### Target Users

The operator running `engram query` and `engram pack` across a 26-repo portfolio,
who currently switches to serena or `rg` for exact symbol lookup and gets vendor
bundle noise in ranked results.

### Success Metrics

- Anonymous headings fall from **41.8%** of code chunks to **under 5%**.
- `easymde.min.js` and `highlight.min.js` contribute **0 chunks**.
- `engram lookup --name stop_served --scope portfolio` returns the defining
  `path:line` with **zero embedding calls** (no llama-server process required).
- Code corpus chunk count drops; the exact figure is recorded in the PRD's
  completion notes rather than predicted here.

## Functional Decomposition

### Capability: Code Corpus Hygiene

Keep non-source and unnameable content out of the code corpus, at enumeration and
chunking time, before anything is embedded.

#### Feature: Exclude vendored and generated files

- **Description**: Skip files that are checked in but not authored in this repo.
- **Inputs**: A tracked file path from `symbols.enumerate`; optional
  `[code] exclude_globs` from `config.toml`.
- **Outputs**: The path is yielded or skipped; skipped paths are counted for
  `status`.
- **Behavior**: Three rules, in order. (1) A path-segment denylist:
  `node_modules`, `vendor`, `dist`, `build`, `.venv`, `third_party` `(guess)`,
  inferred from the offending paths rather than a survey of all 26 repos. (2) A
  filename rule: any `*.min.*` file. (3) A content rule for what slips through: a
  file whose longest line exceeds 1000 characters `(guess)`, a threshold chosen
  to clear normal source while catching bundles. Defaults
  live in code; `[code] exclude_globs` extends the denylist and is validated at
  the config boundary, failing loud on a non-list or non-string entry, matching
  the `[transcripts] error_patterns` precedent.

#### Feature: Drop redundant anonymous symbols

- **Description**: Stop emitting one chunk per unnamed callback.
- **Inputs**: The tree-sitter structure walked by `symbols.chunk`.
- **Outputs**: Chunks whose heading always names something, or is explicitly
  marked anonymous.
- **Behavior**: An anonymous symbol (`item.name is None`) nested inside a named
  ancestor is dropped, because the ancestor's chunk body already spans it -
  `_walk` recurses into children while the parent chunk keeps the full line span,
  so the nested chunk is duplicated text under a useless heading. A top-level
  anonymous symbol is kept, with heading `{Kind} (anonymous)` `(guess)`, an
  invented label, so module-level IIFEs and exported arrow functions stay
  retrievable.

### Capability: Exact Symbol Lookup

Answer name and file questions from the store directly, with no embedding leg.

#### Feature: Look up a symbol by name

- **Description**: Find where a symbol is defined, across one repo or the whole
  portfolio.
- **Inputs**: `engram lookup --name <name> --scope repo|portfolio`, optional
  `--repo <name>`.
- **Outputs**: One tab-separated line per definition:
  `path:line_start-line_end\theading`. Exit 1 and a loud message when nothing
  matches.
- **Behavior**: Matches the symbol name parsed out of `heading` as
  `substr(heading, instr(heading, ' ') + 1)`, which is exact because kinds carry
  no space and symbol names carry none either. Exact match first; when it finds
  nothing, prefix match. Restricted to `corpus='code'`. Scope is required, as it
  is for `query`. No `client.load_config` call, no embedding, no server spawn.

#### Feature: Outline a file's symbols

- **Description**: List every symbol in one file, in source order.
- **Inputs**: `engram lookup --file <path>`.
- **Outputs**: The same tab-separated pointer lines, ordered by `chunk_ordinal`.
- **Behavior**: Resolves the path against the git worktree root the same way
  `pack` does, then selects that path's code chunks. `--name` and `--file` are
  mutually exclusive, mirroring `pack --cycle | --diff`.

## Structural Decomposition

### Repository Structure

```
src/engram/
├── symbols.py       # Maps to: Exclude vendored files, Drop anonymous symbols
├── client.py        # Maps to: [code] config table parsing
├── store.py         # Maps to: Look up by name, Outline a file
└── cli.py           # Maps to: the `lookup` verb
tests/
├── test_symbols.py  # exclusion and anonymous rules
├── test_store.py    # lookup queries
└── test_cli.py      # verb wiring, scope enforcement, exit codes
```

### Module: symbols

- **Maps to capability**: Code Corpus Hygiene
- **Responsibility**: Decide what enters the code corpus and under what heading.
- **Exports**:
  - `enumerate()` - unchanged signature, now filtering excluded paths
  - `is_excluded(path, exclude_globs)` - the three-rule check
  - `count_excluded()` - for `status`, alongside `count_skipped`

### Module: client

- **Maps to capability**: Code Corpus Hygiene
- **Responsibility**: Sole owner of config loading and validation.
- **Exports**:
  - `EngramConfig.exclude_globs` - defaults when `[code]` is absent

### Module: store

- **Maps to capability**: Exact Symbol Lookup
- **Responsibility**: Sole owner of the schema and its queries.
- **Exports**:
  - `lookup_by_name(name, scope, prefix=False)` - definitions for a symbol name
  - `lookup_by_path(path)` - a file's symbols in source order

### Module: cli

- **Maps to capability**: Exact Symbol Lookup
- **Responsibility**: Argument parsing and scope enforcement only.
- **Exports**:
  - `lookup` subcommand - `--name` xor `--file`, `--scope` required for `--name`

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **client**: the `[code]` config table and its boundary validation
- **store**: `lookup_by_name` / `lookup_by_path`, plus the expression index

### Core Layer (Phase 1)

- **symbols**: Depends on [client] for `exclude_globs`

### Integration Layer (Phase 2)

- **cli**: Depends on [store, symbols]

## Implementation Phases

### Phase 0: Foundation

**Goal**: The store can answer name and path questions, and config carries the
exclusion list.

**Tasks**:

- [x] Add optional `[code] exclude_globs` to config load, defaulting when absent
      and failing loud on a non-list or non-string entry (no deps) - Acceptance:
      a test asserts the default, and asserts a `[code] exclude_globs = "x"`
      config raises at load with the key named in the message.
- [x] Add `lookup_by_name` and `lookup_by_path` to `store`, with an expression
      index on the parsed name (no deps) - Acceptance: tests over a fixture store
      assert exact match, prefix fallback, scope filtering, `corpus='code'`
      restriction, and source-order output for a file.

**Exit Criteria**: `uv run pytest` passes; no CLI surface changed yet.

### Phase 1: Core

**Goal**: The code corpus stops ingesting vendor bundles and duplicate anonymous
chunks.

**Tasks**:

- [x] Implement `is_excluded` and wire it into `symbols.enumerate`, counting
      exclusions (depends on: Phase 0) - Acceptance: a fixture tree asserts
      `node_modules/x.js`, `a.min.js`, and a 2000-char-line file are excluded
      while ordinary source is not; `count_excluded()` reports the number.
- [x] Drop anonymous symbols with a named ancestor; label top-level anonymous
      ones (depends on: Phase 0) - Acceptance: a fixture JS file with a named
      function containing two arrow callbacks yields one chunk; a module-level
      anonymous function yields a chunk headed `{Kind} (anonymous)`.

**Exit Criteria**: `uv run pytest` passes; chunking is changed but the live index
is untouched.

### Phase 2: Integration

**Goal**: The verb ships and the live index reflects the new rules.

**Tasks**:

- [x] Add the `lookup` verb to `cli` with `--name` xor `--file`, required
      `--scope` for `--name`, and exit 1 when nothing matches (depends on:
      Phase 1) - Acceptance: a test asserts both modes' output shape, that
      passing both flags exits 2, that a missing scope exits 1, and that no
      embedding client is constructed on either path.
- [x] Report the excluded-file count in `engram status`, beside the existing
      grammarless skipped count (depends on: Phase 1) - Acceptance: `status`
      output contains the excluded count for the code corpus.
- [ ] Re-index the code corpus so excluded files are pruned and anonymous chunks
      are re-chunked (depends on: Phase 1). **Premise**: the live store at
      `~/.local/share/engram/engram.db` holds 41,716 code chunks, 17,449 of them
      anonymous, measured 2026-08-04. Re-check before acting; if the counts have
      materially moved, record the new baseline and continue rather than
      abandoning the task - Acceptance: after `engram index --scope portfolio
      --corpus code`, a query against the store shows anonymous headings under 5%
      of code chunks and zero chunks whose path ends `easymde.min.js` or
      `highlight.min.js`.

**Exit Criteria**: `engram lookup --name <a known symbol> --scope portfolio`
prints its definition with no llama-server running.

## Test Strategy

### Critical Scenarios

- **Happy path**: `lookup --name stop_served --scope portfolio` → the defining
  `path:line_start-line_end` and heading, exit 0, no embedding call.
- **Happy path**: `lookup --file src/engram/client.py` → every symbol in source
  order.
- **Edge case**: a name that exists in four repos → four lines, all four repos
  represented under `--scope portfolio`, only the local one under `--scope repo`.
- **Edge case**: a named function containing arrow callbacks → one chunk, not
  three.
- **Edge case**: a vendored file already in the index → pruned by the re-index,
  not merely skipped on the next pass.
- **Error case**: `lookup --name nosuchsymbol` → a loud "no symbol matched"
  message and exit 1, never silent empty output.
- **Error case**: `[code] exclude_globs = "not-a-list"` → config load fails
  naming the key, not a bare `TypeError` from inside enumeration.

## Risks

- **The re-index costs real embedding time**: Phase 2's last task re-chunks the
  code corpus, which means re-embedding it. Mitigation: it is the only task that
  needs a live server, it is last, and it is scoped `--corpus code` rather than a
  full portfolio rebuild.
- **A full gold-gate re-run is out of scope**: proving the `code` class moved off
  0.600 costs ~20-25 minutes per candidate across three candidates and belongs to
  PRD 00002's gate, which is parked in `hold/`. Mitigation: this PRD's metrics are
  corpus-composition facts checkable by SQL, not retrieval-quality claims. Do not
  report a hit-rate improvement without running that gate.
- **The denylist is inferred, not surveyed**: the default path segments come from
  the offending files found in one measurement, so a repo with an unusual vendor
  directory keeps its noise. Mitigation: `[code] exclude_globs` extends the list
  without a code change, and `count_excluded()` makes the filter's reach
  observable in `status`.
- **Dropping anonymous symbols loses retrievable text**: a large uniquely-worded
  callback inside a named parent stops being its own chunk. Mitigation: the
  parent chunk's body still contains that text verbatim, so it remains
  retrievable through the parent, at a coarser pointer.

## Delivery notes — 2026-11-09

Implementation complete; held for the unmet corpus-composition acceptance target.
The direct implementation is authorized by the user in place of Autopilot.

Live `index --scope portfolio --corpus code` completed with exit 0. Baseline:
67,518 code chunks, 18,886 anonymous headings, 734 chunks from the two named
minified bundles. Result: 71,527 chunks, zero legacy `None` headings, 17,776
retained anonymous headings (24.85%), zero named minified-bundle chunks. Newly
indexed registered repositories explain the increase in total chunks. Exact
`stop_served` lookup succeeds with embedding configuration access blocked.

The under-5% prediction is not achieved by the specified retention rules. Many
test callbacks and exported arrows have no named ancestor in the parser's
structure and must remain retrievable. Deleting them to meet the percentage
would violate this PRD. Resolving the remaining criterion requires revising the
corpus target or explicitly extending symbol naming/filtering scope. The final
index task remains unchecked because its numeric acceptance is unmet.

See [delivery review](../../reviews/2026-11-09-backlog-delivery.md) for tests,
review findings, and the recoverable live-database backup.
