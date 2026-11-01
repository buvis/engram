# engram — confirmed defect: a recycle inside `embed()` strands the caller's lease

Status: **FIXED in `dc225d8`.** Found 2026-08-03 while investigating a llama-server
that survived `stop_served` during manual verification; confirmed by deliberate
reproduction, then fixed on the operator's call while the loop was still planning
PRD 00002 (before the gold gate, which is the code path that leaks).

## What happens

`embed()` replaces a degraded server and keeps the fresh lease in a **local variable**.
The caller still holds the lease it got from `ensure_served`, which now names a dead
pid. `stop_served` on that stale lease is a no-op, and the replacement server keeps
running.

## Evidence

Reproduced deliberately on a spare port (8098), forcing exactly one degraded response
on the real spawn/reap path (`dev/local/../scratchpad/probe_orphan.py`, throwaway):

```
caller's lease pid: 42872
embed returned 2 vectors (one recycle forced)

caller's lease pid 42872 alive? False
engram now owns: {'http://127.0.0.1:8098/v1': 42873}

caller called stop_served(its own lease)
--- after the caller stopped its stale lease ---
llama-server processes on port 8098: 1
  42873 42856 42873 Ss  llama-server --embedding ... --port 8098 -c 8192 -b 8192 --ubatch-size 8192
port answering: yes (HTTP 200)
```

**Ruled out first:** `stop_served` itself is correct. The same probe's scenario 1 spawns
and stops a server with no recycle and leaves nothing behind (0 processes, port dead).
The original suspicion — that `stop_served` signals only `lease.pid` and llama-server
forks — is **wrong**; the binary is a single Mach-O process and `ps` shows one pid, with
`pid == pgid` under `start_new_session=True`.

## Why it matters now

`harness.run_harness` (`src/engram/harness.py:172-199`) is the exact shape that leaks:

```python
for entry in config.embeddings:
    leases.append(ensure_served(entry))
    per_model[entry.id] = _score_candidate(entry, ...)   # indexes -> embed() -> may recycle
...
finally:
    for lease in leases:
        if lease.entry.id != winner_id:
            stop_served(lease)
```

Every candidate whose server recycled while being scored leaks its replacement. This is
not a rare path: `_score_candidate` runs a full cold index of every goldset corpus per
candidate (20-25 min measured), and the backend degrades every ~50-150 requests, so a
recycle during scoring is close to certain. With three candidates the gate can finish
holding **three** orphaned servers — at the ~13 GB per spawn measured for a Qwen-class
model at `-b 8192 --ubatch-size 8192`.

Second-order: a leaked server outlives the process. A later engram run finds the endpoint
already healthy and, having never spawned it, leases it `spawned=False` — which disables
the degraded-server recycle entirely, reproducing the bug fixed in `7b0466e`.

## Recommended fix

`stop_served(lease)` should mean "release engram's server at this endpoint", which is
what every caller intends and what engram already tracks authoritatively. When
`lease.pid` is not the pid currently owned for `lease.entry.endpoint`, fall back to
`_spawned_pids_by_endpoint[lease.entry.endpoint]` rather than signalling a dead pid.
Contained, no API change, and it makes a stale lease harmless instead of silently
leaking.

Regression test: force one recycle inside `embed()`, then `stop_served` the pre-recycle
lease and assert nothing is left listening.

Alternatives considered and not preferred: returning the new lease from `embed()` (an
API change rippling to every caller), or making `ServerLease` mutable (hides the
replacement rather than making it explicit).

## Applied

`dc225d8` implements the recommended fix: `stop_served` resolves the lease through
`_spawned_pids_by_endpoint` instead of trusting `lease.pid`, and is a no-op when engram
owns nothing at that endpoint. Two regression tests (a stale lease signals the
replacement; nothing owned signals nothing). 397 tests pass.

Same probe, re-run against the fix — scenario 2 now ends:

```
caller called stop_served(its own lease)
--- after the caller stopped its stale lease ---
llama-server processes on port 8098: 0
port answering: no (URLError)

not reproduced: nothing survived
```

Timing note: applied while the loop was still in Phase 0 planning (`tasks_total: 0`),
so no task had captured a work-start sha and the gold gate had not run.
