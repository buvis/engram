---
default_model: opus
model_tier_rationale: invented contracts (memory file schema, check verdicts, legacy-skip predicate) consumed by PRD 00011 and host wiring
---

# Repository memory corpus and validator

Source: `docs/dev/project-management/intake/processed/00010-shared-project-memory/discovery.md`

## Overview

### Problem Statement

Engram reads project memory only from Claude auto-memory
(`~/.claude/projects/<encoded-path>/memory/`). The decided model makes
version-controlled files in each repository the authority, shared by Claude,
Codex, and Copilot, with Git as attribution and history. Engram cannot index
those files and cannot tell a valid memory file from a broken one. This PRD adds
the reader and the checker. Migration and host wiring are PRD 00011 and an
attended rollout.

### Target Users

Agents on any host that recall project knowledge through `engram query`. Also
agents and the user who write memory files and need a fast verdict on them.

### Success Metrics

- `tests/test_repo_memory.py` passes: it covers the enumeration, legacy-skip,
  check, and status scenarios in Test Strategy.
- `engram memory check` exits 0 on a valid fixture repository and 1 on each
  invalid fixture, naming the file and the rule.
- Existing memory attribution tests (`tests/test_memory_attribution.py`) keep
  passing unchanged.

## Functional Decomposition

### Capability: Memory file contract

The format every host writes and Engram reads.

#### Feature: Memory schema

- **Description**: One fact per `docs/dev/project-management/memory/<slug>.md`
  file, with YAML frontmatter and a Markdown body.
- **Inputs**: File text.
- **Outputs**: A parsed `MemoryFile` (slug, name, description, type, source,
  evidence, body) or a list of violations.
- **Behavior**: Required keys: `name` (equals the file stem, matches
  `^[a-z0-9][a-z0-9-]*$`), `description` (non-empty, single line), `type` (one
  of `project`, `feedback`, `reference`; Claude's nested `metadata.type` is
  accepted when top-level `type` is absent), `source` (non-empty string),
  `evidence` (non-empty list of non-empty strings). `type: user` is a
  violation. Any `author` or `date` key is a violation (Git carries them).
  Unknown extra keys are allowed. Missing or unparseable frontmatter is a
  violation.

#### Feature: Index contract

- **Description**: `MEMORY.md` in the same directory lists every memory once.
- **Inputs**: `MEMORY.md` text and the set of memory file stems.
- **Outputs**: Violations.
- **Behavior**: Each line matching `- [<title>](<slug>.md)` is one entry. Lines
  that do not match are ignored (headings, blank lines). Violations: an entry
  whose file is missing, a file with no entry, a duplicate entry, entries not
  sorted by slug, more than 200 lines, or more than 25,000 bytes (Claude's
  startup load limit).

#### Feature: Credential guard

- **Description**: Refuse credential-shaped text in a memory file.
- **Inputs**: Full file text.
- **Outputs**: Violations naming the pattern, never echoing the match.
- **Behavior**: Patterns: `-----BEGIN [A-Z ]*PRIVATE KEY-----`,
  `ghp_[A-Za-z0-9]{36}`, `github_pat_[A-Za-z0-9_]{22,}`,
  `sk-[A-Za-z0-9_-]{20,}`, `AKIA[0-9A-Z]{16}`, `xox[baprs]-[A-Za-z0-9-]{10,}`.
  This is a guard, not proof of public safety.

### Capability: Repository memory recall

#### Feature: Repository memory enumeration

- **Description**: Index each registered repository's memory files as corpus
  `memory`, attributed to that repository.
- **Inputs**: Registry rows; `<repo>/docs/dev/project-management/memory/*.md`.
- **Outputs**: `CorpusFile("memory", <repo name>, <path>)` for every `*.md`
  except `MEMORY.md`.
- **Behavior**: An absent memory directory is not reported in `missing_dirs`
  (the corpus is optional until migration). Invalid files are still indexed.

#### Feature: Legacy skip

- **Description**: Do not index a repository's Claude auto-memory once that
  repository has repository memory.
- **Inputs**: The Claude project directory slug and `slug_to_name` from
  `enumerate_corpora`.
- **Outputs**: Legacy files enumerated only for unmapped slugs and for mapped
  repositories without repository memory.
- **Behavior**: A repository has repository memory when its memory directory
  holds at least one `*.md` file other than `MEMORY.md`. Unmapped and colliding
  slugs keep the existing `_unmapped` behavior. The next incremental index then
  prunes the skipped legacy rows through the existing dead-row pruning.

#### Feature: Memory check command

- **Description**: `engram memory check [PATH]` validates one memory directory.
- **Inputs**: Optional path to a repository root or a memory directory; default
  is the Git top level of the current directory.
- **Outputs**: One line per violation, `<file>\t<rule>\t<detail>`, on stdout.
  Exit 0 when clean, 1 on any violation or when the directory is absent.
- **Behavior**: Runs the schema, index, and credential checks. Needs no
  registry, index, or embedding server.

#### Feature: Status reporting

- **Description**: `engram status` reports invalid repository memory.
- **Inputs**: The scope's repositories.
- **Outputs**: A line `memory\tinvalid=<n>` when n > 0, plus a line
  `memory\tlegacy-shadowed=<repo>` for each repository that has repository
  memory and a non-empty legacy Claude directory.
- **Behavior**: `invalid > 0` sets exit 1. `legacy-shadowed` is informational
  and does not change the exit code.

## Structural Decomposition

### Repository Structure

```
src/engram/
├── memory.py            # Maps to: Memory file contract, Memory check command
├── corpora.py           # Maps to: Repository memory enumeration, Legacy skip
└── cli.py               # Maps to: Memory check command, Status reporting
tests/
└── test_repo_memory.py  # All scenarios in Test Strategy
README.md                # Memory corpus row and format section
```

### Module: memory

- **Maps to capability**: Memory file contract
- **Responsibility**: Parse and validate memory files and their index.
- **Location**: `src/engram/memory.py`
- New symbols: `src/engram/memory.py`, `MemoryFile`, `parse_memory`, `check_directory`, `memory_dir`, `feedback`, `ghp_`
- **Exports**:
  - `MemoryFile` - parsed memory record
  - `parse_memory(path)` - returns `(MemoryFile | None, list[str])`
  - `check_directory(path)` - returns all violations for one memory directory
  - `memory_dir(repo_root)` - returns `repo_root/docs/dev/project-management/memory`

### Module: corpora

- **Maps to capability**: Repository memory recall
- **Responsibility**: Enumerate repository memory and apply the legacy skip.
- **Location**: `src/engram/corpora.py`
- **Exports**:
  - `enumerate_corpora()` - unchanged signature; adds repository memory files
    and skips shadowed legacy directories

### Module: cli

- **Maps to capability**: Memory check command, Status reporting
- **Responsibility**: Add the `memory check` subcommand and the status lines.
- **Location**: `src/engram/cli.py`
- New symbols: `_run_memory_check`
- **Exports**:
  - `main()` - gains `memory check`

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **memory**: schema, index, and credential validation

### Core Layer (Phase 1)

- **corpora**: Depends on [memory] (uses `memory_dir`)

### Integration Layer (Phase 2)

- **cli**: Depends on [memory, corpora]

## Implementation Phases

### Phase 0: Foundation

**Goal**: A tested validator for the memory contract.

**Tasks**:

- [ ] Add `src/engram/memory.py` with `parse_memory`, `check_directory`, and `memory_dir` per the schema, index, and credential features (no deps) - Acceptance: `pytest tests/test_repo_memory.py -k "schema or index or credential"` passes. It covers each violation in the Behavior fields, Claude `metadata.type` acceptance, and that violation text never contains the matched credential.

**Exit Criteria**: Every violation rule has a failing-fixture test and a passing-fixture test.

### Phase 1: Core

**Goal**: Repository memory reaches the index; legacy duplicates do not.

**Tasks**:

- [ ] Extend `_enumerate_repo_corpora` in `src/engram/corpora.py` to yield repository memory files, and make `_enumerate_memory_corpora` skip slugs whose mapped repository has repository memory (depends on: Phase 0) - Acceptance: `pytest tests/test_repo_memory.py -k "enumerat or legacy"` passes. It covers attribution, the `MEMORY.md` exclusion, no `missing_dirs` entry for an absent directory, the skip for a populated directory, no skip for an index-only directory, and `_unmapped` kept for collisions. `pytest tests/test_memory_attribution.py` passes unchanged.

**Exit Criteria**: An incremental index of a fixture portfolio holds repository memory rows and no rows from the shadowed legacy directory.

### Phase 2: Integration

**Goal**: Users and agents get verdicts from the CLI.

**Tasks**:

- [ ] Add `engram memory check [PATH]` to `_build_parser` and `_run_memory_check` in `src/engram/cli.py` (depends on: Phase 1) - Acceptance: `pytest tests/test_repo_memory.py -k cli_check` passes for a clean directory (exit 0), each invalid fixture (exit 1, file and rule printed), an absent directory (exit 1), and the default Git top-level path.
- [ ] Add the `memory\tinvalid=<n>` and `memory\tlegacy-shadowed=<repo>` lines to `_run_status` in `src/engram/cli.py` (depends on: Phase 1) - Acceptance: `pytest tests/test_repo_memory.py -k status` passes: invalid > 0 exits 1, legacy-shadowed alone keeps exit 0.
- [ ] Update `README.md`: memory corpus row lists both sources, a "Repository memory" section gives the path, schema, index rule, public-safe rule, and the `docs(memory): <verb> <slug>` commit convention (depends on: Phase 1) - Acceptance: `rg -n "docs/dev/project-management/memory" README.md` and `rg -n "engram memory check" README.md` each return a match.

**Exit Criteria**: `.venv/bin/python -m pytest -q --ignore=eval` passes and `git diff --check` is clean.

## Test Strategy

### Critical Scenarios

- **Happy path**: a registered fixture repository with two valid memories and a sorted index → both indexed under the repository's name, `memory check` exits 0, status shows no invalid line.
- **Edge case**: a repository with only `MEMORY.md` → its legacy Claude directory is still indexed (no skip).
- **Edge case**: a memory with `metadata: {type: feedback}` and no top-level `type` → valid.
- **Error case**: `type: user`, a missing `evidence`, `name` different from the stem, an `author` key, an unsorted or stale index, a 201-line index, or a `ghp_` token → each yields exit 1 with the rule named. The token value never appears in output.
- **Error case**: an invalid memory in a scoped repository → status prints `memory\tinvalid=1` and exits 1, and the file is still queryable.

## Risks

- **Agents keep writing to the Claude directory after migration**: legacy skip keeps stray files out of recall, and `legacy-shadowed` names them in status.
- **Optional-directory silence hides a typo'd path**: `memory check` on an absent directory exits 1, so an explicit check catches it.
- **The credential list misses a format**: the check is labeled a guard. The public-safe review in the rollout stays the real gate.
