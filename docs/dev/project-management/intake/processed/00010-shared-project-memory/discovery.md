# Discovery: Shared project memory in repository files

## Classification

Depth: comprehensive | Date: 2026-11-10

Several repositories, three hosts, a data migration, and public exposure.
Source: `idea.md` beside this file.

## Problem

Project memory now lives in Claude Code auto-memory under
`~/.claude/projects/<encoded-path>/memory/`. Only Claude writes or reads it. It
has no Git history and stays on one machine. Codex and Copilot sessions in the
same repository never see it. The decided model in `buvis/docs`
(`src/agents/components.md`, "Shared memory") makes repository files the
authority. Git supplies author, time, and revisions, and Engram indexes the files
for recall. The file format, path, migration, and host wiring were left open, so
nothing has moved. Every session that writes Claude-only memory widens the gap.

Census on 2026-11-10: 295 memory files in about 40 Claude project directories.
Engram maps 159 files to 21 registered repositories. The other 136 files belong
to non-repository working directories (`~`, `~/.claude`, `~/.config`, `~/bim`,
`~/Downloads`, temporary directories) or unregistered repositories.
`buvis/cellar` is private; the other 28 `buvis` repositories are public.

## Requirements

### Must have

- **R1 Path.** Each Project keeps its memory in
  `docs/dev/project-management/memory/` at the repository root: one fact per
  `<slug>.md` file plus a `MEMORY.md` index. This follows the working-documents
  rule that durable project records live under `docs/dev/project-management/`.
- **R2 Format.** Markdown with YAML frontmatter:
  - `name`: kebab-case slug that equals the file stem.
  - `description`: one line, used for recall and for the index.
  - `type`: `project`, `feedback`, or `reference`. Claude's nested
    `metadata.type` is also accepted. `user` is not allowed, because facts about
    the person stay in host-global memory.
  - `source`: where the knowledge came from (a session ID, a commit, a PR or
    issue URL, a document path, or `migrated:<original path>`).
  - `evidence`: a non-empty list of checkable pointers (commit SHA,
    `path:line`, URL, a command with its observed result). A migrated file
    whose original holds no evidence records the single entry
    `none recorded before migration`.
  - Body: the fact. For `feedback` and `project`, add `**Why:**` and
    `**How to apply:**` lines. Links use `[[slug]]`.
  - No author or date fields. Git commits record the authoring Agent, the time,
    and every revision.
- **R3 Index.** `MEMORY.md` has one line per memory:
  `- [Title](slug.md) — description`, sorted by slug. It must stay inside
  Claude's startup limit (200 lines or 25 KB). The repository adds
  `docs/dev/project-management/memory/MEMORY.md merge=union` to
  `.gitattributes`, so parallel additions merge without conflict.
- **R4 Revisions and deletion.** A correction edits the file in place, and Git
  keeps the old content. A retraction deletes the file and its index line in one
  commit. Engram's next incremental index prunes the deleted file's chunks and
  vectors, so no derived index keeps it. Git history is not rewritten, except to
  remove an exposed secret (see R7).
- **R5 Concurrency.** One fact per file, unique slugs, and the union-merged index
  allow parallel sessions and branches to add memory without coordination. Two
  edits to the same file conflict in Git, and the second writer resolves the
  conflict. A writer commits each memory change on its own, with the message
  `docs(memory): <verb> <slug>`. It never folds the change into an unrelated code
  commit.
- **R6 Scope.** A new memory goes to the repository that holds the current
  working directory (the Git top level). Recall defaults to that repository
  (`engram query --scope repo`). A portfolio query is an explicit choice. A blind
  or limited role (for example Blake) must not receive memory unless its
  assignment allows it. The caller that assembles the role's input enforces
  this; Engram offers corpus filtering and does not decide roles.
- **R7 Public-safe content (user decision Q1).** Repository memory holds only
  content that may be public, the same bar as the rest of
  `docs/dev/project-management/`. Secrets, credentials, personal data, and
  host-private details stay in host-global memory (`~/.claude/rules/`,
  `AGENTS.md`). `engram memory check` refuses credential-shaped content: a
  short pattern list (private-key blocks, common token prefixes such as
  `ghp_`, `github_pat_`, `sk-`, `AKIA`). Engram has no redaction patterns
  today, so this list is new. The check is a guard, not proof of safety. If a secret reaches a public commit, rotate
  it first. Rewriting history needs the user's approval.
- **R8 Engram corpus.** Engram enumerates
  `docs/dev/project-management/memory/*.md` (except `MEMORY.md`) for every
  registered repository as corpus `memory`, attributed to that repository. The
  legacy Claude auto-memory reader stays for directories that have no repository
  memory. When a repository has repository memory, its legacy Claude directory
  is skipped, so the same fact is not indexed twice.
- **R9 Validation.** `engram memory check [PATH]` validates R2 and R3 (fields,
  slug equals stem, index lines match files, size limit) and R7 (credential
  patterns). It exits 1 and names each violation. Indexing stays tolerant: an
  invalid memory is still indexed, and `engram status` reports it.
- **R10 Host integration.**
  - All hosts: the repository's `AGENTS.md` carries a short "Project memory"
    section that names the path, the format, the public-safe rule, and the
    commit rule. Codex and Copilot read the repository's `AGENTS.md` (Codex up
    to 32 KiB by default). Claude reads it through `CLAUDE.md` (`@AGENTS.md`).
  - Claude: the repository's `.claude/settings.json` sets
    `autoMemoryEnabled: false`, and its `CLAUDE.md` adds
    `@docs/dev/project-management/memory/MEMORY.md`. The documentation confirms
    that imports load at startup. Claude then follows the same `AGENTS.md`
    rules as the other hosts. `autoMemoryDirectory` was rejected: the
    documentation shows only absolute and `~/` paths, and repository-supplied
    values depend on workspace trust. A headless probe on 2026-11-10 could not
    run, because nested `claude` failed OAuth in the sandbox.
  - Codex and Copilot: rely on `AGENTS.md` alone. Their native memory features
    could not be verified in official documentation (2026-11-10), so they are
    not wired.
- **R11 Migration.** Move the 159 mapped legacy files into their repositories,
  converted to R2 with `source: migrated:<original path>`. Before any write,
  screen each file against R7. A file that is not public-safe, has `type: user`,
  or holds a cross-project fact stays in host memory, and the migration report
  lists it with the reason. Make one commit per repository. Pushing to the
  public remotes needs the user's explicit approval, given once for the reviewed
  batch, because a push publishes. The original Claude files stay until each
  repository's push is verified. The 136 unmapped files stay where they are.
- **R12 Retirement pointer.** After migration, `~/.claude/rules/memory.md` and
  `~/.claude/AGENTS.md` state that project facts go to repository memory, and
  that Claude auto-memory holds only non-repository and host-private facts.

### Nice to have

- `engram memory check` as an opt-in pre-commit hook.
- A `--corpus` exclusion flag on `engram pack` for blind roles, if a consumer
  needs it.

### Out of scope

- Memory for non-repository directories and the bare `~/.buvis` dotfiles
  repository (`~/.claude` project, 80 files). These stay in Claude auto-memory.
- A memory-writing CLI or service. Agents write the files directly; Engram stays
  a reader (decided model: the index is never another writer).
- Native Codex and Copilot memory features.
- Freshness scoring or automatic conflict detection between memories. Recall
  returns the file pointer, and agents check remembered decisions against the
  current state (`components.md`).
- Embedding model changes or a full rebuild. The new corpus enters through
  ordinary incremental indexing.

## Constraints

- Preserve the production model, configuration, index, and evaluation
  snapshots. Use no full rebuild without explicit authorization.
- Do not edit `buvis/claude-autopilot`; it is frozen. Autopilot companion work
  goes to `buvis/agent-plugins/plugins/autopilot`.
- Edit skills only in `buvis/agent-skills`, then run `braid --check`.
- A push to a public remote publishes. It needs explicit approval and cannot be
  undone.
- Claude's `MEMORY.md` loads only its first 200 lines or 25 KB.

## Codebase Context

- **Relevant code**: `src/engram/corpora.py` (`_enumerate_memory_corpora`,
  `_enumerate_repo_corpora`, `enumerate_corpora`); `src/engram/indexer.py`
  (incremental pruning); `src/engram/pack.py:175-198` (memory hits in packs);
  `src/engram/cli.py` (subcommands); `README.md:25,83,173` (memory corpus
  documentation).
- **Conventions**: per-repository corpora are found under
  `docs/dev/project-management/` by `_enumerate_repo_corpora`. Missing
  directories go to `missing_dirs` and are not errors. Tests use temporary
  registries and project directories (`tests/test_corpora.py`).
- **Integration points**: add a `memory` branch to `_enumerate_repo_corpora`;
  skip the legacy directory whose encoded path matches a repository that has
  repository memory; add the `memory check` CLI; add an invalid-memory count to
  `status`.
- **Similar implementations**: `findings.py` and `harvest.py` validate
  frontmatter for review records; Session 1's slug encoding in
  `enumerate_corpora` maps Claude directories to repositories.
- **Companion surfaces** (outside this repository):
  - `agent-skills/skills/catchup/scripts/load-memories.sh` reads only the
    Claude directory, and its `tr '/.' '-'` misses `_` and other characters.
  - `agent-skills/skills/distil-memory` writes proposals into the Claude
    directory (`write.py --store`).
  - `agent-skills/skills/manage-agents-md/references/promote-memories.md`
    promotes from the Claude directory.
  - `~/.claude/rules/memory.md` and `~/.claude/AGENTS.md` (in `buvis/home`).
  - `agent-plugins/plugins/autopilot`: blind-role input assembly (R6).

## Approach

- **Chosen**: plain Markdown files in each repository, using Claude's existing
  memory format plus `source` and `evidence`. Git provides attribution and
  history, `.gitattributes` union merge handles the index, `AGENTS.md` serves
  every host, and Claude's `autoMemoryDirectory` is used where it works. Engram
  only reads the files and checks them.
- **Why**: it reuses formats and mechanisms that already exist. Migration is
  mostly a copy. All three hosts already read `AGENTS.md`. Claude needs no new
  tool. It keeps the decided authority model: files are the authority, Git is
  the history, and the index can be rebuilt.
- **Rejected alternatives**:
  - Engram as the memory writer or service: the decided model forbids the index
    becoming a writer, and it adds a daemon.
  - A single JSONL or YAML database file per repository: it conflicts on every
    parallel write and is harder for agents to edit.
  - Gitignored local memory files: they lose Git attribution and cross-machine
    reach (Q1 option rejected).
  - Repository memory only in private repositories: this splits the model, and
    almost every repository is public (Q1 option rejected).
  - Host-native memory for Codex and Copilot: it is unverified and creates a
    second authority per host.

## Success Criteria

- `engram query --scope repo --corpus memory` in a migrated repository returns
  its repository memory files, and no legacy duplicates.
- `engram memory check` exits 0 on every migrated repository. It exits 1 on
  fixtures with a missing field, a slug mismatch, an index drift, an oversize
  index, `type: user`, or a credential.
- A Codex or Copilot session in a migrated repository can name the memory path
  and rules from `AGENTS.md` without Claude-specific files.
- A Claude session in a migrated repository either loads repository
  `MEMORY.md` at startup through `autoMemoryDirectory`, or has auto-memory
  disabled for that repository. The spike records which.
- Deleting a memory file and running an incremental index removes its chunks
  and vectors. No other corpus changes.
- The migration report accounts for all 159 mapped files (migrated or retained
  with a reason). No file is pushed before approval.

## Risks

- **Public exposure of migrated content**: R7 screening, a reviewed report, one
  approval for the batch before any push, and originals kept until verified.
- **`autoMemoryDirectory` refuses a relative or repository path, or needs trust
  each time**: the spike decides; the fallback is per-repository disable plus
  `AGENTS.md`.
- **Agents keep writing to the Claude directory out of habit**: R8 skips that
  directory for migrated repositories, so stray writes are not indexed. A
  `status` warning names a non-empty legacy directory beside repository memory.
- **The index outgrows 200 lines**: `memory check` fails at the limit. The
  repository then prunes memories or moves detail into topic files.
- **Union merge leaves duplicate or unsorted index lines**: `memory check`
  reports index drift, and the writer re-sorts.

## Open Questions

- **Prerequisite for the rollout (companion):** the installed autopilot hook
  `enforce_prd_location.py` (0.10.0, whose source is in frozen
  `buvis/claude-autopilot`) blocks writes to
  `docs/dev/project-management/memory/`. It allows only its fixed top-level
  vocabulary. Agents cannot write repository memory until `memory` joins that
  vocabulary in the `agent-plugins` autopilot port, or until the user lifts the
  freeze for a hotfix. The `structure-git-repo` layout reference needs the same
  entry. Engram's own PRDs are not blocked, because their tests use temporary
  directories.
- Should the 80 `~/.claude` memories (bare dotfiles repository) later get the
  same treatment? They are out of scope here, and a separate decision.
- Stray `pytest-of-bob` project directories exist under `~/.claude/projects`
  (`…test_cli_clean_exit_for_ordina0-{home--claude,myrepo}`, runs 718–725).
  Some test suite writes into the real Claude projects directory. No source
  matched the name under `~/git/src`, so the origin is unknown. This is
  separate debt, not part of this feature.

## Discovery Log

### Q1: 28 of 29 buvis repositories are public. Which exposure policy applies to repository memory?
**Answer**: Public-safe rule. Repository memory holds only content that may be
public, the same bar as `docs/dev/project-management/`. Personal, host, and
secret facts stay in host-global memory. The writer and Engram validation refuse
obvious secrets.

### Inferred (not asked; derived from rules, code, or documentation)

- Path: the working-documents rule puts durable project records under
  `docs/dev/project-management/`, so memory goes to `…/memory/`.
- Authorship and time come from Git commits (idea review notes, 2026-11-04);
  only `source` and `evidence` are new fields.
- Host wiring: official documentation (fetched 2026-11-10) confirms that Codex
  and Copilot CLI read the repository's `AGENTS.md`. Claude supports the
  `autoMemoryDirectory` and `autoMemoryEnabled` settings, and `MEMORY.md` loads
  its first 200 lines or 25 KB. Native Codex and Copilot memory could not be
  verified.
- Migration push approval: under the standing authorization, publishing to
  others needs approval, so R11 has a single batch gate, not a design question.
- The scope of non-repository memory follows from the census: 136 files have no
  repository to own them.
