---
default_model: sonnet
model_tier_rationale: exact additive SQL index; no table shape or public API change
---

# Index chunk lookups by corpus and path

Source: 2026-11-16 #2. Original packets: docs/dev/project-management/audit-results/agoge-2026-11-16.md and docs/dev/project-management/audit-results/agoge-2026-11-15-2.md.
Decision: docs/dev/project-management/audit-results/agoge-triage-2026-11-23.md. This is a bounded QA correction, not a replacement of the completed feature PRDs.

Status: HOLD, source evidence for the Gems port. Do not execute in standalone Engram.
Target owner: buvis/gems, port plan docs/dev/project-management/discovery/00161-engram-port-plan.md.
The source paths, tests and Python/config assumptions below describe standalone Engram. Adapt them to the target architecture and port contract before creating executable Gems PRDs.

## Overview

### Problem Statement
Backfill and per-source replacement scan the code corpus once per file. The recorded no-op run reached 27.3 seconds at about 2000 files.

### Target Users
The solo developer and local agents using Engram to index repositories and recall prior work.

### Success Metrics
Every Critical Scenario passes with synthetic data in isolated temporary roots. Historical evidence below is from the QA run, not a fresh measurement. No suite-wide test count or timing target is imposed.

## Functional Decomposition

### Capability: Index chunk lookups by corpus and path
Apply the recorded disposition without changing unrelated behavior.

#### Feature: Add the source index
- **Description**: Add the source index.
- **Inputs**: A new or existing store.
- **Outputs**: An idempotent index for source selection.
- **Behavior**: Execute CREATE INDEX IF NOT EXISTS chunks_corpus_path ON chunks(corpus, path) during open_store. Do not change the vector schema, existing chunk IDs, model metadata, or vectors.

#### Feature: Preserve source semantics
- **Description**: Preserve source semantics.
- **Inputs**: Backfill and finding replacement on upgraded stores.
- **Outputs**: The same selected and replaced rows with bounded lookup work.
- **Behavior**: Retain existing corpus/path predicates. Verify both read and delete query plans use the source index and isolate other corpora and paths. Reopening is idempotent; no rebuild or re-embedding is required.

## Structural Decomposition

### Repository Structure

```text
src/engram/store.py
tests/test_store.py
tests/test_backfill.py
tests/test_findings_store.py
README.md
CHANGELOG.md
```

### Module: Product correction
- **Maps to capability**: Index chunk lookups by corpus and path
- **Responsibility**: Implement the Features in the existing modules; no new public API is required.
- **Location**: `src/engram/store.py`
- **Exports**: `open_store`

### Module: Verification and guidance
- **Maps to capability**: Index chunk lookups by corpus and path
- **Responsibility**: Prove the regression, preserve compatibility, and explain changed behavior.
- **Location**: `tests/test_store.py`, `tests/test_backfill.py`, `tests/test_findings_store.py`, `README.md`, `CHANGELOG.md`
- **Exports**: Existing test entry points and user documentation; no runtime exports.

## Dependency Graph

### Foundation Layer (Phase 0)
- **Verification and guidance**: No internal dependencies; establish reproductions and current premises first.
- External prerequisites: None.

### Core Layer (Phase 1)
- **Product correction**: Depends on Phase 0 evidence and the external prerequisites above.

### Integration Layer (Phase 2)
- **Verification and guidance**: Depends on Product correction for final checks and user guidance.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Establish the precise existing failure or documentation premise.

**Tasks**:
- [ ] Add regressions from Critical Scenarios in the listed test files; run each bug regression against old code and record the expected failure once. (no internal deps) - Acceptance: record command, expected failure or premise, and output for each applicable Critical Scenario. Use only planted markers and temporary data.

**Exit Criteria**: Failure evidence or current documentation premises are recorded; no secrets or live stores are involved.

### Phase 1: Core
**Goal**: Deliver the Functional Decomposition.

**Tasks**:
- [ ] Implement the specified behavior in the listed production modules, preserving the stated safety and compatibility rules. (depends on: Phase 0) - Acceptance: uv run --no-sync python -m pytest -q tests/test_store.py tests/test_backfill.py tests/test_findings_store.py

**Exit Criteria**: All Critical Scenarios pass; required negative checks fail clearly and preserve data as specified.

### Phase 2: Integration
**Goal**: Verify the complete correction and record its limits.

**Tasks**:
- [ ] Update README and add scoped CHANGELOG entries for the implemented behavior; run the selected tests. (depends on: Phase 1) - Acceptance: review the diff against each Feature, confirm all listed scenarios, and run git diff --check.

**Exit Criteria**: Run the repository main gate once: uv run --no-sync python -m pytest -q --ignore=eval -m "not private". Then run the evaluation gate once: PYTHONPATH=src:. uv run --no-sync python -m pytest -q eval -m "not private". Report deselected private tests explicitly. No real portfolio or live database mutation is permitted.

## Test Strategy

### Critical Scenarios
- Open a populated pre-index fixture, then reopen twice; chunk rows, vectors and metadata remain unchanged.
- EXPLAIN QUERY PLAN for the existing corpus/path select and delete uses the source index without a corpus scan.
- Measure SQLite VM steps for all-source no-op backfill at 100 and 1000 synthetic files; tenfold input must use less than twentyfold steps. Record timing as observation only.
- Existing backfill vector-reuse and findings replacement tests still pass.

### Original QA evidence
Verbatim evidence follows. Mocked observations retain that status; local fixture tests do not turn them into real-server measurements. Isolate fixture setup from the user's actual HOME and store.

````text
2026-11-16 #2
SQLite work per backfill: 1.57 M steps at 100 files, 112.5 M at 1000, 439.4 M at 2000 (a rebuild at 2000 used 5.8 M). Wall time against a rebuild of the same tree: 0.45x at 100 files, 0.55-0.62x at 1000, 0.77x at 2000 (104.5 s vs 135.6 s; the 2000 row ran once). A second, no-op backfill took 0.18 s, 7.1 s and 27.3 s at 136, 1100 and 2160 files. `EXPLAIN QUERY PLAN SELECT * FROM chunks WHERE corpus = ? AND path = ?` answers `SCAN chunks USING INDEX code_symbol_name`. Confidence: confirmed for the numbers; the crossover near 3000 files is an extrapolation.
````

## Risks

- Adds disk and write overhead. Use deterministic query plans and VM-step counts rather than wall-clock gates.
- Requirements are resolved. Implementation must not ask for a preference, touch a real store, or weaken assertions to obtain a pass.
