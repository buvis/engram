---
default_model: opus
model_tier_rationale: multiple user-facing explanations must accurately describe measured behavior and limitations
---

# Correct operating and upgrade documentation

Source: 2026-11-16 #5, 2026-11-16 #20, 2026-11-16 #21, 2026-11-16 #31, 2026-11-15 run 2 #1, 2026-11-15 run 2 #2, 2026-11-15 run 2 #6, 2026-11-15 run 2 #7, 2026-11-15 run 2 #10, 2026-11-15 run 2 #11, 2026-11-15 run 2 #15, 2026-11-15 run 2 #16. Original packets: docs/dev/project-management/audit-results/agoge-2026-11-16.md and docs/dev/project-management/audit-results/agoge-2026-11-15-2.md.
Decision: docs/dev/project-management/audit-results/agoge-triage-2026-11-23.md. This is a bounded QA correction, not a replacement of the completed feature PRDs.

Status: HOLD, source evidence for the Gems port. Do not execute in standalone Engram.
Target owner: buvis/gems, port plan docs/dev/project-management/discovery/00161-engram-port-plan.md.
The source paths, tests and Python/config assumptions below describe standalone Engram. Adapt them to the target architecture and port contract before creating executable Gems PRDs.

## Overview

### Problem Statement
The docs promise server shutdown and only one external download, misdescribe module context, omit an upgrade repair path, and repeat changelog categories.

### Target Users
The solo developer and local agents using Engram to index repositories and recall prior work.

### Success Metrics
Every Critical Scenario passes with synthetic data in isolated temporary roots. Historical evidence below is from the QA run, not a fresh measurement. No suite-wide test count or timing target is imposed.

## Functional Decomposition

### Capability: Correct operating and upgrade documentation
Apply the recorded disposition without changing unrelated behavior.

#### Feature: Describe runtime behavior
- **Description**: Describe runtime behavior.
- **Inputs**: Existing detached-server design and grammar download behavior.
- **Outputs**: Accurate lifecycle and network documentation.
- **Behavior**: State that spawned servers stay running for reuse. Give a PID-specific shutdown procedure: identify the engram-started process and verify its command before killing that PID; never recommend a broad pkill. State that model and per-version grammar downloads occur. List the current module-context allowlist and say unsupported top-level-only languages can be omitted.

#### Feature: Describe upgrade and storage costs
- **Description**: Describe upgrade and storage costs.
- **Inputs**: Existing --backfill-code command and historical QA observations.
- **Outputs**: A precise repair route and qualified cost notes.
- **Behavior**: Document backfill as the bounded repair for unchanged code with old line-splitting bodies as well as missing module context, with rebuild as an alternative. State that --reembed-code does not re-chunk. Correct the corpus table. Describe reported rebuild and partition overhead as synthetic observations with source report/date, not measured limits for the user's current portfolio. Do not change vector partitioning or language coverage.

#### Feature: Normalize the unreleased changelog
- **Description**: Normalize the unreleased changelog.
- **Inputs**: Current duplicated categories and dependency pin.
- **Outputs**: One category section per type and an accurate dependency version.
- **Behavior**: Premise: duplicate Added/Fixed headings still sit under one Unreleased heading and pyproject pins 1.25.2. Recheck at execution; skip and report any obsolete premise. Merge like categories without dropping entries, correct the grammar version to the current pin, and classify the worktree feature under Added. Do not invent a release date or create a tag.

## Structural Decomposition

### Repository Structure

```text
README.md
CHANGELOG.md
```

### Module: Product correction
- **Maps to capability**: Correct operating and upgrade documentation
- **Responsibility**: Implement the Features in the existing modules; no new public API is required.
- **Location**: `README.md`, `CHANGELOG.md`
- **Exports**: README and changelog text only

### Module: Verification and guidance
- **Maps to capability**: Correct operating and upgrade documentation
- **Responsibility**: Prove the regression, preserve compatibility, and explain changed behavior.
- **Location**: `README.md`, `CHANGELOG.md`
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
- [ ] Recheck each stated documentation premise against the current source and dependency pin; record and skip any obsolete premise. (no internal deps) - Acceptance: record command, expected failure or premise, and output for each applicable Critical Scenario. Use only planted markers and temporary data.

**Exit Criteria**: Failure evidence or current documentation premises are recorded; no secrets or live stores are involved.

### Phase 1: Core
**Goal**: Deliver the Functional Decomposition.

**Tasks**:
- [ ] Apply the exact documentation scope in all three Features; retain unrelated entries and release history. (depends on: Phase 0) - Acceptance: Headless assertions described in Critical Scenarios; do not add a permanent test for prose.

**Exit Criteria**: All Critical Scenarios pass; required negative checks fail clearly and preserve data as specified.

### Phase 2: Integration
**Goal**: Verify the complete correction and record its limits.

**Tasks**:
- [ ] Check category uniqueness, dependency version, language list and every required operational statement with headless assertions. (depends on: Phase 1) - Acceptance: review the diff against each Feature, confirm all listed scenarios, and run git diff --check.

**Exit Criteria**: All document assertions pass and git diff --check is clean. No runtime tests are required for this docs-only PRD.

## Test Strategy

### Critical Scenarios
- Compare documented language names to CONTEXT_LANGUAGES and runtime lifecycle to ensure_served/stop_served call sites.
- Assert each category occurs once under Unreleased and the grammar version matches pyproject; retain all existing entry content except the specified corrections.
- Verify README includes both downloads, detached reuse, specific-PID shutdown, backfill versus re-embed, and qualified historical cost notes.

### Original QA evidence
Verbatim evidence follows. Mocked observations retain that status; local fixture tests do not turn them into real-server measurements. Isolate fixture setup from the user's actual HOME and store.

````text
2026-11-16 #5
Walter: pid 2522 on port 18101 appeared after the first `harvest` and was still listed after about 60 later CLI calls, until a manual `pkill`. README.md:260 says "Engram spawns and stops the server itself when nothing is serving." Confidence: confirmed.
2026-11-16 #20
With the grammar cache moved away, `engram index --scope repo --corpus code` returned rc 0 in 2.9 s, and the cache directory then held a new `v1.25.2` bundle of 26,317,364 bytes stamped at run time. The remote host was not observed. The operator's cache holds four versions, so it is once per grammar-pack version, not once. CHANGELOG.md:13 already says "Grammars download once per version". Confidence: confirmed that the bundle appears.
2026-11-16 #21
`rg -n "^## |^### " CHANGELOG.md` prints `7:## [Unreleased]`, `9:### Changed`, `20:### Added`, `63:### Fixed`, `142:### Added`, `174:### Fixed`. `git tag --list` is empty and `pyproject.toml` says `version = "0.1.0"`. Line 11 says "update tree-sitter-language-pack to 1.25.0" while `pyproject.toml` pins `1.25.2`. The worktree feature landed as `feat` commits but sits under Fixed. Confidence: confirmed.
2026-11-16 #31
A store with 1 pair and 1,000 chunks: 5.2 MB. With 16 pairs and 1,136 chunks: 68.3 MB. With 81 pairs and 11,280 chunks: 349.8 MB. The link to the partition keys is read from the schema, not isolated by a test. Confidence: confirmed for the sizes, suspected for the cause.
2026-11-15 run 2 #1
Walter: after the first `index`, `pgrep` showed pid 40818 on port 18101. About 20 engram calls later the same pid 40818 was still there, and only a manual `pkill` removed it. README.md:255-256 says "Engram spawns and stops the server itself when nothing is serving." Confidence: confirmed.
2026-11-15 run 2 #2
Heidi: with the `6d0d171` index, `after_marks 7-8` stored `MANGO = 1`. After the HEAD `index` and `index --reembed-code` the body was still `MANGO = 1` (now embedded again). `status` printed `code 9 stale=0 dead=0`, rc 0. Only `index --rebuild` gave `def after_marks():`. Wendy saw the same with `beta 14-15` storing `GAMMA = 3`. Confidence: confirmed.
2026-11-15 run 2 #6
Wendy moved the grammar cache out of a scratch HOME and ran `index --corpus code` with `HF_HUB_OFFLINE=1` → rc 0. Then `du -sh .../tree-sitter-language-pack` → `27M`, with a new `v1.25.0/bundles/macos-arm64-….tar.zst` and `manifest.json`. Confidence: confirmed (a real network download).
2026-11-15 run 2 #7
The ratio was measured 4 times: 10 repos (560 files) cold 41.31 s vs 20.65 s, rebuild 42.44 s vs 20.62 s; 20 repos (1120 files) cold 92.24 s vs 41.49 s, rebuild 81.08 s vs 39.07 s. Module context is 35.5% of chunks but 69% of embedded characters (about 755 vs 196 characters per chunk). The fixture holds about 60% top-level code, so real repos will pay less. An unchanged re-index still embeds nothing (0.2-0.5 s). Confidence: confirmed at synthetic scale.
2026-11-15 run 2 #10
Through the CLI, `src/script.rb` (`puts "hello"` / `PAPAYA = 1`) stayed in `empty_sources` with no rows, while `src/lib.rb` with a `def` got `Module context 1-1 LYCHEE = 1`. Calling `symbols.chunk` directly gave `[]` for the other eight languages (this part is from a direct function call, not the CLI). Confidence: confirmed for Ruby.
2026-11-15 run 2 #11
Wendy's fixture dump holds `settings.py 1-2 Module context` rows, and the tracked `.json`, `.yaml`, `.toml` and `.md` files produced no code chunks. Confidence: confirmed.
2026-11-15 run 2 #15
Wendy quoted the heading lines. Recon found `git tag --list` empty. **Downgraded:** the claim came as verified, but the evidence quoted the file's headings and no command run, so it is `unverified`. Confidence: suspected (likely true).
2026-11-15 run 2 #16
10 repos: 30 vector blocks, 125,829,120 bytes for 2,720 vectors (about 11.1 MB of real data, 8.9% full). 20 repos: 60 blocks, 251,658,240 bytes. Module context adds only 2.25 MB and 4.47 MB. Confidence: confirmed.
````

## Risks

- Documentation makes retained costs and gaps explicit; it does not optimize them. No source code or release metadata changes belong in this PRD.
- Requirements are resolved. Implementation must not ask for a preference, touch a real store, or weaken assertions to obtain a pass.
