# Shared project memory in repository files

Status: intake, not yet specced. Recorded 2026-11-04.

Source: moved on 2026-11-04 from `buvis/docs` (`src/agents/components.md`,
sections "Engram" and "Shared memory") so the public reference keeps only the
decided authority model. Terms follow the
[agent operations taxonomy](https://github.com/buvis/docs/blob/master/src/agents/taxonomy.md).

Why here: Engram is the existing cross-project index. The target replaces its
Claude project memory corpus with authoritative memory files in each
Project's repository. Host-side writing (Claude, Codex, Copilot) may need a
companion item in `agent-plugins` or `agent-skills` once the file format is
fixed.

## Idea (from buvis/docs)

Decided in the reference: new memories belong to the current Project by
default, recall defaults to that Project, Engram provides cross-project recall
when a broader scope is selected, and authoritative project memories live in
version-controlled files in the Project's repository, with Git as their
revision history. An index can be rebuilt from the authoritative files and
does not become another writer of project memory.

To implement:

- Engram's documented memory corpus reads Claude project memory files. The
  target integration indexes authoritative memory files from each Project's
  repository; support for that source remains to be implemented.
- Agents write evidence-backed memories directly within their authorized
  Project scope. Each memory records its source, supporting evidence,
  authoring Agent, and creation time. Corrections create attributable
  revisions that supersede earlier content while preserving its history. A
  separate curation step is not required before a memory becomes available
  for recall.
- The file format, repository path, and host integration remain to be
  implemented. Retrieval at any scope respects the assignment's permitted
  inputs.
- Memory persists independently of the Agents that contribute it. Each fresh
  session has a new Agent identity; retained knowledge records its source and
  author without requiring that Agent to remain active.
- A durable message queue does not by itself supply a memory lifecycle.

The shared-memory contract still needs to define:

- Ownership and access rules for explicitly selected scopes beyond the
  default Project.
- File format and repository path, concurrent updates, retention, and
  deletion, including derived indexes.
- How sessions discover, read, and contribute knowledge across hosts.
- Retrieval rules for freshness, conflicting claims, sensitive material, and
  evidence permitted for each assignment.

## Review notes (2026-11-04)

- Authoring Agent, creation time, and attributable revisions are Git author,
  date, and commits. Only source and evidence are new fields.
- `~/.claude/rules/memory.md` keeps project facts in Claude auto-memory
  (`~/.claude/projects/<hash>/memory/`). That rule needs a pointer to the
  switch when this lands.
