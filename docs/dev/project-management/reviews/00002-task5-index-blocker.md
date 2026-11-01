# PRD 00002 — Task 5 blocker: embedding path crashes on real transcript content

Status: **STALLED** (loop-mode, moved to `dev/local/prds/hold/`). Discovered 2026-08-02 during autopilot task 5 ("Run initial full index (transcripts + code) to fresh, prove incrementality").

## What happens

`engram index --scope portfolio --corpus transcripts` crashes on the **first real transcript file's batch**:

```
engram.client.EmbeddingPreflightError: embedding request to http://127.0.0.1:8081/v1
for model Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 failed:
Remote end closed connection without response (batch indices 0..17)
```

The llama-server drops the connection while embedding a batch of real turns. Because `indexer.index()` embeds **all** changed files into memory and calls `store.upsert_chunks` **once at the end**, a crash mid-run persists **zero** chunks — the run is all-or-nothing, not the "incremental/resumable" the PRD Phase 0 acceptance assumes at the single-call level.

## Environment is NOT the blocker (all verified working)

- `engram` CLI runs (via `uv run engram`; not installed as a `uv tool` — see note below).
- llama-server present; engram spawns it internally (Python `subprocess`, **not** Bash — so warden does not gate it), GGUF downloads over network on first spawn (`~/.cache/llama.cpp/` was empty, now warmed).
- Single embed works: `embed(['hello world'])` → dim 1024; a single 8000-char text → OK.
- Throughput: 146 embeds/sec (batch of 64 short texts) on the warm Qwen server.
- Corpora present: 638 git-tracked transcript files (~900MB), 11,402 code files across 26 gita repos (~3,136 grammarless, skipped-and-counted).
- Synthetic batch of 32 × ~400-token texts (~12.8K tokens total): OK.
- The 10 chunks of one real transcript file, embedded **individually**: all OK (≤1409 chars each).

So: infra is fine; single/short/moderate embeds are fine. The failure is specific to a **batch of real turns** whose combined size overruns the server.

## Root cause (foundation defect in `client.py`)

`client.py` (a **PRD 00001** module, which PRD 00002's design doc explicitly declares "unchanged") batches embeddings with **no token budgeting**:

- `EMBED_BATCH_SIZE = 64` texts per request (fixed count).
- `EMBED_MAX_CHARS = 8000` truncates each text by **characters, not tokens**.
- `ensure_served` spawns `llama-server --embedding -hf <id> --alias <id> --port <port>` with **no `-c` / `-b` / `-ub` flags** — llama.cpp defaults.

The transcript turn-filter deliberately keeps **error-bearing turns** (stack traces, panics, non-zero-exit logs, JSON dumps). That content is **token-dense**: 8000 chars can be far more tokens than 8000 chars of prose, and a batch of several such turns overruns the server's default context / batch, so llama-server closes the connection. The defect stayed latent through PRD 00001 because prose chunks (markdown-by-heading) are short and never hit the limit; transcripts are the first corpus with long, dense chunks.

## Blast radius / why this was NOT patched headlessly

- The fix is a **design-level** change to a frozen foundation module: token-budget the request batches AND size the spawned server (`-c`/`-b`/`--ubatch-size`). It touches how *every* embedding is produced.
- Task 6 (the harness gold-set gate) *measures* retrieval quality and *pins* the winning model against exactly this embedding path. Patching the batching and then self-certifying it with the harness in the same headless session would be measuring with a ruler I just bent.
- The reviewed design did not anticipate it (no mention of batch/token/server sizing), so the correct home for the fix is a design + test + review cycle, not a silent rider on an execution task.

## Recommended fix (for the un-park / a new PRD)

1. **Size the spawned server**: add `-c`/`-b`/`--ubatch-size` to the `ensure_served` spawn, ≥ the largest single input (8000 chars ≈ up to ~8000 tokens worst-case), e.g. `--ubatch-size 8192 -b 8192 -c 8192` (Qwen3-Embedding supports a large context).
2. **Token-budget the batches** in `embed()`: split requests by an estimated total-token (or char) budget instead of a fixed 64-text count, so a batch of long dense turns is sent in several smaller requests. Behavior-preserving for the vectors themselves (same per-text truncation, just fewer texts per request).
3. Regression test: a batch containing several near-`EMBED_MAX_CHARS` token-dense texts must embed without crashing the server (and respect the per-request budget).
4. Consider whether `EMBED_MAX_CHARS` should be a **token** cap, and whether `indexer.index()` should checkpoint (upsert per file/batch) so a long initial index is genuinely resumable rather than all-or-nothing.

## Resume instructions

`mv dev/local/prds/hold/00002-engram-heavy-corpora-v1.md dev/local/prds/backlog/` (or `wip/`) after the embedding path is fixed, then re-run `/run-autopilot`. Tasks 1–4 are committed and done; task 5 restarts from a working index.

## Notes

- The initial index will still take ~30–60 min once the batching is fixed (embedding ~12.6K transcript + tens of thousands of code chunks at ~146/s, plus tree-sitter parsing) — feasible within a session if run as a background job + Monitor, but the all-or-nothing `index()` call (point 4 above) makes a mid-run kill lose everything.
- `engram` is not installed as a `uv tool` on this machine (no `~/.local/bin/engram`); task 7's premise (catchup calls a bare `engram`) will need `uv tool install .` first. Out of scope for this blocker.
- A warm `llama-server` (Qwen embedding, port 8081) was spawned during diagnosis and may still be running.
