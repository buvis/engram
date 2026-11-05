# File-held-out probe — 2026-11-05

## Source drift investigation

Cellar commit `ba64775ddd1e25c3628e0a416496e30bccc41780` (November 3,
22:58:49 CET, `chore: sync`) deleted all 300 lines of transcript
`5a656567-eccb-474e-833a-8ca6a7601e5a.jsonl`. Its earlier addition is in
`af971bbce`. Searches by session UUID in cellar and live Claude projects found
no relocated copy. This establishes deletion from the synced tree; the underlying
pruning mechanism was not investigated. The frozen campaign retains this source.
No historical gold label was changed and no replacement is proposed here.
The live gold-set test still fails, intentionally exposing source availability.

## Method and limits

`eval/probe_heldout.py` samples two eligible chunks per available corpus using
seed 20261105 from frozen snapshot `fc9bf2e6e0038153` (113,258 chunks).
Eligibility: a target file outside the 55 development targets and body length
151–3499 characters. Ten questions were authored by Codex from these passages
before scoring. Ten exact-start passage labels cover two each of code, memory,
PRD, discovery, and transcripts. No decision file remains outside development
targets. Zero independently sourced human questions; no cross-corpus evaluation.
These hold out target files, not authors, topics, or development-informed design.
The tiny convenience sample is exploratory evidence, not a statistical gate.
Only one passage start is accepted per question; useful alternative passages and
files receive no credit. Source-guided questions may favour explicit terminology.

The private freeze contains the selected source bodies and labels at
`~/.cache/engram/compare/heldout-20261105.json`. Its hash and the full source
snapshot hash are recorded in `eval/probe-heldout.json`. Exclusive creation
prevents overwriting the freeze. No questions or labels were tuned after scoring.
The full snapshot and read-only BGE-M3 index supply the frozen distractor pool.
No live source reads or production index access are needed by this probe.

Before new scoring, all 55 development candidate lists reproduced exact order
and membership, and every original embedding metric reproduced within 0.0005.
This is an embedding/retrieval baseline gate; the reranker uses a relevance
sanity check rather than repeating its historical 55-question baseline here.
BGE-M3 Q8 embeddings and Qwen3 Reranker 0.6B Q8 run sequentially on port 18181.
The four fusion variants, 20 candidates per leg, and 8,000-character heading /
full-path / body reranker framing match the preceding probe. No tuning was done.
Metrics use strict chunk ranks. Query latency excludes startup, fusion and
serialization; OR includes the extra AND lookup. This does not measure persistent
simultaneous serving, memory pressure, or down-server fallback.

## Results

| Stage | Fusion | File hit5 | File MRR | Passage hit5 | Passage MRR | Median total s |
|---|---|---:|---:|---:|---:|---:|
| fusion | rrf_prod_order_20_20 | 8/10 | 0.811 | 5/10 | 0.514 | 0.027 |
| fusion | rrf_prod_20_20 | 8/10 | 0.811 | 5/10 | 0.514 | 0.027 |
| fusion | rrf_bm25or_20_20 | 9/10 | 0.764 | 6/10 | 0.534 | 0.051 |
| fusion | rrf_bm25or_20_20_dense2x | 9/10 | 0.804 | 6/10 | 0.524 | 0.051 |
| reranked | rrf_prod_order_20_20 | 9/10 | 0.770 | 6/10 | 0.550 | 0.595 |
| reranked | rrf_prod_20_20 | 9/10 | 0.770 | 6/10 | 0.550 | 0.590 |
| reranked | rrf_bm25or_20_20 | 10/10 | 0.870 | 7/10 | 0.650 | 1.137 |
| reranked | rrf_bm25or_20_20_dense2x | 10/10 | 0.870 | 7/10 | 0.650 | 1.177 |

### Corpus detail: OR, dense weight 2, before → after reranking

Each corpus has two questions and two passage labels.

| Corpus | File hit5 | File MRR | Passage hit5 | Passage MRR |
|---|---:|---:|---:|---:|
| code | 2→2/2 | 0.750→0.600 | 1→1/2 | 0.500→0.500 |
| discovery | 2→2/2 | 1.000→1.000 | 1→1/2 | 0.500→0.500 |
| memory | 2→2/2 | 1.000→0.750 | 2→2/2 | 1.000→0.750 |
| prd | 1→2/2 | 0.522→1.000 | 1→2/2 | 0.522→1.000 |
| transcripts | 2→2/2 | 0.750→1.000 | 1→1/2 | 0.100→0.500 |

OR alone improves file hit5 8→9/10 but file MRR falls .811→.764 (1x) or .804
(2x). Dense-first tie ordering alone changes no scores. Thus the earlier large
fusion MRR gain does not reproduce on this sample. OR plus reranking reaches
10/10 file hit5 and 7/10 passage hit5, file/passage MRR .870/.650. Both weights
reach the same reranked scores. Code and memory file MRR regress after reranking.
Transcript passage hit5 remains 1/2, despite file hit5 2/2; the stronger historical
file results must not be described as solved transcript passage retrieval.

Keep fusion and reranking separate. This set supports further evaluation of
reranking after fusion, not adoption, a weight choice, or an embedding switch.
Independent human questions, broader transcript labels, and exact-identifier
regressions remain necessary. Persistent latency/fallback and full-snapshot
Qwen3-0.6B embeddings remain later probes.

## Verification

All 40 private reranked lists were independently rescored against frozen labels
and match the public artifact. Source and label hashes match. Formatting and
import sorting occurred during the run before the recorded source digest; no
retrieval, question, label, or inference logic changed during measurement.
Eval suite: 30 passed. Main suite: 467 passed, one known missing-source failure.
Isolated Ruff E4/E7/E9/F/I and `git diff --check` pass.
Production source, historical labels, backlog 00005–00007 and config were not
edited. Config MD5 remains `73b87ee352f490f92470b4e19edb173a`.
No rebuild or index command ran. Port 18181 is free; user servers on 8002,
8081 and 8083 remain listening. No production-database byte identity is claimed.
