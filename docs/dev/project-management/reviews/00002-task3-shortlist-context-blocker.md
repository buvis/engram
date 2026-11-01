# PRD 00002 — Gold-gate blocker: engram sizes every shortlist model like Qwen

Status: **STALLED** (loop-mode, `site: blocking_escalation`, moved to `dev/local/prds/hold/`).
Discovered 2026-08-03 running the eval gold-set gate (plan task 2).

This is the **third** distinct embedding-path blocker on this PRD. The first two
(`00002-task5-index-blocker.md`, `00002-task2-null-embedding-blocker.md`) are both
closed. This one is different: it is not about surviving a sick server, it is about
engram only being able to serve **one** of its three configured models.

## What happens

`uv run python eval/harness.py` gets through candidate 1 and dies on candidate 2:

```
engram.client.EmbeddingPreflightError: embedding request to http://127.0.0.1:8082/v1
for model nomic-ai/nomic-embed-text-v1.5-GGUF:Q8_0 failed:
HTTP Error 400: Bad Request (batch indices 50..50)
```

Batch `50..50` is a **single text**, so this is not a batch-size problem.

## Root cause (confirmed by reading, cause of the 400 suspected not proven)

**Confirmed:** engram's embedding budget is a set of module-level constants applied
to every model identically (`src/engram/client.py:20-28`):

```python
EMBED_MAX_CHARS = 8000
EMBED_BATCH_MAX_CHARS = EMBED_MAX_CHARS
EMBED_SERVER_CTX_TOKENS = 8192
```

`ensure_served` spawns **every** shortlist entry with `-c 8192 -b 8192
--ubatch-size 8192`, and `_budgeted_batches` truncates **every** text at 8000
chars, regardless of which model is being served. Those numbers were derived from
Qwen3-Embedding-0.6B (8192-token context) when `fd1b727` fixed the first blocker.

**Suspected (not verified this session — the server was already down before it could
be probed):** the 400 is a context-length rejection. `nomic-embed-text-v1.5` has a
2048-token trained context; at the measured transcript density of ~0.729 tok/char, an
8000-char text is ~5800 tokens, well past it. `bge-m3` (candidate 3) has an 8192
context and was never reached, so it is untested.

Whoever resumes should confirm by spawning the nomic server by hand and posting one
long text, rather than trusting this paragraph.

## Why this was NOT patched headlessly

Choosing how engram sizes a non-Qwen model is **not a mechanical fix**, and it is
the one kind of change that must not be self-certified:

- `EMBED_MAX_CHARS` decides **how much of each chunk gets embedded**. Changing it
  changes the vectors, which changes exactly the retrieval quality the harness is
  there to measure. Patching it and then scoring with that harness in the same
  unattended session is measuring with a ruler I just bent — the same reasoning
  that parked both earlier blockers, and it applies harder here.
- There are at least three real options with different tradeoffs (below), not one
  obvious fix.
- It touches `client.py`, a PRD 00001 foundation module the 00002 design doc
  declares "unchanged".

## Options for the un-park (a decision, not a task)

1. **Per-model context in `config.toml`.** Add a `context_tokens` (and/or
   `max_chars`) field per `[[embedding]]` entry; `ensure_served` spawns with it and
   `_budgeted_batches` truncates to it. Honest and explicit. Cost: the config schema
   is frozen and test-bound, so this is a schema change; every model's number has to
   be looked up by hand.
2. **Probe the server for its real context.** `llama-server`'s `/v1/models` (or
   `/props`) reports the loaded context; size the budget from it at lease time.
   Self-tuning, no config churn. Cost: an extra round trip per lease, and it couples
   engram to a llama.cpp response shape that is not part of the OpenAI API.
3. **Truncate by tokens, not characters.** Fixes the underlying imprecision the
   first blocker already flagged ("consider whether `EMBED_MAX_CHARS` should be a
   token cap"). Most correct. Cost: needs a tokenizer per model — the biggest change
   of the three, and still needs a per-model limit from option 1 or 2.
4. **Shrink the shortlist to models that share Qwen's 8192 context.** Cheapest, and
   `bge-m3` may already qualify. Cost: it narrows what the eval can ever compare,
   which is the opposite of the harness's purpose. Plan task 2 explicitly forbids the
   implementor from doing this silently — it is the user's call, not the loop's.

## What DID land, and is keeping its value

- **`8d897a6`/`a0efbe9` — `symbols.enumerate` skips non-regular tracked paths.**
  `git ls-files` lists submodule gitlinks (a directory) and tracked-but-deleted
  files; hashing either aborted the whole portfolio index. Found live on
  `claude-git-ferry/tests/lib/bats-core`. Two regression tests.
- **`87f9498` — a server-side 5xx now recycles the spawned server.** The earlier
  fix only recycled on null vectors; a `llama-server` degrading into 500s (while
  `/v1/models` still returns 200) bypassed it and killed the run. **Proven in
  production during this very session**: the second harness run recycled its Qwen
  server mid-flight and finished candidate 1, where the first run had died. A 4xx
  deliberately does NOT recycle — that distinction is what let candidate 2's 400
  surface as a real finding instead of an infinite respawn. Three regression tests.
- **The heavy corpora are indexed and incrementality is proven** (plan task 1):
  transcripts 18,740 chunks, code 41,716 chunks; a second full portfolio index took
  **20s** against a 60s bound, with `stale=0` and unchanged chunk counts on
  memory/prd/discovery/code.

## Measured cost of the gate (the number plan task 2 asked for)

- **Candidate 1 (Qwen3-Embedding-0.6B) ≈ 20-25 min** for a full cold index of all
  five goldset corpora into its throwaway DB. Measured: run started 18:00:40Z and had
  moved on to candidate 2 by ~18:25Z, including one mid-run server recycle.
- **× 3 candidates ≈ 60-75 min**, plus first-download time for candidates 2 and 3
  (neither is in `~/.cache/huggingface/hub`; only the Qwen embedding model is cached).
- The harness holds **every** candidate's server open until the end (`run_harness`
  only stops leases in its `finally`), and each spawn sits at **~13 GB RSS** with the
  current `-b 8192 --ubatch-size 8192` sizing. Three concurrent is ~39 GB. Worth
  sizing in before the next attempt; it may be its own reason to revisit the spawn
  flags.
- The pre-existing cost note still stands: `harness._score_candidate`
  (`src/engram/harness.py:74-84`) builds a fresh throwaway DB per candidate and never
  reads the live index, so this cost is paid in full on every harness run.

## Resume instructions

1. Decide the option above (it is a design decision, not a task).
2. `mv dev/local/prds/hold/00002-engram-heavy-corpora-v1.md dev/local/prds/backlog/`
3. Re-run `/run-autopilot`. Plan task 1 is done and committed; task 2 restarts (the
   harness keeps no state between runs), and task 3 (`uv tool install .` + the
   git-ferry catchup wiring) has never been started.

## Update 2026-08-03 — resolved by option 2, with two corrections to this report

The 400 was reproduced by hand before anything was changed, as this report asked.
**The context-length hypothesis is confirmed**, with the exact server message:

```
HTTP 400: input (2609 tokens) is larger than the max context size (2048 tokens). skipping
          type: exceed_context_size_error   n_prompt_tokens: 2609   n_ctx: 2048
```

Two findings above change the option analysis:

- **`-c 8192` is silently ignored.** Spawned with engram's own flags, `/props` still
  reports `n_ctx: 2048` — llama.cpp clamps to the model's trained context. The limit
  is a property of the model, not something a flag can raise, so option 1's premise
  (write the number into config) was recording a fact the server already reports and
  would silently drift. It also means `/props` is authoritative rather than an echo
  of the request, which was the stated objection to option 2.
- **The ~13 GB per spawn does not generalise.** With identical sizing flags nomic sat
  at 215 MB idle / 480 MB after embedding. The 13 GB figure is specific to that model
  at that sizing; "3 concurrent ≈ 39 GB" should be re-measured per model before being
  used as a planning number.

Measured token densities: dense (JSON/traceback/minified) **0.65 tok/char**, prose
**0.17 tok/char**.

**Implemented (`4119722`), option 2 plus the density approximation:** `_max_chars_for`
reads the effective context from `/props` at lease time and sets that endpoint's budget
to `n_ctx / 0.75`, capped by `EMBED_MAX_CHARS` and cached per endpoint. `_budgeted_batches`
takes the budget as a parameter, so it governs both per-text truncation and the
per-request total. An endpoint that does not serve `/props` (not an OpenAI API route)
keeps the static budget. Three regression tests; 395 pass.

Verified against both real servers with real cellar transcript turns:

| model | /props n_ctx | budget | result |
|---|---|---|---|
| nomic-embed-text-v1.5 | 2048 | 2730 chars | 150/150 embedded, incl. 7 turns that used to 400 |
| Qwen3-Embedding-0.6B | 8192 | 8000 chars | 150/150, budget **unchanged** |

Qwen resolving to exactly the previous 8000 is the point: **the live index does not
need rebuilding**, and the gold gate's Qwen candidate is scored on the same vectors as
before.

**Open, and deliberately not decided here:** nomic can only ever see ~2048 tokens of a
chunk where Qwen sees 8192, so the eval compares models on different amounts of text.
That is a real property of the models rather than an engram defect, but it should be
read as a caveat on the gold-gate result rather than ignored. `bge-m3` (candidate 3)
is still untested and remains uncached.
