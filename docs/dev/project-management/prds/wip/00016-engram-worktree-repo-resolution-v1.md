---
design: skip
default_model: opus
model_tier_rationale: changes repo resolution shared by every repo-scoped command; a wrong fallback silently attributes files to the wrong repo
eligibility: test -f docs/dev/project-management/prds/done/00014-engram-findings-pack-correctness-v1.md
---

# Engram repo resolution in git worktrees

Source: user decision 2026-11-16. Evidence: about 50 agent-skills autopilot
reviews (for example
`~/git/src/github.com/buvis/agent-skills/docs/dev/project-management/reviews/00076-distil-tests-see-non-atomic-writes-v1-review-1.md`)
record `engram pack` exit 1 "not inside a registered repo" because autopilot
works in linked worktrees under `~/git/src/worktrees/`, which gita does not list.

## Overview

### Problem Statement

Repo scope resolves through `_resolve_repo_for_path`
(`src/engram/harvest.py:37-67`): it takes `git rev-parse --show-toplevel` and
looks that path up in the gita registry. A linked worktree's toplevel is the
worktree directory, which is never registered, so `engram pack`,
`engram query --scope repo`, `engram index --scope repo`, `engram harvest`,
and repo-scoped `engram mcp` calls all fail there. Autopilot reviews then run
without a context pack.

PRD 00014 changes the same function (canonical path compare, `OSError`
handling). This PRD builds on it, so it waits until 00014 is done.

### Target Users

Autopilot review cycles and agents working in linked git worktrees.

### Success Metrics

- `engram pack --cycle <id>` exits 0 in a linked worktree of a registered repo.
- Every test named in the phases passes and fails against the pre-change code.
- Behavior in a registered main checkout is unchanged.

## Functional Decomposition

### Capability: Worktree-aware repo resolution

#### Feature: Main checkout fallback
- **Description**: A linked worktree resolves to the registry entry of its main checkout.
- **Inputs**: File path, gita `repos.csv`.
- **Outputs**: Repo name or `None`.
- **Behavior**: Keep the existing toplevel lookup first, so a registered
  worktree keeps its own name. Only when it finds no row: run
  `git rev-parse --path-format=absolute --git-common-dir` with the same `cwd`.
  If that succeeds and the result's last path component is `.git`, take its
  parent as the main checkout and look it up in the registry with the same
  canonical compare as the toplevel lookup. A bare common dir (name not
  `.git`) or a git failure returns `None`. Never match by basename or prefix.

#### Feature: Registry root lookup
- **Description**: Return the registry path for a repo name.
- **Inputs**: Repo name, gita `repos.csv`.
- **Outputs**: `Path` or `None`.
- **Behavior**: First row whose name equals the given name; `None` when absent
  or when the registry cannot be read (`OSError`).

### Capability: Pack in worktrees

#### Feature: Self-match exclusion across checkouts
- **Description**: A pack built in a worktree still excludes the changed code.
- **Inputs**: Changed spans (worktree paths), `index_root` (main checkout).
- **Outputs**: Exclusion set covering both checkouts.
- **Behavior**: `build()` takes `index_root: Path | None = None`. When it is set
  and `index_root.resolve() != repo_root.resolve()`, add for every changed span
  a second span `(str(index_root / Path(span_path).relative_to(repo_root)),
  start, end)`. The worktree diff, symbol text and output paths still come from
  `repo_root`.
- **CLI**: `_run_pack` passes `index_root=` the Registry root lookup result for
  `repo_name`.

## Structural Decomposition

### Repository Structure

```
src/engram/
├── harvest.py   # Maps to: Main checkout fallback, Registry root lookup
├── pack.py      # Maps to: Self-match exclusion across checkouts
└── cli.py       # Maps to: Self-match exclusion across checkouts (CLI)
tests/
├── test_harvest.py
├── test_pack_regressions.py
└── test_cli_pack.py
README.md
CHANGELOG.md
```

### Module: harvest
- **Maps to capability**: Worktree-aware repo resolution
- **Responsibility**: Resolve a path to its registered repo, including linked worktrees.
- **Location**: `src/engram/harvest.py`
- **Exports**:
  - `_resolve_repo_for_path()` - unchanged signature; adds the fallback.
  - `registry_root(name, repos_csv)` - registry path for a repo name.
- New symbols: `registry_root`, `test_resolve_repo_for_path_maps_linked_worktree_to_main_checkout`, `test_resolve_repo_for_path_registered_worktree_keeps_its_own_name`, `test_resolve_repo_for_path_worktree_of_unregistered_repo_returns_none`, `test_registry_root_returns_path_for_name`

### Module: pack
- **Maps to capability**: Pack in worktrees
- **Responsibility**: Exclude changed spans under both checkouts.
- **Location**: `src/engram/pack.py`
- **Exports**:
  - `build()` - gains `index_root` keyword, default `None`.
- New symbols: `index_root`, `test_pack_in_worktree_excludes_changed_spans_indexed_under_main_checkout`

### Module: cli
- **Maps to capability**: Pack in worktrees
- **Responsibility**: Pass `index_root` to `build()`.
- **Location**: `src/engram/cli.py`
- **Exports**: none new.
- New symbols: `test_cli_pack_succeeds_in_linked_worktree`

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies inside this PRD (PRD 00014 must be done first; the frontmatter eligibility check enforces it).

- **harvest**: fallback and `registry_root`.

### Core Layer (Phase 1)
- **pack**: Depends on [harvest] only through the CLI wiring; the exclusion change itself has none.

### Integration Layer (Phase 2)
- **cli**: Depends on [harvest, pack].
- **README.md, CHANGELOG.md**: Depend on [cli].

## Implementation Phases

### Phase 0: Foundation
**Goal**: Worktree paths resolve to the main checkout's repo.

**Tasks**:
- [ ] Add the Main checkout fallback and `registry_root` in
  `src/engram/harvest.py`; add
  `test_resolve_repo_for_path_maps_linked_worktree_to_main_checkout`,
  `test_resolve_repo_for_path_registered_worktree_keeps_its_own_name`,
  `test_resolve_repo_for_path_worktree_of_unregistered_repo_returns_none` and
  `test_registry_root_returns_path_for_name` in `tests/test_harvest.py`. Build
  real repos in `tmp_path` with `git init` and `git worktree add` (no deps) -
  Acceptance: `.venv/bin/python -m pytest -q tests/test_harvest.py -k "worktree or registry_root"`
  passes; the first test fails on the pre-change code.

**Exit Criteria**: Worktree resolution tests pass.

### Phase 1: Core
**Goal**: Pack exclusion covers both checkouts.

**Tasks**:
- [ ] Add `index_root` to `build()` in `src/engram/pack.py` per the Feature;
  add `test_pack_in_worktree_excludes_changed_spans_indexed_under_main_checkout`
  in `tests/test_pack_worktree.py` (depends on: Phase 0) - Acceptance:
  `.venv/bin/python -m pytest -q tests/test_pack_worktree.py -k main_checkout`
  passes and fails on the pre-change code.

**Exit Criteria**: Exclusion test passes.

### Phase 2: Integration
**Goal**: The CLI works in worktrees and the docs say so.

**Tasks**:
- [ ] Pass `index_root` from `_run_pack` in `src/engram/cli.py`; add
  `test_cli_pack_succeeds_in_linked_worktree` in `tests/test_cli_pack.py`
  using the file's existing fake-embedder helpers and a store under `tmp_path`
  (depends on: Phase 1) - Acceptance:
  `.venv/bin/python -m pytest -q tests/test_cli_pack.py -k linked_worktree` passes.
- [ ] Add one README sentence after the gita registration paragraph in Install:
  a linked git worktree of a registered repo uses that repo's registration.
  Add a `### Fixed` entry for **cli** in `CHANGELOG.md` under `[Unreleased]`
  (depends on: Phase 2 task 1) - Acceptance:
  `rg -n "worktree" README.md CHANGELOG.md` shows both files.

**Exit Criteria**: `.venv/bin/python -m pytest -q --ignore=eval` and
`PYTHONPATH=src:. .venv/bin/python -m pytest -q eval` pass; `git diff --check` passes.

## Test Strategy

### Critical Scenarios
- **Happy path**: pack in a linked worktree of a registered repo → Expected:
  exit 0, pack written under the worktree's `docs/dev/tmp/`.
- **Edge case**: the worktree itself is registered → Expected: its own name wins.
- **Edge case**: worktree of an unregistered repo → Expected: `None`, existing
  "not inside a registered repo" error.
- **Error case**: `git rev-parse --git-common-dir` fails → Expected: `None`, no crash.

## Risks

- **Stale "Similar code"**: the pack reindexes the main checkout, not the
  worktree, so similar-code hits reflect the main branch. Accepted: the changed
  spans are still excluded and the diff itself comes from the worktree.
- **Harvest attribution**: review files harvested from a worktree are stored
  under the main repo's name with their worktree path. Findings keep their
  body, so they survive worktree removal.
