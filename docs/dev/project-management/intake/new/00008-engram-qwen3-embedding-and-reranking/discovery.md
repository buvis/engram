# Discovery: Evidence required before adding reranking

## Classification

Depth: comprehensive | Date: 2026-11-15
Source: `idea.md` beside this file.
Disposition: deferred; no implementation PRD. Revisit on the evidence below.

## Problem

The original embedding proposal became a reranking proposal after fusion probes
explained much of the apparent model advantage. The development set supports
passage reranking, but the agent-session experiment adds only one top-3 file hit
(10 to 11 of 24). Production subsequently passed a different, user-approved
relevance measure without reranking: 36 of 44, with agreement on all ten human
spot checks. Neither this pass nor the earlier exact-file miss rate establishes
the incremental benefit of reranking on the relevance measure.

## Requirements

### Must have before promotion

- R1: Compare the current production baseline with BGE-M3 plus the already
  evaluated Qwen3 Reranker 0.6B on freshly frozen agent questions. Preserve
  per-question results, candidate pools, source/config hashes and provenance.
- R2: Use the relevance rubric from
  `../../../reviews/2026-11-10-agent-session-evaluation-protocol.md`.
  Keep exact-file and passage scores as diagnostics. Include transcript and
  findings questions and passage labels before making claims about those corpora.
- R3: Measure warm simultaneous serving, median/p95 end-to-end latency and
  unavailable-server behavior. Earlier sequential probes do not measure these.
- R4: Before collecting adoption evidence, set the minimum useful-hit gain and
  acceptable latency overhead. The existing 60% adoption threshold is a baseline
  adequacy test, not a reranker improvement threshold.
- R5: An embedding migration needs separate evidence against the current pin,
  plus a separately authorized migration. Equal scores keep BGE-M3.

### Out of scope

Production reranker plumbing, extra persistent services, model downloads,
embedding repinning, rebuilds, and a broader model tournament in this intake pass.

## Constraints

The 55-question campaign, ten source-authored questions, 24 agent questions,
and inspected 44-question adoption set are historical evidence, not fresh
held-out tuning targets. Preserve their labels and results. The 2026-11-15
adoption decision remains `proceed`.

## Codebase Context

- `src/engram/query.py` fuses lexical and dense results without a reranker.
- `src/engram/client.py` manages embedding identity and serving; it does not
  provide production reranker serving.
- `eval/agent_session_variants.py`, `eval/agent_session_recall.py` and
  `eval/agent_session_relevance.py` provide the existing experiment and rubric
  machinery. Reuse these before inventing another harness.
- `eval/results-agent-session-variants.json`: production median 0.192 s;
  production plus 0.6B reranking 0.610 s; top-3 exact-file hits 10 versus 11.
- `../../../reviews/2026-11-03-probe-rerank-fixed.md` and
  `../../../reviews/2026-11-05-probe-heldout.md` record the stronger passage
  results and their sampling/serving limitations.

## Approach

Defer implementation. Reopen when real usage identifies unresolved ranking
misses and a predeclared comparison budget can test them. Lead with 0.6B because
the existing 4B experiment was slower and no better; this is experiment selection,
not a universal claim about either model. Do not switch embeddings: equal
reranked scores supply no migration benefit. Do not combine this with 00009 or
00013: independently measure each change before testing combinations.

## Success Criteria

Promotion requires a dated protocol containing R1–R4, frozen inputs and a report
of paired gains/losses, corpus detail, latency and failure behavior. A negative
result is a valid experiment outcome. No implementation PRD is ready while its
benefit/latency decision rule is unresolved.

## Risks

- Development-set overfitting: obtain fresh questions before a new adoption claim.
- Poor labels: retain the approved relevance rubric and a human calibration step
  in the attended experiment, outside an unattended build PRD.
- Extra serving cost: measure simultaneous warm operation, not sequential loads.

## Discovery Log

- The user asked to process the intake; no production migration was requested.
- Prior decision, 2026-11-12: relevance judging with a human spot check and the
  existing 60% bar. Prior confirmation, 2026-11-15: all ten spot checks agreed.
- Agent disposition under standing authorization: defer because the current
  evidence does not justify the added serving dependency. This is not a user
  rejection of reranking.
- Scope, integration, constraints, priority, reuse and risks follow from the
  code and recorded probes; no repeated preference questions were needed.

## Open Questions

- On reopening: what minimum paired useful-hit gain warrants what warm median
  and p95 latency overhead? Resolve before freezing a new comparison.
- Which real usage misses justify the next sample, especially history/findings?
