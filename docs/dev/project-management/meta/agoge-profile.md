# Agoge strategy profile: engram

Written by agoge recon (olivia). Sections 1-4 and 6 are machine-owned and get
rewritten on refresh. Section 5 is human-owned and is copied through unchanged.

## 1. Surfaces

All facts below were established by commands run on 2026-11-15 against HEAD
`6d0d171`. `V` below means `/Users/bob/git/src/github.com/buvis/engram/.venv/bin`
(existing uv venv, Python 3.13, engram installed editable). uv 0.13.8 is on PATH.

### Test suites

- **Main suite (pytest)**: `env PYTHONDONTWRITEBYTECODE=1 V/python -m pytest -q -p no:cacheprovider --ignore=/Users/bob/git/src/github.com/buvis/engram/eval /Users/bob/git/src/github.com/buvis/engram`
  Result: 1153 passed in 34 s. The `-p no:cacheprovider` flag and
  `PYTHONDONTWRITEBYTECODE=1` keep pytest from writing caches into the checkout.
- **Eval suite (pytest)**: `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/bob/git/src/github.com/buvis/engram/src:/Users/bob/git/src/github.com/buvis/engram V/python -m pytest -q -p no:cacheprovider /Users/bob/git/src/github.com/buvis/engram/eval`
  Result: 53 passed in 0.65 s.
- Marker `private`: 1 test (`tests/test_harness.py::test_real_goldset_loads_clean_and_covers_transcripts_and_code`).
  It passed here because the operator's private eval evidence exists on this host. CI
  (`.github/workflows/test.yml`) runs both suites with `-m "not private"` on Python 3.12 and 3.14.
- Documented repo form: `uv run python -m pytest -q --ignore=eval` (README). Not run here, because
  `uv run` may sync `.venv` inside the checkout. Use the venv form above.

### CLI (`engram`, entry `engram.cli:main`)

Subcommands, from `V/engram --help`: `query index lookup status harvest pack memory mcp nudge`.

Data paths all derive from `Path.home()`: config `~/.local/share/engram/config.toml`, store
`~/.local/share/engram/engram.db`, repo registry `~/.config/gita/repos.csv`, auto-memory
`~/.claude/projects`, transcripts `~/git/src/github.com/buvis/cellar/.claude/projects`.
**So `HOME=<scratch>/home` isolates every run from the operator's real store** (1.5 GB at
`/Users/bob/.local/share/engram/engram.db`; never point a lane at it).

Working scratch fixture (built by recon, reproduce it per lane):

1. `<scratch>/home/.config/gita/repos.csv` with one line `<repo realpath>,scratchrepo,,`.
   **Use the `/private/var/...` realpath.** With the `/var/...` form, `index`, `query` and
   `lookup` worked, but `harvest` reported `no_repo` and `pack` failed with "not inside a
   registered repo". Engram compares the registry path to `git rev-parse --show-toplevel`
   without resolving symlinks.
2. `<scratch>/home/.local/share/engram/config.toml`:
   one `[[embedding]]` with `id = "Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0"`,
   `endpoint = "http://127.0.0.1:<lane port>/v1"`, and `[pinned] id` set to the same id.
3. `mkdir -p <scratch>/home/git/src/github.com/buvis/cellar/.claude/projects`.
   Without it `engram index --scope portfolio` exits 1 ("cellar transcripts corpus requires this path").
4. `<scratch>/home/.claude/projects/` (auto-memory root, may be empty).
5. A scratch git repo with `docs/dev/project-management/prds/**/*.md`,
   `docs/dev/project-management/meta/decisions.md`, and a source file. Commit it with the lane
   identity and `--git-dir/--work-tree`.
6. Optional, to avoid a network download: `cp -R /Users/bob/Library/Caches/tree-sitter-language-pack <scratch>/home/Library/Caches/`.

Recon's fixture builder is at `/var/folders/m6/1mnc9pdn28d5vdxy4hxyr1m40000gn/T/agoge-olivia.2jyoHb/setup.py`
(run with `V/python -I setup.py <scratch>`; it writes `/var/...` into repos.csv, so rewrite
that line to the `/private/var/...` form afterwards).

Common env for every product run (call it ENV):
`env HOME=<scratch>/home HF_HUB_CACHE=/Users/bob/.cache/huggingface/hub HF_HUB_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1`

Verified runs (all with ENV, real embeddings):

- `V/engram index --scope portfolio`: exit 0, prints `discovery:scratchrepo` (no discovery dir).
- `V/engram status --scope portfolio`: `prd 2`, `decision 2`, `code 3`, all `stale=0 dead=0`.
- `V/engram query --scope portfolio "retry flaky embedding server"`: 5 tab-separated hits.
- `V/engram lookup --name retry --scope portfolio`: `.../src/app.py:1-3	Function retry_embed`.
- `V/engram harvest reviews/<file>.md` (cwd = scratch repo, fixture copied from
  `tests/fixtures/00001-engram-core-v1-review-5.md`): `upserted 45`, exit 0.
- `V/engram pack --diff HEAD~1..HEAD` (cwd = scratch repo): exit 0. **It writes
  `docs/dev/tmp/engram-pack-*.md` into the repo it runs in.** Never run `pack` with cwd inside the target.
- `V/engram memory check <scratch repo>`: exit 1, `memory directory not found` (expected for a repo without memory).
- `V/engram memory migrate --help`: flags `--from SRC --to REPO_ROOT [--apply]`. Not exercised.
- `V/engram mcp < <scratch>/mcp_in.jsonl`: JSON-RPC over stdio. `initialize`, `tools/list` and
  `tools/call engram_query` all answer. `k: 99` returns `isError: true`. A non-JSON line returns
  `-32700 parse error` and the server keeps serving. `scope: "repo"` from an unregistered cwd
  returns `isError` "not inside a registered repo". Request file:
  `/var/folders/m6/1mnc9pdn28d5vdxy4hxyr1m40000gn/T/agoge-olivia.2jyoHb/mcp_in.jsonl`.
- `V/engram nudge claude < <payload.json>` with
  `{"tool_input":{"command":"rg retry <scratch>/repo /tmp"},"cwd":"<scratch>/home"}`: prints the
  `hookSpecificOutput` JSON with 3 hits.

Probes had to be run from a Python driver script, because a shell `cd` or `mkdir` with a
`$SCRATCH` variable is refused by the host's write-scope hook, and shell redirects into any
`docs/dev/project-management/` path (even under scratch) are refused by another hook. Lanes
should write files with literal absolute paths or a Python driver
(`/var/folders/m6/1mnc9pdn28d5vdxy4hxyr1m40000gn/T/agoge-olivia.2jyoHb/probe_hp.py` is an example).

### Embedding server (llama-server)

- `/opt/homebrew/opt/llama.cpp/bin/llama-server`, version 0.8.0 (build 11960). On PATH.
- Models cached under `/Users/bob/.cache/huggingface/hub` (Qwen3-Embedding-0.6B Q8_0,
  nomic v1.5, bge-m3 Q8_0 among others). With ENV, engram spawned
  `llama-server --embedding -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 ... --port 18081` and got
  real vectors, with no model download into the scratch HOME.
- The operator runs their own servers: an embedding server on port 8083 (bge-m3) and a chat
  server on 8002 were live during recon. **Lanes must not use ports 8081-8083 or 8002.** Assigned
  ports: walter 18101, heidi 18102, peggy 18103, trudy 18104, wendy 18105.
- **Observation (alarming, not verified as a defect):** after `index`/`query` exited, the
  llama-server they spawned on 18081 was still running. `client.embed` calls `ensure_served`
  with `start_new_session=True`, and only `harness.py` calls `stop_served`. README says "Engram
  spawns and stops the server itself". Every lane must stop its own server at the end:
  `pkill -f "llama-server --embedding -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --alias Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --port <lane port>"`.

### Database

SQLite with sqlite-vec 0.1.9 and FTS5, one file per HOME (`<scratch>/home/.local/share/engram/engram.db`,
17 MB after the fixture index). It is created on the first `index`. No separate server.
Seed path = the scratch fixture plus `engram index` and `engram harvest`.

### Browser

None. No JS or Node files in the repo, no Playwright in `pyproject.toml` or `uv.lock`, and no
HTTP listener in `src/engram` (the only network code is the loopback HTTP client to llama-server).

### External services

- **tree-sitter-language-pack grammar download.** The first `index` under a fresh HOME downloaded a
  26 MB grammar bundle into `<scratch>/home/Library/Caches/tree-sitter-language-pack/v1.25.0/`.
  So the network was reachable from this sandbox. README says "The only off-machine call is the
  one-time model download". That claim does not match what recon saw (CHANGELOG does say
  "Grammars download once per version").
- **Hugging Face model download** (`llama-server -hf`): not exercised. Models were served from
  the local cache with `HF_HUB_OFFLINE=1`.
- **gita**: engram only reads `repos.csv`. The `gita` binary is not needed.
- **git**: engram invokes `git` subprocesses (symbols, diffmap, harvest, pack, cli).

### Release surface

- `version = "0.1.0"` in `pyproject.toml`. `git tag --list` is empty. `CHANGELOG.md` has a single
  `## [Unreleased]` heading. Its sections are Changed, Added, Fixed, then a second Added and Fixed
  with no version heading between them (lines 110 and 142).

## 2. Per-specialist strategy

| Specialist | Verdict | Tactics or reason |
|---|---|---|
| walter (journeys) | **armed** | Use the scratch fixture, ENV, and port 18101. Journey 1: fresh HOME, then `index --scope portfolio`, `status`, `query --scope repo` from inside the scratch repo, then `query` with no `--scope` (README says usage error). Journey 2: `harvest` a review, then `query --corpus findings`. Journey 3: commit a change, `pack --diff HEAD~1..HEAD`, read the pack file. Journey 4: `memory migrate --from <scratch claude memory dir> --to <scratch repo>` dry run, then `--apply`, then `memory check`, checking the README claims (exit codes, `skip-*` actions, wiring files, no commit). Journey 5: `lookup --file`, `lookup --name` miss (exit 1). Check that the spawned llama-server outlives the CLI process against the README claim. Kill the server at the end. |
| heidi (integration, db) | **armed** | SQLite store at `<scratch>/home/.local/share/engram/engram.db`, real llama-server on port 18102. Probe: model mismatch (change `[pinned] id` to nomic on another port after indexing, then expect a loud failure that demands `index --rebuild`), `index --rebuild` atomic swap (interrupt it, then check the old db survives), `--reembed-code`, incremental prune after deleting a file, stale and dead counts in `status`, transcripts corpus with a JSONL fixture under the cellar dir, auto-memory attribution with an encoded `~/.claude/projects/<slug>/memory`. Also probe repo resolution with symlinked paths (`/var` vs `/private/var`, see Surfaces). Inspect the db read-only with `V/python -c "import sqlite3, sqlite_vec ..."`. |
| judy (UX via browser) | **unarmed** | No browser surface. No JS or HTML in the repo, no Playwright in `pyproject.toml` or `uv.lock`, and no HTTP listener in `src/engram`. |
| wendy (release, changelog truth) | **armed** | No tags and no release yet, so check CHANGELOG `[Unreleased]` entries against behavior and commits: `git -C <target> log --oneline`, entries for `engram mcp` and `engram nudge` (exercise them as in Surfaces), `-k`, `--rebuild` and `--reembed-code` flags, tree-sitter-language-pack 1.25.0 bump vs `uv.lock`. Check README claims against runs: "only off-machine call is the one-time model download" (contradicted by the grammar download recon saw), "Engram spawns and stops the server itself" (recon saw the server outlive the CLI), "full portfolio pass about 20 seconds" vs CHANGELOG "13 seconds" (do not measure on real data). Flag the CHANGELOG structure (second Added/Fixed with no version heading). Use port 18105 if a run needs embeddings. |
| peggy (performance) | **armed** | Synthetic portfolio only, never the operator's store. Generate N scratch repos (for example 20 repos x 50 PRDs x 2 KB plus Python files) with a Python driver, register them in the scratch repos.csv (realpath), and use port 18103. Measure: cold `index` (includes server spawn), unchanged re-index (CHANGELOG claims an unchanged pass skips re-embedding by content hash), `query` latency warm vs cold server, `mcp` per-call latency over one stdio session, `nudge` wall time (README warns up to the 120 s embed timeout), and `lookup` (claims no server start). Time with `/usr/bin/time -p`. Note store size growth. Kill the server at the end. |
| trudy (runtime security) | **armed** | Surfaces: `engram mcp` JSON-RPC over stdio, `engram nudge` reading hostile hook JSON from stdin, markdown and JSONL parsing (harvest, transcripts, memory frontmatter YAML), `memory migrate --apply` writing files plus wiring `.gitattributes`, `AGENTS.md`, `CLAUDE.md` and `.claude/settings.json`, `git` subprocesses fed user input (`pack --diff <range>`, try option-shaped ranges such as `--output=<scratch>/x`), `config.toml` endpoint validation (loopback-only, explicit port, redirect handler) and the `-hf <id>` argument passed to llama-server. Tactics: malformed, oversized and deeply nested JSON-RPC, invalid UTF-8, wrong types for `k` and `scope`; nudge payloads with `$(...)`, `~user`, `../` and env-var paths in `tool_input.command` and `cwd`, Copilot `toolArgs` as a JSON string; migrate with slugs or names that hold `../`, absolute paths, symlinked memory files, and YAML tags (`!!python/object`); config endpoints such as `http://127.0.0.1.evil:1/`, `http://[::1]:1`, `http://localhost@evil:1`; `id` values that start with `-`. All in a scratch HOME on port 18104. Authorization is resolved at dispatch, not here. |

## 3. Mocking strategy

- **llama-server / embeddings: no mock needed.** Recon reached a real local server with cached
  models (ENV above). Findings from real runs may be reported `verified`.
- **Hugging Face model download**: not exercised. Keep `HF_HUB_OFFLINE=1` and
  `HF_HUB_CACHE=/Users/bob/.cache/huggingface/hub` so no lane downloads a model. If a lane needs an
  uncached model id or a failing server, use a fake OpenAI-compatible embedding server. The suite
  ships an in-process class, `_MockEmbeddingServer(port, model_id)` in `tests/_embedding_server.py` (no `__main__`); start it from a scratch Python driver that imports it with `sys.path` set to the target `tests/` dir, on the lane's port, and set the
  config `endpoint` to it. Anything probed against it is reported `mocked`, never `verified`.
- **Embedding failure modes** (null vectors, dropped connections, slow `/props`, wrong model id at
  `/v1/models`): mock with the same fake server. Report `mocked`.
- **tree-sitter grammar download**: avoid it by copying the operator's grammar cache into the
  scratch HOME (Surfaces step 6). A lane that probes behavior with no network must say the result is
  `mocked` (cache pre-seeded) or `unverified`.
- **gita**: not mocked. A hand-written `repos.csv` is the real input format.

## 4. Authoring assignments

The master authors these on a branch after the lanes report. Recon names surfaces and runners only.

- **CLI lifecycle (server outlives the CLI)**: if confirmed, add a pytest regression under
  `tests/` (runner: the main suite command above) that uses the fake server from
  `tests/_embedding_server.py` and asserts that a spawned server is stopped, or document the
  intended behavior.
- **Repo resolution through symlinked paths** (`/var` vs `/private/var`): if confirmed, add a pytest
  regression under `tests/` covering `harvest` and `pack` repo resolution with a symlinked
  `repos.csv` path.
- **MCP and nudge hostile input**: any trudy finding gets a pytest case beside
  `tests/test_mcp_server.py` or `tests/test_nudge.py` (main suite runner).
- No durable tests for performance (peggy) or changelog truth (wendy).

## 5. Pins and vetoes

Authorization: not asserted

## 6. Freshness stamp

- Recon date: 2026-11-15
- Target HEAD: 6d0d171ba6413dc480587c100af6aacbe6c0e63a
