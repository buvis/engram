# Harvest decision audit logs into the findings corpus

Source: finding 2 of the PRD 00002 close-out, `dev/local/reviews/00002-code-retrieval-investigation.md`
(2026-08-06). Observed live, not hypothesised.

## Overview

### Problem Statement

`engram harvest` silently loses an entire genre of durable project knowledge. A single
`/catchup` run in `doogat/ddb` on 2026-08-06 upserted 12 review files and **failed 5
`*-audit.md` files for missing frontmatter** (00161, 00163, 00164, 00165, 00200 audits);
their content is not in the index and cannot be retrieved by any consumer.

The rejection is correct behaviour under the current contract and still wrong in effect.
`findings.parse` implements the review-file contract from PRD 00016: YAML frontmatter
carrying `reviewers:`, plus `Verdict:` / `Tests:` lines, and it fails loud as a total
parse failure rather than degrading to a partial record set. Decision audit logs have
none of that. Their actual shape (verified against
`ddb/dev/local/reviews/00164-unify-id-minting-v1-audit.md`) is:

```
# Decision Audit Log: 00164-unify-id-minting-v1

PRD: `00164-unify-id-minting-v1.md`
Started: <iso8601>
Completed: <iso8601>
Autonomous: 2  |  Deferred: 2  |  Doubts: 0

### [autonomous] <iso8601>

**Decision**: <the question that was open>
**Recommendation**: <what was proposed>
**Choice**: <what was actually adopted>
**Rationale**: <why, including what review dispatches changed>
```

No frontmatter, no `Verdict:`, no `Tests:`. A different genre, not a malformed review.

What is being lost matters more than review findings do. A review finding says "this
line is wrong"; an audit entry records **why a design was chosen over the alternatives
that were rejected**, which is exactly the "have I decided this before" question engram
exists to answer. These files are produced by `/run-autopilot` and
`/review-work-completion` on every PRD, they are the densest decision record the
portfolio has, and `dev/local/` is GC'd by `purge-devlocal` - so unharvested audit logs
are eventually deleted, permanently.

The failure is loud (it printed 5 failures) but nobody is watching: catchup's harvest
step is best-effort by design, and 5 red lines inside a catchup transcript get skimmed.

### Target Users

Claude Code agents at catchup, research-and-reuse step 0, and design time, asking "did we
already decide this, and what did we reject". The solo developer indirectly, via capsule
Related-context hits and `engram query`.

### Success Metrics

- All 6 `*-audit.md` files in `ddb/dev/local/reviews/` harvest without error, and a query
  paraphrasing a recorded decision returns the audit file that holds it in the top 5.
- Each `### [autonomous|deferred|doubt] <timestamp>` block becomes one retrievable
  record carrying its Decision/Recommendation/Choice/Rationale text, so a hit points at
  the decision rather than at the file as a whole.
- A file that is genuinely unparseable (neither review nor audit shape) still fails loud
  and still fails the whole file, never a silent partial.
- `engram harvest` exit code and per-file `path/outcome/count` reporting are unchanged
  for review files; no existing review-file test changes behaviour.

## Functional Decomposition

### Capability: Audit-log ingestion

#### Feature: Genre detection

- **Description**: Decide which contract a review-directory file is being held to,
  before parsing it.
- **Inputs**: The file's text.
- **Outputs**: One of `review`, `audit`, or `unrecognised`.
- **Behavior**: Detection is on shape, never on filename - a `-audit.md` suffix is a
  convention, not a guarantee, and keying on it would misfile a review that happened to
  be named that way. `review` when YAML frontmatter is present; `audit` when the body
  carries a `# Decision Audit Log:` heading or at least one
  `### [autonomous|deferred|doubt]` section heading; `unrecognised` otherwise, which
  keeps today's loud total-failure path.

#### Feature: Audit record extraction

- **Description**: Turn one audit log into per-decision records.
- **Inputs**: An audit-shaped file.
- **Outputs**: One record per decision block, plus one header record carrying the PRD
  reference and the autonomous/deferred/doubt counts.
- **Behavior**: Each `### [<kind>] <timestamp>` starts a record running to the next such
  heading or EOF; the record text keeps the Decision/Recommendation/Choice/Rationale
  bullets verbatim, because the rationale is the retrievable substance. The `<kind>` and
  timestamp are preserved in the record heading so a hit is self-describing. A file whose
  body matches the audit shape but yields zero decision blocks is a parse failure, not an
  empty success - an audit log with no decisions in it means the shape detection was
  wrong.

### Capability: Unchanged review-file behaviour

#### Feature: Review path isolation

- **Description**: Audit support must not weaken the review-file contract.
- **Inputs**: Existing review-contract files.
- **Outputs**: Byte-identical records to today.
- **Behavior**: Genre detection runs first and dispatches; the review parser is not
  modified. The existing "no body line is dropped" rule (unstructured lines are kept as
  record text) continues to apply to review files only.

## Structural Decomposition

### Repository Structure

```
src/engram/
├── findings.py          # EXTEND: genre detection + audit extraction beside parse()
└── (cli, store unchanged - harvest already isolates per-file failures)
tests/
├── test_findings.py     # EXTEND: audit-shape cases
└── fixtures/            # EXTEND: an audit-log fixture
CHANGELOG.md             # EDIT: Fixed entry
```

### Module: findings

- **Maps to capability**: Audit-log ingestion; Unchanged review-file behaviour
- **Responsibility**: Own both contracts and the choice between them. Remains the single
  parser boundary; `cli.harvest` and the store are untouched, since per-file isolation
  and `replace_chunks_for_source` already do the right thing once records exist.
- **Exports**: `parse(path) -> list[Record]` keeps its signature; detection and the audit
  extractor are internal (`_detect_genre`, `_parse_audit_log`).

## Dependency Graph

### Foundation Layer (Phase 0)

- **Genre detection**: no deps; every other piece dispatches on it.

### Core Layer (Phase 1)

- **Audit record extraction**: Depends on [genre detection].

### Integration Layer (Phase 2)

- **Re-harvest + CHANGELOG**: Depends on [Phase 1].

## Implementation Phases

### Phase 0: Genre detection

**Goal**: The parser knows which contract it is applying.

**Tasks**:

- [x] Add `_detect_genre` with tests (no deps) - Acceptance: a real review fixture
      detects `review`; the `00164-unify-id-minting-v1-audit.md` shape detects `audit`;
      a file with neither shape detects `unrecognised`; a review file *named*
      `*-audit.md` still detects `review` (detection is on shape, not filename).

**Exit Criteria**: Detection tested on all three genres; `parse()` behaviour unchanged.

### Phase 1: Audit extraction

**Goal**: Decision blocks become retrievable records.

**Tasks**:

- [x] Write the audit fixture, copied in shape from a real ddb audit log (depends on:
      Phase 0) - Acceptance: fixture carries a header block and at least three decision
      sections across two kinds (`autonomous`, `deferred`).
- [x] TDD `_parse_audit_log` (depends on: previous) - Acceptance: one record per
      decision section plus a header record; Rationale text preserved verbatim; kind and
      timestamp present in each record's heading; an audit-shaped file with zero decision
      sections raises rather than returning an empty list.

**Exit Criteria**: `pytest tests/test_findings.py` green, review cases untouched.

### Phase 2: Prove it against the real corpus

**Goal**: The 5 files that failed now harvest, and are findable.

**Tasks**:

- [x] Harvest ddb's review directory for real (depends on: Phase 1) - Acceptance: all 6
      `*-audit.md` files report success with a nonzero record count; `engram query
      --corpus findings` for a paraphrase of a decision recorded in 00164 (the leaf-module
      existence-oracle choice) returns that audit file in the top 5.
- [x] CHANGELOG `### Fixed` entry prefixed `**findings**:` (depends on: previous) -
      Acceptance: entry names the lost genre and what is now retrievable.

**Exit Criteria**: The five originally-failing files harvest clean; a decision paraphrase
retrieves its audit log.

## Test Strategy

### Critical Scenarios

- **Happy path**: audit log with 3 decision sections → Expected: 4 records (header + 3),
  each carrying its rationale text.
- **Edge case**: review file named `*-audit.md` → Expected: parsed as a review, proving
  detection is shape-based.
- **Edge case**: audit log whose last section runs to EOF with no trailing newline →
  Expected: final record captured whole.
- **Error case**: file with neither frontmatter nor audit shape → Expected: total parse
  failure, loud, unchanged from today.
- **Regression**: every existing review-file test → Expected: byte-identical records.

## Risks

- **Shape detection is a heuristic over prose.** A future audit-log format change silently
  reclassifies files as `unrecognised` and they start failing loud again. Mitigation:
  that is the safe direction (loud, not silent), and the fixture pins today's shape.
- **Audit logs are long; per-decision records may exceed the embed budget.** Mitigation:
  same pointer contract as every other corpus - the store keeps the full body for BM25
  and the pointer sends the reader to the real bytes; measure before adding splitting.
- **`purge-devlocal` may delete audit logs before they are ever harvested.** The findings
  corpus is prune-exempt and survives its source file, so harvesting once is enough - but
  a PRD whose audit log is GC'd before any catchup runs is lost permanently. Mitigation
  is out of scope here; note it when scheduling.

## Delivery notes — 2026-11-09

Implemented and verified directly, as authorized by the user. The original
00161/00163/00164/00165/00200 audit inputs no longer exist in the checkout;
00164 is also absent from available Git history. Under standing authorization,
the obsolete live acceptance fixture is replaced by the nine extant
decision-shaped audits in `ddb/docs/dev/project-management/reviews/`:
00169, 00171, 00172, 00173, 00174, 00176, 00177, 00178, and 00183.

All nine harvest successfully with 276 total records, exit 0. The query
“Why does search conformance cover CLI and GraphQL but omit REST?” returns the
00176 audit at rank 1 (lines 232–237), including its deferred rationale.
This replaces the unavailable 00164 leaf-module question for live acceptance.
Three other files named `*-audit.md` do not have review or decision-audit shape
and remain loud parse failures; filenames do not override content detection.

The durable test fixture excerpts three real 00176 decisions across autonomous
and deferred kinds. Parser regressions cover original body/line spans, EOF
without newline, headerless sections, zero-decision errors, and review-first
detection. Existing review tests remain unchanged. Full suite: 531 passed; one
pre-existing gold-set failure references a missing external transcript.
See [delivery review](../../reviews/2026-11-09-backlog-delivery.md).
