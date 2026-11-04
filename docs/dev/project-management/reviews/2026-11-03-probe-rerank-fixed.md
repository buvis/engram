# Reranker on fixed fusion — 2026-11-03

Probe: `eval/probe_rerank_fixed.py`; machine-readable results:
`eval/probe-rerank-fixed.json`. This extends the
[previous fusion probe](2026-11-02-probe-fusion.md).

## Method and limits

- Frozen campaign snapshot `fc9bf2e6e0038153`: 113,258 chunks, 55 development
  questions, each restricted to its labelled corpus. No held-out validation.
- **Eight passage labels only: five code, three decision; none for transcripts.**
  The three decision questions share one file. Unlabelled corpora have no
  passage score, rather than a zero score.
- BGE-M3 Q8 and Qwen3 Embedding 8B Q8; 20 dense and 20 lexical candidates,
  RRF k=60, up to 40 chunks. Four fusions: production lexical-first order,
  dense-first order, OR-lexical dense-first with dense weight 1, and weight 2.
- Same reranker framing as the campaign: heading, full path, body, truncated
  together at 8,000 characters. These are strict chunk-rank metrics, without
  file deduplication. Prose embeddings lack the full path, so the reranker gain
  is not a metadata-controlled model-only ablation.
- Campaign indexes are opened read-only. Private candidates/rankings go to
  a separate cache, server logs to temporary directories. Only port 18181 is
  used, with no overlap between probe embedding and reranking servers.
- Every reranker first repeats the saved campaign inputs. The gate compares
  all four metrics, overall and per corpus, at published precision (0.0005
  tolerance). Both embeddings regenerate all 55 production candidate lists
  in exactly the campaign order and reproduce their original metrics.
- Every fusion is reranked independently, without cached score reuse. Latency
  is recorded per query as retrieval, reranking, and their sum. Startup is
  excluded; OR retrieval conservatively includes the AND lookup used in
  candidate collection. Fusion and serialization time are excluded. Query
  embedding and reranking are timed in separate model lifecycles, so these are
  not simultaneous production-serving or fallback measurements.

## Results

**Reranking still helps after fixing fusion, including within-file passage ordering.**
For BGE-M3, the 0.6B reranker's file-MRR gain falls from +0.185 with production
fusion to +0.059 with OR/1x and +0.047 with OR/2x: **32% and 25% of the original
gain remain**. Passage-MRR gains remain +0.322 and +0.318, versus +0.340 originally
(95% and 93% remain). These are marginal gains over each fusion, not an isolated
model-only effect or evidence of generalization.

### Qwen3 Reranker 0.6B Q8

Arrows show fusion alone → reranked. Both campaign baselines reproduce exactly,
including every per-corpus metric: BGE-M3 file/passage MRR 0.979/0.917;
Qwen3-8B 0.962/0.917. This uses the same llama.cpp build 11960 (`8642541b2`).

| Embedding | Fusion | File hit5 | File MRR | Passage hit5 | Passage MRR | Median total s |
|---|---|---:|---:|---:|---:|---:|
| BGE-M3 | Production | 53→55/55 | .794→.979 | 5→8/8 | .576→.917 | .676 |
| BGE-M3 | Dense-first | 53→55/55 | .877→.979 | 5→8/8 | .576→.917 | .648 |
| BGE-M3 | OR, dense 1x | 54→55/55 | .918→.977 | 6→8/8 | .584→.906 | 1.246 |
| BGE-M3 | OR, dense 2x | 54→55/55 | .930→.977 | 6→8/8 | .589→.906 | 1.220 |
| Qwen3-8B | Production | 55→54/55 | .798→.962 | 8→8/8 | .594→.917 | .678 |
| Qwen3-8B | Dense-first | 55→54/55 | .909→.962 | 8→8/8 | .594→.917 | .666 |
| Qwen3-8B | OR, dense 1x | 55→55/55 | .932→.977 | 6→8/8 | .601→.906 | 1.259 |
| Qwen3-8B | OR, dense 2x | 55→55/55 | .932→.977 | 7→8/8 | .585→.906 | 1.293 |

For Qwen3-8B, +0.045 file MRR remains after OR fusion, 28% of its original
+0.164 uplift. Both embeddings reach identical overall and per-corpus scores
after OR plus the 0.6B reranker. This supplies no reason to migrate embeddings.
The two OR weights change pre-reranking order but retain the same candidates;
reranking produces the same metrics at either weight.

### Per-corpus detail: OR/2x plus the 0.6B reranker

All variants' complete per-corpus hit5/MRR and per-query latency are in the JSON.
Here each arrow again means fusion alone → reranked. A dash means no label.

| Corpus (questions) | BGE file MRR | Qwen8 file MRR | BGE passage MRR | Qwen8 passage MRR |
|---|---:|---:|---:|---:|
| Code (5) | .567→.850 | .750→.850 | .492→.850 | .569→.850 |
| Decision (3) | 1→1 | 1→1 | .750→1 | .611→1 |
| Discovery (2) | 1→1 | 1→1 | — | — |
| Memory (20) | 1→.975 | .975→.975 | — | — |
| PRD (13) | .962→1 | .962→1 | — | — |
| Transcripts (12) | .903→1 | .875→1 | — | — |

BGE code file hit5 improves 4/5→5/5; all other file hit5 counts remain perfect.
Code passage hit5 improves 3/5→5/5 for BGE and 4/5→5/5 for Qwen8; decision
passage hit5 stays 3/3. There are no transcript passage labels.
On BGE OR/2x, five queries improve file rank and two regress (IDs 4 and 35).
Query 35's file rank falls 3→4 while its labelled passage improves 17→4.

### Latency and remaining work

For BGE, OR grows candidate lists from 20–23 (mean 20.36) to 23–40 (mean 31.96).
The 0.6B reranking median rises from .608 s to 1.163–1.198 s, and combined
median from .676 s to 1.220–1.246 s (OR combined p95: 1.974–2.058 s).
The campaign's production-fusion median was .703 s; the new baseline is similar.
These are sequential measurements with the user's other servers left running,
not a controlled warm-production latency or concurrent-memory test.

Keep fusion and reranking as separate intake items. Validate the inexpensive
fusion change first on held-out questions, then test the remaining reranker
benefit with transcript passage labels. Persistent serving, down-server fallback,
and Qwen3-0.6B embedding on the full snapshot remain separate probes.

### Qwen3 Reranker 4B Q8

The optional comparison completed. Both 4B campaign baselines also reproduce
exactly, overall and per corpus: BGE file/passage MRR .976/.833 and Qwen8
.959/.833. Dense-first alone leaves these scores unchanged. With either OR
weight, both embeddings reach file MRR .976, passage MRR .833, file hit5 55/55,
and passage hit5 8/8 (five code labels, three decision, none for transcripts).

| Embedding | OR dense weight | 0.6B median total s | 4B median total s |
|---|---:|---:|---:|
| BGE-M3 | 1x | 1.246 | 6.464 |
| BGE-M3 | 2x | 1.220 | 6.210 |
| Qwen3-8B | 1x | 1.259 | 6.188 |
| Qwen3-8B | 2x | 1.293 | 5.832 |

The larger reranker provides no quality improvement here and is roughly five
times slower. The 0.6B model remains the candidate for the next held-out probe.

## Verification and isolation

The main suite passes 468 tests; eval tests pass separately (27). Isolated Ruff
checks `E4,E7,E9,F,I` pass for both probes and their tests. No production source
was edited, no index/rebuild command was run, and no model switch was made.
The config MD5 remains `73b87ee352f490f92470b4e19edb173a`.
All four reranker baselines match with zero metric differences. The recorded
source hashes match the committed probe sources. Campaign index/log metadata
and backlog PRDs 00005–00007 are unchanged. Port 18181 is free after completion;
the original processes on 8002, 8081, and 8083 are still running.
All 1,100 saved reranked lists were independently re-scored against the frozen
labels and match the public artifact. Inference finished November 3 at 22:38 CET;
the report was finalized November 4 after the session limit reset.

The production database's mtime advanced from 03:13:39 to 21:53:00 CET during
the run, with its size unchanged at 1,542,074,368 bytes. The writer is unconfirmed;
the probe only opens campaign databases, with SQLite `mode=ro`. No process had
the production database open when checked. This observation prevents a claim
that the production index stayed byte-for-byte unchanged throughout the session.
It does not affect the frozen campaign inputs.
The final metadata check on November 4 shows another production-database mtime
change (08:21:26 CET), still with the same size; its writer also remains unknown.
