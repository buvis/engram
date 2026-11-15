# Discovery: Fusion and lexical matching need a new comparison

## Classification

Depth: comprehensive | Date: 2026-11-15
Source: `idea.md` beside this file.
Disposition: deferred; no production-change PRD.

## Problem

Lexical matching requires every whitespace-separated query token, and equal RRF
scores inherit lexical-first insertion order. Both observations remain true in
the current source. Calling both quality defects overstates the evidence:
the development gains did not reproduce consistently on other samples. The ten
file-held-out questions gained one hit5 but lost file MRR with OR; on the 24
agent questions, neither tested OR weight improved top-3 or top-5 file hits.
Production already passed the later relevance-based adoption check.

## Requirements

### Must have before promotion

- R1: Compare unchanged production, dense-first tie ordering alone, OR with
  equal weights, and OR with double dense weight as separate fixed variants.
  Keep the existing 20-candidate legs and RRF constant 60 during this comparison.
- R2: Freeze fresh agent questions, source pools and the relevance rubric before
  scoring. Record paired useful-hit gains/losses, exact-file diagnostics,
  per-corpus results and latency. Do not select a winner from the old 55 queries.
- R3: Add exact-identifier regressions and caller coverage for query, pack, MCP
  and nudge. Preserve repository/corpus/exclusion filters and literal token
  quoting, including quotes and FTS operator-looking input.
- R4: Specify an explicit tie policy and any lexical/default changes only after
  the comparison. Preserve a report of losing variants, not just aggregate gains.

### Out of scope

Reranking, embedding changes, index rebuilds, stop-word heuristics, query
rewriting and new public tuning flags in the current intake pass.

## Constraints

The original 24 questions are development data. The inspected 44-question set
remains the historical adoption record; it is not fresh held-out evidence for
selecting fusion defaults. Do not alter its scores or close the adoption gate.
Intake 00008 owns reranking; PRD 00013 owns code coverage.

## Codebase Context

- `src/engram/store.py`, `Store.search_bm25`: quoted whitespace tokens joined
  by spaces, with shared scope conditions and parameterized SQL.
- `src/engram/query.py`, `query`: equal-weight RRF, lexical insertion before
  dense insertion, stable score-only sorting.
- `src/engram/pack.py` calls query directly. `src/engram/mcp_server.py`
  shares search with CLI and nudge; a default change reaches all these callers.
- `eval/probe_fusion.py` and `eval/agent_session_variants.py` already implement
  comparison variants; no production option is needed merely to evaluate them.
- Evidence: `../../../reviews/2026-11-05-probe-heldout.md` and
  `eval/results-agent-session-variants.json`.

## Approach

Keep production unchanged and defer a default-change PRD. Reuse the experiment
variants when actual usage supplies new failures. Reject adopting OR/2x from the
55-question score: it ties production top-3/top-5 on the agent set. Reject adding
configuration flags now: they create a supported interface before a caller needs
one. Deterministic tie behavior can be specified separately if reproducibility
becomes the concrete problem; dense-first preference alone is not proof of
greater relevance.

## Success Criteria

A future promotion has frozen inputs, a paired relevance report, literal-query
regression results, a declared latency budget and a selected tie/lexical policy.
The minimum improvement rule is fixed before scoring. A no-change verdict is
valid; neither a ranking default nor a dense weight is selected in this pass.

## Risks

- OR admits common-token noise: include natural-language and identifier cases.
- Shared query callers regress together: evaluate their query shapes separately.
- Optimizing exact-file match repeats the old measurement error: useful-hit
  relevance is primary; exact-file diagnostics remain visible.

## Discovery Log

- Brownfield analysis confirms the mechanics but not the original universal
  quality claim. Newer evidence takes precedence over the idea's initial title.
- Agent disposition: defer rather than ship an unproven shared default change.
  This is a reversible prioritization decision under standing authorization.
- Existing code answers integration/reuse questions. The recorded user decision
  answers measurement choice. There is no remaining adoption blocker to fix.

## Open Questions

- On reopening: what paired relevance improvement and per-caller regression
  allowance justify changing the shared default? Predeclare before scoring.
