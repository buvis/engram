---
default_model: opus
model_tier_rationale: writes into other repositories (destructive blast radius) and invents the conversion and wiring contracts
eligibility: test -f docs/dev/project-management/prds/done/00010-repo-memory-corpus-v1.md
---

# Memory migrate command

Source: `docs/dev/project-management/intake/processed/00010-shared-project-memory/discovery.md`

## Overview

### Problem Statement

159 Claude auto-memory files map to 21 registered repositories. Repository
memory (PRD 00010) becomes the authority only after those files move into each
repository in the PRD 00010 format, and after each repository tells every host
where its memory lives. Doing this by hand for 21 repositories invites format
drift and accidental publication. This PRD ships a deterministic converter with
a dry-run report. Running it, reviewing the report for public safety,
committing, and pushing is an attended rollout outside this PRD, because a push
to a public remote publishes.

### Target Users

The attended rollout session (agent and user) that migrates each repository.

### Success Metrics

- `tests/test_memory_migrate.py` passes for every scenario in Test Strategy.
- `engram memory check` exits 0 on every repository the command applied to in
  tests.
- A second `--apply` on the same input changes no file (idempotence test).

## Functional Decomposition

### Capability: Memory conversion

#### Feature: Migrate plan

- **Description**: `engram memory migrate --from <claude-memory-dir> --to <repo-root>` prints what would happen and writes nothing.
- **Inputs**: A Claude memory directory and a repository root.
- **Outputs**: One TSV line per source file, `<file>\t<action>\t<detail>`.
  Actions: `migrate`, `skip-user`, `skip-credential`, `skip-invalid`,
  `skip-exists`, `skip-identical`. Exit 0 when every line is `migrate` or
  `skip-identical`, 1 otherwise. The report lists every source file.
- **Behavior**: Reads every `*.md` except `MEMORY.md`. The slug is the file
  stem, lowercased, with `_` replaced by `-`. `type` comes from `type` or
  `metadata.type`. `user` gives `skip-user`. A credential pattern hit (PRD 00010
  guard) gives `skip-credential`. Missing `name` or `description`, or
  unparseable frontmatter, gives `skip-invalid`. A target file with the same
  slug and different content gives `skip-exists`; identical content gives
  `skip-identical`.

#### Feature: Migrate apply

- **Description**: `--apply` writes the `migrate` files and the repository wiring.
- **Inputs**: Same as the plan.
- **Outputs**: Converted files in `<repo-root>/docs/dev/project-management/memory/`, a regenerated `MEMORY.md`, and the wiring edits. The same TSV report.
- **Behavior**: Each converted file keeps the body unchanged and gets the
  frontmatter `name: <slug>`, `description`, `type`,
  `source: migrated:claude-auto-memory/<original file name>`, and
  `evidence: [none recorded before migration]`. Other original keys are
  dropped. No absolute host path is written. `[[old_stem]]` links whose
  target was renamed are rewritten to the new slug. `MEMORY.md` is regenerated
  from all memory files in the directory, sorted by slug, one line
  `- [<name>](<slug>.md) — <description>`. Writes go to a temporary file in the
  same directory and are then renamed. Source files are never modified or
  deleted. Nothing is committed.

#### Feature: Repository wiring

- **Description**: `--apply` makes every host find repository memory.
- **Inputs**: The repository root.
- **Outputs**: Idempotent edits to four files.
- **Behavior**:
  - `.gitattributes`: append `docs/dev/project-management/memory/MEMORY.md merge=union` when absent.
  - `AGENTS.md`: append the canonical `## Project memory` section when no such
    heading exists. Create the file with only that section when it is absent.
    The section text is the constant `AGENTS_SECTION` in `src/engram/migrate.py`
    (path, schema summary, public-safe rule, `docs(memory): <verb> <slug>`
    commit rule, "read `MEMORY.md` before work"). It must be 25 lines or fewer.
  - `CLAUDE.md`: append `@docs/dev/project-management/memory/MEMORY.md` when no
    line equals it. Create the file as `@AGENTS.md` plus that line when it is
    absent.
  - `.claude/settings.json`: set `"autoMemoryEnabled": false`, keeping every
    other key. Refuse with exit 1 and change nothing in the repository when the
    file exists and is not a JSON object.

## Structural Decomposition

### Repository Structure

```
src/engram/
├── migrate.py               # Maps to: Migrate plan, Migrate apply, Repository wiring
└── cli.py                   # Maps to: memory migrate subcommand
tests/
└── test_memory_migrate.py   # All scenarios in Test Strategy
README.md                    # Migration section
```

### Module: migrate

- **Maps to capability**: Memory conversion
- **Responsibility**: Plan and apply one Claude memory directory into one repository.
- **Location**: `src/engram/migrate.py`
- New symbols: `src/engram/migrate.py`, `plan_migration`, `apply_migration`, `MigrationLine`, `AGENTS_SECTION`, `parse_memory`, `check_directory` (the last two ship in PRD 00010)
- **Exports**:
  - `plan_migration(src, repo_root)` - returns `list[MigrationLine]`
  - `apply_migration(src, repo_root)` - writes files and wiring, returns the same lines
  - `AGENTS_SECTION` - canonical `AGENTS.md` section text

### Module: cli

- **Maps to capability**: Memory conversion
- **Responsibility**: Expose `engram memory migrate --from DIR --to DIR [--apply]`.
- **Location**: `src/engram/cli.py`
- New symbols: `_run_memory_migrate`
- **Exports**:
  - `main()` - gains `memory migrate`

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first. PRD 00010's `src/engram/memory.py` must be done
(frontmatter eligibility).

- **migrate**: conversion and wiring, using `parse_memory`, `check_directory`, and `memory_dir` from PRD 00010

### Core Layer (Phase 1)

- **cli**: Depends on [migrate]

### Integration Layer (Phase 2)

- **README.md**: Depends on [cli]

## Implementation Phases

### Phase 0: Foundation

**Goal**: Deterministic conversion and wiring.

**Tasks**:

- [ ] Add `plan_migration` and `MigrationLine` in `src/engram/migrate.py` (no deps) - Acceptance: `pytest tests/test_memory_migrate.py -k plan` passes for each action, and asserts that the plan writes nothing.
- [ ] Add `apply_migration` and `AGENTS_SECTION` in `src/engram/migrate.py` (depends on: plan task) - Acceptance: `pytest tests/test_memory_migrate.py -k "apply or wiring or idempot"` passes. Applied output passes `check_directory`. A second apply changes no bytes. Source files are byte-identical afterwards. No written file contains the source directory's absolute path. A non-object `.claude/settings.json` leaves the repository unchanged.

**Exit Criteria**: Conversion of a fixture with every action type yields a valid memory directory and the full report.

### Phase 1: Core

**Goal**: CLI access.

**Tasks**:

- [ ] Add `memory migrate --from --to [--apply]` to `_build_parser` and `_run_memory_migrate` in `src/engram/cli.py` (depends on: Phase 0) - Acceptance: `pytest tests/test_memory_migrate.py -k cli` passes: dry run exits 0 or 1 per the plan rule, writes nothing, and `--apply` writes.

**Exit Criteria**: The command runs end to end on a temporary fixture.

### Phase 2: Integration

**Goal**: Documented rollout input.

**Tasks**:

- [ ] Add a "Migrating Claude auto-memory" section to `README.md`: dry run, review the report for public safety, apply, `engram memory check`, one `docs(memory): migrate claude auto-memory` commit per repository, and push only after approval (depends on: Phase 1) - Acceptance: `rg -n "engram memory migrate" README.md` returns a match.

**Exit Criteria**: `.venv/bin/python -m pytest -q --ignore=eval` passes and `git diff --check` is clean.

## Test Strategy

### Critical Scenarios

- **Happy path**: three valid project/feedback/reference memories into an empty repository → three files, sorted index, four wiring edits, `check_directory` clean.
- **Edge case**: `feedback_foo_bar.md` linked as `[[feedback_foo_bar]]` from another memory → file `feedback-foo-bar.md`, link rewritten.
- **Edge case**: the repository already has `AGENTS.md`, `CLAUDE.md`, `.gitattributes`, and `.claude/settings.json` with other keys → content kept, one addition each, none duplicated on rerun.
- **Error case**: `type: user`, a credential, broken frontmatter, or a conflicting existing slug → the matching `skip-*` line, the file is not written, and dry-run exits 1.
- **Error case**: a `.claude/settings.json` holding a JSON array → exit 1 and no file in the repository changes.

## Risks

- **A converted memory is not public-safe**: the command never commits or pushes. The README rollout requires review of every `migrate` line before commit and approval before push.
- **The `AGENTS.md` section grows Codex context**: the 25-line cap keeps it inside Codex's 32 KiB default.
- **A repository's agents cannot write the new directory**: the installed autopilot `enforce_prd_location.py` hook blocks `docs/dev/project-management/memory/` until the companion vocabulary change ships. Python writes from this command are not affected, but the rollout must wait for the companion before agents add new memories.
