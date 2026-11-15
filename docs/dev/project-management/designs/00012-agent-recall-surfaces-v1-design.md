# Design: agent recall surfaces (`engram mcp`, `engram nudge`)

PRD: `docs/dev/project-management/prds/wip/00012-agent-recall-surfaces-v1.md`.
Reference spike (never merges): `docs/dev/project-management/spikes/engram-plugin/`.

## Architecture fit

Engram is a standalone CLI (`src/engram/cli.py`) over a retrieval core
(`query.py`, `store.py`, `client.py`). Both new surfaces are thin front ends on
the existing `query()` call, run in-process, exactly like `_run_query` in
`cli.py`. No change to retrieval, store, indexing, config, or the production
model. The surfaces add no dependency: JSON-RPC and hook parsing use `json`,
`shlex`, `re`, `os`, `pathlib`, `importlib.metadata` only.

Layering (imports point downward only, no cycles):

```
cli.py  ->  nudge.py  ->  mcp_server.py  ->  query.py / store.py / client.py / harvest.py / corpora.py
cli.py  ->  mcp_server.py
```

`mcp_server.py` owns the one in-process search function both surfaces share
(`search_pointers`) and the one pointer-line formatter (`format_pointer_lines`)
that `engram query` also uses, so the MCP tool text cannot drift from the CLI
output.

## Module placement

New files:

- `src/engram/mcp_server.py` - JSON-RPC stdio loop, `engram_query` tool,
  `search_pointers`, `format_pointer_lines`, `RepoScopeError`.
- `src/engram/nudge.py` - payload reading, broad-search detection, recall query,
  host output.
- `tests/test_mcp_server.py`, `tests/test_nudge.py`.

Edited files:

- `src/engram/cli.py` - `_build_parser` gains subparsers `mcp` and `nudge`;
  `main` dispatches them; `_run_query` prints via `format_pointer_lines` (same
  bytes as today).
- `README.md` - new `## Agent recall` section (after `## Usage`).
- `CHANGELOG.md` - two bullets under `## [Unreleased]` / `### Added`.

Deleted when the last task lands: `docs/dev/project-management/spikes/engram-plugin/`
(PRD Source line).

## Interfaces & contracts

### `src/engram/mcp_server.py`

```python
INSTRUCTIONS: str = (
    "engram is the portfolio memory: past agent sessions, PRDs, decisions, memory files, and code "
    "across all repositories. Call engram_query before a broad rg/grep/git-log sweep for prior "
    "decisions, history, or cross-repo where/why questions. Do not use it to search a known file."
)
DEFAULT_PROTOCOL_VERSION: str = "2025-06-18"
TOOL: dict  # the tools/list entry, below

class RepoScopeError(ValueError): ...

def search_pointers(text: str, scope: str, k: int) -> list[Pointer]
def format_pointer_lines(pointers: list[Pointer]) -> list[str]
def run_query_tool(arguments: object, search: Callable[[str, str, int], list[Pointer]] | None = None) -> dict
def handle_mcp_message(message: object, search: Callable[[str, str, int], list[Pointer]] | None = None) -> dict | None
def serve_mcp(stdin: TextIO, stdout: TextIO, search: Callable[[str, str, int], list[Pointer]] | None = None) -> int
```

`Pointer` is `engram.query.Pointer`. A `search` argument of `None` means
"look up `mcp_server.search_pointers` at call time" (module attribute, so tests
and the CLI tests can monkeypatch `engram.mcp_server.search_pointers`).

`INSTRUCTIONS` is the PRD's exact text: the three string pieces above join with
no extra characters into one line.

`search_pointers(text, scope, k)`:
- `scope == "portfolio"` -> `Scope("portfolio", None)`.
- `scope == "repo"` -> repo name from
  `harvest._resolve_repo_for_path(Path.cwd() / "_", repos_csv=corpora.GITA_REPOS_CSV)`
  (same call as `cli._resolve_repo_name`); `None` raises
  `RepoScopeError("not inside a registered repo; use scope portfolio instead")`.
- Then `query(open_store(), load_config(), text, scope_obj, k=k)` and return the
  list. `corpus`, `include_body` and the rest stay at their defaults, so the
  call matches `engram query --scope <scope> -k <k> <text>`.
- Exceptions from `query` propagate unchanged.

`format_pointer_lines(pointers)` returns, per pointer, the line
`f"{p.rank}\t{p.score:.4f}\t{p.path}:{p.line_start}-{p.line_end}\t{p.heading}"`
followed by `p.body` as its own element when `p.body is not None`. `_run_query`
prints each element with `print()`, so `engram query` output is byte-identical
to today.

`TOOL` (exact):

```python
{
    "name": "engram_query",
    "description": "Search prior sessions, PRDs, memory, and code. Returns ranked path:line hits.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Question in plain words"},
            "scope": {"type": "string", "enum": ["repo", "portfolio"], "default": "portfolio"},
            "k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
        },
        "required": ["query"],
    },
}
```

`run_query_tool(arguments, search)` returns an MCP `CallToolResult` dict
`{"content": [{"type": "text", "text": <str>}], "isError": <bool>}`:
- Validation (each failure -> `isError: true`, text starts `invalid arguments: `
  and names the field): `arguments` must be a `dict` (`None` is treated as
  `{}`); `query` must be a `str` with non-whitespace content; `scope`, when
  present, must be `"repo"` or `"portfolio"`; `k`, when present, must be an
  `int` that is not a `bool` and lies in 1..20 (no clamping). Unknown extra keys
  are ignored.
- Success: text is `"\n".join(format_pointer_lines(hits))`, or `"no hits"` when
  `hits` is empty; `isError: false`.
- Failure: `RepoScopeError`, `StoreModelMismatchError` (text
  `f"{e}; run `engram index --rebuild` to rebuild the store"`, same suffix as
  `_run_query`), `EmbeddingServerError`, `EmbeddingPreflightError`, `OSError`,
  and `sqlite3.Error` -> `isError: true`, text `str(e)` (or the suffixed text).
  Nothing else is caught here; `handle_mcp_message` is the last guard (below).

`handle_mcp_message(message, search)` returns the full JSON-RPC reply object or
`None`:
- `message` not a `dict` -> `{"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}`.
- No `"id"` key -> notification -> `None` (whatever the method).
- `id = message["id"]`; `method = message.get("method")`;
  `params = message.get("params")`, a non-`dict` read as `{}`.
- `"initialize"` -> result `{"protocolVersion": params.get("protocolVersion") if it is a non-empty str else DEFAULT_PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": {"name": "engram", "version": <importlib.metadata.version("engram")>, or "unknown" on PackageNotFoundError}, "instructions": INSTRUCTIONS}`.
- `"ping"` -> result `{}`.
- `"tools/list"` -> result `{"tools": [TOOL]}`.
- `"tools/call"` with `params.get("name") == "engram_query"` -> result
  `run_query_tool(params.get("arguments"), search)`.
- `"tools/call"` with any other name -> error `-32602`, message
  `f"unknown tool: {name}"`.
- Any other method -> error `-32601`, message `"method not found"`.
- An unexpected exception while building a result -> error `-32603`, message
  `f"internal error: {type(e).__name__}: {e}"`; the loop keeps serving.
- Reply shape: `{"jsonrpc": "2.0", "id": id, "result": ...}` or
  `{"jsonrpc": "2.0", "id": id, "error": {"code": int, "message": str}}`.

`serve_mcp(stdin, stdout, search)`: `for line in stdin`; skip lines that are
empty after `strip()`; `json.loads(line)` failure (`ValueError`) writes
`{"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}`;
otherwise write `handle_mcp_message(...)` unless it is `None`. Each reply is
`json.dumps(reply)` plus `"\n"`, then `stdout.flush()`. Returns `0` at EOF.
Nothing but replies goes to stdout.

### `src/engram/nudge.py`

```python
HOSTS: tuple[str, ...] = ("claude", "codex", "copilot", "plain")
HEADER: str = 'engram recall for "{query}" (prior sessions, PRDs, memory, code):'
FOOTER: str = "Read a cited range if it is relevant; ignore it if not."
NUDGE_K: int = 3
SEARCH_VALUE_FLAGS: frozenset[str] = frozenset({
    "-g", "--glob", "-t", "--type", "-T", "--type-not", "-A", "-B", "-C",
    "-m", "--max-count", "--max-depth", "-f", "--file", "-j", "--threads",
    "-M", "--max-columns",
})
PATTERN_FLAGS: frozenset[str] = frozenset({"-e", "--regexp"})
GIT_LOG_FLAGS: tuple[str, ...] = ("-S", "-G", "--grep")
SHELL_OPERATORS: frozenset[str] = frozenset({"|", "||", "&", "&&", ";", ";;", "(", ")", "<", ">", ">>", "<<", ">&", "<&", "|&"})

def read_hook_event(raw: str) -> tuple[str, str]
def find_broad_search(command: str, cwd: str) -> str | None
def build_recall_query(pattern: str) -> str
def format_nudge(host: str, query: str, pointers: list[Pointer]) -> str
def run_nudge(host: str, stdin: TextIO, stdout: TextIO, stderr: TextIO, environ: Mapping[str, str]) -> int
```

`read_hook_event(raw)` -> `(command, cwd)`. Raises `ValueError` on bad input
(`json.JSONDecodeError` is a `ValueError`):
- event = `json.loads(raw)`; must be a `dict`.
- args = `event.get("tool_input")`, else `event.get("toolArgs")`; a `str`
  args value is `json.loads`-ed; args must then be a `dict`.
- command = `args.get("command")`; must be a `str` with non-whitespace content,
  else `ValueError("no shell command in hook payload")`.
- cwd = `event.get("cwd")` when it is a non-empty `str`, else `os.getcwd()`.

`find_broad_search(command, cwd)` -> pattern or `None`. Never raises for any
`str` input.
- Tokenize: `lex = shlex.shlex(command, posix=True, punctuation_chars=True)`;
  `lex.whitespace_split = True`; `tokens = list(lex)`; `ValueError` -> `None`.
  Truncate at the first token in `SHELL_OPERATORS` (first command only). Empty
  -> `None`. `tool = Path(tokens[0]).name`; `args = tokens[1:]`.
- `git`: requires `"log"` in `args`. Scan `args` left to right; for each token
  and each flag in `GIT_LOG_FLAGS`: token `== flag` and a next token exists ->
  return the next token; `--grep=<v>` -> `<v>`; `-S<v>` / `-G<v>` (attached,
  token longer than the flag, flag is a short one) -> `<v>`. No match -> `None`.
  A non-empty value is required; empty -> keep scanning.
- `rg`, `grep`, `egrep`, `fgrep`: walk `args` with an index. After a `--`
  token every later token is bare. Token in `PATTERN_FLAGS` -> next token is the
  explicit pattern (first one wins), skip it. `--regexp=<v>` or `-e<v>` ->
  explicit pattern `<v>`. Token in `SEARCH_VALUE_FLAGS` -> skip it and its next
  token. Any other token starting with `-` (and longer than `-`) -> skip alone
  (covers `--glob=x`, `-g*.py`, boolean flags). Else bare. Pattern = explicit
  pattern if any, else the first bare token, and the rest of the bare tokens are
  paths; with an explicit pattern all bare tokens are paths. No pattern ->
  `None`.
- `find`: paths = tokens of `args` before the first token that starts with
  `-`, `(` or `!`. Pattern = token after the first `-name` or `-iname`; none ->
  `None`.
- Any other tool -> `None`.
- Broadness: no paths -> `None` (current directory). Each path:
  `os.path.expanduser`, joined to `cwd` when relative, `os.path.normpath`; no
  symlink resolution. A path whose parts contain `".claude"` immediately
  followed by `"projects"` -> broad. `repo_root(p)` = nearest of `p` and its
  ancestors holding a `.git` entry (directory or file), else `None`. Broad when
  any path's root differs from `repo_root(cwd)` or the set of path roots has more
  than one element. Broad -> return the pattern; else `None`.

`build_recall_query(pattern)` ->
`" ".join(w for w in re.split(r"[^A-Za-z0-9_-]+", pattern) if len(w) >= 3)`.

`format_nudge(host, query, pointers)`:
- text = `HEADER.format(query=query)` + `"\n"` + one line per pointer
  `f"- {p.path}:{p.line_start}-{p.line_end}  ({p.heading})"` joined by `"\n"`
  + `"\n"` + `FOOTER`.
- `claude`, `codex` -> `json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}})`.
- `copilot` -> `json.dumps({"additionalContext": text})`.
- `plain` -> text.
- Any other host -> `ValueError`.

`run_nudge(host, stdin, stdout, stderr, environ)` -> always `0`:
1. `environ.get("ENGRAM_NUDGE") == "off"` -> return before reading stdin.
2. `raw = stdin.read()`; `read_hook_event(raw)` raising `ValueError` -> one
   stderr line `engram nudge: unreadable hook payload: <e>` and return.
3. `pattern = find_broad_search(command, cwd)`; `None` -> return.
4. `query = build_recall_query(pattern)`; empty -> return.
5. `hits = mcp_server.search_pointers(query, "portfolio", NUDGE_K)` (module
   attribute lookup at call time). Any `Exception` -> one stderr line
   `engram nudge: query failed: <type>: <e>` and return.
6. `pack = environ.get("ENGRAM_PACK_FILE")`; when it names a readable file,
   read its text (`errors="replace"`; an `OSError` keeps all hits) and drop each
   hit whose `p.path` is a substring of that text.
7. No hits left -> return. Else write `format_nudge(host, query, hits)` + `"\n"`
   to `stdout`.

The whole body after step 1 runs inside one `try`/`except Exception` that
writes `engram nudge: <type>: <e>` to stderr and returns `0`, with a comment
stating why: a post-tool hook must never fail the host's tool call. The error
is reported, not swallowed. Nothing but the formatted output goes to stdout.

### `src/engram/cli.py`

- `_build_parser`: `subparsers.add_parser("mcp", help="serve engram_query over MCP stdio")`
  (no arguments); `nudge_parser = subparsers.add_parser("nudge", help="post-tool hook: recall prior work after a broad search")`,
  `nudge_parser.add_argument("host", choices=list(nudge.HOSTS))`.
- `main`: `if args.command == "mcp": return mcp_server.serve_mcp(sys.stdin, sys.stdout)`;
  `if args.command == "nudge": return nudge.run_nudge(args.host, sys.stdin, sys.stdout, sys.stderr, os.environ)`.
  Both checks sit before the final `return _run_status(args)`.
- `_run_query`: replace its print loop with
  `for line in format_pointer_lines(pointers): print(line)`.
- Imports: `from engram import mcp_server, nudge` and
  `from engram.mcp_server import format_pointer_lines`.

### Test names (pinned by the PRD)

`tests/test_nudge.py`: `test_nudges_for_search_outside_repo`,
`test_stays_silent_for_search_inside_repo`, `test_skips_value_of_glob_flag`,
`test_treats_git_log_pickaxe_as_broad`, `test_drops_hits_named_in_pack_file`,
`test_stays_silent_when_nudge_is_off`, `test_exits_zero_when_query_fails`,
`test_accepts_copilot_tool_args_as_object_and_string`,
`test_emits_each_host_format`, `test_cli_nudge_dispatches_with_host`.

`tests/test_mcp_server.py`:
`test_initialize_returns_instructions_and_tools_capability`,
`test_tools_call_returns_query_lines`, `test_notification_gets_no_reply`,
`test_unknown_method_returns_32601`, `test_invalid_json_returns_32700`,
`test_query_failure_sets_is_error_and_keeps_serving`,
`test_cli_mcp_serves_until_eof`.

## Data flow

MCP: host writes a JSON line -> `serve_mcp` parses -> `handle_mcp_message`
routes -> `tools/call` -> `run_query_tool` validates -> `search_pointers`
resolves scope, opens the store, loads config, calls `query()` (which embeds via
the pinned llama-server) -> `format_pointer_lines` -> `CallToolResult` -> one
JSON line on stdout, flushed.

Nudge: host runs `engram nudge <host>` after a shell tool with the hook payload
on stdin -> guard on `ENGRAM_NUDGE` -> `read_hook_event` -> `find_broad_search`
(pure, filesystem reads only for `.git` probes) -> `build_recall_query` ->
`search_pointers(query, "portfolio", 3)` -> pack-file filter -> `format_nudge` ->
stdout. The host injects stdout as additional context. Every error path writes
one stderr line and exits 0.

## Reuse inventory

- `src/engram/query.py:query` and `Pointer` - the retrieval call and its result
  type; called in-process, exactly as `cli._run_query` does.
- `src/engram/store.py:open_store`, `StoreModelMismatchError`, `Scope`.
- `src/engram/client.py:load_config`, `EmbeddingServerError`,
  `EmbeddingPreflightError`.
- `src/engram/harvest.py:_resolve_repo_for_path` with
  `corpora.GITA_REPOS_CSV` - repo-scope resolution, same call as
  `cli._resolve_repo_name` (that wrapper lives in `cli.py`; importing it would
  create a `cli` <-> `mcp_server` cycle, so the one-line call is repeated).
- `cli._run_query`'s pointer-line print loop - extracted to
  `format_pointer_lines` so the tool text and `engram query` share one source.
- Spike `spikes/engram-plugin/engram/server/engram_mcp.py` and
  `engram/nudge/engram_nudge.py` - message routing, `TOOL`, `INSTRUCTIONS`,
  payload reading, query-word rule and host formats are ported; subprocess
  calls become in-process calls, value-flag handling is added.
- Test seams: `tests/test_cli.py` monkeypatches `engram.cli.query`,
  `load_config`, `open_store`; the new tests monkeypatch
  `engram.mcp_server.search_pointers` the same way.
- Searched for an existing JSON-RPC or MCP helper: nothing found, greps tried:
  `rg -n "jsonrpc|json-rpc|mcp|tools/list" src` and
  `rg -n "shlex|hookSpecificOutput|additionalContext" src` (control: `rg -n "json" src`
  hits `client.py`, proving the pattern works). No dependency named `mcp` in
  `pyproject.toml`; the PRD forbids the SDK anyway.

## Alternatives considered

1. **Smallest diff: wrap the spike scripts as console scripts that shell out to
   `engram query`.** Fewest new lines, but the PRD requires in-process calls
   (no subprocess) and per-call Python start plus a second Python process
   doubles nudge latency. Rejected.
2. **Put `search_pointers` in `cli.py` and have `mcp_server`/`nudge` import
   it.** `cli` must import both modules to dispatch them, so this is an import
   cycle (or needs function-local imports). Rejected.
3. **Chosen: `mcp_server.py` owns `search_pointers` and
   `format_pointer_lines`; `nudge.py` imports `mcp_server`; `cli.py` imports
   both.** One extra function over option 1's shape buys: no cycle, one formatter
   shared with `engram query`, and one monkeypatch seam for every test. A
   separate `recall.py` module was not created: the PRD's structure names two
   modules, and two small functions do not earn a third.

## Risks & edge cases

- **Import cost per shell command.** `import engram.cli` measured at about 73 ms
  (dominated by `tree_sitter_language_pack`, `yaml`, `client`). The nudge runs
  after every shell call the host hooks, so this is paid even when no search
  runs. Accepted for v1 (the host never waits on a post-tool hook beyond its
  own timeout). Next change if it matters: lazy imports in `cli.main` for the
  `nudge` path.
- **Redirections.** `rg foo 2>/dev/null` tokenizes as `rg foo 2 > ...`;
  truncation at `>` leaves `2` as a relative path inside `cwd`, which is never
  broad by itself. Harmless.
- **`cd X && rg ...`, pipes after the first command**: not inspected (PRD
  non-goal).
- **Unknown value-taking flags** shift the pattern; result is a poor query,
  never a failure (PRD risk).
- **Paths that do not exist** still walk ancestors for `.git`; a typo outside
  any repo yields root `None`, which differs from a repo `cwd` and counts as
  broad. Acceptable: the agent asked outside its repository.
- **Concurrent store access**: each tool call and each nudge opens the SQLite
  store read-mostly; `busy_timeout=5000` already applies (capsule, Session 4).
- **stdout hygiene**: any stray print would corrupt the MCP stream or the hook
  JSON. `query()` and `embed()` print nothing today; tests assert stdout holds
  only replies.
- **Embedding server start latency**: the first query may spawn the pinned
  llama-server (about 3 s in the spike). Hosts set their own hook timeout.
- **Likely next changes**: (1) repeat suppression within a session (needs a
  session id from the payload; `read_hook_event` would return a third field);
  (2) a relevance threshold once scores support it (a filter between steps 5 and
  6); (3) more hosts (`gemini`, `kiro`) - `HOSTS` and `format_nudge` extend by
  one branch each. Nothing here boxes them in.

## Test strategy outline

- `tests/test_nudge.py`: pure-function tests for `find_broad_search` with
  `tmp_path` repos (a `.git` dir per fake repo); `run_nudge` tests with
  `io.StringIO` streams, a dict `environ`, and
  `monkeypatch.setattr("engram.mcp_server.search_pointers", fake)` returning
  `Pointer` objects or raising `EmbeddingServerError`. Cover Claude/Codex
  (`tool_input`), Copilot (`toolArgs` dict and JSON string), each host format,
  `ENGRAM_NUDGE=off` (stdin never read: a stream whose `read` raises),
  `ENGRAM_PACK_FILE` filtering, `-g '*.py'` value skipping, `git log -S` and
  `--grep=` forms. `test_cli_nudge_dispatches_with_host` calls
  `cli.main(["nudge", "copilot"])` with monkeypatched `sys.stdin`/`sys.stdout`
  and checks the `additionalContext` JSON and exit 0.
- `tests/test_mcp_server.py`: `handle_mcp_message` per method with a fake
  `search`; `serve_mcp` over `io.StringIO` input of several lines (bad JSON, a
  notification, a failing call, then a good call) asserting one reply per
  request in order and that the loop continued. `test_cli_mcp_serves_until_eof`
  runs `cli.main(["mcp"])` with a StringIO stdin holding `initialize` then EOF,
  asserts exit 0 and one reply.
- A check that `engram query` output is unchanged rides on existing
  `tests/test_cli.py` query tests.
- Full suites: `.venv/bin/python -m pytest -q --ignore=eval`; `git diff --check`.

## Review log

Dispatch 1 (claude) open items, recorded not fixed:

- non-blocker: `python -m engram.cli nudge --help` passes vacuously; `cli.py`
  has no `if __name__ == "__main__"` block. Add one or check `.venv/bin/engram nudge --help`.
- non-blocker: `SHELL_OPERATORS` misses `&>`, `>|`, `<<<`; `rg foo &>/dev/null`
  reads `/dev/null` as an outside path. Cut at any token made only of `();<>|&`.
- non-blocker: `.git` probe via `Path.exists()` can raise `OSError` (name too
  long, EPERM under Seatbelt); use `os.path.lexists`, which never raises.
- non-blocker: CLI nudge tests must `monkeypatch.delenv` `ENGRAM_NUDGE` and
  `ENGRAM_PACK_FILE`.
- non-blocker: `EmbeddingModelIdentityError` and config `ValueError` reach -32603
  instead of `isError`; consider adding them to the `run_query_tool` list.
- non-blocker: argparse exits 2 on an unknown host; Claude Code shows PostToolUse
  exit 2 to the model. Consumer PRD 00067 should pin a minimum engram version.
- non-blocker: query-word rule turns `\bfoo\b` into `bfoo`; PRD-level gap.
- non-blocker: `query.py` not weighed as home for `format_pointer_lines`.
- question: the git branch returns its pattern directly (always broad); the
  broadness block applies to rg/grep/find only. Read it that way.
- question: `tool_input` present but `null`/`{}` - falls through to `toolArgs`?
- question: Copilot non-shell tool payloads hit the stderr line every call.
- question: the two `test_cli_*` tests land with the Phase 1 task, not Phase 0.
- question: strict rejection of `k` as `5.0` or `"5"` intended?

dispatch 1 (claude): cardinal-sin 0, blocker 0, non-blocker 8, question 5

dispatch 2: codex unavailable, Claude fallback (codex ran but every read failed:
`sandbox-exec: sandbox_apply: Operation not permitted`, nested Seatbelt).

Dispatch 2 (claude-fallback) open items, recorded not fixed:

- non-blocker: cwd outside any repo (`~/.claude`, `~/git/src`): path root `None`
  equals cwd root `None`, so `rg foo ~/git/src` is not broad; the spike counted
  it (`roots.add(repo_root(path) or path)`). Decide and test.
- non-blocker: shlex reads `\n` as whitespace; multi-line commands merge. Add
  `\n` to punctuation chars, set `whitespace=' \t\r'`, cut at `\n`.
- non-blocker: shlex comments: `rg issue#12 ~/x` -> `['rg','issue']`. Set
  `commenters=''`.
- non-blocker: `(`/`)` cut `find ~/git \( -name x \)`; `find -L` loses paths.
- non-blocker: `$HOME`/`${VAR}` paths not expanded (`os.path.expandvars`).
- non-blocker: `serve_mcp` crashes on `RecursionError` from deep JSON and on
  non-UTF-8 stdin bytes; catch per line, read stdin with `errors="replace"`.
- non-blocker: real `search_pointers` body (scope, k, `RepoScopeError` ->
  isError) never tested; pin from-imports and patch `query`, `open_store`,
  `load_config`, `_resolve_repo_for_path` in one test.
- non-blocker: untested branches (find, `.claude/projects`, two roots, `-e`,
  `--`, unreadable payload, invalid arguments, -32602, -32600, ping, tools/list).
- non-blocker: store connection never closed; `try/finally: store.conn.close()`.
- non-blocker: worst case latency is up to 120 s (`ensure_served`); hook is
  synchronous for Claude Code. Consumer PRD 00067 should pin a hook timeout.
- non-blocker: `run_nudge` should `stdout.flush()` inside its try, or a closed
  pipe exits 120 at shutdown.
- non-blocker: `RepoScopeError` text should match `cli._repo_scope_error_msg`
  (missing gita CSV case).
- question: normalize cwd like paths before comparing roots.
- question: `scope: "repo"` resolves the server process cwd, not the agent's.
- low (uncounted): one shared value-flag list is wrong per tool (grep `-T`
  takes no value; rg `-r` does). PRD-level.

dispatch 2 (claude-fallback): cardinal-sin 0, blocker 0, non-blocker 11, question 3
