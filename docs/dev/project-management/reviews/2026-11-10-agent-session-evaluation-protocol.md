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

## Recall probe (2026-11-12)

Result: **no recall lever clears the bar**. The adoption decision stays `fix
retrieval first`. Best: 12 of 24 (50.0%, Wilson 31% to 69%), from a pool without
transcripts and findings plus the 0.6B reranker. The bar needs 17.

| Pool (RRF) | Chunks, median | Label in pool | Top-3 fused | Top-3 reranked | Reranked median / p95 |
|---|---|---|---|---|---|
| production: AND 20 + dense 20 | 20 | 13 | 10 | - | - |
| OR 20 + dense 20 | 35 | 13 | 10 | 11 | 1.07 / 1.28 s |
| OR 100 + dense 100 | 182 | 18 | 10 | 11 | 4.27 / 5.65 s |
| OR 100 + dense 100 + identifiers 20 | 188.5 | 19 | 10 | 11 | 4.37 / 5.70 s |
| quiet: OR 20 + dense 20 | 36 | 13 | 9 | 12 | 1.08 / 1.30 s |
| quiet: OR 20 + dense 20 + identifiers 20 | 45 | 14 | 10 | 12 | 1.27 / 1.48 s |
| quiet: OR 50 + dense 50 + identifiers 20 | 96.5 | 18 | 10 | 11 | 2.22 / 2.71 s |
| quiet: OR 100 + dense 100 + identifiers 20 | 186.5 | 19 | 10 | 11 | 3.92 / 4.72 s |

"Quiet" drops transcript and findings chunks from every leg. "Identifiers" is a
lexical OR leg over the question's code-like tokens only. Fused retrieval took
0.36 s median. The production row reproduces the baseline (10 of 24, MRR 0.310,
same 14 misses).

- A wider pool raises the label count in the pool from 13 to 18 or 19, but the
  reranker does not lift those labels into the top 3.
- Production's lexical leg returned no rows for 18 of 24 questions and never
  returned a label. It needs every token of the question in one chunk.
- Transcripts and findings fill up to 19 of the 20 dense slots. No label lives
  there, by construction: a label is a file the agent read.
- Q1, Q6, Q17, S7 and S8 have no label in the widest pool. Q17, S7 and S8 have
  none within 500 chunks of any leg.
- Two causes sit outside ranking. Code chunks cover functions and classes only,
  so module-level text (imports, constants) is not indexed: 7% to 24% of four
  label files. And for Q17 and S7 the label files do not contain the
  identifiers the question names (live files, 2026-11-12), so the "file read
  next" label rule marks some good answers as misses.
- Coverage: of about 469 bursts settled outside the index, about 145 ended on
  throwaway files, about 133 on worktree or plugin-cache copies of indexed
  sources, and the rest on real gaps (unindexed project-management folders,
  `~/.config/herdr-app`, `~/.claude`, the notes vault, other repository files).
  This tally takes the first settled file of each burst and is approximate.

Limits: fifteen variants on 24 questions is a multiple comparison; one or two
questions separate them. The set is development data from here on. Nothing
tuned on it may set the adoption decision; that needs a fresh mined set.

Method: `eval/agent_session_recall.py`. Same questions, labels, pool copy,
leakage exclusion and metrics. Question, pool and config hashes were checked
against `freeze.json`. Per-question ranks by id:
`eval/results-agent-session-recall.json`. Follow-up: intake
`00013-engram-agent-question-recall`.

## Second set: relevance measure (fixed 2026-11-12, before any scoring)

User decision 2026-11-12: judge the top 3 for relevance on a fresh mined set,
and keep the pass threshold. This replaces exact-file match as the rule that
sets the adoption decision. The first set stays as development data.

- **Source.** Tool calls made from 2026-10-01 to 2026-10-31 (UTC) in Claude
  sessions that the first set did not use. Only 5 sessions since the first
  sample hold a usable burst, too few for a set. Miner:
  `eval/agent_session_mine.py` (the first miner was never committed; this one
  follows the same burst rule and may differ in detail).
- **Collection.** Steps 2 to 7 above, unchanged: a settled file inside the
  pool is required, one question per session, no project above a third.
  Questions and classes are written before any Engram run.
- **Pool.** The first set's frozen copy of the production index (2026-11-10).
- **Time rule.** The pool holds material written after an October question.
  Drop the question's own transcript, and every transcript that started after
  the burst or whose start cannot be read. PRDs, findings, memory and code
  cannot be dated per chunk; that leak is a stated limit.
- **System.** Production `query()`, portfolio scope, `k=60`, chunks
  deduplicated to files, top 3 after the time rule.
- **Judge.** A model judge in a separate context sees the question, the
  agent's stated intent, the settled files, and each hit's path, heading and
  chunk text. It does not see ranks from other runs. A hit is `useful` when
  reading it would have answered the question or pointed straight at the file
  that does; otherwise `not`. A hit on a settled file is `useful` without
  judging. A question passes when at least one of its top 3 is `useful`.
- **Spot check.** The user reviews 10 judged questions drawn with seed
  20261112. More than 2 disagreements voids the judged result.
- **Threshold.** Unchanged: pass rate of at least 60% with the 95% Wilson
  lower bound above 50%. The `Adoption decision:` line changes only after the
  spot check.
- **No tuning.** Retrieval fixes (intake 00013) are chosen from the first set
  only. If production fails here, the built fixes are scored on this set once.

## Second set results (2026-11-13)

Result: **production passes the judged measure, pending the user's spot
check**. 36 of 44 questions have a useful hit in the top 3 (81.8%, 95% Wilson
interval 68% to 90%). The bar is 60% with a lower bound above 50%. The
`Adoption decision:` line is unchanged until the spot check is done.

| Metric | Value |
|---|---|
| Scored questions | 44 (11 project directories; largest 11) |
| Questions with a useful hit in the top 3 | 36 / 44 = 81.8% (Wilson 68% to 90%) |
| Questions with a settled file in the top 3 (old measure) | 10 / 44 = 22.7% |
| Useful hits of hits shown | 63 / 131 |
| By class (passed / questions) | identifier 23/27, cross-repo 11/15, decision 2/2 |
| Failed | R5, R7, R11, R13, R29, R31, R34, R36 |

- **Sample.** 850 bursts in 1,055 scanned sessions; 224 bursts in 126 sessions
  settled on an indexed file. Writers kept 44 sessions and dropped 82 (74
  `known-file`, 8 too thin to state). The project cap dropped none. No
  `history` question came out, so that class is untested here.
- **Time rule.** 149 transcript hits were dropped. Useful hits by corpus, per
  question: code 28, PRD 8, findings 6, transcripts 3, memory 2.
- **Leak sensitivity.** Six passes rest only on PRD or findings hits, which
  cannot be dated (R1, R16, R20, R23, R26, R33). If all six were leaks, the
  result would be 30 of 44 (68.2%, Wilson 53% to 80%), which still passes.
- **The two measures differ widely.** Exact match gives 23% on this set and the
  judge gives 82%. Either the label rule understates relevance a great deal, or
  the judge is lenient. The spot check decides which.
- **Judge.** Three isolated contexts of the session model (Claude Fable 5.2),
  one per third of the set, with the rubric above. One model family; no second
  family judged. Writers flagged three kept questions as borderline (intent was
  boilerplate); they were kept, since removing them after the fact would be
  selection by hand.
- **Spot check.** `eval.agent_session_relevance spot` writes the 10 seeded
  questions to the private `spot-check.md`. All 10 drawn are judged passes, so
  the check tests leniency, not strictness.

Method: `eval/agent_session_mine.py` (bursts), `eval/agent_session_relevance.py`
(assemble, hits, score, spot). Question, pool and config hashes are in the
private `freeze.json`. Per-question counts by id:
`eval/results-agent-session-relevance.json`.
