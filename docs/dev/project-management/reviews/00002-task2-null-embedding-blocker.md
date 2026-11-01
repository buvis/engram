# PRD 00002 — Task 2 blocker: embedding server returns null vectors / crashes on real transcript load

Status: **STALLED** (loop-mode, moved to `dev/local/prds/hold/`). Discovered 2026-08-03 during
autopilot task 2 ("Run the initial full transcripts + code index to fresh and prove
incrementality").

This is the **second** distinct embedding-path blocker on this PRD. The first
(`00002-task5-index-blocker.md`) was a connection-close on oversized batches, fixed
out-of-band by `fd1b727`. That fix is holding — this is a different failure.

## What happens

`engram index --scope portfolio` dies 6 transcript files in:

```
engram.client.EmbeddingPreflightError: invalid embedding vector at index 1 in response
from http://127.0.0.1:8081/v1 for Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0
```

The server returns a well-formed HTTP 200 whose `data[].embedding` is a 1024-element list
of `null`. Engram's `_parse_vector_item` guard (`client.py:307-316`) rejects it and fails
loud, so **no garbage was written**. That part of the design works exactly as intended.

## What is NOT the cause (each ruled out by measurement)

- **Not the batching or the char/token truncation.** The chunk the run died on truncates
  to 8000 chars = **5835 tokens**, which fits the 8192-token context with 2357 to spare,
  and it embedded fine on a fresh server. Meanwhile a **265-char** text returned nulls
  later in the same session. Input size is not the trigger.
- **Not ANSI escapes / control characters.** An ANSI-stripped copy of the same text
  behaves identically to the raw one.
- **Not a specific corpus file.** After the server degrades, `"hello world"` returns nulls
  too.
- **Not the `fd1b727` size budget.** That fix is working; requests are correctly sized.

## Root cause: the embedding backend is unstable under sustained real load

`llama-server --embedding -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0` on this host fails two
different ways depending on the physical batch size engram spawns it with. Measured by
feeding real, token-dense cellar transcript chunks (0.729 tok/char), one per request:

| spawn flags | outcome |
|---|---|
| `-b 8192 --ubatch-size 8192` (engram's current flags, set by `fd1b727`) | Silent all-null 1024-dim vectors. First null at **request 51 of 60**, on a 265-char input. Sometimes the server recovers; sometimes it stays poisoned and returns nulls for **every** later request, including `"hello world"`. |
| `-b 2048 --ubatch-size 2048` | Server **process crashes outright** at **request 31 of 60**. No error in its log — the last line is a `launch_slot_` with no matching `release`. Every later request gets connection-refused. |

Both configurations fail well before the corpus is exhausted. The corpus needs ~594
transcript files plus ~11,459 code files; the best observed run managed ~50 requests.

Reproductions (throwaway probes, `/tmp`, not committed): `emb-probe.py`, `emb-probe2.py`,
`emb-probe3.py`, `emb-stress.py`. Server logs at `/tmp/emb-stress-{port}.log`.

Caveat on the probe output: `emb-stress.py` prints `SURVIVED` when the server *crashes*,
because its HTTP-error branch skips the null check. Read the per-request lines, not that
summary line.

## Why this was NOT patched headlessly

The precedent set by this PRD's first blocker applies verbatim, same module, same conflict:

- The fix lives in `client.py`'s `ensure_served` spawn flags and/or its server-lifecycle
  handling — a **PRD 00001 foundation module** that PRD 00002's reviewed design doc
  explicitly declares "unchanged".
- **Task 3 measures retrieval quality against this exact embedding path and pins the
  winning model from it.** Patching the embedding backend and then self-certifying it with
  that harness in the same unattended session is measuring with a ruler I just bent.
- Neither tested `ubatch` value is safe, so choosing one is a real judgement call with a
  tradeoff (silent corruption vs hard crash), not a mechanical fix. It may need a different
  embedding model, a llama.cpp upgrade, or a server-recycling strategy.

## What already landed and is keeping its value

Task 1 (`0c221ff`, `7d949f2`) made `indexer.index()` commit each file's chunks as it goes.
**It proved itself in production during this very failure**: the crashed run persisted
~72MB of embedded chunks (DB went 4.9MB → 77MB) that the old all-or-nothing code would
have thrown away. Re-running the index resumes from committed progress instead of
restarting.

Current partial index at `~/.local/share/engram/engram.db`:

| corpus | chunks | files |
|---|---|---|
| prd | 4808 | 218 |
| memory | 192 | 140 |
| discovery | 75 | 2 |
| transcripts | 48 | 5 |

## Recommended fix (for the un-park / a new PRD)

1. **Decide the server-stability strategy.** Options, in rough order of effort:
   - Recycle the spawned server every N requests or on the first null vector (engram owns
     the lifecycle already: `ensure_served` / `stop_served`). Cheap, but treats the symptom.
   - Try a different embedding model from the shortlist (`nomic-embed-text-v1.5`,
     `bge-m3`) — the instability may be specific to Qwen3-Embedding-0.6B's GGUF.
   - Upgrade llama.cpp and re-measure; a silent all-null embedding response is a
     server-side bug worth reporting upstream.
   - Tune slots (`-np`) — the log shows 4 concurrent slots; contention is a plausible
     factor and was not isolated.
2. **Make engram survive a degraded server rather than dying**: on a null-vector response,
   reap and respawn once, then retry the request before failing the run. Engram spawns the
   server, so it owns its health.
3. **Regression test**: a fake server that returns a null-bearing vector must cause a
   reap-and-retry, not an aborted run.
4. Re-run task 2 only after the backend survives a sustained multi-hundred-request soak on
   real transcript content.

## Cost note discovered while planning (independent of this blocker)

`harness._score_candidate` (`src/engram/harness.py:74-84`) builds a **fresh throwaway DB per
candidate model** and re-indexes every goldset corpus into it — for **all 3** models in
`config.toml`. It never reads the live DB. So task 3 is ~3 more full indexes on top of
task 2's one. Whoever resumes this PRD should size that in before starting, and consider
whether the harness should score against a shared index.

Also: `[pinned] id = ""` in `~/.local/share/engram/config.toml` — nothing is pinned yet, so
the live index was built with the fallback (first) shortlist entry. If the harness later
pins a different model, the live index must be rebuilt; the store fails loud on a
model/dim mismatch by design.

## Resume instructions

`mv dev/local/prds/hold/00002-engram-heavy-corpora-v1.md dev/local/prds/backlog/` after the
embedding backend is stable, then re-run `/run-autopilot`. Tasks 1 of the current plan is
committed and done; task 2 restarts and will resume from the committed partial index.

## Update 2026-08-03 — un-parked (operator decision)

Resolved by option 2 of the recommended fix, not option 1: `38f1f4e` makes engram
**survive** a degraded server instead of stabilising the backend. A null-bearing response
now raises `EmbeddingDegradedError`; `embed()` reaps the server it spawned, respawns it,
and retries that batch once. Per batch, so a long index recycles as often as needed. A
server engram did not spawn is never restarted; a replacement that is also degraded fails
loud rather than looping. Three regression tests cover those paths, and the RED was
verified in a detached worktree at HEAD (the null response aborted `embed()` outright).

The PRD was moved back to `backlog/` on this basis.

### The soak WAS run, and it found two bugs in the fix

Initially deferred (the machine was at `kern.memorystatus_vm_pressure_level` 2), then run
after a stale 27B `llama-server` was killed and pressure dropped to 1 with 79% free. Soaking
200 real cellar transcript turns, one request each, exposed two defects that no unit test
would have caught — both in the recycle path itself:

1. **The recycle never fired.** `embed()` calls `ensure_served` on every invocation, and its
   healthy-endpoint branch returned `spawned=False` unconditionally. From the second call
   onward engram disowned the server it had started itself, so `_embed_batch`'s
   "only recycle a server we spawned" guard refused to act. Soak died at request **52/200**
   with `recycles: 0` — the original bug, unchanged, behind a fix that looked correct.
   Ownership now lives in `_spawned_pids_by_endpoint` and outlives the spawning call.
2. **The replacement could not bind.** When the server degrades into 500s rather than nulls
   it still holds the port, so the new process could not start and every readiness probe
   reached the sick one until the deadline. Soak died at request **33/200** after burning
   the full 120s timeout. `ensure_served` now reaps a server it owns before spawning a
   replacement.

Both fixed in `7b0466e`, with three regression tests. Final soak: **200/200 turns embedded
in 8s, one recycle**, firing at almost exactly the request count this report measured the
backend degrading at. 387 tests pass.

So the failure mode changed, not the backend:

- Before: the first null vector killed the whole run.
- After: the run continues through degradation, at the cost of one respawn each time.

The open risk on resume is **duration, not correctness** — but the measured respawn was
cheap (the dip is visible as 23.8 → 14.5 req/s for one interval, then recovery). Whoever
runs task 2 should still watch the rate; if respawns come to dominate, fall back to option
1's other branches (a different shortlist model, a llama.cpp upgrade, `-np` tuning) rather
than grinding.

The cost note above still stands unaddressed: task 3 is three more full indexes.
