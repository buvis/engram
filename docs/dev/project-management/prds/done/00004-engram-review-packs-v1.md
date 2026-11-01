---
catchup: force
---

# Engram Review Packs: Diff-Selective Reviewer Context

Source: `~/.claude/dev/local/discovery/00090-engram-context-engine.md` (PRD C2).
Depends on PRD 00002 (code corpus) and PRD 00003 (findings corpus).

## Overview

### Problem Statement

Reviewers see the diff and the PRD but not similar local code, reuse precedent, or
prior findings - so they miss convention drift and re-litigate known patterns.
Diff-selective AST/embedding retrieval measurably improves review results (discovery
Q6). Generate a bounded, origin-labeled context pack per review cycle and wire it
into every non-blind review surface.

### Target Users

CLI reviewer lanes (Bob/codex, Carl/gemini, Quinn/qwen), Claude consensus and doubt
lenses. The blind lens (Blake, PRD-only) never receives a pack - by design.

### Success Metrics

- On >=3 historical commit ranges (past PRD implementation commits from real
  repos, via `engram pack --diff <range>`): each generated pack contains at least
  one retrieved item absent from the diff.
- Scope-filter test: zero foreign-repo items ever appear in the Similar-code
  section.
- No pack exceeds the 4,000-token hard cap or any per-section cap (composer's own
  estimator).
- The blind lens path carries zero pack references: `references/blind-lens-prompt.md`
  and the blind prompt assembly in review-work-completion contain no engram-pack
  path, section, or variable.

## Functional Decomposition

### Capability: Pack Generation

#### Feature: Diff symbol parser
- **Description**: AST-aware extraction of changed symbols from the staged diff.
- **Inputs**: `dev/local/tmp/review-diff-{id}.diff` (emitted at review time by <!-- link-ok: runtime staging artifact -->
  review-work-completion's gather-context.sh), the repo worktree.
- **Outputs**: List of changed symbols (function/class + file:line).
- **Behavior**: Map diff hunks to enclosing symbols via tree-sitter; hunks in
  grammarless files fall back to file-level entries.
  Premise: gather-context.sh stages `review-diff-{id}.diff` cycle-keyed in
  `dev/local/tmp/`; re-check at execution time - if the staging contract has <!-- link-ok: runtime staging dir -->
  changed, skip and report instead of forcing.

#### Feature: Pack composer
- **Description**: Per-changed-symbol retrieval assembled into a bounded pack.
- **Inputs**: Changed symbols; PRD file; capsule; the engram store.
- **Outputs**: `dev/local/tmp/engram-pack-{id}.md` (absolute path), sections in
  order: Similar code, Reuse precedent, Findings precedent, Task prose; every
  item labeled with its origin (repo + file:line or corpus).
- **Behavior**: Similar code retrieves `--scope repo` ONLY (foreign conventions
  must never read as local precedent); Reuse precedent `--scope portfolio`,
  labeled per source repo; Findings precedent both scopes, labeled; Task prose =
  PRD + capsule extract + related memories. Budget: 4,000-token hard cap;
  per-section caps 1,500 (similar) / 1,000 (reuse) / 1,000 (findings) / 500
  (prose); on overflow trim lowest-score hits within the offending section.
  Deterministic: same inputs, same pack.

#### Feature: Pre-pack reindex
- **Description**: Refresh-before-consume at the pack touchpoint.
- **Inputs**: Current repo + portfolio index state.
- **Outputs**: Fresh index, then the pack.
- **Behavior**: `engram pack --cycle <id>` (or `--diff <range>`) always runs the
  incremental reindex first; staleness never reaches a reviewer silently.

### Capability: Reviewer Wiring

#### Feature: CLI lane templates
- **Description**: codex/gemini/qwen reviewer prompts reference the pack.
- **Inputs**: review-work-completion `references/agent-prompts.md` templates;
  `references/agent-invocation.md` staging steps.
- **Outputs**: Prompt files carrying the pack path/content per lane convention;
  an invocation step that generates the pack before the lanes launch.
- **Behavior**: Packs travel like the other staged inputs: cycle-id keyed,
  absolute paths (subagents misresolve relative `dev/local/`). Edits land in
  ~/.claude (buvis-tracked: stage by absolute path, never `commit -a`).
  Premise: template structure matches the discovery's Codebase Context read;
  re-check at execution time, skip and report on material drift.

#### Feature: Claude lens wiring
- **Description**: Consensus gets the full pack; doubt gets findings only.
- **Inputs**: Consensus/doubt lens prompt assembly in review-work-completion.
- **Outputs**: Full pack prepended to the consensus lens; the Findings-precedent
  section ONLY prepended to the doubt lens; blind lens untouched.
- **Behavior**: Blind (Blake, PRD-only) is asserted pack-free - the wiring change
  must include a check that the blind prompt path has no pack reference.

## Structural Decomposition

### Repository Structure

```
src/engram/
├── diffmap.py               # Maps to: Pack Generation (diff symbol parser)
├── pack.py                  # Maps to: Pack Generation (composer + reindex)
└── (earlier modules unchanged; cli.py gains the pack verb)
(external) ~/.claude/skills/review-work-completion/references/agent-prompts.md
(external) ~/.claude/skills/review-work-completion/references/agent-invocation.md
                             # Maps to: Reviewer Wiring
```

### Module: diffmap
- **Maps to capability**: Pack Generation (diff symbol parser)
- **Responsibility**: Diff-hunk to symbol mapping via tree-sitter.
- **Exports**:
  - `changed_symbols(diff_path) -> list[Symbol]`

### Module: pack
- **Maps to capability**: Pack Generation
- **Responsibility**: Scoped per-symbol retrieval, budget enforcement, section
  assembly, pre-pack reindex.
- **Exports**:
  - `build(cycle_id | diff_range) -> PackReport` - writes engram-pack-{id}.md

### Module: wiring (external edits, ~/.claude)
- **Maps to capability**: Reviewer Wiring
- **Responsibility**: Template + invocation edits; blind-lens assertion.
- **Exports**:
  - Pack references in CLI lane prompts; consensus/doubt prepend; staging step

## Dependency Graph

### Foundation Layer (Phase 0)
No new foundation - PRDs 00001-00003 (query, code corpus, findings corpus) are the
foundation; already built.

### Core Layer (Phase 1)
- **diffmap**: Depends on [symbols (00002)].
- **pack**: Depends on [diffmap, query (00001), findings (00003), indexer
  (00001)].

### Integration Layer (Phase 2)
- **wiring**: Depends on [pack].

## Implementation Phases

### Phase 0: Diff Mapping
**Goal**: Changed symbols extracted from a staged diff.

**Tasks**:
- [ ] Diff symbol parser (no deps) - Acceptance: fixture diff over a fixture repo
      yields the expected symbol list; grammarless hunk falls back to file-level;
      premise re-check on gather-context.sh staging passes.

**Exit Criteria**: `changed_symbols()` correct on fixtures including edge hunks.

### Phase 1: Pack Composition
**Goal**: Bounded, labeled, deterministic packs.

**Tasks**:
- [ ] Pack composer (depends on: Phase 0) - Acceptance: fixture store + diff
      produce a pack with all four sections, origin labels, and stable output
      across two runs.
- [ ] Budget enforcement (depends on: composer) - Acceptance: oversized fixture
      retrieval trims lowest-score hits within the offending section; caps and
      hard cap asserted in tests.
- [ ] `engram pack` verb + pre-pack reindex (depends on: composer) - Acceptance:
      `engram pack --diff <range>` writes engram-pack-{id}.md and the index
      refresh ran first (observable via status timestamps).
- [ ] Scope-filter test (depends on: composer) - Acceptance: with foreign-repo
      chunks seeded in the store, the Similar-code section contains zero of
      them.

**Exit Criteria**: Pack metrics (item-beyond-diff, caps, scope filter) pass on
>=3 historical commit ranges.

### Phase 2: Reviewer Wiring
**Goal**: Every non-blind surface consumes the pack; blind provably does not.

**Tasks**:
- [ ] CLI lane templates + invocation staging step (depends on: Phase 1) -
      Acceptance: premise re-check passes; codex/gemini/qwen prompt templates
      reference the cycle's pack by absolute path; staged edits committed via
      buvis by explicit path.
- [ ] Consensus/doubt prepend + blind assertion (depends on: Phase 1) -
      Acceptance: consensus prompt contains the full pack; doubt prompt contains
      only the Findings-precedent section; blind prompt assembly asserted
      pack-free by a grep over blind-lens-prompt.md + the blind invocation path
      (zero hits).

**Exit Criteria**: A dry-run review cycle on a sample PRD stages prompts for all
lanes with correct pack scoping, unattended.

## Test Strategy

### Critical Scenarios
- **Happy path**: historical commit range → Expected: pack with >=1 item absent
  from the diff, all sections labeled.
- **Edge case**: diff touching only grammarless files; empty findings corpus →
  Expected: file-level retrieval; empty section rendered, caps still hold.
- **Error case**: missing review-diff-{id}.diff → Expected: loud failure naming
  the expected staging path, no empty pack written.

## Risks

- **Pack budget vs usefulness**: caps are config, not constants - retuning is a
  config change, not a code change.
- **Template drift in ~/.claude**: premise re-checks skip-and-report instead of
  forcing edits onto changed templates.
- **Foreign-precedent leakage**: guarded by a dedicated scope-filter test, the
  discovery's named hazard (Q6).
