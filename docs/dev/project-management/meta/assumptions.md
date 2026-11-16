## 1: Add code_chunks_with_vectors and unmark_empty_source to Store

- `code_chunks_with_vectors` takes the path as a `str`, matching how chunk paths are stored. The PRD says "Path" but doesn't say `pathlib.Path`.
- Test vector values are exactly representable in float32, so exact `==` holds after a float32 round trip.
- "Filtered to corpus='code' and the path" means an exact match on the path; there is no filter by repo.
- `unmark_empty_source` on a missing row does nothing and raises nothing. This follows from the stated plain DELETE.
- The model id and dimension for returned vectors come from the store's settings, not from each row; the store allows only one model and dimension per database.
- Like `mark_empty_source`, `unmark_empty_source` does not open its own transaction.
- Found the test file with one `rg` search for a test function name, because the task did not say where the tests live.

## 2: Add backfill_code and BackfillReport to indexer

- `failed_sources` entries are `str(file.path)`, compared as a sorted list.
- `hash_source` on a nonexistent file raises an `OSError` (for example `FileNotFoundError`), so the missing file ends up in `failed_sources`.
- The backfill stores chunks with `path = str(file.path)`, matching `_chunk_file`'s existing convention. Lookups use `code_chunks_with_vectors(str(path))`.
- `symbols.chunk` is called with the `Path` object from `CorpusFile`, not a str.
- The texts sent to `embed` contain each chunk's body; tests look for marker substrings rather than an exact text format (later tightened to exact `text_for_embedding` equality during strengthening).
- `assert_configured_model` passes on a fresh store with no chunks.
- For a known-empty source, whether `sources_rechunked` increments is not stated by the contract; strengthened tests assert it does (=1).
- A known source whose fresh chunking is now empty counts in `sources_rechunked` (contract step 6's "when fresh is empty" branch), even though it is distinct from the normal skip case.
- The order of texts inside one embed call is unspecified; strengthened tests compare sorted lists where order could vary.
- An empty-marked source whose chunker raises keeps its empty mark (contract step 5's "leaves its rows untouched" applied to the empty-source case).
- A stored vector is reused when a fresh chunk's `text_for_embedding` matches an existing stored chunk's, not by chunk_ordinal position (Devon-exploit-driven: position-based reuse passed the initial tests and was tightened).
- `symbols.chunk` is called with `(file.path, repo, hash_source(path))` — the keyword/positional shape wasn't specified in the task description beyond the Behavior steps.

## 3: Add --backfill-code CLI flag

- `backfill_code(store, config, scope) -> BackfillReport` has fields `sources_rechunked`, `chunks_embedded`, `vectors_reused`, `empty_cleared`, `failed_sources` (taken from the tests, without reading indexer.py directly).
- With no `--scope`, `--backfill-code` defaults to the `repo` scope, like plain `index`.
- `--scope` can be combined with `--backfill-code` (only `--corpus`, `--rebuild`, `--reembed-code` are rejected).
- Errors (`StoreModelMismatchError`, `FileNotFoundError`, `EmbeddingServerError`, `EmbeddingPreflightError`) are handled the same way the plain `index` branch already does; untested by this task's two named tests.
- `--backfill-code` does not take the write lock, matching `--reembed-code` and plain `index`.
- A missing file with no stored rows lands in `failed_sources`, mirroring the existing chunker-failure test.
- The order of `failed_sources` is not part of the contract; stderr lines are compared as a sorted set in the strengthened test.

## 4: Document --backfill-code in README and CHANGELOG

- `--backfill-code`'s effect (re-chunks indexed code files, unchanged files gain module-context chunks, unchanged chunks keep their stored vectors) is described from the task brief and the surrounding README paragraph; `src/engram/indexer.py` was not read since it was not in this task's file allowlist.
- The README Usage example uses a concrete `--scope portfolio`, matching the style of the other examples in that block.
- The new CHANGELOG bullet sits next to the related existing **index** Module-context entry, not at the end of the Added section.

## 5: [D1] src/engram/indexer.py (review cycle 1 rework)

- `replace_source_chunks_and_empty_mark` returns `None` and lets any exception propagate unwrapped.
- `content_hash` is ignored when `items` is non-empty (the mark is deleted, not rewritten).
- A deferred `BEGIN` (as in the existing `replace_chunks_for_source`) is enough; `BEGIN IMMEDIATE` is not required for the tested isolation.
- `vectors_reused` counts each chunk that reused a stored vector, so a crash-window source counts `sources_rechunked` 1 and `empty_cleared` 1.
- A source whose stored rows and chunker output are both empty is "nothing to change", even under a mark recorded at a different hash (unreachable from `backfill_code`).
- Items whose `chunk.path` differs from the `path` argument are stored at their own path, while the rows deleted are those of the `path` argument.
- `replace_chunks_for_source`, `known_sources` and `known_empty_sources_by_corpus` treat `"docs"` exactly as `"code"`.
- Interruption is simulated by substituting `Store.conn`; an implementation writing through another connection fails the tests loudly.
- `unmark_empty_source` keeps its own tests but now has no production caller (the PRD named it as a deliverable, so it was kept).
