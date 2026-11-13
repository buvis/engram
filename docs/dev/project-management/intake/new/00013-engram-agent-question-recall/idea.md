# engram: recall for agent questions, and a measure that can show it

Status: new. Recorded 2026-11-12. Evidence:
`reviews/2026-11-10-agent-session-evaluation-protocol.md`, section "Recall
probe (2026-11-12)"; runner `eval/agent_session_recall.py`.

## Problem

PRD 00012 waits for `Adoption decision: proceed`. That needs 17 of 24 agent
questions with a label file in the top 3. Production gets 10. Fusion and
reranking (intakes 00008, 00009) get 11. This intake was meant to close the gap
with a wider pool, query rewriting and more sources. The probe shows those
levers do not close it either, and shows why.

## What the probe found

1. **A wider pool finds more labels but does not rank them.** At 100 chunks per
   leg the label is among the candidates for 18 of 24 (13 at 20 per leg). The
   0.6B reranker still puts only 11 in the top 3, and takes about 4 s.
2. **An identifier-only lexical leg adds one candidate and no top-3 hit.**
3. **Dropping transcripts and findings is the best lever measured: 12 of 24**
   with the reranker, at about 1.1 s. No label lives in those corpora, and they
   take up to 19 of the 20 dense slots.
4. **The production lexical leg does nothing here.** It requires every token,
   returned no rows for 18 of 24 questions, and never returned a label.
   Production is dense-only for natural-language questions.
5. **Module-level code is not indexed.** `symbols.chunk` emits functions and
   classes only. Imports, constants and tables are missing: 7% to 24% of the
   text of four label files (indexed characters against live file size). "Who
   imports X" and "where is CONST defined" cannot hit.
6. **Some labels do not hold the answer.** A label is the file the agent read
   next. For Q17 and S7 no label file contains the identifiers the question
   names (checked against the live files on 2026-11-12, two days after the pool
   copy). Five questions (Q1, Q6, Q17, S7, S8) have no label in the widest pool
   tested, so 19 is the ceiling for any reranker over it; Q17, S7 and S8 have
   none within 500 chunks of any leg. Exact-file match understates relevance by
   an unknown amount.
7. **Coverage.** About 469 of 604 settled bursts ended outside the index.
   Roughly 145 were throwaway files (scratch, `docs/dev/tmp`, autopilot state).
   Roughly 133 were copies of indexed sources (worktrees 75, plugin cache 58).
   The rest are real gaps: unindexed project-management folders (designs,
   reviews, meta, audit-results, specs: about 40), `~/.config/herdr-app` (35),
   `~/.claude` skills, rules and hooks (18), the notes vault (16), and other
   repository files such as `.rst`, `.toml` and loose Markdown (about 50).

## Candidate work, in order of evidence

1. Index module-level code (one chunk per file for what lies outside symbols).
2. Give the lexical leg OR semantics (intake 00009 already asks for this).
3. A default scope for file-seeking queries that leaves out transcripts and
   findings, or a per-corpus quota. The nudge is the first caller.
4. Map worktree and plugin-cache paths to their indexed source, in scoring and
   in the nudge's "already seen" filter.
5. Index the missing project-management folders, then decide on dotfiles and
   `~/.claude`.
6. Reranking with a wider pool only if a later set shows it pays for 4 s.

## Questions for discovery

1. Resolved 2026-11-12 (user): judge the top 3 for relevance on a fresh mined
   set, with a human spot check; the 60% bar stays. Rules are in the
   protocol, section "Second set: relevance measure".
2. The 24 questions are development data. The second set (October sessions)
   sets the adoption decision; fixes are not tuned on it.
3. Does a file-seeking scope belong in `query()`, or only in `engram nudge`?
4. Does a module-level chunk need a full rebuild of the code corpus, or can it
   land incrementally? A complete rebuild needs explicit authorization.
5. Should PRD 00012 split, so `engram mcp` (a tool the agent chooses to call)
   ships while the nudge stays gated?

## Out of scope

Embedding model change (intake 00008). Changing the pass threshold without a
user decision.
