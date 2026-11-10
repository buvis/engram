---
eligibility: rg -q "^Adoption decision: proceed" docs/dev/project-management/reviews/2026-11-10-agent-session-evaluation-protocol.md
default_model: opus
model_tier_rationale: broad-search predicate and JSON-RPC contract are designed here and consumed by agent-plugins PRD 00067
---

# Agent recall surfaces: `engram mcp` and `engram nudge`

Source: `docs/dev/project-management/spikes/engram-plugin/SPEC.md` (graduated
spike, 2026-11-10). The spike directory is reference only; its code never
merges. Delete it when this PRD's implementation lands.

## Overview

### Problem Statement

Agents do not ask Engram on their own. Over Claude sessions since 2026-11-01
(364 sessions, 40 projects), 14 sessions (4%) called Engram, all through the
catch-up skill, while 212 sessions ran 5,671 ad-hoc searches. Engram has no
surface an agent host can load: no tool in the tool list, and no way to push a
hit into context after a search. A portable plugin (agent-plugins PRD 00067)
needs two bare commands to point at, so that it ships configuration only.

### Target Users

Coding agents on Claude Code, Codex, Copilot CLI, and Pi, and the Engram plugin
that wires them. The user is the solo maintainer of both repositories.

### Success Metrics

- `engram mcp` answers `initialize`, `tools/list`, and `tools/call` over stdio
  (tests in `tests/test_mcp_server.py` pass).
- `engram nudge <host>` emits the host's context-injection output for a broad
  search and nothing for a narrow one (tests in `tests/test_nudge.py` pass).
- `engram nudge` exits 0 on every input, including an unreachable embedding
  server.

Non-goals for v1: a relevance threshold (rank-fusion scores do not support
one; the nudge shows its top 3), repeat suppression within a session, and
commands behind a `cd X &&` prefix or a pipe (first command only).

## Functional Decomposition

### Capability: MCP server

A stdio Model Context Protocol server that exposes Engram retrieval as a tool.

#### Feature: MCP stdio loop

- **Description**: Serve newline-delimited JSON-RPC 2.0 on stdin/stdout.
- **Inputs**: One JSON object per line on stdin.
- **Outputs**: One JSON reply per request line on stdout, flushed per line.
- **Behavior**: Standard library only; no MCP SDK dependency. `initialize`
  returns `protocolVersion` (echo the client's, default `"2025-06-18"`),
  `capabilities: {"tools": {}}`, `serverInfo: {"name": "engram", "version":
  <package version>}`, and `instructions` (see below). `ping` returns `{}`.
  A message without `id` is a notification and gets no reply. An unknown
  method returns error `-32601`. A line that is not valid JSON returns error
  `-32700` with `id: null`. EOF on stdin ends the loop with exit 0.
  `instructions` text, exact: "engram is the portfolio memory: past agent
  sessions, PRDs, decisions, memory files, and code across all repositories.
  Call engram_query before a broad rg/grep/git-log sweep for prior decisions,
  history, or cross-repo where/why questions. Do not use it to search a known
  file."

#### Feature: `engram_query` tool

- **Description**: Run an Engram query and return pointer lines.
- **Inputs**: `query` (string, required), `scope` (`repo` or `portfolio`,
  default `portfolio`), `k` (integer 1 to 20, default 5).
- **Outputs**: `content: [{"type": "text", "text": ...}]` holding the same
  tab-separated lines `engram query` prints (`src/engram/cli.py:204-207`), or
  `no hits`; `isError` true on failure.
- **Behavior**: Call `query()` in-process (`src/engram/cli.py:190-193` shows
  the call shape), never a subprocess. Invalid arguments, a `repo` scope
  outside a registered repository, `StoreModelMismatchError`,
  `EmbeddingServerError`, and `EmbeddingPreflightError` return `isError: true`
  with the message; the server keeps running.

### Capability: Search nudge

A host-neutral command a post-tool hook calls after a shell command.

#### Feature: Payload reading

- **Description**: Extract the shell command and working directory from any
  supported host's post-tool hook payload.
- **Inputs**: JSON on stdin. Observed live shapes: Claude Code and Codex send
  `tool_input.command` and `cwd`; Copilot CLI sends `toolArgs.command` (an
  object; accept a JSON string too) and `cwd`.
- **Outputs**: `(command, cwd)`; `cwd` falls back to the process directory.
- **Behavior**: Unreadable JSON or a missing command prints one line to
  stderr and exits 0 with no stdout.

#### Feature: Broad-search detection

- **Description**: Decide whether the command is a broad search and extract
  its pattern.
- **Inputs**: `command`, `cwd`.
- **Outputs**: The search pattern, or nothing.
- **Behavior**: Tokenize with the standard library's shlex split; a parse
  error means no nudge.
  Look at the first command only.
  - `git ... log` with `-S`, `-G`, or `--grep` (separate or attached value):
    always broad; the pattern is that value.
  - `rg` and grep: skip the value of each value-taking flag (`-g`, `--glob`,
    `-t`, `--type`, `-T`, `--type-not`, `-A`, `-B`, `-C`, `-m`, `--max-count`,
    `--max-depth`, `-f`, `--file`, `-j`, `--threads`, `-M`, `--max-columns`).
    The pattern is the value of `-e`/`--regexp` when present, else the first
    bare token; remaining bare tokens are paths.
  - `find`: paths are the bare tokens before the first flag; the pattern is
    the value of `-name` or `-iname`; without one, no nudge.
  - The search is broad when a path lies under a `.claude/projects` directory,
    when any path's repository root (nearest ancestor holding `.git`) differs
    from the repository root of `cwd`, or when the paths span more than one
    root. No paths means the current directory, which is not broad.

#### Feature: Recall and emit

- **Description**: Query Engram for the pattern and print the host's
  context-injection output.
- **Inputs**: Pattern, host name (`claude`, `codex`, `copilot`, `plain`),
  environment `ENGRAM_NUDGE` and `ENGRAM_PACK_FILE`.
- **Outputs**: stdout in the host's format, or nothing. Exit code always 0.
- **Behavior**: `ENGRAM_NUDGE=off` exits before reading stdin. The query text
  is the pattern split on characters outside `[A-Za-z0-9_-]`, keeping words of
  three or more characters; an empty query means no nudge. Query in-process,
  scope `portfolio`, `k=3`. When `ENGRAM_PACK_FILE` names a readable file,
  drop each hit whose path occurs in that file's text. No remaining hits
  means no output. Any query failure prints one line to stderr and exits 0.
  Text, one line per hit: `- <path>:<start>-<end>  (<heading>)`, under the
  header `engram recall for "<query>" (prior sessions, PRDs, memory, code):`
  and above the footer `Read a cited range if it is relevant; ignore it if
  not.` Formats: `claude` and `codex` print
  `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": <text>}}`;
  `copilot` prints `{"additionalContext": <text>}`; `plain` prints the text.

## Structural Decomposition

### Repository Structure

```
src/engram/
├── mcp_server.py        # Maps to: MCP server
├── nudge.py             # Maps to: Search nudge
└── cli.py               # Subcommands `mcp` and `nudge`
tests/
├── test_mcp_server.py   # MCP server
└── test_nudge.py        # Search nudge
README.md                # Document both commands and the two environment guards
CHANGELOG.md             # Added entries
```

### Module: mcp_server

- **Maps to capability**: MCP server
- **Responsibility**: JSON-RPC loop and the `engram_query` tool.
- **Location**: `src/engram/mcp_server.py`

New symbols: `serve_mcp`, `handle_mcp_message`, `run_query_tool`, `engram_query`, `initialize`, `protocolVersion`, `isError`, `initialize_returns_instructions_and_tools_capability`, `tools_call_returns_query_lines`, `notification_gets_no_reply`, `unknown_method_returns_32601`, `invalid_json_returns_32700`, `query_failure_sets_is_error_and_keeps_serving`, `cli_mcp_serves_until_eof`

- **Exports**:
  - `serve_mcp(stdin, stdout)` - run the loop until EOF; returns 0
  - `handle_mcp_message(message)` - one request to one result or error

### Module: nudge

- **Maps to capability**: Search nudge
- **Responsibility**: Payload reading, detection, recall, and host output.
- **Location**: `src/engram/nudge.py`

New symbols: `run_nudge`, `read_hook_event`, `find_broad_search`, `build_recall_query`, `format_nudge`, `ENGRAM_NUDGE`, `ENGRAM_PACK_FILE`, `tool_input.command`, `toolArgs.command`, `nudges_for_search_outside_repo`, `stays_silent_for_search_inside_repo`, `skips_value_of_glob_flag`, `treats_git_log_pickaxe_as_broad`, `drops_hits_named_in_pack_file`, `stays_silent_when_nudge_is_off`, `exits_zero_when_query_fails`, `accepts_copilot_tool_args_as_object_and_string`, `emits_each_host_format`, `cli_nudge_dispatches_with_host`

- **Exports**:
  - `run_nudge(host, stdin, stdout, stderr, environ)` - whole flow; returns 0
  - `find_broad_search(command, cwd)` - pattern or `None`

### Module: cli

- **Maps to capability**: MCP server, Search nudge
- **Responsibility**: Register `engram mcp` and
  `engram nudge {claude,codex,copilot,plain}` in `_build_parser` and dispatch
  them in `main` (`src/engram/cli.py:555-571`).
- **Location**: `src/engram/cli.py`

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **nudge**: detection and formatting are pure functions.
- **mcp_server**: message handling is a pure function over a query callable.

### Core Layer (Phase 1)

- **cli**: Depends on [nudge, mcp_server]

### Integration Layer (Phase 2)

- **README.md, CHANGELOG.md**: Depend on [cli]

## Implementation Phases

### Phase 0: Foundation

**Goal**: Both modules work and are tested without the CLI.

**Tasks**:
- [ ] Write `src/engram/nudge.py` and `tests/test_nudge.py` (no deps) -
  Acceptance: `.venv/bin/python -m pytest -q tests/test_nudge.py` passes,
  including tests named for these rules: `nudges_for_search_outside_repo`,
  `stays_silent_for_search_inside_repo`, `skips_value_of_glob_flag`,
  `treats_git_log_pickaxe_as_broad`, `drops_hits_named_in_pack_file`,
  `stays_silent_when_nudge_is_off`, `exits_zero_when_query_fails`,
  `accepts_copilot_tool_args_as_object_and_string`,
  `emits_each_host_format`.
- [ ] Write `src/engram/mcp_server.py` and `tests/test_mcp_server.py`
  (no deps) - Acceptance:
  `.venv/bin/python -m pytest -q tests/test_mcp_server.py` passes, including
  `initialize_returns_instructions_and_tools_capability`,
  `tools_call_returns_query_lines`, `notification_gets_no_reply`,
  `unknown_method_returns_32601`, `invalid_json_returns_32700`,
  `query_failure_sets_is_error_and_keeps_serving`.

**Exit Criteria**: Both test files pass with the query callable faked.

### Phase 1: Core

**Goal**: The commands exist on the installed CLI surface.

**Tasks**:
- [ ] Register and dispatch the mcp and nudge subcommands in `src/engram/cli.py`
  (depends on: Phase 0) - Acceptance:
  `.venv/bin/python -m pytest -q tests/test_nudge.py tests/test_mcp_server.py -k cli`
  passes tests `cli_nudge_dispatches_with_host` and
  `cli_mcp_serves_until_eof`; `.venv/bin/python -m engram.cli nudge --help`
  exits 0.

**Exit Criteria**: `engram nudge plain` and `engram mcp` run from the checkout.

### Phase 2: Integration

**Goal**: Documented and released.

**Tasks**:
- [ ] Document both commands, the payload shapes, and `ENGRAM_NUDGE` /
  `ENGRAM_PACK_FILE` in `README.md`; add two Added entries to `CHANGELOG.md`
  (depends on: Phase 1) - Acceptance: `rg -c "engram nudge" README.md` and
  `rg -c "engram mcp" CHANGELOG.md` each print at least 1.

**Exit Criteria**: `.venv/bin/python -m pytest -q --ignore=eval` passes and
`git diff --check` is clean.

## Test Strategy

### Critical Scenarios

- **Happy path**: Codex payload with `rg -l foo /other/repo` → Expected:
  the additional-context field of the hook output holds three pointer lines.
- **Edge case**: `rg -n -g '*.py' needle src/` inside the repository →
  Expected: no output (pattern is `needle`, not the glob; path is inside).
- **Edge case**: every hit is named in `ENGRAM_PACK_FILE` → Expected: no output.
- **Error case**: embedding server unreachable → Expected: one stderr line,
  no stdout, exit 0; the MCP tool returns `isError: true` and serves the next
  request.

## Risks

- **Weak hits teach agents to ignore the block**: the frontmatter eligibility check keeps
  this PRD out of the queue until the agent-session evaluation records
  `Adoption decision: proceed`.
- **Latency**: a query took about 3 s in the spike. The nudge runs after the
  tool, never blocks it, and hook configs set their own timeout.
- **Misdetected pattern**: unknown value-taking flags can shift the pattern.
  The result is a poor query, never a failure; extend the flag list when seen.
- **Blind roles**: a caller that must not leak recall sets `ENGRAM_NUDGE=off`
  (agent-plugins intake 00066).
