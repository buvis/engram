## 1: Add code_chunks_with_vectors and unmark_empty_source to Store

- `code_chunks_with_vectors` takes the path as a `str`, matching how chunk paths are stored. The PRD says "Path" but doesn't say `pathlib.Path`.
- Test vector values are exactly representable in float32, so exact `==` holds after a float32 round trip.
- "Filtered to corpus='code' and the path" means an exact match on the path; there is no filter by repo.
- `unmark_empty_source` on a missing row does nothing and raises nothing. This follows from the stated plain DELETE.
- The model id and dimension for returned vectors come from the store's settings, not from each row; the store allows only one model and dimension per database.
- Like `mark_empty_source`, `unmark_empty_source` does not open its own transaction.
- Found the test file with one `rg` search for a test function name, because the task did not say where the tests live.
