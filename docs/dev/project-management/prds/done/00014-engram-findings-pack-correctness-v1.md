---
design: skip
default_model: opus
model_tier_rationale: harvest/rebuild advisory lock is a concurrency fix on the path that writes the production DB; the other six fixes carry exact expressions
---

# Engram findings, harvest and pack correctness

Source: defects verified against current code on 2026-11-16 (capsule "Session 4
complete" triage; `docs/dev/project-management/reviews/00003-engram-findings-corpus-v1-review-2.md`,
`docs/dev/project-management/reviews/00004-engram-review-packs-v1-review-2.md`).
No discovery doc: every item is a reproduced defect with a fixed expected behavior.

## Overview

### Problem Statement

Seven defects remain in harvest, rebuild and review packs:

1. The parse check (`src/engram/findings.py:157-159`) tests `reviewers`
   via its string form,
   so `reviewers: [""]` or `reviewers: [" "]` passes validation as non-blank.
2. Repo resolution (`src/engram/harvest.py:58-67`) compares `repo_path` to
   git's real `toplevel` with `==`, so a symlinked or trailing-slash
   registry row never matches. It catches only `FileNotFoundError` from
   `corpora.read_repos_csv`, so a `PermissionError` aborts the whole batch.
3. Rebuild (`src/engram/cli.py:294-302`) returns on an index
   failure without closing `tmp_store` or deleting `engram.db.rebuild-tmp`
   (a multi-GB leftover).
4. `_preserve_findings` (`src/engram/cli.py:266`) copies findings from the live
   DB, then `os.replace` swaps the rebuilt DB in. A harvest that writes between
   the copy and the swap is lost without any error. Findings are the one corpus
   that cannot be re-derived from sources.
5. `pack._exclude` (`src/engram/pack.py:66-76`) matches hit paths to changed-span
   paths by raw string. Span paths come from git's toplevel, indexed paths from
   the registry path; a symlinked registry root defeats self-match exclusion,
   so a pack recommends the changed code to itself.
6. `diffmap._section_file_identity` (`src/engram/diffmap.py:81-111`) does not
   decode Git's C-quoted paths (`+++ "b/caf\303\251.py"`), so non-ASCII files
   map to a nonexistent path.
7. The `id_` line (`src/engram/cli.py:479`) sanitizes `--diff` ranges into
   ids that collide (`a/b..c` and `a-b..c` both become `a-b--c`), so one pack's
   diff and pack files overwrite another's.

### Target Users

Agents and autopilot review cycles that call `engram harvest`, `engram pack`
and `engram index --rebuild`.

### Success Metrics

- Every regression test named in the phases passes and fails against the
  pre-fix code (fail-first).
- `--cycle` file names are unchanged: autopilot's `review_stage.py` stages
  `review-diff-{cycle}.diff` and reads `engram-pack-{cycle}.md`.

## Functional Decomposition

### Capability: Findings validation

#### Feature: Strict reviewers check
- **Description**: Reject reviewers values that hold no real reviewer name.
- **Inputs**: Parsed frontmatter mapping.
- **Outputs**: `ValueError("frontmatter must contain reviewers")` or pass.
- **Behavior**: Valid when `reviewers` is a `str` with non-blank `strip()`, or a
  `list` that is non-empty and whose every element is a `str` with non-blank
  `strip()`. Every other value (missing, `None`, blank string, empty list, list
  with a blank or non-string element, number, mapping) raises.

### Capability: Harvest repo resolution

#### Feature: Canonical registry match
- **Description**: Match registry rows to the git toplevel by canonical path.
- **Inputs**: File path, gita `repos.csv`.
- **Outputs**: Registered repo name or `None`.
- **Behavior**: Compare `Path(repo_path).resolve() == Path(toplevel).resolve()`.
  Catch `OSError` (not only `FileNotFoundError`) around
  `corpora.read_repos_csv` and return `None`, so the file gets a `no_repo`
  result and the batch continues.

### Capability: Rebuild safety

#### Feature: Rebuild cleanup
- **Description**: A failed rebuild leaves no temp DB behind.
- **Inputs**: `engram index --rebuild`.
- **Outputs**: Exit 1 and `rebuild failed: <error>` on stderr; no
  `engram.db.rebuild-tmp` file; live DB untouched.
- **Behavior**: On any exception after `.rebuild-tmp` is created, close the temp
  store connection if it was opened, then `unlink(missing_ok=True)` the temp file.

#### Feature: Store write lock
- **Description**: Harvest and rebuild never run at the same time.
- **Inputs**: Lock file `<DEFAULT_DB_PATH>.lock` (for example
  `~/.local/share/engram/engram.db.lock`).
- **Outputs**: `StoreBusyError` when the lock is held.
- **Behavior**: `store.write_lock(lock_path)` is a context manager. It opens
  the file (creating parent dirs), calls
  `fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)`, and on BlockingIOError
  raises `StoreBusyError(f"engram store busy: {lock_path} is held by another harvest or rebuild")`.
  It releases and closes on exit. It never waits: a rebuild can take hours.
  Rebuild holds the lock from before temp-DB creation through `os.replace`.
  `_run_harvest` holds it around `harvest(...)`. On `StoreBusyError` both
  print the message to stderr and exit 1 without writing. Plain incremental
  `engram index` does not take the lock: rebuild re-derives every non-findings
  corpus from sources, so losing its writes is harmless.

### Capability: Review pack correctness

#### Feature: Canonical self-match exclusion
- **Description**: A pack never lists the changed code as its own precedent.
- **Inputs**: Retrieved hits, changed spans.
- **Outputs**: Hits that do not overlap any changed span.
- **Behavior**: In `_exclude`, compare `os.path.realpath(hit.path)` with
  `os.path.realpath(span_path)`. Resolve each span path once, before the loop.

#### Feature: C-quoted diff paths
- **Description**: Decode Git's quoted path form.
- **Inputs**: `+++ ` / `--- ` lines from a unified diff.
- **Outputs**: Correct relative path.
- **Behavior**: When the path text after `+++ ` or `--- ` starts and ends with `"`,
  strip the quotes and decode with
  `codecs.escape_decode(inner.encode("utf-8"))[0].decode("utf-8")`, then strip
  the `a/` or `b/` prefix as today. Unquoted paths are unchanged. Replace the
  `ponytail:` comment at `src/engram/diffmap.py:85-87`.

#### Feature: Collision-free --diff ids
- **Description**: Different `--diff` ranges write to different files.
- **Inputs**: `--diff` range string.
- **Outputs**: Pack id.
- **Behavior**: `id_ = f"{re.sub(r'[^A-Za-z0-9_-]', '-', range_str)}-{hashlib.sha1(range_str.encode()).hexdigest()[:8]}"`.
  The `--cycle` slug (`src/engram/cli.py:456`) is an external contract and stays
  unchanged.

## Structural Decomposition

### Repository Structure

```
src/engram/
├── findings.py   # Maps to: Strict reviewers check
├── harvest.py    # Maps to: Canonical registry match
├── store.py      # Maps to: Store write lock
├── cli.py        # Maps to: Rebuild cleanup, Store write lock, Collision-free --diff ids
├── pack.py       # Maps to: Canonical self-match exclusion
└── diffmap.py    # Maps to: C-quoted diff paths
tests/
├── test_findings.py
├── test_harvest.py
├── test_write_lock.py
├── test_cli_index_status.py
├── test_cli_pack.py
├── test_pack_regressions.py
└── test_diffmap.py
CHANGELOG.md
```

### Module: findings
- **Maps to capability**: Findings validation
- **Responsibility**: Review/audit parsing.
- **Location**: `src/engram/findings.py`
- **Exports**:
  - `parse()` - unchanged signature; stricter reviewers check.
- New symbols: `test_parse_rejects_blank_or_non_string_reviewers`, `test_parse_accepts_string_or_list_of_names`

### Module: harvest
- **Maps to capability**: Harvest repo resolution
- **Responsibility**: Map a review file to its registered repo.
- **Location**: `src/engram/harvest.py`
- **Exports**:
  - `_resolve_repo_for_path()` - unchanged signature.
- New symbols: `test_resolve_repo_for_path_matches_symlinked_registry_path`, `test_resolve_repo_for_path_matches_trailing_slash_registry_path`, `test_harvest_unreadable_registry_yields_no_repo_without_aborting_batch`

### Module: store
- **Maps to capability**: Rebuild safety
- **Responsibility**: Advisory write lock shared by harvest and rebuild.
- **Location**: `src/engram/store.py`
- **Exports**:
  - `write_lock()` - context manager taking a lock path.
  - `StoreBusyError` - raised when the lock is held.
- New symbols: `write_lock`, `StoreBusyError`, `test_write_lock_second_holder_raises_store_busy`, `test_write_lock_released_after_exit`

### Module: cli
- **Maps to capability**: Rebuild safety, Review pack correctness
- **Responsibility**: Rebuild cleanup and locking, harvest locking, `--diff` ids.
- **Location**: `src/engram/cli.py`
- **Exports**: none new.
- New symbols: `test_rebuild_index_failure_removes_tmp_db_and_keeps_live_db`, `test_harvest_exits_1_without_writing_while_rebuild_holds_lock`, `test_rebuild_exits_1_while_harvest_holds_lock`, `test_pack_diff_ids_differ_for_ranges_that_sanitize_alike`

### Module: pack
- **Maps to capability**: Review pack correctness
- **Responsibility**: Self-match exclusion on canonical paths.
- **Location**: `src/engram/pack.py`
- **Exports**: none new.
- New symbols: `test_exclude_drops_hit_whose_path_is_symlink_of_changed_span`

### Module: diffmap
- **Maps to capability**: Review pack correctness
- **Responsibility**: Decode C-quoted diff paths.
- **Location**: `src/engram/diffmap.py`
- **Exports**: none new.
- New symbols: `test_changed_symbols_decodes_c_quoted_non_ascii_path`, `test_changed_symbols_decodes_c_quoted_deleted_path`

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **findings**: strict reviewers check.
- **harvest**: canonical registry match.
- **store**: `write_lock`, `StoreBusyError`.
- **pack**: canonical exclusion.
- **diffmap**: C-quoted paths.

### Core Layer (Phase 1)
- **cli**: Depends on [store] for rebuild/harvest locking; rebuild cleanup and
  `--diff` ids have no dependency.

### Integration Layer (Phase 2)
- **CHANGELOG.md**: Depends on [all modules].

## Implementation Phases

### Phase 0: Foundation
**Goal**: Fix the module-local defects.

**Tasks**:
- [ ] Strict reviewers check in `src/engram/findings.py` per the Feature; add
  `test_parse_rejects_blank_or_non_string_reviewers` (parametrized: `[""]`,
  `[" "]`, `[]`, `["alice", ""]`, `[1]`, `1`, `{"a": "b"}`) and
  `test_parse_accepts_string_or_list_of_names` (`alice,bob` and
  `["alice", "bob"]`) in `tests/test_findings.py` (no deps) - Acceptance:
  `.venv/bin/python -m pytest -q tests/test_findings.py -k reviewers` passes;
  the reject test fails on the pre-fix code.
- [ ] Canonical registry match in `src/engram/harvest.py`; add
  `test_resolve_repo_for_path_matches_symlinked_registry_path`,
  `test_resolve_repo_for_path_matches_trailing_slash_registry_path` and
  `test_harvest_unreadable_registry_yields_no_repo_without_aborting_batch`
  (the registry read raises `PermissionError`) in `tests/test_harvest.py`
  (no deps) - Acceptance: `.venv/bin/python -m pytest -q tests/test_harvest.py -k "symlinked_registry or trailing_slash_registry or unreadable_registry"`
  passes; each fails on the pre-fix code.
- [ ] `write_lock` and `StoreBusyError` in `src/engram/store.py`; add
  `test_write_lock_second_holder_raises_store_busy` (a second flock call from a
  separate open file description while the first is held) and
  `test_write_lock_released_after_exit` in `tests/test_write_lock.py`
  (no deps) - Acceptance: `.venv/bin/python -m pytest -q tests/test_write_lock.py` passes.
- [ ] Canonical exclusion in `src/engram/pack.py` `_exclude`; add
  `test_exclude_drops_hit_whose_path_is_symlink_of_changed_span` in
  `tests/test_pack_regressions.py` (no deps) - Acceptance:
  `.venv/bin/python -m pytest -q tests/test_pack_regressions.py -k symlink_of_changed_span`
  passes and fails on the pre-fix code.
- [ ] C-quoted path decoding in `src/engram/diffmap.py`; add
  `test_changed_symbols_decodes_c_quoted_non_ascii_path` (file `café.py`,
  diff line `+++ "b/caf\303\251.py"`, expects a symbol whose path ends in
  `café.py`) and `test_changed_symbols_decodes_c_quoted_deleted_path`
  (`--- "a/caf\303\251.py"` with `+++ /dev/null`) in `tests/test_diffmap.py`
  (no deps) - Acceptance: `.venv/bin/python -m pytest -q tests/test_diffmap.py -k c_quoted`
  passes; both fail on the pre-fix code.

**Exit Criteria**: All Phase 0 tests pass.

### Phase 1: Core
**Goal**: CLI rebuild safety and pack ids.

**Tasks**:
- [ ] Rebuild cleanup in `src/engram/cli.py` `_run_index`; add
  `test_rebuild_index_failure_removes_tmp_db_and_keeps_live_db` in
  `tests/test_cli_index_status.py` (patch `engram.cli.DEFAULT_DB_PATH` as the
  existing rebuild tests do; make `index` raise) (depends on: Phase 0) -
  Acceptance: `.venv/bin/python -m pytest -q tests/test_cli_index_status.py -k tmp_db_and_keeps_live_db`
  passes and fails on the pre-fix code.
- [ ] Rebuild and harvest take `write_lock(Path(str(DEFAULT_DB_PATH) + ".lock"))`
  per the Store write lock Feature; add `test_harvest_exits_1_without_writing_while_rebuild_holds_lock`
  and `test_rebuild_exits_1_while_harvest_holds_lock` in
  `tests/test_write_lock.py` (depends on: Phase 0) - Acceptance:
  `.venv/bin/python -m pytest -q tests/test_write_lock.py` passes; both new
  tests fail on the pre-fix code.
- [ ] Collision-free `--diff` id in `src/engram/cli.py` `_resolve_pack_diff`;
  add `test_pack_diff_ids_differ_for_ranges_that_sanitize_alike` (`a/b..c`
  vs `a-b..c`) in `tests/test_cli_pack.py`. Premise: `rg -c "engram-pack-(diff-)?(abc123--def456|feature-foo--bugfix-bar)" tests/test_cli_pack.py`
  reports 7 lines pinning the old unhashed names; update exactly those to the
  hashed form and change nothing else in them. If the count differs, skip the
  test edits and report. `--cycle` names must stay unchanged (depends on: Phase 0) -
  Acceptance: `.venv/bin/python -m pytest -q tests/test_cli_pack.py` passes;
  `rg -n "cycle_slug = re.sub" src/engram/cli.py` still matches the unchanged
  line.

**Exit Criteria**: All Phase 1 tests pass.

### Phase 2: Integration
**Goal**: Record the user-visible fixes.

**Tasks**:
- [ ] Add `### Fixed` entries under `[Unreleased]` in `CHANGELOG.md` for
  harvest (`reviewers` check, symlinked registry, unreadable registry), index
  (rebuild cleanup, harvest/rebuild lock) and pack (self-match exclusion,
  non-ASCII paths, `--diff` id collisions) (depends on: Phase 1) -
  Acceptance: `rg -n "rebuild-tmp|lock|C-quoted|non-ASCII|collid" CHANGELOG.md`
  shows the new entries.

**Exit Criteria**: `.venv/bin/python -m pytest -q --ignore=eval` and
`PYTHONPATH=src:. .venv/bin/python -m pytest -q eval` pass; `git diff --check` passes.

## Test Strategy

### Critical Scenarios
- **Happy path**: string reviewers, unquoted ASCII diffs, unlocked harvest and
  rebuild → Expected: behavior unchanged.
- **Edge case**: symlinked registry root → Expected: harvest maps the repo, pack
  excludes the changed spans.
- **Edge case**: non-ASCII file in a diff → Expected: correct symbol path.
- **Error case**: harvest while rebuild holds the lock → Expected: exit 1,
  `engram store busy` on stderr, no findings written.
- **Error case**: rebuild index failure → Expected: exit 1, no
  `.rebuild-tmp`, live DB bytes unchanged.

## Risks

- **Lock left by a crashed process**: an flock lock releases on process exit, so no
  stale-lock cleanup is needed.
- **Hashed `--diff` names break a caller**: autopilot and the review skill use
  `--cycle` only (checked in agent-plugins and agent-skills on 2026-11-16);
  `--cycle` names stay unchanged.
- **Tests touch the real production DB**: every new CLI test must patch
  `engram.cli.DEFAULT_DB_PATH` to `tmp_path`.
