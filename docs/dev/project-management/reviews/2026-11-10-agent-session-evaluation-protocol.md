# Agent-session evaluation protocol

Status: scored 2026-11-10 (see Results). Replaces human-question collection
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

Adoption decision: fix retrieval first (measured top-3 file hit rate 41.7%, 10 of 24, 95% Wilson interval 24% to 61%)

The line above is machine-read: PRD 00012's `eligibility` check passes only
when it reads `Adoption decision: proceed`. Change it when scoring is reported,
to `proceed` or to `fix retrieval first`, with the measured hit rate beside it.

Pass threshold (fixed by the user 2026-11-10, before any scoring): "usually
relevant" means top-3 file hit rate of at least 60% on scored questions, with
the 95% Wilson lower bound above 50%. Otherwise `fix retrieval first`.

If top-3 hits are usually relevant, proceed with orchestrator injection
(agent-plugins intake 00066) and the Engram plugin
(`../spikes/engram-plugin/`). If not, fix retrieval first (intakes 00008 and
00009); pushing weak hits into every prompt teaches agents to ignore them.

## Results (2026-11-10)

Result: **fix retrieval first**. Top-3 file hit rate 10 of 24 (41.7%); the
95% Wilson interval is 24% to 61%. The threshold needed at least 60% with a
lower bound above 50%, which at n=24 means 17 hits. The upper end of the
interval (61%) barely reaches the 60% bar. Scores are in `eval/results-agent-sessions.json`
(per-question ranks by id, no question text). Tool: `eval/agent_session_eval.py`.

| Metric | Value |
|---|---|
| Scored questions | 24 (13 projects; largest project 4) |
| Top-3 file hit rate | 10 / 24 = 41.7% (Wilson 24% to 61%) |
| Top-5 file hit rate | 11 / 24 = 45.8% (Wilson 28% to 65%) |
| MRR | 0.310 |
| Median search calls the agent spent | 3.5 |
| Questions with no label file in the top 60 chunks | 11 of 24 |

By class (top-3 hits / questions): identifier 8/16, cross-repo 1/4, decision
1/3, history 0/1. By answer corpus: code-answer questions 9/19, PRD or
discovery-answer questions 1/4 (Q1 has a mixed code and PRD label and missed).
Top-3 hits: 9 from the `code` corpus, 1 from `prd`; S1 (`prd`) came at rank 5.
No label sat in transcripts, memory or decision, so those corpora are untested
here.

Top-3 misses (14): Q1, Q2, Q6, Q10, Q13, Q15, Q16, Q17, S1, S2, S4, S7, S8, S9.
Eleven found no label file in the top 60 chunks (Q1, Q2, Q6, Q13, Q16, Q17,
S2, S4, S7, S8, S9). Q10 (rank 7), Q15 (rank 10) and S1 (rank 5) found the
label late.

Leakage: for 15 of 24 questions the question's own session transcript sat in
the unfiltered top 5. It was excluded before ranking, as the protocol requires.
Excluding it did not change the top-3 count (10 either way) but moved several
hits up a rank.

### Sample and method

- Source: 642 search bursts (three or more search calls within six tool
  calls) in 179 of 386 eligible Claude sessions modified since 2026-11-01.
  Seed 20261110. This repository's sessions, test temp dirs and live-probe
  dirs were excluded. 38 bursts had no later read or edit (`unresolved`).
- 136 bursts settled on at least one file inside the indexed pool. The other
  468 (604 minus 136) settled only on files outside it, mostly the installed
  plugin cache, notes vault, scratch files and ledgers: `outside-corpora`,
  neither scored nor classified one by one.
- Of the 136, 24 became scored questions. The rest were `known-file` lookups
  (the agent already worked inside the file), repeats from a session already
  used, or intent too thin to state as a question. I did not tally the split by
  reason, so the dropped share by reason is not reported. Classes of the 24:
  identifier 16, cross-repo 4, decision 3, history 1.
- Questions use the agent's or user's stated words where present; otherwise the
  command description. Labels are the in-pool files the agent read or edited
  next. They were written before any Engram run.
- Pool: a `sqlite3 .backup` copy of the production index taken 2026-11-10
  (not the November 1 campaign snapshot, which predates these sessions).
  Production was only read. All labels existed in the copy before freezing.
- Retrieval: production `engram.query.query`, portfolio scope, no corpus
  filter, pinned bge-m3 Q8 on the running server at port 8083, 60 fused
  chunks deduplicated to files. No reranker. Questions, copy, config, script
  and git head are frozen by SHA-256 in the private `freeze.json`.

### Limits

- n=24 is below the 30 to 50 target. The remaining bursts were in-task code
  navigation without a clear question, and I did not pad the set.
- Selection requires a settled file in the pool. That removes cases where
  Engram could not help at all, so the rate is not biased against it, but it
  also means 468 of 604 settled bursts were out of reach of the current
  corpora. That is a coverage gap, not a ranking result.
- Labels are what the agent happened to read. Other files may also answer the
  question, so hit rates are conservative. The five human questions were not
  scored (still secondary).
- S3 and S4 come from one session; Q8 and Q9 share one label file.
- Wording of some questions mixes the agent's intent with its command text.
  Long natural-language questions may lose under production's AND-matched
  lexical leg (the November campaign tested OR as a variant). That is a
  candidate cause, not tested here.

### Next step

Per the decision rule: do not start PRD 00012. Retrieval work goes to intakes
00008 (reranking) and 00009 (fusion). The earlier campaign found OR-lexical
fusion and the Qwen3 reranker helped on gold questions; rerun this frozen set
with those variants before choosing, since the questions and pool are now fixed.

## Variant results (2026-11-10)

Result: **no variant clears the bar**. The adoption decision stays `fix
retrieval first`. The best variant, production fusion plus the Qwen3 Reranker
0.6B Q8, got 11 of 24 in the top 3 (45.8%, Wilson 28% to 65%). The bar needs
17 of 24.

| Variant | Top-3 | Top-5 | MRR | Median / p95 latency |
|---|---|---|---|---|
| production (AND-BM25 + dense, RRF) | 10 (41.7%, 24-61%) | 11 | 0.310 | 0.19 / 0.20 s |
| OR-BM25 + dense x1 | 10 (41.7%, 24-61%) | 11 | 0.286 | 0.26 / 0.29 s |
| OR-BM25 + dense x2 | 10 (41.7%, 24-61%) | 11 | 0.310 | 0.26 / 0.29 s |
| production + rerank 0.6B | 11 (45.8%, 28-65%) | 12 | 0.404 | 0.61 / 0.80 s |
| OR x1 + rerank 0.6B | 11 (45.8%, 28-65%) | 11 | 0.398 | 0.97 / 1.16 s |
| OR x2 + rerank 0.6B | 11 (45.8%, 28-65%) | 11 | 0.398 | 1.02 / 1.23 s |

Top-3 brackets give the hit rate and 95% Wilson interval. Latency covers query
embedding, search and reranking per question; server startup is excluded.

- The runner reproduced the baseline first: production `query()` and the reused
  `rrf_prod_order_20_20` fusion gave the same chunk order for all 24
  questions, and the score matched the earlier run (10/24, MRR 0.310, same 14
  misses).
- OR-lexical fusion recovered none of the 11 questions with no label in the
  candidates (Q1, Q2, Q6, Q13, Q16, Q17, S2, S4, S7, S8, S9). It lost Q11 from
  the top 3 and gained S1. The reranker cannot help where no label is in the
  candidates, so 13 of 24 is the ceiling for any reranker over these pools.
- On production fusion the reranker moved S1 from rank 5 to 2, Q15 from 10 to
  4 and Q11 from 2 to 1. It moved S6 from 2 to 3 and Q10 from 7 to 9 (16 on
  OR). Production plus reranker misses: Q1, Q2, Q6, Q10,
  Q13, Q15, Q16, Q17, S2, S4, S7, S8, S9.
- Six variants on 24 questions is a multiple comparison. The one-question gain
  from the reranker is a lead, not proof; its interval overlaps the baseline.
- The candidate pool is at most 40 chunks (20 per leg, `RRF_POOL` in
  `engram.query`), not 60. The Results section's "top 60 chunks" means the
  `k=60` request; production caps it at 40.

The bottleneck is recall, not order: 11 of 24 questions have no label among
the candidates under any fusion tested. The coverage gap above (468 of 604
settled bursts outside the index) is the larger limit, and no ranking variant
touches it. Transcript, memory and decision corpora stay untested here.

Method: `eval/agent_session_variants.py`. Same questions, labels, pool copy,
leakage exclusion (`file_ranks`) and metrics as the baseline. Query vectors
come from the pinned bge-m3 Q8 server on port 8083; the reranker ran on port
18181 with 8000-character documents and passed a relevance smoke check.
Inputs, runner and git head are frozen in the private `freeze_variants.json`.
Per-question ranks by id: `eval/results-agent-session-variants.json`.
