# Agent-session evaluation protocol

Status: specified 2026-11-10, not started. Replaces human-question collection
as the primary independent evidence (user decision, Session 7). The
[human-question protocol](2026-11-05-independent-evaluation-protocol.md) and its
five private questions stay as a small secondary set.

## Why

Engram exists to help agents, and agents write the code. The questions that
matter are the ones agents face mid-task, not ones the user thinks up.

Measured 2026-11-10 over Claude sessions modified since 2026-11-01 (364
sessions, 40 projects, this repository excluded): 14 sessions (4%) called
Engram, all through the catch-up skill; 212 sessions ran 5,671 ad-hoc
`rg`/`grep`/`find`/`git log` searches. A pilot of 8 random sessions found 91
search bursts. Most were lookups inside a file the agent already knew, where
`rg` is right. A minority were memory questions: provenance across repositories,
what an earlier PRD decided, where an identifier is referenced.

## Collection

1. Sample sessions at random across projects, with a fixed seed. Exclude this
   repository's sessions and any session that ran after the freeze.
2. Find retrieval moments by code: three or more search calls within six tool
   calls. Keep the agent's stated intent before the burst, the commands, and
   the files it read or edited next.
3. Classify each moment (model judgment, recorded with a reason):
   `known-file` (drop: not Engram's job), `cross-repo`, `history`, `decision`,
   `identifier`. Report the class counts, including the dropped share.
4. Write the question from the agent's stated intent, in its words where it
   gave any. Do not rewrite it to fit sources or scores.
5. Label from behaviour, before any Engram run: the files the agent settled on
   (read then cited, or edited) are the acceptable targets. Record the number of
   search calls the agent spent; that is the cost Engram could save.
6. Keep a moment with no settled file as `unresolved`. Keep answers that live
   only in non-indexed sources as `outside-corpora`. Report both; score neither.
7. Target 30 to 50 scored questions, at least 5 projects, no project above a
   third of the set. Report the real distribution; do not pad it.

Questions and transcript excerpts stay private under
`~/.cache/engram/compare/agent-sessions/`. Git gets counts and methods only.

## Leakage rule

The session a question came from is itself indexed as a transcript. Exclude
that session's transcript from the pool for its own question, and report hits
on it separately. Otherwise Engram scores by finding the question, not the
answer.

## Scoring

Freeze questions, labels, pool and runtime identity first, as in the earlier
protocol (same ports, read-only indexes, production untouched).

- Primary: top-3 and top-5 file hit rate, and MRR, against the settled files.
- Cost: median search calls the agent spent per question.
- Breakdown by class and by corpus of the answer.
- Report sample size and uncertainty. List every miss.

## Decision this feeds

Adoption decision: pending

The line above is machine-read: PRD 00012's `eligibility` check passes only
when it reads `Adoption decision: proceed`. Change it when scoring is reported,
to `proceed` or to `fix retrieval first`, with the measured hit rate beside it.

If top-3 hits are usually relevant, proceed with orchestrator injection
(agent-plugins intake 00066) and the Engram plugin
(`../spikes/engram-plugin/`). If not, fix retrieval first (intakes 00008 and
00009); pushing weak hits into every prompt teaches agents to ignore them.
