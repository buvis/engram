# Assumptions ledger (PRD 00012)

## 1: Write src/engram/mcp_server.py and tests/test_mcp_server.py

- Tess: `serverInfo.version` is only checked as a non-empty string; it is not compared to `importlib.metadata`.
- Tess: non-dict `arguments` (str, list, int) are only checked for the `invalid arguments: ` prefix; which field is named is not pinned.
- Tess: `scope: None`, and `k` given as `5.0` or `"5"`, count as present and invalid (not treated as missing, not converted).
- Tess: "deeply nested JSON" is tested as 200000 `[` then 200000 `]`, expecting one -32700 reply.
- Tess: `sqlite3.OperationalError` stands in for `sqlite3.Error`.
- Tess (strengthen): `load_config` is called with no arguments; the query text reaches search unchanged; `query` gets scope as the 4th positional argument and `k` as a keyword.
- Ivan: the wording after `invalid arguments: ` is the implementor's (for example "k must be an integer from 1 to 20").
- Ivan: non-dict `arguments` gets "invalid arguments: arguments must be an object".
- Ivan: `GITA_REPOS_CSV.exists()` is checked only after `_resolve_repo_for_path` returns None.

## 2: Write src/engram/nudge.py and tests/test_nudge.py

- Tess: `~` and `$VAR` expand from the process environment, since `find_broad_search` takes no environ.
- Tess: `format_nudge` with no pointers gives header, blank line, footer.
- Tess: only exactly `ENGRAM_NUDGE=off` disables the nudge (`OFF`, `on`, empty, `0` do not).
- Tess: `git log -s` and `git logs -S foo` are not pickaxe searches.
- Tess: an unknown host with a broad search and hits is an unexpected error: one stderr line naming `ValueError`, exit 0.
- Tess (strengthen): a path's repo root is found by walking ancestors whether or not the path exists.
- Ivan: `OPERATOR_CHARS = ";<>|&\n"` replaces the design's `SHELL_OPERATORS`; a quoted token made only of those characters also ends the command.
- Ivan: an empty explicit pattern (`-e ''`) still counts as the pattern, so nothing is searched.
- Ivan: an unreadable `ENGRAM_PACK_FILE` keeps all hits.

## 3: Register and dispatch the mcp and nudge subcommands in src/engram/cli.py

- Tess: an unknown nudge host raises argparse `SystemExit(2)` from `main`.
- Tess: `serve_mcp` reads stdin line by line (iteration or `readline`), never `read()`.
- Tess: one Copilot payload serves all four hosts; the JSON hosts print default `json.dumps` formatting.
- Orchestrator: the style gate flagged `_build_parser` at 55 lines; the orchestrator moved the two agent subparsers into `_add_agent_parsers` in-session instead of an Ivan style-fix dispatch (5-line mechanical move).

## 4: Document engram mcp and engram nudge, add CHANGELOG entries, delete the spike

- Orchestrator: the two CHANGELOG bullets landed with tasks 1 and 2 (the `feat` commits), so task 4 left CHANGELOG.md unchanged; the spike was removed with `git rm -r` by the orchestrator, plus its untracked `__pycache__`.
- Ivan: the MCP config example sits in its own fenced `json` block; added "It reads the hook payload from stdin."
