# Fusion and candidate-recall probe — 2026-11-02

Probe: `eval/probe_fusion.py` (results `eval/probe-fusion.json`). It reuses the
read-only per-model indexes from the full-snapshot campaign (113,258 chunks,
55 development questions, 8 passage labels), re-embeds the queries, and swaps
retrieval strategies. Production code and index were not touched.

Validation: the probe's "production order" variant reproduces the campaign's
published RRF file MRR to three digits for all four embeddings (0.794, 0.776,
0.810, 0.798).

## Findings

1. **RRF tie-breaking costs about 0.08 file MRR.** Production inserts lexical
   hits before dense hits in the fusion dict, and `sorted` is stable, so at equal
   RRF score the lexical hit wins. Same fusion with dense first: BGE-M3 0.794 →
   0.877, Qwen3-8B 0.798 → 0.909. Transcripts (BGE-M3): 0.42 → 0.76.
2. **Lexical search is empty for 34 of 55 queries.** `search_bm25` quotes every
   token and ANDs them, so long natural-language queries match nothing. Expected
   file in lexical top-100: 11%. Lexical only, OR semantics: file MRR 0.864 and
   hit5 0.909.
3. **Lexical OR + RRF (dense first) is the best cheap fix.** BGE-M3 file MRR 0.918
   (0.930 with dense weight 2, hit5 0.982), above dense-only 0.899; transcripts
   0.90. Qwen3-8B 0.932. No embedding change or rebuild needed.
4. **Candidate recall is not the bottleneck.** The expected file is in the dense
   top-20 for 100% of questions with BGE-M3 and Qwen3-8B (96–98% for Gemma 2 and
   Jina v5). Pool depth 20→100 never helped, and deeper pools lowered MRR.
5. **Passage MRR is unchanged by fusion** (0.58 BGE-M3). Ordering within a file is
   the reranker's gain (0.917), so fusion and reranking are separate levers.

## Caveats

Development questions only; 8 passage labels; BM25 OR was tested only as an
alternative lexical leg, not tuned. Gains need confirmation on held-out
questions and transcript passage labels before any production change.

## Probes still open

- Held-out questions; transcript passage labels; cross-corpus queries.
- Reranker over the fixed fusion (does the 0.6B reranker still add as much?).
- Warm persistent reranker server latency and down-server fallback.
- Qwen3-0.6B on the full snapshot.
