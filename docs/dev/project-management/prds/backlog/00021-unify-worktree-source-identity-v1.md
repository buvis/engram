---
default_model: opus
model_tier_rationale: cross-checkout identity and history preservation require design
---

# Use one source identity across linked worktrees

Source: 2026-11-16 #4, 2026-11-16 #7, 2026-11-16 #25. Original packets: docs/dev/project-management/audit-results/agoge-2026-11-16.md and docs/dev/project-management/audit-results/agoge-2026-11-15-2.md.
Decision: docs/dev/project-management/audit-results/agoge-triage-2026-11-23.md. This is a bounded QA correction, not a replacement of the completed feature PRDs.

## Overview

### Problem Statement
File lookup uses worktree paths while the index uses the registered checkout. Harvest stores the same review under multiple checkout paths, and a fabricated gitdir pointer can claim a registered repository.

### Target Users
The solo developer and local agents using Engram to index repositories and recall prior work.

### Success Metrics
Every Critical Scenario passes with synthetic data in isolated temporary roots. Historical evidence below is from the QA run, not a fresh measurement. No suite-wide test count or timing target is imposed.

## Functional Decomposition

### Capability: Use one source identity across linked worktrees
Apply the recorded disposition without changing unrelated behavior.

#### Feature: Verify real worktree membership
- **Description**: Verify real worktree membership.
- **Inputs**: Current root, common Git directory and registered checkout.
- **Outputs**: A registered root only for a genuine listed checkout.
- **Behavior**: Require the resolved current root to appear in git worktree list --porcelain -z from the registered checkout before accepting fallback common-dir mapping. Preserve direct registered-root and claude-home resolution. Reject fabricated gitdir references.

#### Feature: Map file lookup to stored paths
- **Description**: Map file lookup to stored paths.
- **Inputs**: Relative or absolute file inside the current checkout.
- **Outputs**: Lookup under the registered canonical root.
- **Behavior**: Derive a repo-relative path from the current checkout and map it onto the registered root. Refuse paths outside the checkout. Report registered-checkout paths and document that spans describe the indexed checkout, not branch-local line positions.

#### Feature: Canonicalize future harvested sources
- **Description**: Canonicalize future harvested sources.
- **Inputs**: A review read from a registered root or its listed worktree.
- **Outputs**: One canonical registered-root plus relative-path source identity.
- **Behavior**: Read content from the actual worktree but store the canonical registered path. Reharvesting that source retains existing last-write-wins semantics. Within the current harvest, remove an old alias source only when all its records and vectors correspond to the canonical replacement; preserve differing historical variants and report them. Do not sweep vanished worktrees or discard divergent historical findings automatically.

## Structural Decomposition

### Repository Structure

```text
src/engram/harvest.py
src/engram/findings.py
src/engram/cli.py
src/engram/store.py
tests/test_harvest_resolve.py
tests/test_harvest.py
tests/test_findings_store.py
tests/test_cli.py
README.md
CHANGELOG.md
```

### Module: Product correction
- **Maps to capability**: Use one source identity across linked worktrees
- **Responsibility**: Implement the Features in the existing modules; no new public API is required.
- **Location**: `src/engram/harvest.py`, `src/engram/findings.py`, `src/engram/cli.py`, `src/engram/store.py`
- **Exports**: `registry_root`, `harvest`, `upsert`, `main`

### Module: Verification and guidance
- **Maps to capability**: Use one source identity across linked worktrees
- **Responsibility**: Prove the regression, preserve compatibility, and explain changed behavior.
- **Location**: `tests/test_harvest_resolve.py`, `tests/test_harvest.py`, `tests/test_findings_store.py`, `tests/test_cli.py`, `README.md`, `CHANGELOG.md`
- **Exports**: Existing test entry points and user documentation; no runtime exports.

## Dependency Graph

### Foundation Layer (Phase 0)
- **Verification and guidance**: No internal dependencies; establish reproductions and current premises first.
- External prerequisites: [00019](00019-validate-repository-registry-v1.md). Execute these PRDs first; do not work on overlapping source modules concurrently.

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
- [ ] Implement the specified behavior in the listed production modules, preserving the stated safety and compatibility rules. (depends on: Phase 0) - Acceptance: uv run --no-sync python -m pytest -q tests/test_harvest_resolve.py tests/test_harvest.py tests/test_findings_store.py tests/test_cli.py

**Exit Criteria**: All Critical Scenarios pass; required negative checks fail clearly and preserve data as specified.

### Phase 2: Integration
**Goal**: Verify the complete correction and record its limits.

**Tasks**:
- [ ] Update README and add scoped CHANGELOG entries for the implemented behavior; run the selected tests. (depends on: Phase 1) - Acceptance: review the diff against each Feature, confirm all listed scenarios, and run git diff --check.

**Exit Criteria**: Run the repository main gate once: uv run --no-sync python -m pytest -q --ignore=eval -m "not private". Then run the evaluation gate once: PYTHONPATH=src:. uv run --no-sync python -m pytest -q eval -m "not private". Report deselected private tests explicitly. No real portfolio or live database mutation is permitted.

## Test Strategy

### Critical Scenarios
- Relative and absolute lookup works in a genuine worktree and the primary checkout; outside paths fail.
- Harvest identical text from both checkouts and receive one logical source, including a legacy exact-duplicate fixture.
- Different historical text remains retained and reported; failed embedding leaves all existing sources intact.
- A hand-made gitdir pointer not listed by Git cannot inject findings into the registered repo.

### Original QA evidence
Verbatim evidence follows. Mocked observations retain that status; local fixture tests do not turn them into real-server measurements. Isolate fixture setup from the user's actual HOME and store.

````text
2026-11-16 #4
From the worktree: `engram lookup --file src/app.py` gives `no symbol matched`, rc 1. From the main checkout the same command returns 5 rows, rc 0. From the worktree, `lookup --name retry_embed --scope repo` works. README.md:114-115 says "A linked git worktree of a registered repo uses that repo's registration"; the CHANGELOG line for 00016 lists five verbs and leaves `lookup --file` out without saying so. Confidence: confirmed.
2026-11-16 #7
After harvesting `00001-review.md` from `wt` and from `repo`, `engram query --scope repo -k 2 retry backs off` returns the same finding in both result slots, one per path, with equal scores. After `git worktree remove --force`, `status` still prints `findings 15 stale=0 dead=0`, and a query returns a path that no longer exists. Heidi read in the code that `status` never computes stale or dead for findings; that part is an inference. Confidence: confirmed for the duplicates.
2026-11-16 #25
`spoof1/.git` contained `gitdir: S/f1/repo/.git`; `spoof1` was not in `repos.csv`. `engram harvest reviews/r.md` there: `upserted 4`, rc 0, stored under `scratchrepo`. In the real repo, `engram query --scope repo` then returned the spoofed finding first, and a pack listed it under "Findings precedent". A directory pointing at an unregistered `.git` was refused. Confidence: confirmed.
````

## Risks

- Future harvests of different branch text share last-write-wins source identity. Historical divergent variants remain intentionally retained, and their cleanup is outside this PRD.
- Requirements are resolved. Implementation must not ask for a preference, touch a real store, or weaken assertions to obtain a pass.
