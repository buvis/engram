# Local model comparison

The [comparison report](../docs/dev/project-management/discovery/research-local-models-2026-11-01.md)
and [aggregate results](results-2026-11-02.json) record the current campaign.

Run from the repository root with its development environment:

```sh
uv run python -m eval.compare_models prepare
uv run python -m eval.compare_models run
uv run python -m eval.compare_rerankers --models bge-m3-q8 gemma2-q8
```

`--models NAME...` selects embedding candidates. Completed models are skipped.
Interrupted document indexing resumes. `run --retest` repeats queries without
re-embedding documents. Models run sequentially on loopback port 18181.
The production database is opened read-only during preparation. Production
configuration and vectors are never changed. Raw material and candidate databases
stay in `~/.cache/engram/compare/`, outside Git.

The initial screen freezes all 55 existing gold questions, all chunks from their
target files, 20 lexical hard negatives per question, and 100 random chunks per
corpus (seed 20261101). Gold files are re-read and chunked into the private
snapshot because some moved after production indexing. The same snapshot is
used by every candidate. This deliberately small corpus is a screening test,
not evidence of full-portfolio accuracy. Random findings are included in the
screen but are excluded by corpus-scoped queries.

Use `prepare --full --max-chars 8000` and `run --full --models NAME...` to test finalists against
all indexed chunks in the six evaluated corpora. Findings have no gold questions
and are excluded from that run. A full snapshot remains an evaluation of the
indexed portfolio at capture time, not a guarantee that every source is current.

Screened models get the same first 4,000 characters of each chunk's embedding text
(including code paths). Model-specific prompt framing is then added. The
character limit controls workload and truncates some long chunks. Report this
limit with scores; the experiment is not identical to production's 8,000-character
limit. The full trials use the production 8,000-character budget instead.
Each of four server slots has an 8192-token context (32768 total). A long-input
BGE-M3 check compared serial and four-input execution; the largest component
difference was 0.000178, consistent with numerical rounding. Normalized dense
vectors and production's BM25/RRF
retrieval are used, with 20 candidates per leg. The report also scores dense-only
retrieval, so lexical matching cannot hide a weak embedding model.

Metrics are strict top-five **chunks** containing the expected file, reciprocal
rank of the expected file, and exact acceptable chunk starts on eight manually
labelled code/decision questions. The labels were written before candidate
scoring. There are no transcript passage labels. Scores do not use the old
harness's file-deduplicated top-five rule. Both small passage sample size and
three decision questions sharing one file limit conclusions. These questions
are development data, not a held-out generalization test.

Query timing excludes model startup and includes embedding plus retrieval.
Startup timing includes any download. Indexing time and characters processed
are recorded separately. Process-memory sampling was denied by the macOS agent
sandbox, so RSS is null. llama.cpp buffer allocations are recorded separately;
they are not peak process RAM. Swap after each trial is recorded, but existing
swap is not a measure of currently available RAM. Retest query latency after
downloads and compilation finish to reduce competing-load effects.

Rerankers receive the saved RRF candidates without loading the embedding model
at the same time. They receive the snapshot's passage budget (4K screen, 8K full). This
measures an alternating model lifecycle, not simultaneous-model peak RAM.
Reranking cannot recover a passage absent from the candidate set.
Reranker inputs contain the heading, full source path, and body. Prose embeddings
do not contain that path, so stage improvements are not a metadata-controlled
ablation of the reranking model alone.

Each question uses its labelled corpus as a filter. The experiment does not
measure cross-corpus search, and it has no labelled findings queries. Replacing
weights under the same model ID requires a fresh candidate cache.
Keep the embedding renderer and retrieval implementation unchanged during a
comparison. The cache signature covers the model specification and prompt
functions, but not every imported dependency. If chunk rendering changes,
use a fresh candidate cache. If query scoring changes, use `run --retest`;
the existing completed query results otherwise remain authoritative.

## Model input rules

- **Qwen3:** query instruction plus `Query:`; raw documents; last-token pooling.
  [Official instructions](https://huggingface.co/Qwen/Qwen3-Embedding-4B-GGUF).
- **F2LLM-v2:** the same published retrieval instruction; raw documents; EOS
  `<|im_end|>` before last-token pooling. The server tokenizer is checked to avoid
  duplicate EOS or an unrecognized EOS. Community GGUFs preserve the original
  model lineage. [Author model](https://huggingface.co/codefuse-ai/F2LLM-v2-4B),
  [tokenizer](https://huggingface.co/codefuse-ai/F2LLM-v2-4B/blob/main/tokenizer.json),
  [conversion](https://huggingface.co/mradermacher/F2LLM-v2-4B-GGUF).
- **EmbeddingGemma 2:** task prefix on queries (code retrieval for code), title
  and text framing on documents; mean pooling. Only text weights are needed.
  [Author model](https://huggingface.co/google/embeddinggemma-2),
  [GGUF](https://huggingface.co/ggml-org/embeddinggemma-2-GGUF).
- **Jina v5 small retrieval:** `Query:` and `Document:` prefixes; last-token
  pooling. [Official GGUF](https://huggingface.co/jinaai/jina-embeddings-v5-text-small-retrieval-GGUF).
- **BGE-M3:** raw inputs; CLS pooling, matching the existing deployment.
- **Qwen3 rerankers (0.6B and 4B):** llama.cpp `/rerank` and rank pooling, using the model's
  question/passage template. [Runtime docs](https://github.com/ggml-org/llama.cpp/tree/master/tools/server).
  The selected [0.6B conversion](https://huggingface.co/Voodisss/Qwen3-Reranker-0.6B-GGUF-llama_cpp)
  and [4B conversion](https://huggingface.co/Voodisss/Qwen3-Reranker-4B-GGUF-llama_cpp)
  include `cls.output.weight`, classifier labels, rank pooling, and the rerank
  template. The initially considered mradermacher conversion lacks these in
  the inspected file and must not be used for this test. A relevance sanity
  check runs before scoring either reranker.
- **Jina reranker v3.5:** a separate listwise evaluation route is required. The
  official implementation uses a custom llama.cpp fork, special-token states,
  and an external projector. Plain `/rerank` would not test this model correctly.
  [Official requirements](https://huggingface.co/jinaai/jina-reranker-v3.5-GGUF).

Jina's weights carry CC-BY-NC-4.0; local experimental results do not authorize
commercial deployment. Other candidate sources and quantizations are listed
in `models.toml`. No model is promoted automatically.

## Jina v3.5 runtime

The author's clone command uses the fork's default branch, which lacks the
required `--output-token-ids` flag. Use branch `qwen3-swa`, verified from upstream
PR 26286, commit `491219a2bfa0a5a51acfc6a233bea911515b2134` for this experiment.
Build only `llama-embedding` with Metal. Keep the fork and all assets under
`~/.cache/engram/jina-v35/`; no system runtime is replaced.

Place `rerank.py`, `projector.safetensors`, `tokenizer.json`, and
`jina-reranker-v3.5-Q8_0.gguf` from the official repo in that directory. The
author's Python code was read before execution. It loads the projector and
tokenizer locally and invokes the built CLI for each block. Dependencies are
NumPy, PyTorch, safetensors, and tokenizers.

```sh
uv run --no-project --with numpy --with torch --with safetensors --with tokenizers \
  python -m eval.compare_jina --models bge-m3-q8 gemma2-q8
```

The adapter sets a 32K-token block budget and a 64K context cap. Documents use
the same character budget as other rerankers: 4,000 for screens and 8,000 for
full trials. Add `--full` to both reranker commands for the full snapshot.
Add `--block-tokens 65536` to the Jina command to compare 64K blocks under the
same context cap. The profile gets a separate result cache.
Its per-query latency includes the author's CLI model reloads; this is not a
comparison of equally optimized persistent serving implementations.

## Download transport

`python -m eval.fetch_models --models NAME...` downloads selected public GGUFs
under `~/.cache/engram/models/`. It uses HTTP ranges, validates response ranges,
resumes completed byte ranges, and checks the complete published SHA-256 before
making a file available to the runner. This avoids the excessive retries seen
with the default download transport on this machine. Servers prefer these
verified files; existing small-model downloads can still use llama.cpp's cache.
