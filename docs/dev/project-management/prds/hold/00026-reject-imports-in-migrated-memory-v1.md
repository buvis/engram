---
default_model: opus
model_tier_rationale: security-sensitive import predicate and false-positive boundary
---

# Reject import paths in migrated memory metadata

Source: 2026-11-16 #27. Original packets: docs/dev/project-management/audit-results/agoge-2026-11-16.md and docs/dev/project-management/audit-results/agoge-2026-11-15-2.md.
Decision: docs/dev/project-management/audit-results/agoge-triage-2026-11-23.md. This is a bounded QA correction, not a replacement of the completed feature PRDs.

Status: HOLD, source evidence for the Gems port. Do not execute in standalone Engram.
Target owner: buvis/gems, port plan docs/dev/project-management/discovery/00161-engram-port-plan.md.
The source paths, tests and Python/config assumptions below describe standalone Engram. Adapt them to the target architecture and port contract before creating executable Gems PRDs.

## Overview

### Problem Statement
Migration copies path-like @ references and control bytes from descriptions into the imported memory index. The downstream import effect was not tested, but the unsafe write is established.

### Target Users
The solo developer and local agents using Engram to index repositories and recall prior work.

### Success Metrics
Every Critical Scenario passes with synthetic data in isolated temporary roots. Historical evidence below is from the QA run, not a fresh measurement. No suite-wide test count or timing target is imposed.

## Functional Decomposition

### Capability: Reject import paths in migrated memory metadata
Apply the recorded disposition without changing unrelated behavior.

#### Feature: Reject import-shaped descriptions
- **Description**: Reject import-shaped descriptions.
- **Inputs**: Candidate memory descriptions.
- **Outputs**: Existing skip-invalid outcome before writing.
- **Behavior**: Reject @ followed by slash, tilde, dot, backslash or an alphanumeric character at a token boundary in descriptions; this intentionally excludes path-like @mentions as well. Reject C0/C1 control characters in descriptions. Reject token-start ~/ and ../ host-path forms in description or body using the existing host-private rule. Do not rewrite source files or escape text using an unverified host syntax.

#### Feature: Preserve migration transaction behavior
- **Description**: Preserve migration transaction behavior.
- **Inputs**: Dry-run and apply with good and rejected candidates.
- **Outputs**: Only valid candidates are migrated; rejected text reaches no import index.
- **Behavior**: Use existing skip-invalid reporting and rollback behavior. Keep legitimate repository-relative links without @ and ordinary prose intact; neither dry-run nor rejected candidates alter their sources.

## Structural Decomposition

### Repository Structure

```text
src/engram/migrate.py
tests/test_memory_migrate.py
README.md
CHANGELOG.md
```

### Module: Product correction
- **Maps to capability**: Reject import paths in migrated memory metadata
- **Responsibility**: Implement the Features in the existing modules; no new public API is required.
- **Location**: `src/engram/migrate.py`
- **Exports**: `contains_host_path`, `plan_migration`

### Module: Verification and guidance
- **Maps to capability**: Reject import paths in migrated memory metadata
- **Responsibility**: Prove the regression, preserve compatibility, and explain changed behavior.
- **Location**: `tests/test_memory_migrate.py`, `README.md`, `CHANGELOG.md`
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
- [ ] Implement the specified behavior in the listed production modules, preserving the stated safety and compatibility rules. (depends on: Phase 0) - Acceptance: uv run --no-sync python -m pytest -q tests/test_memory_migrate.py

**Exit Criteria**: All Critical Scenarios pass; required negative checks fail clearly and preserve data as specified.

### Phase 2: Integration
**Goal**: Verify the complete correction and record its limits.

**Tasks**:
- [ ] Update README and add scoped CHANGELOG entries for the implemented behavior; run the selected tests. (depends on: Phase 1) - Acceptance: review the diff against each Feature, confirm all listed scenarios, and run git diff --check.

**Exit Criteria**: Run the repository main gate once: uv run --no-sync python -m pytest -q --ignore=eval -m "not private". Then run the evaluation gate once: PYTHONPATH=src:. uv run --no-sync python -m pytest -q eval -m "not private". Report deselected private tests explicitly. No real portfolio or live database mutation is permitted.

## Test Strategy

### Critical Scenarios
- Dry-run and apply reject descriptions containing @~/, @../, @/ and @relative forms plus ESC/tab/control bytes.
- Tilde-home and parent-relative host paths are rejected while safe prose and repo-relative Markdown links migrate.
- Rejected metadata is absent from the resulting index and wiring; existing rollback and idempotence tests pass.

### Original QA evidence
Verbatim evidence follows. Mocked observations retain that status; local fixture tests do not turn them into real-server measurements. Isolate fixture setup from the user's actual HOME and store.

````text
2026-11-16 #27
Source file with `description: see @~/.aws/credentials and @../../../../.ssh/config`; `engram memory migrate --from ... --to ... --apply` reported `migrate`, and the resulting `MEMORY.md` line holds both `@` paths. A description with a raw ESC byte was also written as is. Whether Claude Code then follows those paths was not exercised, so the effect is unverified. Confidence: confirmed for the write, suspected for the effect.
````

## Risks

- Some harmless @mentions will be refused. This addresses generated import text without claiming a demonstrated downstream file read.
- Requirements are resolved. Implementation must not ask for a preference, touch a real store, or weaken assertions to obtain a pass.
