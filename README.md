# engram

Local semantic recall across every repo you work in.

Engram indexes the artifacts a coding session produces (PRDs, decisions, discovery
docs, review findings, agent memories, session transcripts, and code symbols) into
one sqlite store, and answers questions against all of it with hybrid BM25 +
vector search. Results are `file:line` pointers. You read the source yourself.

It answers "have I solved this before, and what did the reviewer say about it",
across every repo you have registered and every session you have run. It does
not answer "what does this function do" (see
[Pairing with serena](#pairing-with-serena)).

Everything runs on your machine. The only off-machine call is the one-time model
download the first time an embedding server starts.

## Corpora

| Corpus | Source | Pointer |
|---|---|---|
| `prd` | `docs/dev/project-management/prds/**/*.md` in every registered repo | heading |
| `decision` | `docs/dev/project-management/meta/decisions.md` | heading |
| `discovery` | `docs/dev/project-management/discovery/*.md` | heading |
| `memory` | `~/.claude/projects/*/memory/*.md` | heading |
| `findings` | review files ingested by `engram harvest` | record |
| `transcripts` | session JSONL, one turn per chunk | JSONL line |
| `code` | every git-tracked file, one chunk per function or class | line span |

`findings` is the only corpus whose hits carry their text, because a harvested
finding has to survive the review file being trashed. Every other corpus is
pointer-only.

## Install

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and `llama-server`
(`brew install llama.cpp`) for embeddings.

```sh
uv tool install .
```

Repos are discovered through [gita](https://github.com/nosarthur/gita)'s
`~/.config/gita/repos.csv`. A repo that is not registered there is invisible to
engram.

## Usage

```sh
engram index --scope portfolio          # index everything (incremental)
engram index --scope repo --corpus prd  # index one corpus in the current repo
engram index --rebuild                  # re-embed from scratch, atomic swap
engram status --scope portfolio         # per-corpus counts, stale and dead rows
engram query --scope repo "retry a flaky embedding server"
engram query --scope portfolio --corpus findings -k 10 "token budget overflow"
engram harvest docs/dev/project-management/reviews/00003-audit.md
engram pack --diff HEAD~5..HEAD         # reviewer context pack for a diff
```

`query` requires `--scope`. Unscoped retrieval is a correctness bug, not a
convenience gap, so it is a usage error.

Output is one tab-separated line per hit:

```
1	0.0328	/path/to/client.py:404-457	Function _spawn_server
```

Indexing keys on content hash, so re-indexing unchanged content embeds nothing.
A full portfolio pass over unchanged content takes about 20 seconds.

## Config

`~/.local/share/engram/config.toml`, written with defaults on first run:

```toml
[[embedding]]
id = "Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0"
endpoint = "http://127.0.0.1:8081/v1"

[pinned]
id = ""
```

Endpoints must be loopback with an explicit port. Engram spawns and stops the
server itself when nothing is serving. The store records the model id and
dimension; a mismatch fails loud and demands `engram index --rebuild` rather
than leaving a half-embedded index behind.

The database lives at `~/.local/share/engram/engram.db`.

`eval/harness.py` scores the configured models against a gold set, compares them
to an `rg` baseline, and pins the winner.

## Pairing with serena

[Serena](https://github.com/oraios/serena) reads your code through a language
server. Engram reads your history through an index. They overlap on almost
nothing, and the pair covers more than either alone.

| | serena | engram |
|---|---|---|
| Backend | language server (LSP) | sqlite-vec + FTS5, local embeddings |
| Scope | the active project | every registered repo, plus transcripts and memories |
| Match | exact, resolved | fuzzy, ranked |
| Freshness | live | indexed, refreshed on demand |
| Writes | edits symbols in place | read-only |

Serena knows that `stop_served` is a method on this class and that eleven call
sites resolve to it. That needs import, alias, and inheritance resolution, which
is what a language server does and what tree-sitter cannot do. Engram will not
try to compete there.

Engram knows you hit this exact problem in another repo four months ago, that the
fix was reverted, and that a reviewer left a finding explaining why. No language
server can see any of that, because none of it is code.

The working split:

- Starting something? Ask engram for precedent first. It returns pointers into
  other repos, old sessions, and past review findings.
- Reading or changing code? Use serena. `find_symbol` and
  `find_referencing_symbols` beat ranked retrieval whenever an exact answer
  exists.
- Reviewing a diff? `engram pack` builds the context (similar code, reuse
  precedent, findings precedent), then serena navigates whatever the pack points
  at.

Their memories differ too. Serena's live in `.serena/memories/` and describe one
project. Engram indexes `~/.claude/projects/*/memory/` across all of them, so a
lesson learned in one repo surfaces while you work in another.

Planned: exact symbol lookup and file symbol overview in engram, cross-repo,
built on the symbol data already in the store. Reference finding stays serena's
job.

## Development

```sh
uv run pytest
```

Working documents, PRDs, and reviews live under tracked
`docs/dev/project-management/`; disposable packs live under globally ignored
`docs/dev/tmp/`.
