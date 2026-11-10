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
| `memory` | Claude auto-memory `~/.claude/projects/<slug>/memory/*.md` and repository memory `docs/dev/project-management/memory/*.md` | heading |
| `findings` | reviews and decision audit logs ingested by `engram harvest` | record |
| `transcripts` | session JSONL, one turn per chunk | JSONL line |
| `code` | every git-tracked file, one chunk per function or class | line span |

`findings` is the only corpus whose hits carry their text, because a harvested
finding has to survive the review file being trashed. Every other corpus is
pointer-only.

## Repository memory

A repo can keep its own memory in `docs/dev/project-management/memory/`, one
fact per `<slug>.md` file, with YAML frontmatter and a Markdown body.

Required keys:

- `name`: equals the file stem and matches `^[a-z0-9][a-z0-9-]*$`.
- `description`: non-empty, one line.
- `type`: `project`, `feedback`, or `reference`. Claude's nested
  `metadata.type` counts when top-level `type` is absent. `type: user` is a
  violation.
- `source`: non-empty string.
- `evidence`: non-empty list of non-empty strings.

Any `author` or `date` key is a violation, because Git carries both. Other
extra keys are allowed.

`MEMORY.md` in the same directory lists every memory once, as
`- [<title>](<slug>.md)` lines sorted by slug, in at most 200 lines and 25,000
bytes.

Repository memory must be public-safe. Keep host-private, personal, and secret
facts in host-global memory. The credential check is a guard, not proof of
public safety.

Commit each change as `docs(memory): <verb> <slug>`.

`engram memory check [PATH]` checks the directory. It exits 0 when clean and 1
on any violation or when the directory is absent. Each violation prints as
`<file><TAB><rule><TAB><detail>`. `engram status` adds `memory<TAB>invalid=<n>`
(exit 1) and `memory<TAB>legacy-shadowed=<repo>` (informational). Once a repo
has at least one repository memory file, engram stops indexing its Claude
auto-memory.

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
engram index --reembed-code             # refresh code vectors in place
engram status --scope portfolio         # per-corpus counts, stale and dead rows
engram lookup --name stop_served --scope portfolio  # exact name, then prefix
engram lookup --name stop_served --scope portfolio --repo engram
engram lookup --file src/engram/client.py # symbols in source order
engram query --scope repo "retry a flaky embedding server"
engram query --scope portfolio --corpus findings -k 10 "token budget overflow"
engram harvest docs/dev/project-management/reviews/00003-audit.md
engram pack --diff HEAD~5..HEAD         # reviewer context pack for a diff
```

`query` requires `--scope`. Unscoped retrieval is a correctness bug, not a
convenience gap, so it is a usage error.

`query -k N` (also `--k N`) sets the positive result limit; the default is 5.
`index --rebuild` rebuilds the portfolio index and cannot be combined with
`--scope` or `--corpus`. Both flags are supported interfaces.

Output is one tab-separated line per hit:

```
1	0.0328	/path/to/client.py:404-457	Function _spawn_server
```

Indexing keys on content hash, so re-indexing unchanged content embeds nothing.
A full portfolio pass over unchanged content takes about 20 seconds.

Memory attribution matches Claude's project directory encoding against complete
registered repository paths. Unknown directories and ambiguous encodings stay
`_unmapped` and are available only through portfolio queries. After upgrading
from the old path mapping, run `engram index --scope portfolio --corpus memory`
to replace old attribution across the memory corpus. This incremental pass keeps
other corpora intact; a repository-only pass cannot prune old `_unmapped` rows.

`lookup` reads code definitions directly from SQLite without loading embedding
configuration or starting a server. Output is `path:start-end<TAB>heading`;
no matches prints an error and exits 1. Relative file paths resolve from the
current registered Git worktree root.

Code indexing excludes `node_modules`, `vendor`, `dist`, `build`, `.venv`, and
`third_party` path segments, `*.min.*` filenames, and files with lines longer
than 1000 characters. Extra globs match repository-relative or absolute paths.
Anonymous symbols inside named ancestors remain in their parent's body;
top-level anonymous symbols emitted by the parser get an explicit label.
The next code index prunes exclusions and migrates old `None` headings once.
`status` reports excluded files separately from files without a grammar.

`status` exits 1 for degraded stale files, dead rows, or unavailable required
sources. Recently modified stale transcripts are reported as `in-flight` and
alone do not make it fail. Optional, never-indexed PRD/decision/discovery
directories may be absent without degrading the index.

`harvest` detects audit logs by their heading or decision-section shape, keeps
the header and each decision block, and preserves rationale text. An audit
without decision blocks fails; review parsing and per-file reporting are unchanged.

## Config

`~/.local/share/engram/config.toml`, written with defaults on first run:

```toml
[[embedding]]
id = "Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0"
endpoint = "http://127.0.0.1:8081/v1"

[pinned]
id = ""

[code]
exclude_globs = [] # extra exclusions, for example "generated/*"

[transcripts]
in_flight_seconds = 600 # positive integer; default is ten minutes
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

Local model comparisons, including challenger embeddings and rerankers, are
documented in [eval/README.md](eval/README.md). These experiments use private
snapshots and leave the production model and index unchanged.

```sh
uv run python -m pytest -q --ignore=eval
PYTHONPATH=src:. uv run python -m pytest -q eval
```

Tests marked `private` check the maintainer's retained evaluation evidence and
fail without it. CI runs only the portable tests, with `-m "not private"`, so a
green CI run says nothing about that private evidence.

Working documents, PRDs, and reviews live under tracked
`docs/dev/project-management/`; disposable packs live under globally ignored
`docs/dev/tmp/`.
