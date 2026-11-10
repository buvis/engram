# Spike: engram plugin feasibility

Throwaway. Nothing here ships. Date: 2026-11-10.

## Idea (user, verbatim)

> we can't rely on hooks, the solution must be portable and hooks aren't
> standardized. I think Agent Plugins tries to fix that and probably, we'll need
> to have a plugin for engram.

> we will ship the plugin with as many per-host hooks we can develop knowing the
> hosts (of course we know the ones we use). We'll just need to make sure it
> doesn't clash with the orchestrator injection

## Smallest end-to-end outcome

One plugin directory that passes the agent-plugins validator and holds:

1. a portable skill and a portable MCP server (the pull path),
2. one host-neutral nudge core plus thin per-host hook adapters (the push
   path): after a broad search, the agent sees engram hits,
3. a guard that keeps the nudge silent or deduplicated when the orchestrator
   already injected engram context.

## Guessed contract

- Plugin name `engram`, in `buvis/agent-plugins/plugins/engram/` (guess).
- MCP server is `engram mcp` (a new CLI subcommand); the plugin only names the
  command (guess). The spike stands in with `server/engram_mcp.py`.
- MCP tools: `engram_query(query, scope, k)` and `engram_lookup(symbol)` (guess;
  spike builds query only).
- Nudge fires **after** a broad search (post-tool-use), not before (guess,
  driven by host research: post-tool injection is the common denominator).
- "Broad" = `rg`/`grep`/`find`/`git log -S|-G|--grep` that targets a path
  outside the current repo, more than one repo, or a transcript store (guess).
- Orchestrator clash contract (guess): the orchestrator sets
  `ENGRAM_NUDGE=off` to silence the nudge, or `ENGRAM_PACK_FILE=<path>` so the
  nudge drops hits the pack already contains.
- Per-host adapters live in reverse-domain extension directories (guess at the
  directory names).

## Host research (2026-11-10)

Sources: installed packages on this machine (Codex 0.167.0 binary strings, Pi
1.5.0 `docs/extensions.md` and `docs/mcp.md`, Gemini CLI `docs/hooks/reference.md`)
and official hook docs for Copilot, Kiro, and Codex.

| Host | Skills | MCP | Inject before tool | Inject after tool | Session / prompt inject | Plugin ships hooks |
|---|---|---|---|---|---|---|
| Claude Code | yes | yes | `additionalContext` | `additionalContext` | yes | yes (`hooks/hooks.json`) |
| Codex | yes | yes | `hookSpecificOutput.additionalContext` (JSON only) | same | yes | yes, needs `/hooks` trust |
| Copilot CLI | yes | yes | no (deny reason only) | `additionalContext`, 10 KB cap | session start only; prompt output dropped | yes (`hooks.json`) |
| Kiro CLI | yes | yes | stdout on exit 0 (inferred for tool events) | same (inferred) | yes | not stated |
| Gemini CLI | n/a | yes | no (decision only) | `hookSpecificOutput.additionalContext` | `BeforeAgent`, `SessionStart` | via extension |
| Pi | yes | yes (stdio, HTTP) | block or mutate only | `tool_result` can modify result | `before_agent_start` system prompt | TypeScript extension |

Common denominator: every host can add text **after** a tool call.

## Round 1 result (simulated payloads)

`python3 demo.py`: validator passes; MCP `initialize`, `tools/list`,
`tools/call` answer; the nudge emits each host's documented output; a search
inside the repo is silent; `ENGRAM_NUDGE=off` is silent; `ENGRAM_PACK_FILE`
drops packed hits.

## Round 2 result (live hosts, 2026-11-10)

Goal: replace simulated payloads with real ones. Each host ran one prompt in a
scratch repository whose hook config pointed at the nudge.

| Host | Result |
|---|---|
| Copilot CLI 1.0.108 | **Verified end to end.** Repo hook `.github/hooks/*.json` + `--trust-folder`; the model quoted the three recall lines. Real payload: `toolName: "bash"`, `toolArgs` is an object (not a string), `cwd`, `sessionId`, `toolCallId`. |
| Codex 0.167.0 | **Not verified.** User-level hooks fire (and the user's gateguard hook blocks the first Bash call, then allows the retry). A repo `.codex/hooks.json` PostToolUse hook never fired, even with `--dangerously-bypass-hook-trust` and a project trust override. Delivery must be user-level `hooks.json` or a real plugin install; neither was tried. |
| Claude Code | **Adapter not run.** A nested `claude -p` cannot authenticate inside the agent sandbox. The mechanism itself is known good: this session received `additionalContext` from other PreToolUse hooks. |
| Pi 1.5.0 | **Not run.** The local model server is down and the Copilot provider rejects the sandbox token. The adapter stays an unrun sketch. |
| Gemini CLI 0.67.0 | **Not usable on this machine.** Authentication fails with `IneligibleTierError` (client no longer supported for the account tier). Drop Gemini from the host list unless that changes. |
| Kiro | **Not run.** No Kiro CLI on PATH in the sandbox. |

Contract changes from round 2:

- Copilot's `toolArgs` arrives as an object; keep accepting the string form too.
- A repo-level hook file is not a reliable delivery path on Codex. The plugin
  must install hooks where each host loads them for every session.
- Existing user hooks run beside the nudge (gateguard blocked first). The nudge
  must stay post-tool and never block, so it cannot fight a gate.
- Claude, Pi, Codex-as-plugin, and Kiro need a run outside the sandbox.

## Round 3 (2026-11-10)

- **Codex 0.167.0: verified end to end** when the hook comes from config
  (`-c hooks.PostToolUse=[…]`, the same table `~/.codex/config.toml` holds).
  The model quoted the recall lines. Real payload: `tool_name: "Bash"`,
  `tool_input.command`, `cwd`, `session_id`, `turn_id`, `hook_event_name`,
  `permission_mode`. So Codex delivery is user-level config or a plugin install,
  not a repo file. A hook shipped by an installed Codex plugin is still untested.
- **Claude and Pi: awaiting a run outside the sandbox.** `live_check.py` sets up
  scratch repositories, runs both hosts, and writes
  `docs/dev/tmp/engram-plugin-live.json`. Inside the sandbox it ran and reported
  both hosts unauthenticated, as expected.
- Kiro stays untested: no CLI in the sandbox and the hook file schema is unread.
