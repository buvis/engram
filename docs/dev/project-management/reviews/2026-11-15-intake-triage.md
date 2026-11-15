# Intake triage — 2026-11-15

Processed the three unspecced intake ideas against current source and the recorded
experiments. This is requirements work; no production implementation, index,
model, server, benchmark rerun or adoption-gate change was performed.

## Dispositions

| Intake | Outcome | Evidence / next action |
|---|---|---|
| [00008](../intake/new/00008-engram-qwen3-embedding-and-reranking/discovery.md) | Deferred, discovery recorded | Reranking adds one exact-file top-3 hit on the 24-question agent set; no paired relevance or simultaneous-serving case for adoption. Reopen with fresh questions and a predeclared gain/latency rule. Embedding migration remains unproven. |
| [00009](../intake/new/00009-engram-fusion-tie-break-and-lexical-or/discovery.md) | Deferred, discovery recorded | OR gains did not reproduce consistently outside development. Reuse existing comparison variants; do not add public flags or change shared defaults merely to evaluate them. |
| [00013](../intake/processed/00013-engram-agent-question-recall/discovery.md) | [Backlog PRD 00013](../prds/backlog/00013-engram-module-context-v1.md) | Index source outside emitted symbols, preserve name lookup and incremental caches. Other candidate work remains in its discovery's ownership table. |

Deferred ideas remain in `intake/new`: lifecycle rules reserve `processed` for
items with a spec. Their status lines distinguish deferred discovery from unread
intake. Only 00013 moved. No new PRD numbers were allocated, and no work was lost
from its larger original proposal.

## Evidence checked

- Current `src/engram/query.py`: lexical-first insertion into equal-weight RRF.
- Current `src/engram/store.py`: AND-joined quoted tokens; name lookup considers
  all code headings; source/hash/ordinal uniqueness and cached-empty sources.
- Current `src/engram/symbols.py` and `src/engram/indexer.py`: emitted structure
  spans, unchanged-source skips, empty cache and existing anonymous migration.
- Temporary fixture: `import os`, `LIMIT = 10`, a function at lines 4–5 and a
  trailing table produce only that function chunk. Imports/constants alone
  produce zero chunks. Probe used the installed project parser, no model/index.
- `eval/results-agent-session-variants.json`: production and both OR variants
  score 10/24 top-3, 11/24 top-5; reranking reaches 11/24 top-3.
- [File-held-out probe](2026-11-05-probe-heldout.md): OR hit5 gains coexist with
  file-MRR losses; the sample is small and source-authored.
- [Agent-session protocol](2026-11-10-agent-session-evaluation-protocol.md):
  production useful-hit result 36/44, all ten user spot checks agreed,
  adoption decision proceed. Historical bias/leak caveats remain in that record.
- `prds/done/00012-agent-recall-surfaces-v1.md` and current MCP/nudge source:
  the adoption feature is shipped, so the old split/gate question is obsolete.

## Discovery review

Applied the review-discovery-doc five lenses to all three comprehensive discovery
documents. Routine decisions were adjudicated under the user's standing
authorization; no new user answers or independent reviewers are claimed.

| Lens | Result |
|---|---|
| Completeness | Requirements, scope, constraints, code context, alternatives, risks, success criteria, logs and remaining questions are present. Each original 00013 candidate has an owner/disposition. |
| Coherence | Adoption is already resolved; evidence-gathering conditions in 00008/00009 are not unattended build tasks. PRD 00013 claims coverage only for processed sources. |
| Integrity | Source slices and lookup/cache effects have observable tests. The historical adoption threshold is explicitly not an incremental-improvement threshold. |
| Feasibility | Local fixture confirms the coverage defect. Preserve cached-empty and unchanged records rather than silently scheduling portfolio re-embedding. Reranking and broad source expansion remain separate. |
| Evolvability | Existing Chunk shape and parser outputs remain; reserved context type leaves real module symbols available to lookup. No premature public tuning API or model-service dependency. |

One review finding was resolved: the draft's generic module type could overlap
with a genuine parser symbol kind. The discovery and PRD now reserve
module_context and require name lookup to exclude only that type. The local
choice is labeled as agent-selected, not a previous user decision. No blocking
findings remain in the promoted slice; the two deferred items retain their
explicit measurement questions. No review lens was skipped.

## Specification checks

- Used create-prd's standard template: all required headings, module mapping,
  dependency layers, three phases and headless acceptance commands.
- Guess-density gate: no unresolved contract markers or build-blocking questions.
- Model floor: opus, because existing symbol output must remain equivalent while
  new span and lookup behavior is added; this is not a mechanical transcription.
- Grounding gate passed with zero blocking and zero unverified claims. An initial
  false positive treated the prose word backfill as a symbol; prose quoting fixes
  it without waiving a real code reference.
- No source/tests changed, so implementation suites were not rerun. The scoped
  fixture probe verified the premise; document links, numbering, template order
  and whitespace are checked separately.

## Remaining questions

00008 and 00009 need predeclared gain/regression/latency rules and fresh usage
evidence before promotion. Portfolio backfill and the other 00013 candidates
remain separate follow-ups. None blocks implementing PRD 00013 through the
normal autopilot workflow and its required fresh-session completion review.
