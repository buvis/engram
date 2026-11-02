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

An uncommitted parallel experiment already measures embeddings and rerankers
without touching production: `docs/dev/project-management/discovery/research-local-models-2026-11-01.md`
and `eval/README.md`. Its screen (1,816 frozen chunks, 55 questions, 8 exact-passage
labels) shows a reranker lifting file MRR from 0.866–0.904 to 0.96–0.98 and passage
hits to 8/8, at roughly 1.5–2.5 s extra median latency in an unoptimized CLI
implementation. It also puts other embeddings (EmbeddingGemma 2, Jina v5) ahead of
Qwen3-0.6B on some measures, and lists larger Qwen3 embedding and Qwen3 Reranker 4B
as still under test. Treat Qwen3 as one candidate in that comparison, not a foregone
winner.

## Questions the discovery must answer

1. Does Qwen3 (which size) beat bge-m3 on a larger, held-out set, rather than the
   55 development queries? The screen's questions are development data.
2. Does reranking improve top-5 file and passage hits enough to justify the latency
   and a second persistent local server, measured with a warm server rather than
   a per-block model reload?
3. Which reranker: Qwen3 Reranker 4B, or Jina v3.5 (license CC-BY-NC-4.0, custom
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

Run `/elicit-requirements` on this item once the parallel model comparison finishes
its full-portfolio trials.
