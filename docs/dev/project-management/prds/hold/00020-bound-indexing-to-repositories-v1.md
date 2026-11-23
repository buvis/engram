---
default_model: opus
model_tier_rationale: security boundary across independent enumerators and direct pack inputs
---

# Index tracked paths without reading outside repositories

Source: 2026-11-16 #3, 2026-11-16 #11, 2026-11-16 #14. Original packets: docs/dev/project-management/audit-results/agoge-2026-11-16.md and docs/dev/project-management/audit-results/agoge-2026-11-15-2.md.
Decision: docs/dev/project-management/audit-results/agoge-triage-2026-11-23.md. This is a bounded QA correction, not a replacement of the completed feature PRDs.

Status: HOLD, source evidence for the Gems port. Do not execute in standalone Engram.
Target owner: buvis/gems, port plan docs/dev/project-management/discovery/00161-engram-port-plan.md.
The source paths, tests and Python/config assumptions below describe standalone Engram. Adapt them to the target architecture and port contract before creating executable Gems PRDs.

## Overview

### Problem Statement
Line-based git output loses Unicode and quoted filenames. Tracked or discovered symlinks can cause outside files to be read and included in context packs.

### Target Users
The solo developer and local agents using Engram to index repositories and recall prior work.

### Success Metrics
Every Critical Scenario passes with synthetic data in isolated temporary roots. Historical evidence below is from the QA run, not a fresh measurement. No suite-wide test count or timing target is imposed.

## Functional Decomposition

### Capability: Index tracked paths without reading outside repositories
Apply the recorded disposition without changing unrelated behavior.

#### Feature: Read exact tracked filenames
- **Description**: Read exact tracked filenames.
- **Inputs**: Git tracked file output.
- **Outputs**: Each supported tracked source exactly once.
- **Behavior**: Use git ls-files -z with NUL splitting and preserve Unicode, spaces, tabs, quotes, backslashes and embedded newlines. Keep deduplication for unmerged stages. Never decode Git C quoting by hand for this command.

#### Feature: Enforce resolved-root containment
- **Description**: Enforce resolved-root containment.
- **Inputs**: Repo code, PRDs, decisions, discovery, repo memory and pack PRD/capsule paths.
- **Outputs**: Only sources resolving inside the registered repo root are read.
- **Behavior**: Check resolved containment before reading or hashing. Permit in-root symlinks; skip outside or broken links and report them as excluded. Cover direct pack reads as well as enumerators. User-provided diff files remain valid outside the repo because they are explicit inputs. Keep host-global memory/transcript sources under their own existing roots.

#### Feature: Apply scope before traversal
- **Description**: Apply scope before traversal.
- **Inputs**: Selected repo scope and validated registry.
- **Outputs**: Repo-scoped index and pack touch only that repo's sources.
- **Behavior**: Filter repo rows before git enumeration or file reads in code and prose enumeration, including backfill. Preserve portfolio behavior, global-memory attribution, and failed-source retention. Scope pruning to exactly the selected repo/corpus.

## Structural Decomposition

### Repository Structure

```text
src/engram/symbols.py
src/engram/corpora.py
src/engram/cli.py
src/engram/pack.py
tests/test_symbols.py
tests/test_corpora.py
tests/test_repo_memory.py
tests/test_cli_pack.py
tests/test_pack_regressions.py
README.md
CHANGELOG.md
```

### Module: Product correction
- **Maps to capability**: Index tracked paths without reading outside repositories
- **Responsibility**: Implement the Features in the existing modules; no new public API is required.
- **Location**: `src/engram/symbols.py`, `src/engram/corpora.py`, `src/engram/cli.py`, `src/engram/pack.py`
- **Exports**: `enumerate`, `enumerate_corpora`, `build`

### Module: Verification and guidance
- **Maps to capability**: Index tracked paths without reading outside repositories
- **Responsibility**: Prove the regression, preserve compatibility, and explain changed behavior.
- **Location**: `tests/test_symbols.py`, `tests/test_corpora.py`, `tests/test_repo_memory.py`, `tests/test_cli_pack.py`, `tests/test_pack_regressions.py`, `README.md`, `CHANGELOG.md`
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
- [ ] Implement the specified behavior in the listed production modules, preserving the stated safety and compatibility rules. (depends on: Phase 0) - Acceptance: uv run --no-sync python -m pytest -q tests/test_symbols.py tests/test_corpora.py tests/test_repo_memory.py tests/test_cli_pack.py tests/test_pack_regressions.py

**Exit Criteria**: All Critical Scenarios pass; required negative checks fail clearly and preserve data as specified.

### Phase 2: Integration
**Goal**: Verify the complete correction and record its limits.

**Tasks**:
- [ ] Update README and add scoped CHANGELOG entries for the implemented behavior; run the selected tests. (depends on: Phase 1) - Acceptance: review the diff against each Feature, confirm all listed scenarios, and run git diff --check.

**Exit Criteria**: Run the repository main gate once: uv run --no-sync python -m pytest -q --ignore=eval -m "not private". Then run the evaluation gate once: PYTHONPATH=src:. uv run --no-sync python -m pytest -q eval -m "not private". Report deselected private tests explicitly. No real portfolio or live database mutation is permitted.

## Test Strategy

### Critical Scenarios
- Index and lookup accented, CJK and quoted/newline filenames through real temporary Git repos.
- Plant marker files outside a repo and link code, PRDs, memory and capsule paths to them; no marker is read, embedded or published. In-root links still work.
- Repo-scoped index, backfill and pack perform no enumeration or file read in a second registered repo; its stored rows remain unchanged.
- Portfolio enumeration still covers both repos and retains existing failure protection.

### Original QA evidence
Verbatim evidence follows. Mocked observations retain that status; local fixture tests do not turn them into real-server measurements. Isolate fixture setup from the user's actual HOME and store.

````text
2026-11-16 #3
`engram lookup --name brew --scope portfolio` gives `no symbol matched`, rc 1, and `status` shows `code 6` for a repo with seven code files. After `git config core.quotepath false` in the scratch repo, the same lookup returns `.../src/café.py:1-3 Function brew_espresso` and `status` shows `code 7` (heidi). The 00014 fix decodes the same quoting in diffs, so `pack` maps a changed symbol in a file the index cannot hold. Three lanes saw no skip line in `status`; trudy saw `code skipped=1` in hers. Confidence: confirmed.
2026-11-16 #11
With `src/creds.py -> ../../outside/creds.ini` committed in a scratch repo: `engram index --scope portfolio` rc 0, and `engram pack --diff HEAD~1..HEAD` wrote a pack (mode 0644) whose Similar code holds the outside file's `aws_secret_access_key = <planted marker>` line. The same happened for a symlinked PRD, capsule and wip PRD. A non-code target is taken whole as a "Module context" chunk. `diffmap` already has a guard against paths outside the repo. Confidence: confirmed.
2026-11-16 #14
Unchanged store, `index --scope repo` in one repo: with 4 repos registered, 4 `git ls-files` runs and 136 file scans; with 20 repos, 20 runs and 1100 scans, for 78 files in scope. At 20 repos the repo-scoped run (0.36 s) cost the same as the portfolio run (0.33 s). Both `pack` runs showed the same 20 and 1100. Confidence: confirmed at this scale; the real portfolio was not measured.
````

## Risks

- Legitimate shared files outside the repo cease to be indexed. This is a containment check, not a guarantee against a hostile process swapping filesystem objects concurrently.
- Requirements are resolved. Implementation must not ask for a preference, touch a real store, or weaken assertions to obtain a pass.
