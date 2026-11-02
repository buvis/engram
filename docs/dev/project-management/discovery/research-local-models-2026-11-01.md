# Local embedding and reranking comparison

Campaign started 2026-11-01. Results updated 2026-11-02.

Recommendation: BGE-M3 Q8 plus Qwen3 Reranker 0.6B Q8 is the strongest tested
pair for ranked search. On the full snapshot it returns all 55 expected files
and all eight labelled passages in the first five results. File MRR is 0.979,
passage MRR is 0.917, and median query time is 0.703 seconds, excluding startup.

For search without a neural reranker, Qwen3 Embedding 8B Q8 has the best tested
coverage: 55/55 files and 8/8 passages, at 0.123 seconds median. Its file MRR is
0.798; Jina v5 ranks files slightly better on average but misses one expected
file and one labelled passage from the first five results.

Nine embeddings were screened. Four were tested on the full 113,258-chunk
snapshot. Three rerankers were tested on all four full candidate sets; Jina
also received a larger-block trial. These are development-set results, not
proof of a universal winner across models, quantizations, or serving backends.

No production configuration or index was changed by this experiment. Any
adoption must preserve the tested model-specific input framing and rebuild
the index when changing embedding identity. A production reranking stage has
not been added by these evaluation tools.
[Aggregate results](../../../../eval/results-2026-11-02.json) contain scores and
allocation logs and exact weight/asset hashes, without private queries or
passages. Context-probe counts are included for the Jina block comparison.

## Machine and method

- Apple M5 Max, 48 GiB unified memory, measured with `sysctl`.
- Main backend: llama.cpp build 11960, commit `8642541b2`, Metal.
- Jina v3.5 backend: `littlewine/llama.cpp`, branch `qwen3-swa`, commit
  `491219a2bfa0a5a51acfc6a233bea911515b2134`, built locally with Metal.
- Every candidate uses Q8 weights and its published input framing.
- Screen: 1,816 frozen chunks, 55 existing questions, 4,000-character inputs.
  Snapshot `9b24859c30474c6d`.
- Full trial: 113,258 frozen chunks from the six evaluated corpora,
  8,000-character inputs. Snapshot `fc9bf2e6e0038153`.
- Each question uses its labelled corpus as a filter. Cross-corpus search and
  findings retrieval are not measured.
- Eight exact-passage labels cover five code questions and three decision
  questions. No transcript passage labels exist. Three decision questions
  share one file.
- All 55 questions are development data, not held-out data. Each question has
  one expected file; useful alternative files are not credited.
- Both stages score production BM25/vector reciprocal-rank fusion (RRF), with
  20 candidates per leg. Dense-only scores are retained separately.
- Rerankers receive each embedding's saved candidate list. They cannot recover
  a passage missing from that list.

The stages differ in both corpus size and input budget. Compare models within
a stage; the change between stages is not an isolated corpus-size effect.

File hit5 means an expected-file chunk occurs among the first five chunks.
Passage hit5 requires an acceptable exact chunk start. MRR means mean reciprocal
rank; larger values put the expected result nearer the first position. These
are strict chunk ranks, unlike the historical harness's file-deduplicated top
five. Its historical accuracy is therefore not directly comparable.

See [commands and input rules](../../../../eval/README.md). Raw source, vectors,
rankings, logs, and weights stay in the local cache, outside Git. Queries and
documents go only to local inference. A gold document moved from `wip` to `done`
during the experiment; its tracked reference was corrected, while every
candidate continued using the unchanged frozen snapshot.

## Nine embedding screens

| Model | File hit5 | File MRR | Passage hit5 | Passage MRR | Median seconds |
|---|---:|---:|---:|---:|---:|
| BGE-M3 | 55/55 | 0.857 | 6/8 | 0.606 | 0.034 |
| Qwen3 0.6B | 55/55 | 0.858 | 7/8 | 0.442 | 0.030 |
| EmbeddingGemma 2 | 54/55 | 0.872 | 8/8 | 0.754 | 0.020 |
| Jina v5 small retrieval | 55/55 | 0.904 | 6/8 | 0.778 | 0.025 |
| F2LLM-v2 4B | 55/55 | 0.898 | 7/8 | 0.552 | 0.094 |
| Qwen3 4B | 53/55 | 0.896 | 8/8 | 0.531 | 0.111 |
| F2LLM-v2 8B | 54/55 | 0.894 | 6/8 | 0.533 | 0.071 |
| Qwen3 8B | 55/55 | 0.918 | 8/8 | 0.781 | 0.071 |
| F2LLM-v2 14B | 55/55 | 0.903 | 6/8 | 0.635 | 0.175 |

Qwen3 8B leads the screened embeddings on both file MRR and passage MRR.
F2LLM-v2 14B runs successfully, but scores lower and uses more memory.
F2LLM-v2 8B scores slightly below its 4B version. Size alone is not a selection
rule. All nine candidates retain all 55 expected files and eight passages in
their screened candidate pools, so this small screen is a weak test of recall.

Qwen3 8B advances as the strongest larger finalist. BGE-M3 is the production
baseline. Gemma 2 and Jina v5 advance as efficient alternatives with different
passage and file-ranking strengths. The other five embeddings receive screen
results only; they are not represented as full-portfolio measurements.

## Full snapshot: embeddings

| Model | File hit5 | File MRR | Passage hit5 | Passage MRR | Median seconds |
|---|---:|---:|---:|---:|---:|
| BGE-M3 | 53/55 | 0.794 | 5/8 | 0.576 | 0.075 |
| EmbeddingGemma 2 | 53/55 | 0.776 | 8/8 | 0.650 | 0.035 |
| Jina v5 small retrieval | 54/55 | 0.810 | 7/8 | 0.739 | 0.022 |
| Qwen3 8B | 55/55 | 0.798 | 8/8 | 0.594 | 0.123 |

## Dense-only comparison

| Embedding | RRF file MRR | Dense-only file MRR | Dense file hit5 |
|---|---:|---:|---:|
| BGE-M3 | 0.794 | 0.899 | 54/55 |
| EmbeddingGemma 2 | 0.776 | 0.901 | 53/55 |
| Jina v5 small retrieval | 0.810 | 0.937 | 54/55 |
| Qwen3 8B | 0.798 | 0.933 | 55/55 |

The existing hybrid pipeline produces lower file MRR than dense-only retrieval.
For Qwen3 8B, transcript file MRR drops from 0.917 to 0.465. This comparison
also changes candidate composition: dense-only takes 40 dense chunks, while RRF
combines 20 dense and 20 lexical chunks. It justifies a separate candidate-budget
and fusion evaluation, not a silent production algorithm change.

## Full snapshot: paired reranking

Times include the original embedding query and retrieval time plus reranking.
They exclude model startup. The benchmark alternates models; it does not load
an embedding model and reranker simultaneously.

| Model | File hit5 | File MRR | Passage hit5 | Passage MRR | Median seconds |
|---|---:|---:|---:|---:|---:|
| Qwen3 reranker 4B on BGE-M3 | 55/55 | 0.976 | 8/8 | 0.833 | 3.794 |
| Qwen3 reranker 4B on EmbeddingGemma 2 | 53/55 | 0.939 | 8/8 | 0.833 | 3.843 |
| Qwen3 reranker 4B on Jina v5 small retrieval | 54/55 | 0.958 | 8/8 | 0.833 | 2.812 |
| Qwen3 reranker 4B on Qwen3 8B | 54/55 | 0.959 | 8/8 | 0.833 | 3.248 |
| Qwen3 reranker 0.6B on BGE-M3 | 55/55 | 0.979 | 8/8 | 0.917 | 0.703 |
| Qwen3 reranker 0.6B on EmbeddingGemma 2 | 53/55 | 0.941 | 8/8 | 0.906 | 0.652 |
| Qwen3 reranker 0.6B on Jina v5 small retrieval | 54/55 | 0.959 | 8/8 | 0.906 | 0.585 |
| Qwen3 reranker 0.6B on Qwen3 8B | 54/55 | 0.962 | 8/8 | 0.917 | 0.659 |
| Jina reranker v3.5 (32K) on BGE-M3 | 55/55 | 0.967 | 8/8 | 0.667 | 1.511 |
| Jina reranker v3.5 (32K) on EmbeddingGemma 2 | 53/55 | 0.936 | 8/8 | 0.781 | 1.542 |
| Jina reranker v3.5 (32K) on Jina v5 small retrieval | 54/55 | 0.939 | 8/8 | 0.671 | 1.203 |
| Jina reranker v3.5 (32K) on Qwen3 8B | 55/55 | 0.967 | 8/8 | 0.677 | 1.345 |
| Jina reranker v3.5 (64K) on BGE-M3 | 55/55 | 0.967 | 8/8 | 0.667 | 1.545 |
| Jina reranker v3.5 (64K) on EmbeddingGemma 2 | 53/55 | 0.936 | 8/8 | 0.781 | 1.586 |
| Jina reranker v3.5 (64K) on Jina v5 small retrieval | 54/55 | 0.939 | 8/8 | 0.671 | 1.193 |
| Jina reranker v3.5 (64K) on Qwen3 8B | 55/55 | 0.967 | 8/8 | 0.677 | 1.363 |

BGE already retains every labelled target in its candidate pool. The 0.6B
Qwen reranker fixes result order without an embedding migration. It exceeds
the 4B reranker's file and passage MRR on this set and takes 0.703 seconds
instead of 3.794 seconds at the median. Its reported Metal model, KV, and
compute buffers sum to about 4.7 GiB, with additional CPU memory unmeasured.

A larger embedding does not guarantee a better combined result. Qwen3 8B has
55/55 raw file hit5, but both Qwen rerankers reduce that to 54/55 on its
candidate pool. Gemma and Jina v5 omit two and one expected files respectively
from their RRF candidate pools; reranking cannot recover those files.

Jina v3.5 was tested with 32K and 64K block budgets. Aggregate accuracy is
unchanged across all four embeddings. At 64K, every one of the 220 candidate
lists fits one block. The largest actual prompt is 26,874 tokens. Raising the
cap further would not combine additional candidates in these tests. Jina is
therefore a measured challenger, with no demonstrated benefit from the extra
block budget here. BGE plus Jina has file MRR 0.967 and passage MRR 0.667,
below BGE plus the smaller Qwen reranker.

The current rank-fusion settings warrant separate evaluation: dense-only file
MRR is higher for every full embedding trial. Neither model promotion nor a
fusion change was applied to production. Held-out questions, transcript passage
labels, and cross-corpus tests remain necessary before generalizing these
results.

## Reranking screen checks

These use 4,000-character passages and the same saved candidate list for each
embedding. Listwise Jina is sensitive to candidate ordering, so BGE and Gemma
screens were repeated after their final embedding runs. The older Jina-on-Jina
screen was retained only after verifying all 55 candidate lists were unchanged.

| Model | File hit5 | File MRR | Passage hit5 | Passage MRR | Median seconds |
|---|---:|---:|---:|---:|---:|
| Qwen3 reranker 4B on BGE-M3 | 55/55 | 0.970 | 8/8 | 0.854 | 4.550 |
| Qwen3 reranker 4B on F2LLM-v2 4B | 55/55 | 0.970 | 8/8 | 0.854 | 4.923 |
| Qwen3 reranker 4B on EmbeddingGemma 2 | 55/55 | 0.970 | 8/8 | 0.854 | 5.237 |
| Qwen3 reranker 4B on Qwen3 4B | 55/55 | 0.970 | 8/8 | 0.854 | 4.337 |
| Qwen3 reranker 0.6B on BGE-M3 | 55/55 | 0.968 | 8/8 | 0.906 | 0.588 |
| Qwen3 reranker 0.6B on F2LLM-v2 4B | 55/55 | 0.968 | 8/8 | 0.906 | 0.610 |
| Qwen3 reranker 0.6B on EmbeddingGemma 2 | 55/55 | 0.968 | 8/8 | 0.906 | 0.588 |
| Qwen3 reranker 0.6B on Qwen3 4B | 55/55 | 0.959 | 8/8 | 0.906 | 0.568 |
| Jina reranker v3.5 (32K) on BGE-M3 | 55/55 | 0.964 | 8/8 | 0.812 | 2.046 |
| Jina reranker v3.5 (32K) on F2LLM-v2 4B | 55/55 | 0.970 | 8/8 | 0.854 | 1.502 |
| Jina reranker v3.5 (32K) on EmbeddingGemma 2 | 55/55 | 0.973 | 8/8 | 0.938 | 1.929 |
| Jina reranker v3.5 (32K) on Jina v5 small retrieval | 55/55 | 0.961 | 8/8 | 0.854 | 2.410 |
| Jina reranker v3.5 (32K) on Qwen3 4B | 55/55 | 0.962 | 8/8 | 0.833 | 1.301 |

## RAM and runtime

Every screened model completed on this 48 GiB machine, including F2LLM-v2 14B
Q8. Four server slots share a 32K-token context, giving 8K per input. Reported
Metal model + KV + compute buffers were about 9.8 GiB for Qwen3 Embedding
4B, 13.7 GiB for Qwen3 Embedding 8B, and 21.2 GiB for F2LLM-v2 14B. These are logged allocations,
not peak physical RAM. CPU allocations and other processes need additional
memory. Weight-file size is not a memory measurement.

A 136-document slot probe compared four and sixteen slots with the same 8K
context per input. It took 32.4 versus 31.3 seconds and produced identical
vectors. The sixteen-slot KV allocation rose from 4.5 to 18 GiB. This single
probe did not establish a useful throughput gain, so full runs retain four
slots. Qwen3 8B indexing resumed from its private cache after the probe.

The agent sandbox denied `ps`, so peak process RSS is unmeasured and recorded as
null. No alternative sampling route was used. Existing swap is not a measure
of current free RAM. These runs do not establish memory use with a simultaneous
local chat model.

Embedding query times include embedding and retrieval. Indexing records include
resumed work; they are not comparable uninterrupted cold-build times. BGE's
initial serial indexing was resumed with four slots after checking batch
consistency (largest vector-component difference 0.000178). Full query trials
ran after weight downloads and compilation completed. Screen timing is
indicative because some earlier screens overlapped download work.

Jina v3.5 timings include the official CLI's model reload for each block. Its
runtime is not optimized like a persistent Qwen server. Jina weights carry
CC-BY-NC-4.0; both the license and custom runtime affect deployment suitability.

## Artifact and implementation checks

- Qwen queries use the published retrieval instruction. Gemma uses task and
  title/text prefixes. Jina v5 uses query/document prefixes.
- F2 EOS handling is checked against the running tokenizer, avoiding a double
  EOS when the GGUF already appends it.
- The first mradermacher Qwen reranker artifact lacked the classifier tensor
  and rank metadata required by llama.cpp. The selected Voodisss conversions
  supply them. This was an artifact issue, not a model-quality failure.
- Both Qwen rerankers and Jina pass a relevant/irrelevant sanity pair before
  scoring. Invalid, zero, or non-finite vectors and invalid rank outputs fail
  instead of entering the evaluation store.
- Jina's default fork branch lacks `--output-token-ids`. The explicit PR branch
  works with its external projector and official wrapper. Plain `/rerank`
  would not evaluate that model correctly.
- The added downloader validates HTTP ranges and whole-file published SHA-256
  before publishing a model file. No runtime or system tool was replaced.
- Rerankers see heading, full path, and body. Prose embeddings do not receive
  the full path, so gains are not a metadata-controlled model-only ablation.
- The source and prompts remain unchanged during inference. The evaluation
  README defines when code or weight changes require fresh caches or retesting.

Validation: 485 tests pass. Isolated Ruff checks `E4,E7,E9,F,I` pass. This does
not claim compliance with every rule in the user's global Ruff configuration.

Primary model sources and requirements are linked in the evaluation README.
