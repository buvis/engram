---
default_model: opus
model_tier_rationale: symbol correspondence across different source versions
---

# Exclude changed code from worktree packs after line shifts

Source: 2026-11-16 #8, 2026-11-16 #13, 2026-11-16 #29. Original packets: docs/dev/project-management/audit-results/agoge-2026-11-16.md and docs/dev/project-management/audit-results/agoge-2026-11-15-2.md.
Decision: docs/dev/project-management/audit-results/agoge-triage-2026-11-23.md. This is a bounded QA correction, not a replacement of the completed feature PRDs.

Status: HOLD, source evidence for the Gems port. Do not execute in standalone Engram.
Target owner: buvis/gems, port plan docs/dev/project-management/discovery/00161-engram-port-plan.md.
The source paths, tests and Python/config assumptions below describe standalone Engram. Adapt them to the target architecture and port contract before creating executable Gems PRDs.

## Overview

### Problem Statement
Worktree line spans are compared directly to main-checkout spans. Shifted functions match themselves while unrelated symbols are excluded; path resolution also repeats within the hit/span product.

### Target Users
The solo developer and local agents using Engram to index repositories and recall prior work.

### Success Metrics
Every Critical Scenario passes with synthetic data in isolated temporary roots. Historical evidence below is from the QA run, not a fresh measurement. No suite-wide test count or timing target is imposed.

## Functional Decomposition

### Capability: Exclude changed code from worktree packs after line shifts
Apply the recorded disposition without changing unrelated behavior.

#### Feature: Match across source versions
- **Description**: Match across source versions.
- **Inputs**: Changed symbols and indexed-checkout candidates.
- **Outputs**: No changed symbol offered as its own precedent after line drift.
- **Behavior**: For distinct worktree/index roots compare canonical relative file plus symbol kind/name against the indexed symbol identity rather than reusing worktree line numbers. Keep line overlap for the same source version. For ambiguous duplicate names, renamed symbols, or unnamed module context in a divergent file, conservatively omit candidates from that file and report the omission; do not invent a precise match.

#### Feature: Bound path resolution
- **Description**: Bound path resolution.
- **Inputs**: All hits and changed spans in one pack.
- **Outputs**: At most one realpath resolution per distinct path.
- **Behavior**: Canonicalize distinct paths once before comparisons; preserve ranking, deduplication, scope and all-symbol exclusion even beyond the query symbol cap.

#### Feature: Keep physical source lines
- **Description**: Keep physical source lines.
- **Inputs**: Diff content and code excerpts containing form feeds or Unicode separators.
- **Outputs**: Correct changed-symbol spans and excerpt bodies.
- **Behavior**: Use newline-only splitting for physical diff/source lines in changed_symbols and _symbol_query_text. Do not change Markdown prose splitting. Preserve existing quoted-path decoding and traversal guards.

## Structural Decomposition

### Repository Structure

```text
src/engram/pack.py
src/engram/diffmap.py
tests/test_pack_worktree.py
tests/test_pack_correctness.py
tests/test_pack_regressions.py
tests/test_diffmap.py
tests/test_diffmap_decoding.py
README.md
CHANGELOG.md
```

### Module: Product correction
- **Maps to capability**: Exclude changed code from worktree packs after line shifts
- **Responsibility**: Implement the Features in the existing modules; no new public API is required.
- **Location**: `src/engram/pack.py`, `src/engram/diffmap.py`
- **Exports**: `changed_symbols`, `build`

### Module: Verification and guidance
- **Maps to capability**: Exclude changed code from worktree packs after line shifts
- **Responsibility**: Prove the regression, preserve compatibility, and explain changed behavior.
- **Location**: `tests/test_pack_worktree.py`, `tests/test_pack_correctness.py`, `tests/test_pack_regressions.py`, `tests/test_diffmap.py`, `tests/test_diffmap_decoding.py`, `README.md`, `CHANGELOG.md`
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
- [ ] Implement the specified behavior in the listed production modules, preserving the stated safety and compatibility rules. (depends on: Phase 0) - Acceptance: uv run --no-sync python -m pytest -q tests/test_pack_worktree.py tests/test_pack_correctness.py tests/test_pack_regressions.py tests/test_diffmap.py tests/test_diffmap_decoding.py

**Exit Criteria**: All Critical Scenarios pass; required negative checks fail clearly and preserve data as specified.

### Phase 2: Integration
**Goal**: Verify the complete correction and record its limits.

**Tasks**:
- [ ] Update README and add scoped CHANGELOG entries for the implemented behavior; run the selected tests. (depends on: Phase 1) - Acceptance: review the diff against each Feature, confirm all listed scenarios, and run git diff --check.

**Exit Criteria**: Run the repository main gate once: uv run --no-sync python -m pytest -q --ignore=eval -m "not private". Then run the evaluation gate once: PYTHONPATH=src:. uv run --no-sync python -m pytest -q eval -m "not private". Report deselected private tests explicitly. No real portfolio or live database mutation is permitted.

## Test Strategy

### Critical Scenarios
- Shift six lines above a changed function in a real linked worktree; exclude it while retaining uniquely named unrelated neighbors.
- Duplicate names, rename and module-context ambiguity produce conservative omission plus a diagnostic; unchanged-source overlap still works.
- Instrument path resolution for repeated hits/spans and assert calls are bounded by distinct path count.
- Diffs and excerpt source with form feed, NEL and Unicode line separator retain physical line positions.

### Original QA evidence
Verbatim evidence follows. Mocked observations retain that status; local fixture tests do not turn them into real-server measurements. Isolate fixture setup from the user's actual HOME and store.

````text
2026-11-16 #8
In the worktree, one commit added six lines above `retry_embed` (now lines 14-16), the next changed its return. `engram pack --diff HEAD~1..HEAD` rc 0; the pack's Similar code starts with `scratchrepo:S/f1/repo/src/app.py:8-10 def retry_embed(n)`, and `Class Store` (13-15) and `Function open` (14-15) are gone. Before the drift, the same pack correctly left `retry_embed` out and listed both. The cause is inferred from the output, not traced. Confidence: confirmed for the symptom.
2026-11-16 #13
On an 11,280-chunk store: a 5-symbol diff made 531 `realpath` calls; a 50-symbol diff made 38,365 (538,643 `lstat` calls, 2.26-2.28 s); the same 50-symbol diff from a linked worktree made 77,186 (3.12-3.24 s). Ten times the symbols gave 72 times the calls. Confidence: confirmed.
2026-11-16 #29
One example each: `reviewers: [[[[...` nested 5000 deep makes `engram harvest good.md deep.md good.md` print a `RecursionError` traceback of about 200 KB and no result lines at all. `engram.db.lock` as a dangling symlink is followed and the target is created with mode 0755. The lock as a directory ends in an uncaught `IsADirectoryError`. A transcript with one bad line is skipped whole, valid turns included. A `config.toml` with bad TOML or no `endpoint` gives a traceback from `query` (`mcp` and `nudge` report it cleanly). A diff line with form feeds is split into a fake section and aborts the pack; the path guard still held. Confidence: confirmed.
````

## Risks

- Conservative fallback reduces recall for ambiguous divergent files. Report that limitation instead of presenting incorrect source correspondence.
- Requirements are resolved. Implementation must not ask for a preference, touch a real store, or weaken assertions to obtain a pass.
