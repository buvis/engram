# Engram Findings Corpus: Durable Review Precedent

Source: `~/.claude/dev/local/discovery/00090-engram-context-engine.md` (PRD C1).
Depends on PRD 00001 (store + retrieval). Scheduled after 00002 per discovery
sequencing; no technical dependency on it.

## Overview

### Problem Statement

Review findings are mortal: review satellites die with their PRD and autopilot
artifacts GC at 14 days, so review patterns never accumulate into precedent.
Reviewers repeat discoveries and precedent queries ("have we hit this failure mode
before?") have nothing to search. Harvest findings into durable extracted records at
the GC choke point, loss-proof, and make them queryable through engram's standard
scoped retrieval.

### Target Users

Review lenses (via PRD 00004 packs), agents running precedent queries, the future
distill loop (separate consumer skill, out of scope here).

### Success Metrics

- Zero-loss harvest: purging a repo with review satellites leaves every finding
  queryable afterwards (fixture-repo test).
- A precedent query for a known past finding's pattern returns its record in top-5.
- Re-harvesting the same review file - unchanged or amended - leaves exactly one
  record set for that path.

## Functional Decomposition

### Capability: Findings Records

#### Feature: Review-file parser
- **Description**: Extract durable records from review-contract files.
- **Inputs**: Review files following the review-file contract (frontmatter
  `reviewers:` + `Verdict:`/`Tests:` lines; the ~/.claude PRD 00016 convention).
- **Outputs**: Records: severity, file, pattern/description, verdict, PRD id,
  repo, date.
- **Behavior**: Frontmatter and Verdict/Tests lines parse per the contract.
  Finding entries parse from the two shapes observed in real review files
  (`~/.claude/dev/local/reviews/*.md`): rows of the Consolidated Findings
  markdown table (columns #, Consensus, Severity, Issue, File) and
  deferred-section bullets prefixed with an emoji severity marker (🔴/🟠/🟡)
  plus a consensus tag like `[3/5]`. Fixtures are copies of real review files.
  Lines matching neither shape are kept as unstructured record text so no
  finding content is dropped.

#### Feature: Record store
- **Description**: Findings persist as extracted records, not pointers.
- **Inputs**: Parsed records.
- **Outputs**: Rows in the central store, corpus=findings.
- **Behavior**: The mortal-source exception to the pointer contract: full record
  text is stored and embedded because the source file is about to die. Exempt
  from reindex pruning. Retrievable via the standard hybrid scoped query
  (`--scope repo` and `--scope portfolio`). Dedup key = source file path:
  re-harvest replaces that path's records (idempotent under amendment; a file
  that fails to parse is skipped and never replaces existing records).

### Capability: Harvest

#### Feature: Harvest CLI
- **Description**: `engram harvest <review-file>...` ingests review files
  (fifth CLI verb extending the discovery's query|index|status|pack surface).
- **Inputs**: Absolute paths to review files.
- **Outputs**: Records upserted; per-file summary on stdout; nonzero exit if any
  file failed to parse entirely.
- **Behavior**: Idempotent - re-harvest of an unchanged file is a no-op; an
  amended file replaces its path's records.

#### Feature: Purge pre-trash sweep
- **Description**: The loss-proof hook at the GC choke point.
- **Inputs**: Review satellites purge-devlocal is about to trash.
- **Outputs**: Harvested records, then normal trash flow.
- **Behavior**: Edit `~/.claude/skills/purge-devlocal/scripts/purge_devlocal.py`:
  before trashing files matching the review-file contract, invoke
  `engram harvest` on them. If harvest fails for a file, that file is NOT
  trashed this run - it is skipped and reported (loss-proof beats clean GC).
  A missing install is not a per-file failure: with no `engram` on PATH the
  sweep is skipped once with one warning and the purge proceeds normally, so a
  broken install never freezes review-file GC across every repo.
  Premise: purge_devlocal.py exists at that path and is the single trash path
  for review satellites; re-check at execution time - if the script has
  materially changed, skip the edit and report instead of forcing it.

#### Feature: Catchup opportunistic harvest
- **Description**: Harvest current-repo review files at catchup.
- **Inputs**: Review files under the current repo's `dev/local/` (reviews
  satellites + `dev/local/tmp/` review outputs). <!-- link-ok: per-repo pattern, not a local path -->
- **Outputs**: Records upserted before they can age out.
- **Behavior**: Catchup calls `engram harvest` on matching files after its
  engram refresh step (extends the claude-git-ferry SKILL.md section added by
  PRD 00002; same premise re-check, same release flow with CHANGELOG entry).
  Accepted lag: precedent may trail its review by days.

## Structural Decomposition

### Repository Structure

```
src/engram/
├── findings.py              # Maps to: Findings Records
├── harvest.py               # Maps to: Harvest (CLI verb wiring in cli.py)
└── (cli.py gains the harvest verb; store.py/indexer.py prune logic gains the
     findings prune-exemption; other 00001 modules unchanged)
(external) ~/.claude/skills/purge-devlocal/scripts/purge_devlocal.py  # pre-trash sweep
(external) claude-git-ferry/skills/catchup/SKILL.md                   # opportunistic harvest
```

### Module: findings
- **Maps to capability**: Findings Records
- **Responsibility**: Parse review-contract files into records; store as
  prune-exempt extracted content.
- **Exports**:
  - `parse(path) -> list[Record]` - contract-aware extraction
  - `upsert(records)` - dedup-keyed persistence

### Module: harvest
- **Maps to capability**: Harvest
- **Responsibility**: CLI verb, idempotency, per-file reporting.
- **Exports**:
  - `harvest(paths) -> HarvestReport`

### Module: integrations (external edits)
- **Maps to capability**: Harvest
- **Responsibility**: purge_devlocal.py pre-trash sweep; catchup harvest step.
- **Exports**:
  - Pre-trash hook call; SKILL.md harvest step

## Dependency Graph

### Foundation Layer (Phase 0)
No new foundation - PRD 00001's store and query are the foundation; already built.

### Core Layer (Phase 1)
- **findings**: Depends on [store (00001)].
- **harvest**: Depends on [findings, cli (00001)].

### Integration Layer (Phase 2)
- **integrations**: Depends on [harvest].

## Implementation Phases

### Phase 0: Findings Records
**Goal**: Contract files parse into durable, queryable records.

**Tasks**:
- [ ] Review-file parser (no deps) - Acceptance: fixture review files (verdict
      pass + fail, docs-only `Tests: none (docs-only)` variant, malformed body)
      parse to expected records; unmatched body text lands in the unstructured
      field, never dropped.
- [ ] Record store, prune-exempt (depends on: parser) - Acceptance: records
      queryable via hybrid scoped query; a full reindex-with-prune leaves
      findings rows intact.

**Exit Criteria**: Fixture findings retrievable by pattern query in both scopes.

### Phase 1: Harvest CLI
**Goal**: Idempotent ingestion verb.

**Tasks**:
- [ ] `engram harvest` verb (depends on: Phase 0) - Acceptance: harvesting a
      fixture file twice yields one record set; harvesting an amended copy
      replaces the old records (still one set, no dupes); per-file summary
      printed; unparseable file exits nonzero.

**Exit Criteria**: Harvest is safe to call from any consumer repeatedly.

### Phase 2: Harvest Wiring
**Goal**: Loss-proof at the choke point, opportunistic at catchup.

**Tasks**:
- [ ] purge_devlocal.py pre-trash sweep (depends on: Phase 1) - Acceptance:
      premise re-check passes; fixture repo with review satellites: after a purge
      run every finding is queryable and satellites are trashed; with harvest
      forced to fail, the satellite survives the purge and the failure is
      reported; with `engram` absent from PATH, the sweep is skipped with one
      warning and satellites are trashed as usual.
- [ ] Catchup opportunistic harvest (depends on: Phase 1) - Acceptance: premise
      re-check passes; catchup on a repo with fresh review files upserts their
      records; claude-git-ferry release commit includes a CHANGELOG entry.

**Exit Criteria**: Zero-loss success metric passes on the fixture repo end-to-end.

## Test Strategy

### Critical Scenarios
- **Happy path**: purge a repo with satellites → Expected: findings queryable,
  files trashed.
- **Edge case**: re-harvest unchanged file; docs-only review file → Expected:
  no dupes; record with `Tests: none (docs-only)` preserved.
- **Error case**: harvest failure during purge → Expected: file kept, loud
  report, purge continues for other files.

## Risks

- **Finding-line shape drift**: reviewer output format varies; the unstructured
  fallback field guarantees no content loss while parsing improves.
- **Choke-point bypass**: satellites deleted outside purge-devlocal are lost;
  accepted - purge-devlocal is the mandated GC path (hand-deletion is already
  against standing rules).
