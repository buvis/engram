# Make `engram status` staleness mean something while sessions are running

Source: finding 3 of PRD 00002's close-out
(`dev/local/reviews/00002-code-retrieval-investigation.md`, 2026-08-06).

**Filing note.** This was raised as a catchup problem and was going to be filed against
`claude-git-ferry`. It is filed here instead because the fix has to be here: catchup only
reports what `status` tells it, and it reports it correctly. Every other caller of
`engram status` - the operator at a prompt, any future script, the harness - sees the same
useless exit code. Fixing it in catchup would paper over it for one consumer and leave the
semantics broken for the rest. If this turns out to be wanted as a catchup-side
presentation change after all, `mv` this file into git-ferry's backlog; nothing here
depends on engram-only context.

## Overview

### Problem Statement

`engram status` exits nonzero whenever any corpus has stale or dead rows. The transcripts
corpus indexes live Claude Code session JSONL files, and those files are appended to
continuously while any session is open. So the corpus that records the current session is
always stale by definition, and `status` therefore exits nonzero essentially always.

Measured across 2026-08-05/06, over a full `--rebuild` and several incremental reindexes:

| moment | transcripts rows | stale |
|---|---|---|
| before rebuild | 18,981 | 3 |
| immediately after `--rebuild` | 17,673 | 3 |
| minutes later | 17,691 | 3 |
| during the ddb catchup | 17,713 | 3 |

The row count moves every few minutes; `stale=3` never clears, because by the time an
index finishes, the sessions that were being indexed have written more turns. A freshly
rebuilt index reports itself stale within seconds.

The consequence is that the staleness stamp is uninformative in the exact place PRD 00002
put it to be informative. Catchup's capsule now carries "Exit code 1 (nonzero = the stale
transcript rows)" on every run. A signal that is always red is not a signal; a reader
learns within two catchups to skip the line, and will then also skip it on the day it
means something real - a genuinely dead corpus, a repo whose files vanished, an index
built against the wrong model.

This is not a bug in staleness detection. The detection is right: those files really did
change. It is a semantics problem - "stale" conflates *"this index is degraded and you
should act"* with *"you are using the machine right now"*.

### Target Users

Anyone reading a staleness stamp: catchup's capsule readers, the operator running
`engram status` directly, and any future script that branches on its exit code.

### Success Metrics

- On a machine with active Claude Code sessions and an otherwise fresh index,
  `engram status --scope portfolio` exits **0**.
- A genuinely degraded index still exits nonzero: dead rows, a corpus whose source
  directory disappeared, or files stale for reasons other than being an in-flight session
  transcript.
- The stamp still *reports* in-flight transcript churn - it is suppressed as an alarm, not
  hidden as a fact. A reader can still see how many transcripts are mid-write.
- Ten consecutive `engram status` runs during an active session produce a stable verdict
  rather than flapping with whatever was written in the last minute.

## Functional Decomposition

### Capability: Distinguish churn from degradation

#### Feature: In-flight transcript classification

- **Description**: Recognise a stale transcript that is simply an open session.
- **Inputs**: The stale file list for the transcripts corpus; each file's mtime.
- **Outputs**: Each stale transcript classified `in-flight` or `degraded`.
- **Behavior**: A transcript modified within a recency window (default minutes, config
  key alongside `[transcripts] error_patterns`) is `in-flight`. Recency is the honest
  signal available: engram cannot know which session is "the current one" - it is a CLI
  invoked from anywhere, sometimes by a session that is not itself indexed, so any
  attempt to identify the caller's own transcript would be guesswork. A transcript stale
  but untouched for longer than the window is `degraded` and still counts, because that is
  a real "you never reindexed" condition.

#### Feature: Exit code reflects degradation only

- **Description**: Reserve the nonzero exit for conditions worth acting on.
- **Inputs**: Per-corpus counts of dead rows, degraded-stale files, in-flight files.
- **Outputs**: Exit 0 or 1.
- **Behavior**: Nonzero when any dead rows exist, or any stale file is `degraded`, or a
  corpus's source is missing. In-flight transcripts alone never set it. The rule is stated
  in `--help` so a script author can rely on it.

#### Feature: The stamp keeps telling the truth

- **Description**: Suppressing the alarm must not suppress the fact.
- **Inputs**: The classification above.
- **Outputs**: The status line for transcripts.
- **Behavior**: Report in-flight separately from degraded, e.g.
  `transcripts 17713 stale=0 in-flight=3 dead=0`, so "three sessions are writing right
  now" is visible and distinguishable from "three files need reindexing". PRD 00002's
  fail-loud posture is preserved: nothing is hidden, one thing is reclassified.

## Structural Decomposition

### Repository Structure

```
src/engram/
├── store.py        # EXTEND: CorpusStatus gains an in-flight count; classification input
├── cli.py          # EDIT: _run_status exit rule + status line format
└── transcripts.py  # EXTEND (maybe): the recency window default lives with its corpus
tests/
├── test_store.py   # EXTEND
└── test_cli_index_status.py  # EXTEND
CHANGELOG.md        # EDIT: Fixed entry
```

### Module: store

- **Maps to capability**: Distinguish churn from degradation
- **Responsibility**: Classify stale files and expose the counts; it already owns
  `status(scope)` and stale detection, so the classification belongs beside it rather than
  in the CLI, where a second consumer would have to re-derive it.
- **Exports**: `CorpusStatus` gains `in_flight_files`; `stale_files` keeps meaning
  "degraded" once classification is applied.

### Module: cli

- **Maps to capability**: Exit code reflects degradation only; The stamp keeps telling the
  truth
- **Responsibility**: Render the line and decide the exit code. No classification logic.
- **Exports**: `_run_status` behaviour; `--help` text stating the exit contract.

## Dependency Graph

### Foundation Layer (Phase 0)

- **Classification in store**: everything else consumes it.

### Core Layer (Phase 1)

- **CLI exit rule + line format**: Depends on [classification].

### Integration Layer (Phase 2)

- **CHANGELOG**: Depends on [Phase 1].

## Implementation Phases

### Phase 0: Classification

**Goal**: The store can tell churn from degradation.

**Tasks**:

- [x] TDD in-flight classification in `store.status` (no deps) - Acceptance: a transcript
      touched inside the window classifies in-flight; one outside it classifies degraded;
      non-transcript corpora are never classified in-flight regardless of mtime; the
      window is configurable and has a documented default.

**Exit Criteria**: `pytest tests/test_store.py` green; `CorpusStatus` carries both counts.

### Phase 1: Exit contract

**Goal**: Nonzero means act.

**Tasks**:

- [x] TDD `_run_status` exit rule (depends on: Phase 0) - Acceptance: in-flight-only
      exits 0; any dead row exits 1; any degraded-stale file exits 1; a missing corpus
      source still exits 1 with its own message.
- [x] Update the status line format and `--help` (depends on: previous) - Acceptance:
      transcripts line shows `stale=` and `in-flight=` separately; `--help` states the
      exit contract.

**Exit Criteria**: `engram status --scope portfolio` exits 0 on this machine with sessions
open and a fresh index.

### Phase 2: Record it

**Tasks**:

- [x] CHANGELOG `### Fixed` entry prefixed `**cli**:` (depends on: Phase 1) - Acceptance:
      entry explains that an always-red stamp was training readers to ignore it.

**Exit Criteria**: Entry present.

## Test Strategy

### Critical Scenarios

- **Happy path**: fresh index, three transcripts written seconds ago → Expected: exit 0,
  `in-flight=3 stale=0`.
- **Edge case**: transcript stale for a week → Expected: `degraded`, exit 1.
- **Edge case**: dead rows present but all stale files in-flight → Expected: exit 1 (dead
  rows always count).
- **Edge case**: clock skew makes a file's mtime slightly in the future → Expected:
  treated as in-flight, never as an error.
- **Regression**: non-transcript corpora → Expected: unchanged behaviour and exit
  semantics.

## Risks

- **A recency window is a heuristic and can mask a real problem**: a machine that stopped
  reindexing for exactly-under-the-window minutes reports clean. Mitigation: the window is
  minutes, not hours, and dead rows and missing sources are unaffected by it.
- **Changing an exit code is an interface change** for anything already branching on it.
  Mitigation: catchup is the only known consumer today and reports rather than branches;
  state the new contract in `--help` and the CHANGELOG.
- **`in-flight` may be the wrong word** if a transcript is written by a session on another
  machine syncing into cellar. Mitigation: it is still churn rather than degradation, so
  the classification holds even if the name is imprecise.

## Delivery notes — 2026-11-09

Implemented and verified directly, as authorized by the user. Configuration is
`[transcripts] in_flight_seconds`, a positive integer defaulting to 600. The
existing optional-directory contract remains: absent, never-indexed optional
PRD/decision/discovery directories are informational. Missing required sources
and vanished indexed files still fail status.

Ten consecutive CLI checks on a fresh fixture index with a transcript being
appended to all return zero and expose `in-flight=1`. Tests cover custom windows,
old and future timestamps, dead rows, unavailable code sources, and unchanged
non-transcript semantics. Full suite: 531 passed; the only failure is an existing
gold-set reference to a missing external transcript.

The live portfolio is not otherwise fresh (5,748 dead transcript rows and 140
dead PRD rows were measured), so its nonzero exit remains correct. This task
does not prune unrelated historical corpora to manufacture a green status.
See [delivery review](../../reviews/2026-11-09-backlog-delivery.md).
