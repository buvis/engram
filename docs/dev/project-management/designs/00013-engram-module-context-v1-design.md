# Design: index code outside parsed symbols (PRD 00013)

PRD: `docs/dev/project-management/prds/wip/00013-engram-module-context-v1.md`

## Architecture fit

Two existing modules change; no new runtime module, dependency, schema, CLI
flag or config key.

- **Chunking layer, `src/engram/symbols.py`.** `symbols.chunk` is the only
  producer of code chunks (`indexer._chunk_file` routes the `code` corpus to
  it). After its existing `_walk` over `result.structure`, it appends
  source-context chunks for the lines no emitted chunk covers. The indexer
  embeds and stores whatever `chunk` returns, so context reaches FTS, the
  vector table, `lookup_by_path`, query, packs, MCP and nudge with no change
  in those modules.
- **Store layer, `src/engram/store.py`.** Owns the reserved doc type constant
  and filters it out of `Store.lookup_by_name`. `symbols.py` already imports
  `Chunk` from `store.py`, so the constant lives in `store.py` and the import
  direction stays `symbols -> store`.
- **Indexer, `src/engram/indexer.py`: unchanged.** Its hash cache
  (`known`), empty cache (`known_empty`), legacy-anonymous migration
  (`legacy_code_sources`), failure retention and pruning already give the
  PRD's rollout: a source is re-chunked only when its content hash is new, so
  an unchanged source (chunked or cached-empty) keeps its rows and costs no
  embedding call. A changed formerly empty source has a new hash, misses
  `known_empty`, and is re-chunked.

## Module placement

| Path | Change |
|---|---|
| `src/engram/store.py` | Edit: add `MODULE_CONTEXT_DOC_TYPE`; exclude it in `Store.lookup_by_name` |
| `src/engram/symbols.py` | Edit: add `MODULE_CONTEXT_HEADING`, private `_context_chunks`; call it at the end of `chunk` |
| `tests/test_module_context.py` | New: chunk, lookup and index regressions |
| `README.md` | Edit: partial-rollout paragraph |
| `CHANGELOG.md` | Edit: one `Added` line under `[Unreleased]` (commit is `feat`) |

Not touched: `indexer.py`, `query.py`, `cli.py`, `diffmap.py`, `pack.py`,
`mcp_server.py`, `nudge.py`, existing tests, `eval/`.

## Interfaces & contracts

### `src/engram/store.py`

```python
# Reserved doc type for source text outside emitted symbol spans. Not a
# symbol: Store.lookup_by_name excludes it. A parser kind "module" is a
# different value and stays a symbol.
MODULE_CONTEXT_DOC_TYPE = "module_context"
```

Module-level constant, placed next to `DEFAULT_DB_PATH`.

`Store.lookup_by_name(self, name: str, scope: Scope, prefix: bool = False) -> list[Chunk]`
keeps its signature, scope handling, `ORDER BY path, chunk_ordinal` and
exact-then-prefix fallback. The only change: the `WHERE` clause gains
`AND doc_type != ?` bound to `MODULE_CONTEXT_DOC_TYPE`, in the one SQL
statement that serves the exact match, the explicit `prefix=True` match and
the fallback recursion. Parameter order: `[*params, MODULE_CONTEXT_DOC_TYPE, *values]`
with the new condition placed between `{where}` and `{match}`.

`Store.lookup_by_path`, `search_bm25`, `search_knn`, `legacy_code_sources`
and the schema are unchanged. `legacy_code_sources` matches heading suffix
`'None'`; the context heading suffix is `context`, so context never triggers
the legacy migration.

### `src/engram/symbols.py`

```python
from engram.store import MODULE_CONTEXT_DOC_TYPE, Chunk

MODULE_CONTEXT_HEADING = "Module context"
# Languages whose symbol-less files still get context. Data and doc grammars
# (markdown, json, yaml, ...) are left out: they would index whole files.
CONTEXT_LANGUAGES = frozenset(
    {
        "python", "javascript", "typescript", "tsx", "rust", "go", "c", "cpp",
        "arduino", "swift", "kotlin", "lua", "bash", "batch",
    }
)


def _context_chunks(
    lines: list[str], chunks: list[Chunk], path: Path, repo: str, content_hash: str
) -> list[Chunk]:
    """Chunks for the source lines no emitted symbol chunk covers."""
```

Behavior of `_context_chunks`:

1. `covered` = the set of one-based line numbers in
   `range(c.line_start, c.line_end + 1)` for every chunk in `chunks`
   (a union, so nested and overlapping spans count once; numbers past
   `len(lines)` are harmless).
2. Walk `lines` with one-based numbering. A **run** is a maximal sequence of
   consecutive line numbers not in `covered`.
3. Trim each run: drop leading and trailing lines for which
   `not line.strip()`. A run with nothing left is omitted. Interior
   whitespace-only lines stay.
4. For each remaining run, in source order, build
   `Chunk(corpus="code", repo=repo, doc_type=MODULE_CONTEXT_DOC_TYPE, path=str(path), heading=MODULE_CONTEXT_HEADING, body="\n".join(lines[first - 1 : last]), line_start=first, line_end=last, content_hash=content_hash, chunk_ordinal=n)`
   where `first`/`last` are the trimmed one-based bounds and `n` starts at
   `chunks[-1].chunk_ordinal + 1` when `chunks` is non-empty, else `1`, and
   increases by one per context chunk.
5. Return only the context chunks; it never mutates `chunks`.

`chunk(path: Path, repo: str, content_hash: str) -> list[Chunk]` keeps its
signature. Its last statement `return chunks` becomes:

```python
    if not chunks and language not in CONTEXT_LANGUAGES:
        return []
    return chunks + _context_chunks(lines, chunks, path, repo, content_hash)
```

`language` is the existing `detect_language_from_path(str(path))` result (a
plain string such as `"python"`, `"json"`, `"markdown"`). Gate (PRD, user
decision 2026-11-15): a file with at least one emitted symbol always gets
context; a symbol-less file gets it only when its language is in
`CONTEXT_LANGUAGES`; any other symbol-less file returns `[]` and is cached
empty by the indexer exactly as today. Everything before the gate is
unchanged, so:

- unsupported grammar: still appended to `skipped_files`, returns `[]`;
- read failure (`OSError`) and `process` exceptions: still propagate, raised
  before `_context_chunks` is reached;
- `not source.strip()`: still returns `[]` early;
- a nonblank file with no symbols in a `CONTEXT_LANGUAGES` language:
  `chunks` is empty, the whole file is one run (blank lines never split a
  run: only covered lines end one), ordinals start at 1;
- a nonblank file with no symbols in any other grammar (`.json`, `.md`,
  `.yaml`, `.toml`, ...): returns `[]`, not added to `skipped_files`.

`lines` is the existing `source.splitlines()` list that symbol bodies are
already sliced from. No size splitting: the body is the full trimmed run.

### Fixed values

| Name | Value |
|---|---|
| doc type | `module_context` |
| heading | `Module context` |
| corpus | `code` |
| new test file | `tests/test_module_context.py` |
| pytest selectors | `-k chunk`, `-k lookup`, `-k index` (test names must contain the word) |
| README phrases (literal) | `unchanged files`, `backfill` |

### README text (Phase 2)

One paragraph in the code-corpus/indexing part of `README.md` stating: code
outside parsed symbols (imports, constants, top-level statements) is indexed
as `Module context` chunks; they appear when a file is first indexed or its
content changes; unchanged files keep their old chunks, including files
cached as empty, and there is no automatic migration; re-embedding existing
chunks does not discover missing spans; a backfill is a separate, explicit
operation. `engram lookup --name` returns symbols only; `--file` and queries
include context. Data and doc files with no symbols (markdown, JSON, YAML,
TOML and the like) stay out of the code corpus. Also reword the existing
`engram lookup --file` comment "symbols in source order": context chunks list
after the symbols.

## Data flow

1. `indexer.index` hashes a code file. Hash known (chunks or empty cache):
   skip, no parse, no embedding. Otherwise `_chunk_file` -> `symbols.chunk`.
2. `symbols.chunk` reads and parses as today, walks symbols, then appends
   context chunks for uncovered trimmed runs.
3. Indexer embeds `text_for_embedding` (`"Module context\n<repo/rel/path>\n<body>"`,
   truncated to the existing per-model character budget by
   `client._budgeted_batches`) and upserts. FTS stores the full body.
4. A file that still yields `[]` (blank, unsupported, or symbol-less in a
   non-allowlisted grammar) is marked empty as today. A nonblank file in a
   `CONTEXT_LANGUAGES` language no longer yields `[]`.
5. `search_bm25`/`search_knn`/`lookup_by_path` return context rows like any
   code row. `lookup_by_name` filters `doc_type != 'module_context'`.

## Reuse inventory

- `symbols.chunk` and its `lines`/`chunks` locals
  (`src/engram/symbols.py:78`): the context pass consumes them directly; no
  second read or parse.
- `store.Chunk` (`src/engram/store.py:17`): reused unchanged; no new field.
- `Store.lookup_by_name` SQL (`src/engram/store.py:516`): one extra bound
  condition; the partial index `code_symbol_name` still applies.
- Indexer caches and migration (`src/engram/indexer.py:74-125`): reused as
  is; they already implement the rollout policy.
- Embed truncation (`client._budgeted_batches`, `EMBED_MAX_CHARS = 8000`):
  bounds a long context body at embed time; no new limit.
- Test patterns: `tests/test_symbols.py` (tmp file + `symbols.chunk`),
  `tests/test_backlog_delivery.py::add_chunk` (store rows with a fake
  2-dim `Vector`), `tests/test_empty_sources.py` and `tests/test_indexer.py`
  (temporary store, monkeypatched enumeration and `embed`).
- Gap/complement helper: nothing found, greps tried:
  `rg "uncovered|gap|complement|module_context|Module context|span" src`
  (hits only `diffmap.py`/`pack.py` span overlap checks for diff hunks, not
  a complement); control `rg "span" src` returned hits, so the pattern works.
  Synonyms from `rationalizations.md` (get/find/lookup/resolve/select,
  build/create/make) applied to "context"/"gap"/"lines": no helper.

## Alternatives considered

1. **Chosen: line-set complement inside `symbols.chunk`, filter in
   `lookup_by_name`.** About 30 lines of production code, no schema or
   indexer change. This is also the smallest diff that meets the PRD.
2. **Whole-file "module" chunk per file.** Simpler (no gap math) but
   duplicates every symbol body in FTS and vectors, roughly doubling code
   rows and distorting BM25. Rejected: PRD requires no duplication of
   emitted symbols.
3. **Top-level-only spans from the parser (use only depth-0 items).**
   Equivalent for well-nested output, but depends on the parser's nesting
   being complete; the union of all emitted spans is correct even when
   spans overlap oddly or a named child sticks out of its parent.
4. **Filter context by heading text (`heading != 'Module context'`) instead
   of doc type.** Rejected: a real symbol can be named `context`; the doc
   type is the reserved discriminator the PRD names.

## Risks & edge cases

- **Line model.** `str.splitlines()` also splits on form feed, `\x1c-\x1e`,
  `\x85`, ` `, ` ` and lone `\r`, while tree-sitter rows split on
  `\n`. Existing symbol bodies already slice `lines` by parser rows, so a
  file with such characters can have shifted symbol bodies today. Context
  is computed against the same `lines` and the same emitted
  `line_start`/`line_end`, so the invariant "each line of `lines` is in a
  symbol span or a context run, never both" holds by construction even
  there. Fixing the pre-existing shift is out of scope.
- **Same-line neighbors.** Coverage is line-granular. Text sharing a line
  with a symbol (`x = 1; def f(): ...`) counts as covered, and it is already
  inside that symbol's line-sliced body.
- **Comments and decorators** outside a symbol's span become context. That
  is intended coverage, not noise filtering.
- **Which files gain rows (measured 2026-11-15, read-only probe over the
  registered portfolio).** Without a gate, every grammar-supported file with
  no symbols would become one whole-file chunk: markdown 5,777 files, json
  5,399, vimdoc 1,673, html 568, yaml 497 (in this repo alone 1.9 MB,
  including one 740 KB JSON row), and markdown would be duplicated into the
  code corpus that packs read. `CONTEXT_LANGUAGES` is the set of languages
  whose parser emitted symbols somewhere in the portfolio. Svelte, CSS,
  Terraform, YAML and shell dialects without symbols (fish, powershell) are
  out; widening the set is a one-line change with its own measurement.
- **Large context.** A constants-only file is one chunk. Embedding input is
  truncated at the existing budget; FTS keeps the full body. Files with a
  line over 1000 chars are already excluded upstream.
- **Row growth.** Only newly processed sources gain rows; no bulk
  re-embedding. `chunks_added` rises for such files; no existing test
  asserts a count on a file with uncovered nonblank lines (checked:
  `test_symbols.py`, `test_backlog_delivery.py`, `test_empty_sources.py`,
  `test_indexer.py`, pack tests use symbol-only or fully covered sources).
- **Name lookup of the word `context`.** The heading suffix is `context`;
  without the doc-type filter, `lookup --name context` would return every
  context chunk. The filter covers exact, prefix and fallback.
- **Mixed rollout.** Old-hash sources have no context until edited.
  Documented in README; `engram status` is unchanged.
- **Rollback.** No schema or cache-version change. Reverting the commit
  stops new context rows; existing ones are ordinary code rows that vanish
  when their file changes, or on `engram index --rebuild`.
- **Likely next changes.** (1) An explicit backfill command: needs a way to
  find old-hash code sources without context; nothing here blocks it (a
  query on `doc_type` works). (2) Splitting long context by size: would
  change only `_context_chunks`. (3) OR lexical matching (intake 00009):
  independent of chunking.

## Test strategy outline

All in `tests/test_module_context.py`, temporary files and stores only, fake
embeddings, test names carrying `chunk`, `lookup` or `index`.

- **chunk** (direct `symbols.chunk`): preamble + interstitial + tail around
  two functions (exact bodies, line numbers, ordinals after the last symbol
  ordinal, source order); symbol chunks equal the pre-change list exactly
  (computed by filtering `doc_type != "module_context"` and compared to
  hand-written expected `Chunk`s); imports/constants-only `.py` file gives
  one chunk with ordinal 1; a symbol-less `.json` and `.md` file return `[]`
  and are not in `skipped_files`; nested class/method does not duplicate lines;
  leading/trailing blank lines trimmed, interior blank kept, all-blank gap
  omitted; non-ASCII lines before a symbol keep correct line numbers; every
  nonblank line outside symbol spans appears exactly once across context
  bodies (property check over the fixture); whitespace-only and unsupported
  files still return `[]`; a raising `process` still raises.
- **lookup** (store rows): a `module_context` row with heading
  `Module context` is absent from `lookup_by_name("context")` exact,
  `prefix=True` and fallback (`"cont"`); a real `function` named `context`
  and a `module`-doc-type row named `context` are returned; `lookup_by_path`
  returns the context row in ordinal order; `search_bm25` finds an
  outside-symbol token; repo scope isolates two repos.
- **index** (`indexer.index`, monkeypatched enumeration and counting fake
  `embed`): new file gains context and the token is FTS-searchable; second
  unchanged run makes zero embed calls and adds zero chunks; a pre-seeded
  cached-empty source with the same hash stays cached (no parse, no embed);
  the same source after a content change is re-chunked and gains context;
  deleting the file prunes its context rows; a chunker failure on a changed
  file keeps the old rows and is reported in `failed_sources`.
- Existing suites run unchanged: `tests/test_symbols.py`,
  `tests/test_indexer.py`, `tests/test_empty_sources.py`,
  `tests/test_backlog_delivery.py`, then the portable main and eval suites.

## Review log

- blocker (dispatch 1, fixed): every grammar-supported data/doc file would
  become a whole-file context chunk. Resolved by user decision 2026-11-15
  ("code only"): `CONTEXT_LANGUAGES` gate; PRD amended.
- non-blocker (dispatch 1): editing `symbols.py`/`store.py` changes the
  harness chunking signature (`harness._chunking_sources`), so the next gate
  run pays a cold candidate build, and harness indexes then have full
  context while production is in partial rollout.
- non-blocker (dispatch 1): about half of code-side context chunks are
  single lines (top-level decorators, interstitial one-liners). Merging or
  attaching decorators to the next symbol is a follow-up, not a bug here.
- non-blocker (dispatch 1): after a code revert, leftover context rows match
  `lookup --name context` until `engram index --rebuild` or
  `DELETE FROM chunks WHERE doc_type='module_context'`.
- non-blocker (dispatch 1): absence of a context row does not identify an
  old-hash source (fully covered files have none), so a later backfill needs
  a full code re-chunk or a new marker; rollout progress is not observable.
- non-blocker (dispatch 1, folded into the README contract): `lookup --file`
  lists context after symbols, so README's "symbols in source order" needs
  rewording.
- question (dispatch 1): context `line_start`/`line_end` inherit the
  existing `splitlines()` drift on form feed, `\x1c-\x1e`, `\x85`, U+2028/9
  and lone `\r`. The non-ASCII fixture uses accented and CJK letters only.
- question (dispatch 1): heading `Module context` prints the same as a real
  `Module` symbol named `context` in pointers; accepted, the PRD fixes the
  heading and `doc_type` tells them apart.
dispatch 1 (claude): cardinal-sin 0, blocker 1, non-blocker 5, question 2
- non-blocker (dispatch 2): the unchanged-file wording omits the existing
  legacy-anonymous migration (`indexer.index` `migrate` path), which
  re-chunks an unchanged source and so also gives it context. README must
  name that exception; indexer behavior stays.
- non-blocker (dispatch 2): a nested class/method fixture cannot tell a
  union of all spans from top-level spans only. The chunk tests should add a
  direct `_context_chunks` case with crossing spans and a child that extends
  past its parent.
- dispatch 2 engagement re-run (fewer than 3 findings): seven named checks
  (gate language names for 18 extensions, gate scope and empty cache,
  `_context_chunks` walk-through, lookup SQL bindings in both scopes,
  existing-test impact, heading/doc-type consumers, test feasibility) all
  returned section-anchored "checked, correct"; no new findings. Not weak.
dispatch 2 (codex): cardinal-sin 0, blocker 0, non-blocker 2, question 0
