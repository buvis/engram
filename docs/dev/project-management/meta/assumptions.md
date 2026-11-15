# Assumptions ledger (PRD 00013)

## 1: Emit module-context chunks for source lines outside emitted symbol spans

- Tess: the direct `_context_chunks` test keeps the highest-ordinal span last, so it separates `chunks[-1].chunk_ordinal + 1` from `len(chunks) + 1` but not from `max + 1` (the contract says last; `chunk` always passes increasing ordinals).
- Tess: `[1, 2, 3]` in `consts.py.json` and plain prose in `README.md` are detected as json and markdown and yield no symbols (confirmed against the pre-change `chunk`).
- Tess (strengthen): ruby's `method` doc type, `Method size` heading and span come from observed parser output, not the contract; the js, rs, go and sh fixtures yield no symbols today.
- Tess (strengthen): a `.java` file holding only `package demo;` yields a `module` symbol, so java was left out of the symbol-less cases.
- Ivan: `CONTEXT_LANGUAGES` lists one entry per line (formatter style); values match the design.
- Ivan: the CHANGELOG bullet is one physical line; neighboring entries wrap near 80 columns.
- Orchestrator: a formatter hook reflowed `store.py`, `symbols.py` and the test file during subagent dispatches (trailing commas, line splits only); the orchestrator reverted the unrelated reflow in `src/` each time and committed the test reflow with the strengthen commit.
- Pat (LOW, not fixed): `_context_chunks` builds full line-number lists per run; the test re-types the `CONTEXT_LANGUAGES` literal; `_sym` takes nine positional arguments.

## 2: Exclude module-context chunks from Store.lookup_by_name

- Tess: an exact match that finds only context rows counts as "finds nothing", so the call falls back to the prefix match.
- Tess: `lookup_by_name("Module context", ...)` (a name with a space) returns `[]` when only context rows exist.
- Tess (strengthen): non-code rows use corpus and doc type `prd`; a context row may carry a lower ordinal than a symbol in store-level tests, although the chunker never emits that.
- Tess (strengthen): FTS splits `wombat.run()` into tokens, so `wombat` is found (confirmed by the passing run after implementation).
- Orchestrator: the CHANGELOG bullet from task 1 was extended in the task 2 commit instead of adding a second bullet.
- Pat (LOW, not fixed): `_put` is a third near-duplicate row constructor in the test file; one test ends with an assertion over its own fixture literals; the `_sym` reflow came from the formatter hook.

## 3: Add incremental index regressions for module context and document the partial rollout

- Orchestrator: test-and-docs task, so Tess and Devon did not run; Ivan wrote the index tests against the unchanged indexer and all passed first time (no red-check possible, no production change).
- Ivan: the cached-empty unchanged and changed cases share one test (case 4 runs "after that"); this also keeps the file under 800 lines (797).
- Ivan: parser failure is simulated by setting `symbols.process` to `None` (calling it raises `TypeError`, which the indexer treats as a parse failure) instead of an explicit raising function, to stay under the line limit.
- Ivan: the README paragraph sits after the code-indexing paragraph (near line 169), not at the "Indexing keys on content hash" line; it names `--reembed-code` as the re-embedding path that does not find missing spans.
- Ivan: `files_skipped` is not asserted in the index tests.
- Pat (LOW): trailing blank line and README wrap fixed by the orchestrator in a style commit; the `_service` helper name (writes a file and returns expected rows) was left as is.

## 4: [D1] Count lines at newline only and trim context runs in one pass (review cycle 1 rework)

- Orchestrator (micro lane): `source.split("\n")` needs no CRLF handling because `Path.read_text()` uses universal newlines, which turn `\r\n` and lone `\r` into `\n`. A CRLF probe chunked with no `\r` in any body, which refutes Pat's MEDIUM.
- Orchestrator: the form-feed regression test lives in `tests/test_symbols.py` because adding it to `tests/test_module_context.py` pushed that file to 820 lines.
