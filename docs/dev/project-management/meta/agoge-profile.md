# Agoge strategy profile: engram

Written by agoge recon (olivia). Sections 1-4 and 6 are machine-owned and get
rewritten on refresh. Section 5 is human-owned and is copied through unchanged.

## 1. Surfaces

Facts below come from commands run on 2026-11-16 against HEAD `fba0967` unless a line says
it carries over from an earlier recon. `V` means
`/Users/bob/git/src/github.com/buvis/engram/.venv/bin` (existing uv venv, Python 3.13.18, engram
installed editable, `tree-sitter-language-pack` 1.25.2 installed). `R` means recon's scratch root
`/private/var/folders/m6/1mnc9pdn28d5vdxy4hxyr1m40000gn/T/agoge-olivia.MqQaui`.

Changes since `a49e020` (product files, from `git diff --stat`): `src/engram/cli.py`, `diffmap.py`,
`findings.py`, `harvest.py`, `indexer.py`, `pack.py`, `store.py`, README, CHANGELOG, `pyproject.toml`
and `uv.lock` (grammar pack 1.25.0 to 1.25.2). PRDs 00014, 00015, 00016.

### Test suites

- **Main suite (pytest)**: `env PYTHONDONTWRITEBYTECODE=1 V/python -m pytest -q -p no:cacheprovider --ignore=/Users/bob/git/src/github.com/buvis/engram/eval /Users/bob/git/src/github.com/buvis/engram`
  Result at `fba0967`: 1402 passed in 40 s (was 1193 at `a49e020`). The flags keep pytest from
  writing caches into the checkout; `git status --porcelain` was empty afterwards.
- **Eval suite (pytest)**: `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/bob/git/src/github.com/buvis/engram/src:/Users/bob/git/src/github.com/buvis/engram V/python -m pytest -q -p no:cacheprovider /Users/bob/git/src/github.com/buvis/engram/eval`
  Result: 53 passed in 0.5 s.
- Marker `private` and the CI matrix (`.github/workflows/test.yml`, Python 3.12 and 3.14,
  `-m "not private"`) carry over from the `6d0d171` recon; `.github` did not change since.
- Documented repo form `uv run python -m pytest -q --ignore=eval` was not run, because `uv run`
  may sync `.venv` inside the checkout. Use the venv form above.

### CLI (`engram`, entry `engram.cli:main`)

Subcommands, from `V/engram --help` at `fba0967`: `query index lookup status harvest pack memory mcp nudge`
(unchanged). `index` flags: `--scope {repo,portfolio}`, `--corpus`, `--rebuild`, `--reembed-code`,
and new `--backfill-code`. `pack` flags: `--cycle --diff --prd --capsule`. `harvest` takes paths.
There is no `__main__.py`; another revision runs through `R/run_rev.py` (below).

Data paths all derive from `Path.home()`: config `~/.local/share/engram/config.toml`, store
`~/.local/share/engram/engram.db`, write lock `~/.local/share/engram/engram.db.lock`, rebuild temp
`engram.db.rebuild-tmp`, repo registry `~/.config/gita/repos.csv`, auto-memory `~/.claude/projects`,
transcripts `~/git/src/github.com/buvis/cellar/.claude/projects`.
**So `HOME=<fixture>/home` isolates every run from the operator's real store**
(`/Users/bob/.local/share/engram/engram.db`; never point a lane at it).

**Helpers (rebuilt this recon; copy them into the lane's own scratch root, do not write under `R`).**
All take the fixture dir as an argument, none has a hard-coded scratch path except
`nudge_claude.json`. Run each with `V/python -I <script> ...`.

- `R/setup.py <fixture dir> <lane port> [lane name]`: builds `<fixture>/home`, `<fixture>/repo`
  and `<fixture>/wt`. It resolves the realpath itself and registers the repo by realpath as
  `scratchrepo`. Repo content: PRD `prds/done/00001-retry.md`, `meta/decisions.md`,
  `reviews/00001-review.md` (valid: `reviewers: [alice, blake]`, Verdict, Tests, two severity
  bullets), `reviews/00002-blank-reviewers.md` (`reviewers: "   "`), `src/app.py` (imports and
  constants lines 1-5, `retry_embed` 8-10, `class Store` 13-15, `__main__` block 18-19),
  `src/settings.py` (two constants, no symbols), `src/café.py` (`brew_espresso`, non-ASCII name).
  Two commits on `master`: the second changes `retry_embed` and `brew_espresso`, so
  `HEAD~1..HEAD` is a usable diff. `<fixture>/wt` is a linked worktree on branch `feature/wt`.
  It also copies the operator's grammar cache, writes `config.toml` for the lane port, and
  makes the cellar and `.claude/projects` dirs. Commits carry `agoge-<lane name>` identity.
- `R/run_in.py <fixture dir> <repo|wt|home|absolute cwd> <engram args...>`: runs `V/engram` with
  the fixture HOME, the standard ENV and that cwd; passes stdin through; prints `rc N`.
- `R/dbcount.py <engram.db> [corpus]`: read-only (`mode=ro`) chunk dump with `content_hash` and
  `chunk_ordinal`; corpus defaults to `code`.
- `R/hold_lock.py <fixture dir> <seconds>`: holds the store's flock the way a rebuild or harvest
  does, so the busy path is deterministic. Run it in the background.
- `R/export_rev.py <rev> <dest dir>`: `git archive` of the target into scratch (refuses a dest
  inside the target). `R/old` is `6d0d171` (pre-00013, no module context).
- `R/run_rev.py <fixture dir> <cwd> <export dir> <engram args...>`: runs an exported revision
  with `PYTHONPATH=<export>/src` in the same venv; prints `engram from <path>` to stderr as proof.
- `R/mcp_in.jsonl` (initialize, tools/list, two good calls, `k: 99`, a non-JSON line, a
  `scope: repo` call) and `R/nudge_claude.json` (paths point at `R/f1`; edit for your fixture).

Manual fixture rules, if a lane builds its own: register by realpath or not as the probe needs
(00014 claims symlinked rows now resolve), keep the cellar dir (without it
`index --scope portfolio` exited 1 in the `6d0d171` recon), copy the grammar cache.

Common env for every product run (ENV), already set by `run_in.py` and `run_rev.py`:
`env HOME=<fixture>/home HF_HUB_CACHE=/Users/bob/.cache/huggingface/hub HF_HUB_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1`

Verified runs at `fba0967` (real embeddings, port 18106, fixtures `R/f1` and `R/f2`):

- `index --scope portfolio` (cwd home): exit 0, prints `discovery:scratchrepo`.
- `status --scope portfolio`: `prd 2`, `decision 2`, `code 6`, all `stale=0 dead=0`; after harvest
  and rebuild also `findings 5`.
- **Linked worktree (00016)**, cwd `wt`: `harvest <two reviews>` gave `00001-review.md upserted 5`
  and `00002-blank-reviewers.md parse_failed 0 frontmatter must contain reviewers`, exit 1 (so the
  worktree resolved to `scratchrepo`, and the 00014 strict `reviewers` check fired).
  `query --scope repo --corpus findings "..."`: 5 hits, exit 0. `index --scope repo`: exit 0.
  `pack --diff HEAD~1..HEAD`: exit 0, wrote
  `wt/docs/dev/tmp/engram-pack-HEAD-1--HEAD-bff9ed11.md`; its `Similar code` lists
  `repo/src/app.py` 14-15, 18-19, 1-5, 13-15 and `settings.py` 1-2 but not 8-10 (the changed
  `retry_embed`), so the `index_root` self-match exclusion held. `mcp` with `scope: repo`: hits.
- **Pack ids (00014)**: `pack --diff HEAD~1...HEAD` from `repo` wrote
  `engram-pack-HEAD-1---HEAD-b252ca8a.md`; the id is slug plus 8 hex of sha1 of the range.
  **`pack` writes `docs/dev/tmp/engram-pack-*.md` into the repo it runs in, so never run `pack`
  with cwd inside the target.**
- **Backfill (00015)**: store built with `6d0d171` code (`run_rev.py ... R/old index --scope portfolio`)
  held 3 code rows, all symbols of `app.py`. `index --backfill-code --scope portfolio` with HEAD
  printed `backfilled 2 code sources: 3 chunks embedded, 3 vectors reused, 1 empty marks cleared`,
  exit 0; the store then held 6 code rows (3 context rows added, `settings.py` no longer empty).
  A second run printed `backfilled 0 code sources: 0 chunks embedded, 0 vectors reused, 0 empty marks cleared`.
  `--backfill-code --corpus code`: exit 2, "cannot be combined with --corpus, --rebuild or
  --reembed-code". `--backfill-code` with no `--scope` from outside a repo: exit 1, "not inside a
  registered repo; pass --scope portfolio instead" (default scope is `repo`).
- **Write lock (00014)**: with `hold_lock.py` running, `harvest` and `index --rebuild` both exited 1
  with `engram store busy: <path>/engram.db.lock is held by another harvest or rebuild`. After
  release, `index --rebuild` exited 0, kept `findings 5`, and left no `engram.db.rebuild-tmp`
  (dir held `config.toml`, `engram.db` 16.9 MB, `engram.db.lock`).
- `mcp` over stdio with `R/mcp_in.jsonl`: initialize, tools/list (one tool `engram_query`, `k`
  1..20), calls return hits, `k: 99` gives `isError: true`, the non-JSON line gives `-32700` and
  the server keeps serving. Exit 0.
- `nudge claude` with `R/nudge_claude.json`: prints `hookSpecificOutput` JSON citing the review and
  `app.py:8-10`. `memory check` from a non-git cwd: exit 1, "not inside a git worktree; pass PATH".
- Not re-run this recon (carried over): `lookup --name` exclusion of module context,
  `memory migrate` (`--from SRC --to REPO_ROOT [--apply]`), `--reembed-code`.

**Leads seen during recon (observations, not verified defects; lanes should confirm):**

1. **Non-ASCII file names never reach the code corpus.** `src/café.py` holds `brew_espresso` but
   `status` shows `code 6` (only `app.py` and `settings.py`), and
   `lookup --name brew --scope portfolio` exits 1 `no symbol matched`. `src/engram/symbols.py:79`
   runs `git ls-files` without `-z`, and git printed the path as `"src/caf\303\251.py"`. 00014
   fixed the same quoting in `diffmap` only, so a pack can map a changed symbol in a file the
   index cannot hold.
2. **`lookup --file` from a linked worktree finds nothing.** `lookup --file src/app.py` with cwd
   `wt` exited 1 `no symbol matched`, while the same file is indexed under `repo/`. The CHANGELOG
   line for 00016 lists pack, query, index, harvest and mcp, not lookup; README says "A linked git
   worktree of a registered repo uses that repo's registration" without that limit.
3. **Findings harvested from a worktree keep the worktree's path** (`.../wt/docs/.../00001-review.md`
   in `query`, `pack` and `nudge` output). What happens to them once the worktree is removed was
   not probed.
4. **Server outlives the CLI (seen a third time).** After `index`, `harvest` and `pack` exited, the
   llama-server engram spawned on 18106 was still running. README says "Engram spawns and stops the
   server itself".

Host quirk (confirmed again): a Bash call that writes through a shell variable
(`mkdir -p "$SCRATCH/old"`) was refused by the write-scope hook ("cannot resolve the write
target"). Use literal absolute paths or a Python driver. Shell redirects into
`docs/dev/project-management/` are also refused.

### Embedding server (llama-server)

- `/opt/homebrew/opt/llama.cpp/bin/llama-server`. Models cached under
  `/Users/bob/.cache/huggingface/hub`; with ENV engram spawns
  `llama-server --embedding -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --alias <same> --port <lane port> -c 8192 -b 8192 --ubatch-size 8192`.
- The operator runs an embedding server on 8083 (bge-m3) and a chat server on 8002, both seen live
  at `fba0967`. **Lanes must not use ports 8081-8083 or 8002.** Assigned ports: walter 18101,
  heidi 18102, peggy 18103, trudy 18104, wendy 18105 (recon used 18106).
- Every lane must stop its own server before returning:
  `pkill -f "llama-server --embedding -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --alias Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --port <lane port>"`.
  Recon stopped its own (pgrep afterwards showed only the operator's 8002 and 8083 servers).

### Database

SQLite with sqlite-vec and FTS5, one file per HOME (`<fixture>/home/.local/share/engram/engram.db`),
created on the first `index`. No separate server. Table `chunks` holds `corpus, repo, doc_type, path,
heading, body, line_start, line_end, content_hash, chunk_ordinal`; module context rows have
`doc_type = 'module_context'` and `heading = 'Module context'`. Seed path = `R/setup.py` plus
`engram index` and `engram harvest`. A pre-00013 store is seeded with `R/run_rev.py` and `R/old`.
Inspect read-only (`R/dbcount.py`, `?mode=ro`). The advisory lock is a `flock` on `engram.db.lock`
taken by `harvest` and `index --rebuild` only (from `cli.py`); plain `index`, `--backfill-code`,
`--reembed-code` and `pack` do not take it.

### Browser

None. No tracked `.js`, `.ts`, `.tsx`, `.html` or `.css` file (`git ls-files`), and no playwright,
selenium, flask, fastapi, uvicorn or `http.server` in `pyproject.toml`, `uv.lock` or `src`
(search returned nothing; a control search on the same files matched).

### External services

- **tree-sitter-language-pack grammar download**: the operator's cache now holds `v1.14.0`,
  `v1.23.1`, `v1.25.0` and `v1.25.2`; the venv runs 1.25.2. The copy recipe still works: with the
  whole cache dir copied into the fixture HOME, indexing ran with `HF_HUB_OFFLINE=1` and parsed
  Python. Whether it touched the network was not measured. A HOME without the copy downloaded a
  26 MB bundle in the `6d0d171` recon. README says "The only off-machine call is the one-time
  model download".
- **Hugging Face model download**: not exercised; models served from cache with `HF_HUB_OFFLINE=1`.
- **gita**: only `repos.csv` is read. **git**: subprocesses in symbols, diffmap, harvest, pack, cli.

### Release surface

- `version = "0.1.0"`, `git tag --list` empty, one `## [Unreleased]` heading. Headings at `fba0967`:
  Changed (line 9), Added (20), Fixed (63), then a second Added (142) and Fixed (174) with no
  version heading between them.
- New entries since `a49e020`: Added `**index**: engram index --backfill-code ...`; Fixed
  `**harvest**` (reviewers validity), `**harvest**` (canonical registry match, unreadable
  `repos.csv` gives no-repo), `**pack**` (canonical self-match exclusion), `**diffmap**` (C-quoted
  paths), `**cli**` (rebuild temp file cleanup), `**cli**` (linked worktree resolution for pack,
  query, index, harvest, mcp), `**cli**` (advisory write lock), `**cli**` (pack `--diff` id
  collisions).

## 2. Per-specialist strategy

Every armed lane: copy the helpers from `R` into its own scratch root, build a fixture with
`setup.py <own scratch>/f1 <own port> <lane name>`, drive the CLI with `run_in.py`, and stop its
own server at the end.

| Specialist | Verdict | Tactics or reason |
|---|---|---|
| walter (journeys) | **armed** | Port 18101. Journey 1, worktree (00016): from cwd `wt` run `harvest` on a review, `query --scope repo`, `index --scope repo`, `pack --diff HEAD~1..HEAD`, then read the pack file and check the changed span is absent from `Similar code`; repeat from a nested subdirectory of the worktree, from a worktree whose branch has a file the main checkout lacks, and from a worktree of a repo that is not registered (expect the "not inside a registered repo" error). Confirm lead 2: `lookup --file src/app.py` from `wt`. Journey 2, backfill (00015): build a store with old code (`run_rev.py ... R/old`), see `query` miss a module-level constant, run `index --backfill-code --scope portfolio`, see the query hit; also `--backfill-code` from inside the repo with no `--scope`, and combined with `--rebuild`, `--corpus`, `--reembed-code` (exit 2). Journey 3, findings (00014): harvest reviews with `reviewers` as a blank string, empty list, list with a number, a valid string and a valid list; then `query --corpus findings`. Journey 4, pack ids: two ranges that sanitize alike (branches `a/b` and `a-b`, `..` vs `...`) give two files. Journey 5, non-ASCII: change `src/café.py`, run `pack --diff`, see whether its symbol is mapped, and confirm lead 1 (`lookup --name brew`). Standing: module context via `query`, `lookup --file` order, `lookup --name <constant>` exits 1, `memory migrate` dry run, `--apply`, `memory check`. Note whether the server outlives each call. |
| heidi (integration, db) | **armed** | Port 18102, inspect with `dbcount.py`. **Backfill (00015):** seed with `R/old` code, snapshot rows and vector rowids, run `--backfill-code`; check symbol rows keep `content_hash` and vectors (report line `vectors reused`), context rows appear, `settings.py` loses its empty mark, `chunk_ordinal` stays unique, a second run is a no-op. Interrupt a backfill (kill mid-run on a larger fixture) and re-run: no half-written source (atomic empty-source claim). Backfill after editing a file without indexing it; backfill with a file deleted from disk; `--scope repo` touches only that repo. **Write lock (00014):** `hold_lock.py` then `harvest` and `index --rebuild` (expect exit 1 busy); two real `harvest` runs at once; `harvest` during a real `--rebuild`; check plain `index`, `--backfill-code`, `--reembed-code` and `pack` during a rebuild, which take no lock (does the swap lose their writes?). Stale `engram.db.lock` file with no holder must not block. **Rebuild cleanup:** make a rebuild fail (stop the server or point `endpoint` at a dead port, or use the fake server) and check no `engram.db.rebuild-tmp` remains and the old `engram.db` is intact; check findings survive a good rebuild. **Registry match:** register the repo by `/var/...` (symlink), with a trailing slash, and through a symlink dir, then `harvest` and `pack`; `chmod 000` on `repos.csv` gives per-file `no_repo`, not a crash. **Worktree:** rows written from `wt` carry `repo = scratchrepo`; check their `path` (lead 3), `status` stale and dead after the worktree is removed, and that `index --scope repo` from `wt` indexes the main checkout's files, not the worktree's. **Non-ASCII (lead 1):** confirm `café.py` has no rows, with and without `core.quotepath=false` in the scratch repo's config. Standing: prune after file delete, model-mismatch failure, `\f` and Unicode line separator line counts. |
| judy (UX via browser) | **unarmed** | No browser surface. No tracked JS, TS, HTML or CSS file, no Playwright or other browser driver in `pyproject.toml` or `uv.lock`, no HTTP listener in `src/engram` (searched at `fba0967`, control search matched). |
| wendy (release, changelog truth) | **armed** | Port 18105. No tags or release. Check each new CHANGELOG line against a run: backfill "reusing the stored vectors of unchanged chunks" and "an interrupted run is safe to repeat"; reviewers rejection for "blank strings, empty lists, non-string elements"; "symlinked or trailing-slash registry entry resolves correctly"; unreadable `repos.csv` "yields a no-repo result for the file instead of aborting the whole batch"; C-quoted `caf\303\251.py` maps "to the correct path" (and whether that path is indexed at all, lead 1); rebuild "no longer leaves ... rebuild-tmp ... on any failure"; the worktree line names `pack`, `query --scope repo`, `index --scope repo`, `harvest` and repo-scoped `mcp` (run each from `wt`; note `lookup --file` is absent from the list but README's "uses that repo's registration" is unqualified, lead 2); "a rebuild and a harvest can never run at the same time"; pack ids for `a/b..c` vs `a-b..c`. README: the `--backfill-code --scope portfolio` usage line, the module-context paragraph, the linked worktree sentence. `git -C <target> log --oneline a49e020..HEAD` vs entries: every `fix`/`feat` has a line? (the `1af23eb`, `d366537`, `e84f7eb` follow-up fixes and the 1.25.2 bump). Carried-over leads: "only off-machine call is the one-time model download" vs the grammar download, "spawns and stops the server itself" vs the leftover server (lead 4), and the second Added/Fixed pair with no version heading (lines 142, 174). |
| peggy (performance) | **armed** | Port 18103. Synthetic portfolio only: generate N scratch repos (for example 20 x 50 Python files with sizeable module-level code, plus PRDs), registered by realpath. Measure with `/usr/bin/time -p`: (1) `--backfill-code --scope portfolio` on a store built with `R/old` code vs `index --rebuild` on the same tree, wall time and embed count (the report line gives `chunks embedded` and `vectors reused`); backfill should cost far less than a rebuild. (2) A second backfill (no-op) wall time. (3) `pack --diff` from the main checkout vs from a linked worktree (the worktree path adds a `git rev-parse --git-common-dir` call and extra spans). (4) `harvest` of many files: `_resolve_repo_for_path` now resolves every registry row per file, so time 200 review files against a 5-row and a 500-row `repos.csv`. (5) `pack` exclusion calls `os.path.realpath` per hit per span: a diff touching 50 symbols. (6) Lock overhead on `harvest`. Standing: cold index, unchanged re-index, `query`, `lookup --name`, `mcp` per-call latency, `nudge` wall time. |
| trudy (runtime security) | **armed** | Port 18104, scratch HOME only. Surfaces: `engram mcp` JSON-RPC over stdio, `engram nudge` reading hook JSON from stdin, markdown, JSONL and YAML parsing (harvest, transcripts, memory frontmatter), `memory migrate --apply` writing files and wiring `.gitattributes`, `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`, `git` subprocesses fed user input, `config.toml` endpoint validation and the `-hf <id>` passed to llama-server. New since `a49e020`: (a) **diff path decoding**: hand `pack --diff` a range whose diff carries C-quoted names that decode to `../../x`, absolute paths, NUL or newline bytes, invalid UTF-8 octal runs, and names with quotes or backslashes; check nothing outside the repo is read into the pack. (b) **Worktree resolution**: a directory with a hand-made `.git` file whose `gitdir:` or `commondir` points at a registered repo's `.git`, or a `--git-common-dir` ending in `.git` under an attacker path, to see whether an unregistered tree can claim a registered repo's name and write findings or packs under it; a worktree whose files are symlinks out of the tree (the `relative_to` guard in `pack.py`). (c) **Lock file**: `engram.db.lock` pre-created as a symlink to another file, as a directory, or unwritable; the lock is advisory, so check a held lock is a clean exit 1 and not a hang. (d) **Rebuild temp**: `engram.db.rebuild-tmp` pre-created as a symlink (it is unlinked first; does the unlink or `os.replace` follow it?). (e) **Pack id**: range strings with `/`, `..`, leading `-` (`--output=<scratch>/x`), very long ranges; confirm the file name stays inside `docs/dev/tmp`. (f) **Reviewers**: YAML tags, anchors and huge aliases in review frontmatter. (g) `repos.csv` rows with relative paths, `~`, or symlink loops now that every row is `resolve()`d. Standing: module-level secrets surfacing through `query`, `mcp` and `nudge`; malformed, oversized, deeply nested JSON-RPC; nudge payloads with `$(...)`, `../`; migrate names with `../` and symlinks; endpoints like `http://127.0.0.1.evil:1/`; ids starting with `-`. Authorization is resolved at dispatch, not here. |

## 3. Mocking strategy

- **llama-server / embeddings: no mock needed.** Recon reached a real local server with cached
  models at `fba0967`. Findings from real runs may be reported `verified`.
- **Hugging Face model download**: not exercised. Keep `HF_HUB_OFFLINE=1` and
  `HF_HUB_CACHE=/Users/bob/.cache/huggingface/hub`. For an uncached model id or a failing server, use
  `_MockEmbeddingServer(port, model_id)` from `tests/_embedding_server.py` (in-process class, no
  `__main__`; carried over, not re-run): start it from a scratch Python driver with `sys.path` set
  to the target `tests/` dir, on the lane's port, and point `endpoint` at it. Anything probed
  against it is reported `mocked`, never `verified`.
- **Embedding failure modes** (null vectors, dropped connections, slow `/props`, wrong model id,
  a rebuild or backfill that fails midway): same fake server. Report `mocked`. A rebuild failure
  forced by a dead port with no fake server is a real run.
- **tree-sitter grammar download**: avoided by copying the operator's grammar cache into the
  fixture HOME. A lane probing no-network behaviour reports `mocked` (cache pre-seeded) or
  `unverified`.
- **Lock contention**: `hold_lock.py` takes the real `flock` on the real lock path, so the busy
  path is a real run. It does not stand in for a real concurrent rebuild's writes; a claim about
  lost writes needs two real engram processes.
- **Pre-00013 store**: not a mock. Built with real code from `git archive 6d0d171` (`R/old`).
- **gita**: not mocked; a hand-written `repos.csv` is the real input.

## 4. Authoring assignments

The master authors these on a branch after the lanes report. Recon names surfaces and runners only.
Runner for all: the main suite command in Surfaces.

- **Code enumeration with non-ASCII file names** (lead 1): if confirmed, a regression in
  `tests/test_symbols.py` (or beside the enumeration tests) that indexes a repo holding `café.py`
  and expects its symbol, with the fix `git ls-files -z`.
- **`lookup --file` from a linked worktree** (lead 2): if confirmed and judged a defect, a case
  beside `tests/test_pack_worktree.py` or the lookup CLI tests; otherwise a README limit.
- **Worktree findings paths** (lead 3): if a lane shows dead or duplicate findings after worktree
  removal, a regression beside `tests/test_harvest_resolve.py`.
- **Unlocked writers during rebuild**: if heidi shows a plain `index`, backfill or `pack` write lost
  across a rebuild swap, a regression beside the `write_lock` CLI tests in
  `tests/test_cli_index_status.py`.
- **Backfill interruption**: `tests/test_indexer*.py` already pins the atomic empty-source
  transition; add a case only for a gap a lane confirms.
- **CLI lifecycle (server outlives the CLI)** (lead 4): if confirmed, a pytest regression using the
  fake server from `tests/_embedding_server.py`, or a documented decision.
- **Hostile diff paths and forged worktree metadata**: if trudy confirms either, a regression beside
  `tests/test_diffmap_decoding.py` or `tests/test_harvest_resolve.py`.
- No durable tests for performance (peggy) or changelog truth (wendy).

## 5. Pins and vetoes

Authorization: not asserted

## 6. Freshness stamp

- Recon date: 2026-11-16
- Target HEAD: fba09676699e5b440200b8a17bd0cfccc7d1878a
