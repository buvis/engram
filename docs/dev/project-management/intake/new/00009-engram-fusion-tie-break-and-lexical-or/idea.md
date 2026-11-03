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

## Questions for discovery

1. Confirm on held-out questions (the 55 are development data) and add transcript
   passage labels.
2. Lexical OR: plain OR, or token filtering (stop words), or BM25 weights? Does it
   hurt exact-identifier code queries?
3. Dense weight (1x vs 2x) and tie-break rule as explicit, tested behaviour.
4. Interaction with `pack`, which also calls `query()`.

## Out of scope

Embedding model change and reranking (intake 00008).
