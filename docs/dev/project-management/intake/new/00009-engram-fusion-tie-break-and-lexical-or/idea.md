# engram: fix rank-fusion tie-breaking and lexical AND-matching

Status: new. Recorded 2026-11-02. Evidence: `reviews/2026-11-02-probe-fusion.md`.

## Problem

Two defects in `query()` / `Store.search_bm25` depress ranking with the current
bge-m3 index, found by probing the full-snapshot indexes:

- Lexical hits are inserted before dense hits in the fusion map, so equal RRF
  scores resolve in favour of lexical noise. Dense-first order alone lifts
  BGE-M3 file MRR from 0.794 to 0.877 (transcripts 0.42 → 0.76).
- Lexical search requires every query token, so natural-language queries return
  nothing for 34 of 55 questions. With OR semantics the lexical leg reaches 0.864
  file MRR alone, and fused with dense it reaches 0.918–0.930 (above dense-only).

No embedding change, rebuild, or new server is involved.

## Reranker interaction, 2026-11-03

[Fixed-fusion probe](../../../reviews/2026-11-03-probe-rerank-fixed.md): the
0.6B reranker preserves a smaller file-ranking benefit after the fix. For BGE,
production fusion 0.794→0.979 becomes OR/1x 0.918→0.977 or OR/2x 0.930→0.977.
Only 25–32% of the old file-MRR uplift remains, supporting this as an independent
inexpensive improvement. Dense-first ordering alone leaves reranked scores
unchanged; changing the lexical leg changes the candidate set.

Fusion does not replace passage reranking: BGE OR/2x passage MRR is 0.589 and
hit5 is 6/8, rising to 0.906 and 8/8 with the 0.6B reranker. OR also expands
candidate lists (mean 20.36→31.96), almost doubling reranking median time.
Both OR weights give the same reranked metrics, so do not select a weight from
reranked scores. Qwen3-8B reaches the same reranked scores as BGE after OR.
The optional 4B trial confirms no benefit from the larger reranker: OR gives
0.976 file MRR and 0.833 passage MRR, versus 0.977/0.906 with 0.6B, at roughly
five times the combined median latency.

The baselines reproduce the campaign. Evidence remains 55 development queries
and eight passage labels: five code, three decision, none for transcripts.
Keep held-out confirmation and exact-identifier regressions in this item's
acceptance criteria; the probe neither edits production retrieval code nor opens
the production index.

## Questions for discovery

1. Confirm on held-out questions (the 55 are development data) and add transcript
   passage labels.
2. Lexical OR: plain OR, or token filtering (stop words), or BM25 weights? Does it
   hurt exact-identifier code queries?
3. Dense weight (1x vs 2x) and tie-break rule as explicit, tested behaviour.
4. Interaction with `pack`, which also calls `query()`.

## Out of scope

Embedding model change and reranking (intake 00008).

## File-held-out probe, 2026-11-05

[Probe](../../../reviews/2026-11-05-probe-heldout.md): ten agent-authored
questions on files outside the development targets, with ten exact passage
labels (two each code, memory, PRD, discovery, transcripts; no decision labels).
Zero independent human questions. OR/2x improves file hit5 8→9/10 but file MRR
falls .811→.804; dense-first alone changes no scores. OR plus 0.6B reranking
reaches file hit5 10/10, passage hit5 7/10, MRR .870/.650 at 1.18 s median.
Transcript passage hit5 remains 1/2. This small source-authored sample does not
confirm the prior fusion MRR uplift or authorize adoption. Expand independent
questions and passage labels before deciding. Historical labels remain unchanged;
the missing live transcript was deleted by cellar sync, not silently replaced.
