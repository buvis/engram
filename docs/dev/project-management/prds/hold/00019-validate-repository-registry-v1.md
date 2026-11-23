---
default_model: opus
model_tier_rationale: cross-cutting registry shape and pruning safety
---

# Validate repository registration before indexing

Source: 2026-11-16 #6, 2026-11-16 #9, 2026-11-16 #16, 2026-11-16 #23, 2026-11-16 #28, 2026-11-15 run 2 #4. Original packets: docs/dev/project-management/audit-results/agoge-2026-11-16.md and docs/dev/project-management/audit-results/agoge-2026-11-15-2.md.
Decision: docs/dev/project-management/audit-results/agoge-triage-2026-11-23.md. This is a bounded QA correction, not a replacement of the completed feature PRDs.

Status: HOLD, source evidence for the Gems port. Do not execute in standalone Engram.
Target owner: buvis/gems, port plan docs/dev/project-management/discovery/00161-engram-port-plan.md.
The source paths, tests and Python/config assumptions below describe standalone Engram. Adapt them to the target architecture and port contract before creating executable Gems PRDs.

## Overview

### Problem Statement
Empty or malformed registration can silently prune indexed corpora, alias paths disagree between producers and consumers, and harvest reloads the whole registry per file.

### Target Users
The solo developer and local agents using Engram to index repositories and recall prior work.

### Success Metrics
Every Critical Scenario passes with synthetic data in isolated temporary roots. Historical evidence below is from the QA run, not a fresh measurement. No suite-wide test count or timing target is imposed.

## Functional Decomposition

### Capability: Validate repository registration before indexing
Apply the recorded disposition without changing unrelated behavior.

#### Feature: Validate one registry snapshot
- **Description**: Validate one registry snapshot.
- **Inputs**: The existing gita CSV file.
- **Outputs**: Validated absolute roots and actionable failures.
- **Behavior**: Reject an empty registry, non-absolute paths, NUL bytes, blank names, malformed nonblank rows, unreadable bytes, and conflicting canonical-root/name mappings. Preserve valid extra CSV fields. Resolve roots once per command. Keep original spelling available for existing Claude project-slug attribution; canonicalization must not strand legacy memory.

#### Feature: Fail before mutation
- **Description**: Fail before mutation.
- **Inputs**: Validated registry and index/rebuild/harvest commands.
- **Outputs**: Clear registry errors with unchanged indexed content on failure.
- **Behavior**: Validate before embedding, pruning, or replacing a rebuild store. Name the registry file in errors; do not describe a read error as an unregistered repository. Harvest retains one result per supplied file with no_repo and the registry diagnostic. An empty registry is refused even for a new store.

#### Feature: Use canonical roots consistently
- **Description**: Use canonical roots consistently.
- **Inputs**: Validated rows and repeated source files.
- **Outputs**: One storage path spelling and one registry read per harvest.
- **Behavior**: Index code and repo prose under resolved roots and have lookup match the same spelling. Re-index replaces superseded alias-path code/prose within the selected repo without touching findings. Snapshot the registry once for a harvest batch. Preserve non-selected repos and explicit claude-home behavior.

## Structural Decomposition

### Repository Structure

```text
src/engram/corpora.py
src/engram/symbols.py
src/engram/harvest.py
src/engram/indexer.py
src/engram/cli.py
tests/test_read_repos_csv.py
tests/test_corpora.py
tests/test_harvest_resolve.py
tests/test_harvest.py
tests/test_indexer.py
tests/test_cli_index_status.py
tests/test_cli_index_rebuild.py
README.md
CHANGELOG.md
```

### Module: Product correction
- **Maps to capability**: Validate repository registration before indexing
- **Responsibility**: Implement the Features in the existing modules; no new public API is required.
- **Location**: `src/engram/corpora.py`, `src/engram/symbols.py`, `src/engram/harvest.py`, `src/engram/indexer.py`, `src/engram/cli.py`
- **Exports**: `read_repos_csv`, `enumerate_corpora`, `registry_root`, `harvest`, `index`

### Module: Verification and guidance
- **Maps to capability**: Validate repository registration before indexing
- **Responsibility**: Prove the regression, preserve compatibility, and explain changed behavior.
- **Location**: `tests/test_read_repos_csv.py`, `tests/test_corpora.py`, `tests/test_harvest_resolve.py`, `tests/test_harvest.py`, `tests/test_indexer.py`, `tests/test_cli_index_status.py`, `tests/test_cli_index_rebuild.py`, `README.md`, `CHANGELOG.md`
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
- [ ] Implement the specified behavior in the listed production modules, preserving the stated safety and compatibility rules. (depends on: Phase 0) - Acceptance: uv run --no-sync python -m pytest -q tests/test_read_repos_csv.py tests/test_corpora.py tests/test_harvest_resolve.py tests/test_harvest.py tests/test_indexer.py tests/test_cli_index_status.py tests/test_cli_index_rebuild.py

**Exit Criteria**: All Critical Scenarios pass; required negative checks fail clearly and preserve data as specified.

### Phase 2: Integration
**Goal**: Verify the complete correction and record its limits.

**Tasks**:
- [ ] Update README and add scoped CHANGELOG entries for the implemented behavior; run the selected tests. (depends on: Phase 1) - Acceptance: review the diff against each Feature, confirm all listed scenarios, and run git diff --check.

**Exit Criteria**: Run the repository main gate once: uv run --no-sync python -m pytest -q --ignore=eval -m "not private". Then run the evaluation gate once: PYTHONPATH=src:. uv run --no-sync python -m pytest -q eval -m "not private". Report deselected private tests explicitly. No real portfolio or live database mutation is permitted.

## Test Strategy

### Critical Scenarios
- Empty, unreadable, invalid UTF-8, relative and NUL-bearing registries fail without changing seeded rows or vectors, including rebuild.
- A symlinked registration indexes and lookup-by-file succeeds from either spelling; legacy memory attribution still works.
- A 200-file harvest reads the registry once and canonicalizes each root once.
- Conflicting registrations fail deterministically; valid four-column gita rows remain supported.

### Original QA evidence
Verbatim evidence follows. Mocked observations retain that status; local fixture tests do not turn them into real-server measurements. Isolate fixture setup from the user's actual HOME and store.

````text
2026-11-16 #6
`repos.csv` = `S/f3/link,scratchrepo,,` (`link` points at `repo`). After `index --scope repo` rc 0: `lookup --file src/app.py` gives `no symbol matched`, rc 1, from `repo`, from `link`, and with the full link path. `lookup --name retry_embed --scope repo` returns `S/f3/link/src/app.py:8-10`. A trailing-slash entry works. Harvest stores the resolved form, so one store holds both spellings. Heidi also saw, once and without a root cause, a pack that lost a `settings.py` row under a `/var` registration. Confidence: confirmed.
2026-11-16 #9
With `repos.csv` truncated to zero bytes: `status --scope portfolio` showed `prd 2`, `decision 2`, `code 6`, `findings 5`; `engram index --scope portfolio` returned rc 0 with no output; `status` then showed only `findings 5`. `index --rebuild` did the same. A missing file is refused with `repos.csv not found; register repos with gita first`, rc 1. Confidence: confirmed.
2026-11-16 #16
With `repos.csv` at mode 000: `engram status --scope portfolio` ends in `PermissionError: [Errno 13]` with a traceback; `engram query --scope repo retry` inside a registered repo says `not inside a registered repo; pass --scope portfolio instead`. With non-UTF-8 bytes: `status` and `index --scope portfolio` end in a `UnicodeDecodeError` traceback. `harvest` reports `no_repo` per file as the changelog says. Confidence: confirmed.
2026-11-16 #23
200 files against a 5-row registry: 1,200 `realpath` calls, 200 registry reads, 8.43-8.44 s. Against a 500-row registry: 100,200 `realpath` calls, 1,005,010 `lstat` calls, 10.18-10.25 s. A 1.21x slowdown, reproduced twice. Confidence: confirmed.
2026-11-16 #28
`repos.csv` = `.,relname,,`. In an unrelated scratch repo, `engram index --scope repo` returned rc 0 and the store held a row with repo `relname` and the relative path `o.py`. A `~` row is not expanded and is refused. Confidence: confirmed.
2026-11-15 run 2 #4
Registry line `/tmp/agoge-heidi.eadzeu/T/repo,scratchrepo,,`. From that repo, `index --scope repo` gave `not inside a registered repo; pass --scope portfolio instead`, rc 1, and `lookup --file src/app.py` also gave rc 1. `index --scope portfolio` gave rc 0. Cause: a raw string compare with the realpath from `git rev-parse --show-toplevel`. Confidence: confirmed.
````

## Risks

- Stricter validation rejects previously tolerated hand edits. Canonicalizing roots must preserve legacy Claude memory slugs and must not automatically remove historical findings.
- Requirements are resolved. Implementation must not ask for a preference, touch a real store, or weaken assertions to obtain a pass.
