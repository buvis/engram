# Agoge strategy profile: engram

Written by agoge recon (olivia). Sections 1-4 and 6 are machine-owned and get
rewritten on refresh. Section 5 is human-owned and is copied through unchanged.

## 1. Surfaces

Facts below come from commands run on 2026-11-15 against HEAD `a49e020` unless a line says
it carries over from the `6d0d171` recon. `V` means
`/Users/bob/git/src/github.com/buvis/engram/.venv/bin` (existing uv venv, Python 3.13, engram
installed editable). uv 0.13.8 is on PATH.

Changes since `6d0d171` (PRD 00013, product files only): `src/engram/symbols.py` (module-context
chunks, `CONTEXT_LANGUAGES`, line split at `\n` only), `src/engram/store.py`
(`MODULE_CONTEXT_DOC_TYPE = "module_context"`, excluded from `lookup_by_name`),
`tests/test_module_context.py` (new), `tests/test_symbols.py`, README and CHANGELOG.

### Test suites

- **Main suite (pytest)**: `env PYTHONDONTWRITEBYTECODE=1 V/python -m pytest -q -p no:cacheprovider --ignore=/Users/bob/git/src/github.com/buvis/engram/eval /Users/bob/git/src/github.com/buvis/engram`
  Result at `a49e020`: 1193 passed in 43 s (was 1153 at `6d0d171`). The flags keep pytest from
  writing caches into the checkout; `git status --porcelain` was empty afterwards.
- **Eval suite (pytest)**: `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/bob/git/src/github.com/buvis/engram/src:/Users/bob/git/src/github.com/buvis/engram V/python -m pytest -q -p no:cacheprovider /Users/bob/git/src/github.com/buvis/engram/eval`
  Result: 53 passed in 1 s.
- Marker `private` (carried over): 1 test needing the operator's private eval evidence. CI
  (`.github/workflows/test.yml`) runs both suites with `-m "not private"` on Python 3.12 and 3.14.
- Documented repo form `uv run python -m pytest -q --ignore=eval` was not run, because `uv run`
  may sync `.venv` inside the checkout. Use the venv form above.

### CLI (`engram`, entry `engram.cli:main`)

Subcommands, from `V/engram --help` at `a49e020`: `query index lookup status harvest pack memory mcp nudge`
(unchanged). There is no `__main__.py`; to run another revision use
`V/python -c "from engram.cli import main; import sys; sys.argv=['engram', ...]; main()"` with
`PYTHONPATH=<exported tree>/src` (recon confirmed `engram.__file__` then resolves to the export).

Data paths all derive from `Path.home()`: config `~/.local/share/engram/config.toml`, store
`~/.local/share/engram/engram.db`, repo registry `~/.config/gita/repos.csv`, auto-memory
`~/.claude/projects`, transcripts `~/git/src/github.com/buvis/cellar/.claude/projects`.
**So `HOME=<scratch>/home` isolates every run from the operator's real store**
(`/Users/bob/.local/share/engram/engram.db`; never point a lane at it).

Scratch fixture (rebuilt and re-verified at `a49e020`):

1. `<scratch>/home/.config/gita/repos.csv` with one line `<repo realpath>,scratchrepo,,`.
   **Use the realpath** (`/private/var/...` or `/private/tmp/...`). From the `6d0d171` recon:
   with the `/var/...` form `index`, `query` and `lookup --name` worked, but `harvest` reported
   `no_repo` and `pack` failed with "not inside a registered repo" (no symlink resolution).
2. `<scratch>/home/.local/share/engram/config.toml`: one `[[embedding]]` with
   `id = "Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0"`, `endpoint = "http://127.0.0.1:<lane port>/v1"`,
   and `[pinned] id` set to the same id.
3. `mkdir -p <scratch>/home/git/src/github.com/buvis/cellar/.claude/projects` (without it
   `index --scope portfolio` exits 1).
4. `<scratch>/home/.claude/projects/` (auto-memory root, may be empty).
5. A scratch git repo with a PRD, `meta/decisions.md`, and source files. For module context,
   include module-level code: imports, constants, an `if __name__ == "__main__":` block, and one
   symbol-less `.py` file.
6. Copy `/Users/bob/Library/Caches/tree-sitter-language-pack` into
   `<scratch>/home/Library/Caches/` to avoid the grammar download.

Recon's builder does all six and resolves the realpath itself:
`V/python -I /tmp/agoge-olivia.pzcrtN/setup.py <scratch dir> <lane port>` (it writes
`<scratch dir>/home` and `<scratch dir>/repo`; `src/app.py` has imports and constants on lines 1-5,
`retry_embed` 8-10, `class Store` 13-15, a `__main__` block 18-19; `src/settings.py` has two
constants and no symbols). Copy it into the lane's own scratch root before use. A cwd driver
for commands that must run inside the repo (`lookup --file`, `harvest`, `pack`, `--scope repo`) is
at `/tmp/agoge-olivia.pzcrtN/run_in_repo.py` (paths hard-coded to recon's scratch; copy and edit).
A read-only chunk dumper: `/tmp/agoge-olivia.pzcrtN/dbcount.py <db path>` (opens with `mode=ro`).

Common env for every product run (ENV):
`env HOME=<scratch>/home HF_HUB_CACHE=/Users/bob/.cache/huggingface/hub HF_HUB_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1`

Verified runs at `a49e020` (ENV, real embeddings, port 18106):

- `V/engram index --scope portfolio`: exit 0, prints `discovery:scratchrepo`, 2.4 s wall.
- `V/engram status --scope portfolio`: `prd 2`, `decision 2`, `code 6`, all `stale=0 dead=0`.
  Code is 3 symbols plus 3 module-context chunks.
- `V/engram query --scope portfolio "WATERMELON endpoint environment variable"`: hit 1 is
  `src/app.py:1-5	Module context`, hit 3 is `src/settings.py:1-2	Module context`.
- `lookup --file src/app.py` (cwd = scratch repo): 3 symbols in source order, then
  `app.py:1-5 Module context` and `app.py:18-19 Module context`. Exit 0.
  `lookup --file` with `--scope` exits 1: "lookup --file does not accept --scope or --repo".
  From outside a registered repo it exits 1: "not inside a registered repo".
- `lookup --name retry --scope portfolio`: only `Function retry_embed`.
  `lookup --name PINEAPPLE` (a constant that lives only in module context) and `lookup --name Module`:
  exit 1, `no symbol matched`. So the exclusion holds for name and prefix match.
- **Incremental rollout** (store built with `6d0d171` code from a `git archive` export, then
  `index --scope portfolio` with HEAD code, files unchanged): code chunks stayed at the 3 symbols.
  No module context was added for `app.py`, and `settings.py` (cached as empty) got nothing. This
  matches the README ("no automatic migration ... a backfill is a separate, explicit operation").
  Changed-file rollout was not exercised by recon.
- Store size: 12.7 MB after the fixture index (was 17 MB for the smaller `6d0d171` fixture; not
  comparable, different fixture and session).

Carried over from the `6d0d171` recon, not re-run: `harvest` (`upserted 45`), `pack --diff HEAD~1..HEAD`
(exit 0; **writes `docs/dev/tmp/engram-pack-*.md` into the repo it runs in, so never run `pack` with
cwd inside the target**), `memory check` (exit 1 without memory), `memory migrate --help`
(`--from SRC --to REPO_ROOT [--apply]`), `mcp` over stdio (initialize, tools/list, tools/call; `k: 99`
gives `isError`; non-JSON line gives `-32700` and the server keeps serving), and `nudge claude`
(prints `hookSpecificOutput` JSON). Old probe inputs: `/var/folders/m6/1mnc9pdn28d5vdxy4hxyr1m40000gn/T/agoge-olivia.2jyoHb/mcp_in.jsonl`
and `.../nudge_claude.json`.

Host quirk (from the `6d0d171` recon): a shell `cd` or `mkdir` with a `$SCRATCH` variable, and shell
redirects into any `docs/dev/project-management/` path, were refused by host hooks. Use literal
absolute paths or a Python driver with `cwd=`.

### Embedding server (llama-server)

- `/opt/homebrew/opt/llama.cpp/bin/llama-server`, on PATH. Models cached under
  `/Users/bob/.cache/huggingface/hub`; with ENV engram spawns
  `llama-server --embedding -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 ... --port <lane port>`.
- The operator runs an embedding server on 8083 (bge-m3, seen live again at `a49e020`) and a chat
  server on 8002. **Lanes must not use ports 8081-8083 or 8002.** Assigned ports: walter 18101,
  heidi 18102, peggy 18103, trudy 18104, wendy 18105 (recon used 18106).
- **Observation (alarming, not verified as a defect), seen again at `a49e020`:** after `index`,
  `status`, `query` and `lookup` exited, the server they spawned on 18106 was still running.
  README says "Engram spawns and stops the server itself". Every lane must stop its own server:
  `pkill -f "llama-server --embedding -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --alias Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --port <lane port>"`.
  Recon stopped its own (pgrep afterwards showed only the operator's 8083 server).

### Database

SQLite with sqlite-vec and FTS5, one file per HOME (`<scratch>/home/.local/share/engram/engram.db`),
created on the first `index`. No separate server. Table `chunks` holds `corpus, repo, doc_type, path,
heading, body, line_start, line_end, content_hash, chunk_ordinal`; module context rows have
`doc_type = 'module_context'` and `heading = 'Module context'`. Seed path = the scratch fixture plus
`engram index` and `engram harvest`. Inspect read-only (`?mode=ro`).

### Browser

None (re-checked by diff: 00013 added no JS, HTML, Playwright or HTTP listener).

### External services

- **tree-sitter-language-pack grammar download** (from the `6d0d171` recon): a fresh HOME without the
  copied cache downloaded a 26 MB grammar bundle. README says "The only off-machine call is the
  one-time model download"; CHANGELOG says "Grammars download once per version".
- **Hugging Face model download**: not exercised; models served from cache with `HF_HUB_OFFLINE=1`.
- **gita**: only `repos.csv` is read. **git**: subprocesses in symbols, diffmap, harvest, pack, cli.

### Release surface

- `version = "0.1.0"`, `git tag --list` empty, one `## [Unreleased]` heading. Headings at `a49e020`:
  Changed (line 9), Added (20), Fixed (59), then a second Added (113) and Fixed (145) with no
  version heading between them.
- 00013 entries: Added "**index**: code outside parsed symbols ... indexed as `Module context`
  chunks for newly indexed or changed files. Queries and `engram lookup --file` include them;
  `engram lookup --name` still returns symbols only." Fixed "**symbols**: keep symbol bodies and
  line numbers aligned in files that contain form feeds or Unicode line separators."

## 2. Per-specialist strategy

| Specialist | Verdict | Tactics or reason |
|---|---|---|
| walter (journeys) | **armed** | Scratch fixture (builder above), ENV, port 18101. Journey 1, module context: fresh HOME, `index --scope portfolio`, then `query` for text that lives only at module level (an import, a constant, a `__main__` block) and expect a `Module context` hit; `lookup --file <path>` from inside the repo and expect symbols first, then context in line order; `lookup --name <constant>` and `lookup --name Module` and expect exit 1 `no symbol matched`; `query --corpus code` for the same text. Journey 2: add a Markdown, JSON or YAML file with no symbols and confirm it stays out of the code corpus (README claim). Journey 3: `harvest` a review, then `query --corpus findings`. Journey 4: commit a change, `pack --diff HEAD~1..HEAD` (cwd = scratch repo), read the pack file and see whether module-context chunks appear in it. Journey 5: `memory migrate` dry run, `--apply`, `memory check`. Note whether the spawned server outlives each CLI call. Kill the server at the end. |
| heidi (integration, db) | **armed** | SQLite store in the scratch HOME, port 18102. **Rollout:** export `6d0d171` with `git -C <target> archive 6d0d171` into scratch, index the fixture with that code (`PYTHONPATH=<export>/src`, see CLI), then: (a) re-index with HEAD unchanged and confirm no context rows appear and no vectors are rewritten (compare `content_hash` and embedding rowids or counts before and after); recon saw no new rows, matching the README. Note: the README says unchanged files do **not** gain context, so "gaining rows without re-embed" is not the claimed behaviour. (b) edit one file and re-index; expect context rows for that file only and no re-embed of other files. (c) `index --reembed-code` and confirm it adds no context (README). (d) the `None`-heading migration exception: a pre-migration store re-chunks once and gains context; build one if the old code path allows. (e) `index --rebuild` gives full context. Also: `chunk_ordinal` uniqueness across symbols and context, prune after deleting a file removes its context rows, `status` counts and stale or dead after the rollout, model-mismatch failure, `/var` vs `/private/var` repo resolution. Line-count fix: a file with `\f`, ` ` or `\x85` inside a string or comment, then check `line_start`/`line_end` and bodies against the file. Inspect with `?mode=ro`. |
| judy (UX via browser) | **unarmed** | No browser surface. No JS or HTML in the repo, no Playwright in `pyproject.toml` or `uv.lock`, no HTTP listener in `src/engram`; the 00013 diff added none. |
| wendy (release, changelog truth) | **armed** | No tags or release. Check each 00013 CHANGELOG line against runs: context "for newly indexed or changed files" (and not for unchanged ones, see heidi rollout), "Queries and `engram lookup --file` include them", "`engram lookup --name` still returns symbols only", and the form-feed / Unicode line separator fix (index a file with `\f` and ` `, compare reported lines). Check the README module-context paragraph (data and doc files stay out, `--reembed-code` finds no missing spans, `lookup --file` order "symbols, then module context"). `git -C <target> log --oneline 6d0d171..HEAD` vs entries. Carried-over leads: "only off-machine call is the one-time model download" vs the grammar download, "Engram spawns and stops the server itself" vs the leftover server, and the second Added/Fixed pair with no version heading (lines 113, 145). Port 18105. |
| peggy (performance) | **armed** | Synthetic portfolio only. Generate N scratch repos (for example 20 x 50 Python files with sizeable module-level code, plus PRDs) and register them by realpath; port 18103. Measure with `/usr/bin/time -p`: (1) cold `index` with the `6d0d171` export vs HEAD on identical copies, for wall time, chunk count (`doc_type='module_context'` share) and `engram.db` size, to give the cost of the extra chunks; (2) unchanged re-index on HEAD (should skip embedding by content hash); (3) `index --rebuild` on HEAD; (4) `query` and `lookup --name` latency before vs after, since `lookup_by_name` gained a `doc_type != ?` filter; (5) `mcp` per-call latency and `nudge` wall time. Kill the server at the end. |
| trudy (runtime security) | **armed** | Surfaces: `engram mcp` JSON-RPC over stdio, `engram nudge` reading hook JSON from stdin, markdown, JSONL and YAML parsing (harvest, transcripts, memory frontmatter), `memory migrate --apply` writing files and wiring `.gitattributes`, `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`, `git` subprocesses fed user input (`pack --diff <range>`, try option-shaped ranges such as `--output=<scratch>/x`), `config.toml` endpoint validation and the `-hf <id>` passed to llama-server. New with 00013: module context indexes raw top-level code verbatim, so probe whether secrets at module level (an `API_KEY = "..."` constant, a `.env`-like `.py`) now surface through `query`, `mcp engram_query` and `nudge` where before only function bodies did; and huge or pathological files (one 50 MB top-level line, many blank-line-separated statements) for chunk explosion. Hostile inputs: malformed, oversized, deeply nested JSON-RPC, invalid UTF-8, wrong types for `k` and `scope`; nudge payloads with `$(...)`, `~user`, `../`, env-var paths; migrate names with `../`, absolute paths, symlinks, YAML tags; endpoints like `http://127.0.0.1.evil:1/`, `http://localhost@evil:1`; ids starting with `-`. Scratch HOME, port 18104. Authorization is resolved at dispatch, not here. |

## 3. Mocking strategy

- **llama-server / embeddings: no mock needed.** Recon reached a real local server with cached
  models at `a49e020`. Findings from real runs may be reported `verified`.
- **Hugging Face model download**: not exercised. Keep `HF_HUB_OFFLINE=1` and
  `HF_HUB_CACHE=/Users/bob/.cache/huggingface/hub`. For an uncached model id or a failing server, use
  `_MockEmbeddingServer(port, model_id)` from `tests/_embedding_server.py` (in-process class, no
  `__main__`): start it from a scratch Python driver with `sys.path` set to the target `tests/` dir,
  on the lane's port, and point `endpoint` at it. Anything probed against it is reported `mocked`,
  never `verified`.
- **Embedding failure modes** (null vectors, dropped connections, slow `/props`, wrong model id):
  same fake server. Report `mocked`.
- **tree-sitter grammar download**: avoided by copying the operator's grammar cache into the scratch
  HOME. A lane probing no-network behaviour reports `mocked` (cache pre-seeded) or `unverified`.
- **Pre-00013 store**: not a mock. Build it with real code from `git archive 6d0d171` in scratch; it
  is the real old format.
- **gita**: not mocked; a hand-written `repos.csv` is the real input.

## 4. Authoring assignments

The master authors these on a branch after the lanes report. Recon names surfaces and runners only.
Runner for all: the main suite command in Surfaces.

- **Module context rollout**: `tests/test_module_context.py` (797 lines, new in 00013) already covers
  chunking and incremental rollout. Add a case only for a gap a lane confirms, e.g. a store written by
  real pre-00013 code, `chunk_ordinal` collisions, or prune of context rows on file delete.
- **Line counting with `\f` / ` `**: if wendy or heidi finds a mismatch, add the case beside the
  existing one in `tests/test_symbols.py`.
- **Module-level secrets reaching `nudge`/`mcp` output**: if trudy confirms it, a regression beside
  `tests/test_nudge.py` or `tests/test_mcp_server.py`, or a documented decision.
- **CLI lifecycle (server outlives the CLI)**: if confirmed, a pytest regression using the fake server
  from `tests/_embedding_server.py` that asserts a spawned server is stopped, or document the intended
  behaviour.
- **Repo resolution through symlinked paths** (`/var` vs `/private/var`): if confirmed, a regression
  covering `harvest` and `pack` with a symlinked `repos.csv` path.
- No durable tests for performance (peggy) or changelog truth (wendy).

## 5. Pins and vetoes

Authorization: not asserted

## 6. Freshness stamp

- Recon date: 2026-11-15
- Target HEAD: a49e0201113bd0ebdbf0df6d25036f18fbc2a3ab
