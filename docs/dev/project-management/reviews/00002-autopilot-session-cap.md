# autoclaude: the bootstrap session that was SIGTERM'd at the 7200s cap

Date: 2026-08-04. Diagnosis of the batch that ended
`Backlog drained. 0 PRDs completed.` after the operator saw:

```
── autoclaude: loop exited (rc 0); last output below ──
autoclaude: session exceeded the 7200s wall-clock cap; SIGTERM (session cap).
```

Evidence: `dev/local/autopilot/wrapper.log`, `loop-metrics.jsonl`, and the killed
session's own transcript
(`~/.claude/projects/-Users-bob-git-src-github-com-buvis-engram/fec58d62-….jsonl`).

## What happened

Not a hang and not a loop. **The session spent its two hours waiting for the gold
gate**, on purpose.

The wrapper's phase caps are asymmetric:

| phase launched | cap |
|---|---|
| build / bootstrap / done | `_AUTOPILOT_SESSION_MAX`, default **7200s** |
| review | `_AUTOPILOT_SESSION_MAX_REVIEW`, default **10800s** |

Bootstrap falls into the `build\|""` branch, so it got 7200s.

The session's first ~60 tool calls are ordinary Phase 0: read state, park handling,
plugin-version pin, PRD selection, catchup (`github-state.sh`, `load-memories.sh`),
capsule refresh, `statectl` writes, contract card, planning (`TaskCreate` x2). All of
that completed. It then began task 1 — the gold gate — and from there:

1. wrote `/tmp/engram-goldgate.sh` and launched `eval/harness.py` detached
2. wrote `/tmp/engram-goldgate-wait.sh` and polled it
3. spawned a **Watcher agent**: *"keep this session alive until a long-running
   background job finishes"*
4. while waiting, diagnosed the ARG_MAX crash (`getconf ARG_MAX`), dispatched Tess to
   write tests and Ivan to implement, and committed the rg-batching fix
5. relaunched the gate, spawned a second Watcher
6. was SIGTERM'd mid-second-run

The four `system` entries of subtype `stop_hook_summary` in the transcript, each
followed by a long gap, are that wait — **not** a slow hook. Gaps after them: 2658s,
2252s, 949s, 155s = **6014s of the 7200s (84%)**. The Stop hook
(`python3 ~/.claude/hooks/dispatch.py stop`) has a 60s timeout and cannot account for
any of it.

## Root cause

A single gold-gate run is ~40 minutes (three candidates, each a full cold index of
every goldset corpus). Two runs plus Phase 0 do not fit inside 7200s. The cap is a
runaway backstop meeting a legitimately long external job; the Watcher agent exists
precisely to hold the session open for it, and it did its job right up to the ceiling.

## The kill was not harmful

- `state.json` already carried `next_phase: build`; the metrics line records
  `signal: continue`, and the loop relaunched correctly.
- The relaunched harness was detached, so it **survived** the session's death and ran
  to completion. Its results are the ones in `00002-goldgate-results.md`.

## What it cost

Batch sessions, from `loop-metrics.jsonl`:

| phase launched | wall | signal | cost |
|---|---|---|---|
| bootstrap | 7205s (capped) | continue | $17.31 |
| build | 4942s | continue | $24.85 |
| review | 9085s | continue | **$116.32** |
| review | 1698s | continue | $22.35 |
| build | 151s | done | $1.35 |

**$182 for 0 PRDs completed.** The zero is honest: 00002 was parked because its
per-class metrics were not met, not because of the cap.

Note the 9085s review session was **under** its 10800s review cap, which is why it was
not killed — the asymmetry works as designed, it is just that the phase doing the long
external work is the one with the shorter cap.

## Options, none applied

1. **Raise the build cap** (`_AUTOPILOT_SESSION_MAX`) for this repo. Cheapest; weakens
   the runaway backstop for every build session, not just gate runs.
2. **Hand the gate off across sessions** — start it, end the turn, let the next session
   poll for the result. Structurally correct, and it is what the loop already does for
   phases; it needs the gate's completion state to survive a session boundary.
3. **Make the gate cheaper** so it fits. Partly done: candidate index reuse landed in
   `d8730b8`, so a re-run with unchanged code and corpora reindexes in seconds instead
   of 20-25 minutes per candidate. The first run after any engram change still pays full
   price by design.
4. **Accept it.** The kill is survivable and the batch continues; the cost is one wasted
   session per gate run that overruns.

## Operator-visibility note

The `── autoclaude: loop exited (rc 0); last output below ──` header that surfaced this
is new as of 2026-08-03. Before it, `_autoclaude_tracon_surface` returned early on a
zero exit code, so a clean stop printed nothing at all and the terminal showed only
`[1] Done` — the pause/park/drain branches all `return 0`, which is exactly the set of
exits whose reason lived only in `wrapper.log`.
