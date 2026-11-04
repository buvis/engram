# engram: move to Qwen3 embeddings and add a reranking stage if probes support it

Status: new. Recorded 2026-11-02.

## Idea

Switch engram's embedding model from bge-m3 to Qwen3-Embedding, and add a
second-stage reranker over the retrieved candidates, but only if measured probes
show a real gain. Both parts are conditional on evidence, not decided.

## Why

- The 2026-11-02 cold harness run on the 55-entry gold set scored Qwen3-Embedding-0.6B
  at 0.945 against 0.927 for bge-m3 and nomic (prd 12/13 vs 11/13). One entry
  separates them, so the run alone is not decisive. The user reports the same
  ordering from experience on other machines.
- The user's production pin stays bge-m3 until this is decided, because a model
  switch needs a whole-index rebuild (163,739 chunks, about 75 minutes for a cold
  harness build, longer for production).
- Remaining production misses are ranking misses, which a reranker targets: the
  engram core PRD query and one code query. Code stays the weakest class at 0.800.

## Existing evidence to build on

The completed campaign is committed in `f25ac54`; see
`docs/dev/project-management/discovery/research-local-models-2026-11-01.md`
and `eval/README.md`. On 113,258 frozen chunks and 55 development questions,
BGE-M3 plus Qwen3 Reranker 0.6B reaches file MRR 0.979, passage MRR 0.917,
and 0.703 s median combined latency, excluding startup. Eight passage labels
cover five code and three decision questions; none cover transcripts. The
campaign includes Qwen3 Embedding 8B and Qwen3 Reranker 4B. An embedding switch
remains unproven, and no production configuration or index was changed.

## Probe update, 2026-11-02

`reviews/2026-11-02-probe-fusion.md`: candidate recall is not the bottleneck (the
expected file is in the dense top-20 for 100% of questions with BGE-M3 and Qwen3-8B),
and much of the apparent embedding gap is a fusion tie-break defect, split out as
intake 00009. The campaign's best pair is bge-m3 plus Qwen3 Reranker 0.6B (file MRR
0.979, passage MRR 0.917, 0.70 s), so this item should lead with the reranker and
treat an embedding switch as unproven. Re-measure the reranker's gain on top of the
fixed fusion before sizing it.

## Fixed-fusion probe, 2026-11-03

[Results](../../../reviews/2026-11-03-probe-rerank-fixed.md) and
`eval/probe-rerank-fixed.json`: the 0.6B reranker still adds value after OR-lexical
dense-first fusion. BGE-M3 file MRR rises 0.918→0.977 at dense weight 1 and
0.930→0.977 at weight 2; only 32% and 25% of the original +0.185 file-MRR gain
remain. Passage MRR rises 0.584/0.589→0.906, retaining 93–95% of the original
passage uplift. File hit5 reaches 55/55 and passage hit5 8/8.

Qwen3-8B plus OR fusion and the same reranker reaches identical aggregate and
per-corpus scores. An embedding migration still has no demonstrated benefit.
OR expands the BGE candidate pool from a mean 20.36 to 31.96 chunks; median
combined time rises from 0.676 s to 1.220–1.246 s. Budget and serving design
therefore matter even with the smaller reranker. Some individual file ranks
regress, and OR's reranked passage MRR is slightly below the original 0.917.

The optional 4B comparison is complete: after either OR fusion, both embeddings
reach file/passage MRR 0.976/0.833, below 0.6B's 0.977/0.906, at 5.83–6.46 s
median combined time. The larger reranker supplies no advantage on this set.

All four reranker campaign baselines reproduce exactly. These are still 55 development
questions and only eight passage labels (five code, three decision, none for
transcripts); they do not authorize adoption or a model switch.

## Questions the discovery must answer

1. Does Qwen3 (which size) beat bge-m3 on a larger, held-out set, rather than the
   55 development queries? The screen's questions are development data.
2. Does reranking improve top-5 file and passage hits enough to justify the latency
   and a second persistent local server, measured with a warm server rather than
   a per-block model reload?
3. Which reranker: Qwen3 Reranker 0.6B or 4B, or Jina v3.5 (license CC-BY-NC-4.0, custom
   runtime)? Local GGUF compatibility matters: some conversions lack the classifier
   tensor llama.cpp needs.
4. Where does reranking sit in `query` and `pack`: candidate pool size, which
   corpora, and a fallback when the reranker server is down.
5. Migration cost: whole-index rebuild for a new embedding model, versus the
   targeted `index --reembed-code` that exists only for same-model text changes.
   Query-side instruction prefixes (Qwen3 expects one) must be handled in `client`.
6. Transcripts and findings have no passage labels; add them before judging those
   classes.

## Out of scope

Changing the production pin, rebuilding the production index, or choosing a model
from the 55-entry result alone.

## Next step

Confirm the fixed-fusion reranker results on held-out questions and add transcript
passage labels. Measure persistent serving latency and down-server fallback in
a separate probe before sizing production work with `/elicit-requirements`.
