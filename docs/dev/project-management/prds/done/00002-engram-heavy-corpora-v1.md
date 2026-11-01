# Engram Heavy Corpora: Transcripts, Code Symbols, Capsule Integration

Source: `~/.claude/dev/local/discovery/00090-engram-context-engine.md` (PRD B).
Depends on PRD 00001 (core pipeline + eval gate passed).

## Overview

### Problem Statement

The core engine (PRD 00001) retrieves over light prose. Two heavy recall classes
remain: ~1,700 cellar transcripts (~900MB JSONL) holding past incidents that
paraphrase queries should find, and code symbols across the 26 gita-registered repos
for "have I built X" reuse discovery (research-and-reuse step 0 mandates this search;
today it is manual). Retrieval also reaches no agent automatically yet - catchup
should feed top hits into the project capsule with zero manual steps.

### Target Users

Claude Code agents at catchup and mid-task; reviewers indirectly (PRD 00004 consumes
the code corpus).

### Success Metrics

- Extended gold set (transcript past-incident paraphrases): right doc in top-5 for
  >=80%.
- Seeded cross-repo duplicates (known repeated patterns, e.g. retry logic, notify
  plumbing): each seed's "have I built X" query hits in top-5 for >=80% of seeds.
- Catchup emits a "Related context" capsule section with zero manual steps.
- Incremental reindex of an unchanged portfolio completes in under 60 seconds
  (discovery: "seconds, not minutes").

## Functional Decomposition

### Capability: Transcript Corpus

#### Feature: Transcript enumerator
- **Description**: Enumerate cellar transcript JSONL files incrementally.
- **Inputs**: `~/git/src/github.com/buvis/cellar/.claude/projects/*/*.jsonl`.
- **Outputs**: (corpus=transcripts, path) entries with content hashes.
- **Behavior**: Files are git-tracked in cellar, so blob-hash incrementality
  applies; unchanged transcripts are never re-read.

#### Feature: Turn filter
- **Description**: Keep only turns worth recalling.
- **Inputs**: Parsed JSONL turns.
- **Outputs**: User + assistant text turns PLUS error-bearing tool results.
- **Behavior**: Error-bearing start set: tracebacks/panics, non-zero exit markers,
  ERROR/FAIL patterns. The pattern list lives in config and is tuned against the
  eval harness, not hardcoded.

#### Feature: Turn chunking
- **Description**: One chunk per kept turn, pointer-addressable.
- **Inputs**: Filtered turns.
- **Outputs**: Chunks with pointer = transcript path + JSONL line number.
- **Behavior**: Turn text embeds as-is; the pointer contract (Read the real bytes)
  handles length at consumption time.

### Capability: Code Corpus

#### Feature: Symbol chunker
- **Description**: tree-sitter symbol-level chunking for code.
- **Inputs**: Source files; tree-sitter-language-pack grammars.
- **Outputs**: One chunk per function/class: signature + docstring + file path
  embedded; pointer = file:line.
- **Behavior**: Whole-symbol chunks, never fixed-token windows; files with no
  grammar are skipped and counted in `status`.

#### Feature: Code enumerator
- **Description**: Enumerate tracked code across all registered repos.
- **Inputs**: `~/.config/gita/repos.csv`; each repo's current checkout.
- **Outputs**: (corpus=code, repo, path) entries.
- **Behavior**: `git ls-files` at HEAD of the current checkout; local commits
  included; a repo parked on a WIP branch indexing transient symbols is accepted.

### Capability: Capsule Integration

#### Feature: Catchup wiring
- **Description**: git-ferry catchup writes a "Related context" capsule section.
- **Inputs**: Current branch name + active PRD title (when present) as query
  topics.
- **Outputs**: Section in `dev/local/project-capsule.md`: top scoped hits with
  scores and a staleness stamp.
- **Behavior**: Catchup runs `engram index` (refresh-before-consume), then
  `engram query --scope repo` and `--scope portfolio` for the topic, then writes
  the section. Implemented by editing the claude-git-ferry catchup SKILL.md and
  releasing it (feat entry in that repo's CHANGELOG, `dev/bin/release`).
  Premise: catchup's capsule-section flow matches the discovery's Codebase
  Context read; re-check the SKILL.md structure at execution time - if it has
  materially changed, skip the edit and report instead of forcing it.

## Structural Decomposition

### Repository Structure

```
src/engram/
├── transcripts.py           # Maps to: Transcript Corpus
├── symbols.py               # Maps to: Code Corpus
├── corpora.py               # extended: registers both new corpora
└── (00001 modules unchanged: client, store, indexer, query, cli)
eval/
└── goldset.yaml             # extended: transcript + code-seed entries
(external) claude-git-ferry/skills/catchup/SKILL.md   # Maps to: Capsule Integration
```

### Module: transcripts
- **Maps to capability**: Transcript Corpus
- **Responsibility**: Enumerate, filter, and chunk cellar transcripts.
- **Exports**:
  - `enumerate() -> list[Entry]` - hash-keyed transcript listing
  - `chunk(path) -> list[Chunk]` - filtered turn chunks

### Module: symbols
- **Maps to capability**: Code Corpus
- **Responsibility**: tree-sitter symbol extraction across registered repos.
- **Exports**:
  - `enumerate() -> list[Entry]` - tracked files per repos.csv
  - `chunk(path) -> list[Chunk]` - symbol chunks with signatures

### Module: capsule (external edit, claude-git-ferry)
- **Maps to capability**: Capsule Integration
- **Responsibility**: Refresh-then-query-then-write section flow inside catchup.
- **Exports**:
  - SKILL.md step invoking `engram index` + `engram query`, section template

## Dependency Graph

### Foundation Layer (Phase 0)
No new foundation - PRD 00001's client, store, indexer, and query are the
foundation; already built.

### Core Layer (Phase 1)
- **transcripts**: Depends on [store, indexer, client (00001)].
- **symbols**: Depends on [store, indexer, client (00001)].

### Integration Layer (Phase 2)
- **capsule**: Depends on [query (00001), transcripts, symbols].

## Implementation Phases

### Phase 0: Transcript Corpus
**Goal**: Transcripts indexed and retrievable.

**Tasks**:
- [x] Enumerator + turn filter (no deps) - Acceptance: fixture JSONL yields exactly
      the expected turns; error-heuristic unit tests cover each start-set pattern.
- [x] Turn chunking + corpus registration (depends on: filter) - Acceptance:
      fixture transcript indexed; query returns pointer with correct JSONL line.
- [x] Initial transcript index (depends on: above) - Acceptance: `engram status`
      shows transcripts corpus fresh; second run embeds 0 chunks. The initial run
      is long (~900MB); indexing is incremental/resumable, so invoke repeatedly
      or in background until status reads fresh - never one bounded foreground
      call (10-minute Bash ceiling).

**Exit Criteria**: Transcript corpus indexed; incremental re-run is a no-op.

### Phase 1: Code Corpus
**Goal**: Cross-repo symbols indexed; retrieval quality proven.

**Tasks**:
- [x] Symbol chunker (no deps) - Acceptance: fixture repo yields symbol chunks with
      signature + docstring + path; grammarless files counted as skipped.
- [x] Code enumerator + registration (depends on: chunker) - Acceptance: fake
      repos.csv + fixture repos yield expected entries from `git ls-files`.
- [x] Extend gold set: transcript paraphrases + cross-repo duplicate seeds
      (depends on: Phase 0, enumerator) - Acceptance: goldset.yaml gains both
      classes; harness reports top-5 >=80% on each; unchanged-portfolio reindex
      under 60s.

**Exit Criteria**: Both success-metric retrieval thresholds met at the harness.

### Phase 2: Capsule Integration
**Goal**: Catchup feeds retrieval to agents with zero manual steps.

**Tasks**:
- [x] Edit claude-git-ferry catchup SKILL.md + release (depends on: Phase 1) -
      Acceptance: premise re-check passes (capsule flow present); running catchup
      in a sample repo produces a "Related context" section with scored hits and a
      staleness stamp; CHANGELOG entry present in the release commit.

**Exit Criteria**: Fresh catchup run writes the section end-to-end unattended.

## Test Strategy

### Critical Scenarios
- **Happy path**: paraphrase of a known past incident → Expected: its transcript in
  top-5.
- **Edge case**: transcript with only tool chatter and no errors → Expected: zero
  chunks; repo with no grammar coverage → Expected: skipped-and-counted.
- **Error case**: cellar path missing → Expected: loud status failure, not a silent
  empty corpus.

## Risks

- **Transcript noise**: heuristic tuned against eval; turn summarization is the
  named upgrade path (nice-to-have, not this PRD).
- **Embedding quality on code**: harness re-run decides; if code scores lag, the
  LLM one-liner enrichment is the named upgrade path (nice-to-have).
- **Initial index cost**: one-time; incrementality keeps steady-state under the
  60s bound.

## Completion (2026-11-01)

All tasks done. Gate evidence, all measured on 2026-11-01:

- Eval harness (`eval/harness.py`, 52 gold entries) passed the gate. All three
  candidates scored 0.962 overall against an rg baseline of 0.519. The pinned
  bge-m3 scored transcripts 1.000 and code 0.800; Qwen and nomic scored
  transcripts 0.917 and code 1.000. Every gated class is at or above 0.80.
- An unchanged-portfolio `engram index --scope portfolio` ran in 12.6 s against
  the 60 s bound, with about 24,400 files enumerated.
- `engram status --scope portfolio` reports the transcripts and code corpora as
  fresh, with 32,888 transcript chunks and 65,349 code chunks.
- Capsule integration shipped in claude-git-ferry 0.3.0 (feat entry in that repo's
  CHANGELOG). Catchup wrote the "Related context" section, with scored hits and a
  portfolio staleness stamp, in six repos' capsules.

The PRD stayed in wip because finalization kept failing. These fixes closed it:
gold-set paths had rotted after the docs move and cellar pruning, an unmerged
merge index crashed the code enumerator, nomic's 2048-token context overflowed,
zero-chunk files were re-parsed on every run (94 s), and a tie in the harness
repointed production away from the live index's model.

## Completion review (2026-11-01)

Fresh-session review 3 covers the seven finalization commits over
`7610ef5..1a3b49f`. Consensus, blind, and independent Codex doubt lenses ran;
the optional Gemini route was unavailable. The empty-source cache regression
was repaired in `ce71263`, along with the requested core follow-ups. See
`../../reviews/00002-engram-heavy-corpora-v1-review-3.md` for all findings and
dispositions. Existing spec gaps are retained there, not claimed resolved.

The historical harness used 52 entries (corrected from 64). The gold set now
contains 55 entries after adding decision coverage; these load successfully,
but no live score is claimed for the enlarged set. Production remains on bge-m3.
