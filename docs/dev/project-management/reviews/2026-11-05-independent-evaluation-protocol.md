# Independent-question evaluation protocol

Status: collecting. No independent questions received or scored.
Continues the [file-held-out probe](2026-11-05-probe-heldout.md).

## Collection and annotation

Collect 20–30 actual retrieval questions, starting with five to ten from the
user's work. Preserve original wording, collection time, intended repository or
portfolio scope, and message reference when available. Record whether the answer
was already sought; report previously searched questions separately.

Copy `eval/independent_questions.template.yaml` into private storage under
`~/.cache/engram/compare/`. Keep private questions and evidence outside Git.
Seek transcript incidents and exact code identifiers through natural work;
report missing coverage rather than manufacture questions to fill quotas.

Locate answers through source inspection before running candidate systems.
Record all verified acceptable files and exact chunk starts, evidence hashes,
and relevance rationales. Retain unavailable, ambiguous and unanswerable cases
in the collection ledger. Report exclusions and reasons without hiding misses.
Check overlap with both earlier sets; distinguish novel questions and targets.
Do not rewrite questions to fit sources or scores.

## Freeze and comparison

Use the existing frozen full snapshot when it contains the required evidence.
Otherwise prepare a separate evaluation-only snapshot and index. Preserve
historical labels and campaign material. Never score a question against a pool
that lacks its labelled answer.

Before inference, freeze questions, scope, exclusions, labels, full retrieval
pool, model/runtime identity, framing, probe code and variants. Retain private
copies and SHA-256 digests. Changes after scoring create development data.

Keep BGE-M3 Q8 and 20 candidates per leg. Compare production lexical-first AND,
dense-first AND, and dense-first OR at the already tested dense weights 1 and 2.
Rerank production and both OR candidate sets with Qwen3 Reranker 0.6B Q8.
Reproduce known embedding and reranker baselines before accepting new scores.
Preserve heading, full path and body within the 8,000-character reranker budget.

Honor original scope. Do not filter by the labelled answer corpus unless the
original question supplied it. Report additional corpus-filtered runs separately.
Use only port 18181, temporary server-log directories and sequential probe model
lifecycles. Open campaign indexes read-only. Preserve production configuration,
index, pin and retrieval code; leave servers on 8002, 8081 and 8083 running.

## Reporting and next decision

Report file/passage hit5 and MRR, corpus/scope breakdowns, provenance, label counts,
exclusions, individual regressions, candidate recall and latency. Retain rankings
for independent rescoring. Keep transcript and exact-identifier results visible.
Report sample size and uncertainty; one improved question is not an adoption gate.

If gains hold, measure warm persistent reranker latency and down-server fallback
in an isolated follow-up. Scope fusion and reranking separately in intakes 00009
and 00008. Production changes, rebuilds and model migration require authorization.

Unresolved input: actual user questions collected before answer search.
