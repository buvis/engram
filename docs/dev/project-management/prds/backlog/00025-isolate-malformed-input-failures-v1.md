---
default_model: opus
model_tier_rationale: several parser error boundaries and continuation semantics
---

# Isolate malformed input failures and clarify diagnostics

Source: 2026-11-16 #29, 2026-11-15 run 2 #12. Original packets: docs/dev/project-management/audit-results/agoge-2026-11-16.md and docs/dev/project-management/audit-results/agoge-2026-11-15-2.md.
Decision: docs/dev/project-management/audit-results/agoge-triage-2026-11-23.md. This is a bounded QA correction, not a replacement of the completed feature PRDs.

## Overview

### Problem Statement
Deeply nested inputs can escape per-file error handling and abort a harvest batch. Known config failures print tracebacks, and optional missing directories appear as unlabeled output.

### Target Users
The solo developer and local agents using Engram to index repositories and recall prior work.

### Success Metrics
Every Critical Scenario passes with synthetic data in isolated temporary roots. Historical evidence below is from the QA run, not a fresh measurement. No suite-wide test count or timing target is imposed.

## Functional Decomposition

### Capability: Isolate malformed input failures and clarify diagnostics
Apply the recorded disposition without changing unrelated behavior.

#### Feature: Contain parser failures
- **Description**: Contain parser failures.
- **Inputs**: Reviews, memory frontmatter and transcript records.
- **Outputs**: Per-file or per-record errors without loss of neighboring work.
- **Behavior**: Convert expected RecursionError at YAML/JSON parser boundaries into the existing parse-failed result. Continue harvest after a bad review and preserve its existing rows. Skip a malformed/deep transcript record while retaining valid neighboring turns. Ordinary malformed JSON already skips one record; preserve that behavior and add only the missing deep-nesting case. Do not add a blanket catch around all application exceptions.

#### Feature: Report known configuration failures
- **Description**: Report known configuration failures.
- **Inputs**: Malformed TOML, missing embedding fields, unreadable config and SQLite open errors.
- **Outputs**: A concise diagnostic and documented nonzero status.
- **Behavior**: Catch expected configuration and store errors at CLI boundaries and name the relevant path without raw secret values. Preserve nudge's always-zero contract and MCP's structured error result.

#### Feature: Label optional missing directories
- **Description**: Label optional missing directories.
- **Inputs**: Existing optional-directory diagnostics.
- **Outputs**: missing followed by a tab and the existing corpus:repo payload.
- **Behavior**: Change _print_missing to print missing<TAB>{existing value}. Preserve existing scope filtering and status exit rules; optional absence alone stays nonfatal. Document the output change.

## Structural Decomposition

### Repository Structure

```text
src/engram/findings.py
src/engram/harvest.py
src/engram/transcripts.py
src/engram/memory.py
src/engram/client.py
src/engram/cli.py
tests/test_findings.py
tests/test_harvest.py
tests/test_transcripts.py
tests/test_repo_memory.py
tests/test_cli_embedding_errors.py
tests/test_cli_index_status.py
README.md
CHANGELOG.md
```

### Module: Product correction
- **Maps to capability**: Isolate malformed input failures and clarify diagnostics
- **Responsibility**: Implement the Features in the existing modules; no new public API is required.
- **Location**: `src/engram/findings.py`, `src/engram/harvest.py`, `src/engram/transcripts.py`, `src/engram/memory.py`, `src/engram/client.py`, `src/engram/cli.py`
- **Exports**: `parse`, `harvest`, `chunk`, `parse_memory`, `load_config`, `main`

### Module: Verification and guidance
- **Maps to capability**: Isolate malformed input failures and clarify diagnostics
- **Responsibility**: Prove the regression, preserve compatibility, and explain changed behavior.
- **Location**: `tests/test_findings.py`, `tests/test_harvest.py`, `tests/test_transcripts.py`, `tests/test_repo_memory.py`, `tests/test_cli_embedding_errors.py`, `tests/test_cli_index_status.py`, `README.md`, `CHANGELOG.md`
- **Exports**: Existing test entry points and user documentation; no runtime exports.

## Dependency Graph

### Foundation Layer (Phase 0)
- **Verification and guidance**: No internal dependencies; establish reproductions and current premises first.
- External prerequisites: [00019](00019-validate-repository-registry-v1.md), [00017](00017-verify-embedding-model-identity-v1.md). Execute these PRDs first; do not work on overlapping source modules concurrently.

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
- [ ] Implement the specified behavior in the listed production modules, preserving the stated safety and compatibility rules. (depends on: Phase 0) - Acceptance: uv run --no-sync python -m pytest -q tests/test_findings.py tests/test_harvest.py tests/test_transcripts.py tests/test_repo_memory.py tests/test_cli_embedding_errors.py tests/test_cli_index_status.py

**Exit Criteria**: All Critical Scenarios pass; required negative checks fail clearly and preserve data as specified.

### Phase 2: Integration
**Goal**: Verify the complete correction and record its limits.

**Tasks**:
- [ ] Update README and add scoped CHANGELOG entries for the implemented behavior; run the selected tests. (depends on: Phase 1) - Acceptance: review the diff against each Feature, confirm all listed scenarios, and run git diff --check.

**Exit Criteria**: Run the repository main gate once: uv run --no-sync python -m pytest -q --ignore=eval -m "not private". Then run the evaluation gate once: PYTHONPATH=src:. uv run --no-sync python -m pytest -q eval -m "not private". Report deselected private tests explicitly. No real portfolio or live database mutation is permitted.

## Test Strategy

### Critical Scenarios
- Harvest valid, deeply nested YAML, valid files and assert all three results, retained bad-file rows, and both valid updates.
- Transcript with a deep JSON record retains valid turns before and after; normal malformed JSON still behaves as before.
- Malformed and incomplete config produce no traceback across CLI commands; unexpected programmer errors remain visible in tests.
- Missing optional directory output is labeled and scoped, with exit 0 when it is the only issue.

### Original QA evidence
Verbatim evidence follows. Mocked observations retain that status; local fixture tests do not turn them into real-server measurements. Isolate fixture setup from the user's actual HOME and store.

````text
2026-11-16 #29
One example each: `reviewers: [[[[...` nested 5000 deep makes `engram harvest good.md deep.md good.md` print a `RecursionError` traceback of about 200 KB and no result lines at all. `engram.db.lock` as a dangling symlink is followed and the target is created with mode 0755. The lock as a directory ends in an uncaught `IsADirectoryError`. A transcript with one bad line is skipped whole, valid turns included. A `config.toml` with bad TOML or no `endpoint` gives a traceback from `query` (`mcp` and `nudge` report it cleanly). A diff line with form feeds is split into a fake section and aborts the pack; the path guard still held. Confidence: confirmed.
2026-11-15 run 2 #12
Every `index` and `status` run printed `discovery:scratchrepo`, rc 0. Confidence: confirmed.
````

## Risks

- Catch only known input exceptions so programming errors remain diagnosable. The report's blanket claim about any bad transcript line was broader than the current code supports.
- Requirements are resolved. Implementation must not ask for a preference, touch a real store, or weaken assertions to obtain a pass.
