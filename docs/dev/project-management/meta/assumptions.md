# Assumption ledger — PRD 00014 (batch 202611161217)

## 1: Strict reviewers check in findings.py

- The literal "alice,bob" is written as a plain YAML scalar (reviewers: alice,bob); other values are encoded with json.dumps, which YAML parses back to the same Python objects. (Tess)
- The error message must match exactly (anchored regex), as the contract states it verbatim. (Tess)
- Only tests selected by `-k reviewers` count for the strengthen pass, so an allowlist exploit also allowlisted the default fixture "alice,bob,carl". (Devon)
- YAML `true`, `3.5`, `null` and tab-only strings are invalid reviewers values; the tests reject `1` and `[1]`, which only implies this. (Devon)
- A single string such as "alice,bob" counts as valid if it is not blank; it is not split on commas or checked per-name, since the tests accept "alice,bob" as one string. (Ivan)
- A tuple or other non-list sequence is rejected; YAML only produces lists, so this cannot come up in practice. (Ivan)

## 2: Canonical registry match in harvest.py

- `_resolve_repo_for_path` runs `git rev-parse --show-toplevel` before it reads the registry; the unreadable-registry test picks the failing file by the last git working directory, so it depends on this order. (Tess)
- `harvest.py` reads the registry through the module attribute `corpora.read_repos_csv`. (Tess)
- When the registry read fails, the `no_repo` result's `error` field is not checked, since the contract does not say what it holds. (Tess)
- `//` counts as a valid trailing-slash spelling alongside `/`. (Tess)
- Non-`OSError` exceptions from the registry read (e.g. `ValueError`) are expected to propagate rather than be swallowed. (Tess, Ivan)
- Resolving a registry path inside the loop needs no per-row error handling: non-strict `Path.resolve()` does not raise for a missing path, and no test covers an unresolvable registry entry. (Ivan)
- Moving the resolve-path tests into a new `tests/test_harvest_resolve.py` module counts as "splitting the test file" for the style gate; the setup helper extraction is an allowed fix for the function-length violation. (Ivan, style-fix dispatch)
- Shared test helpers (`_init_git_repo`, `_write_repos_csv`) moved into a new `tests/_harvest_helpers.py` rather than reusing the identical helper already in `_cli_helpers.py`, to avoid touching an existing helper module. (Ivan, style-fix dispatch)

## 3: write_lock and StoreBusyError in store.py

- `write_lock` accepts only `pathlib.Path` arguments; `str` paths are untested. (Tess)
- `StoreBusyError` is raised when the `with` block is entered, so the block body never runs on contention. (Tess)
- "Never waits" is tested as completing well under 1 second, proving LOCK_NB with no retry/sleep. (Tess)
- The lock file is kept (not deleted) on release, required for mutual exclusion to keep working across repeated acquire/release cycles, even though the contract only says "releases and closes on exit". (Tess)
- Closing the file descriptor releases the lock; there is no explicit LOCK_UN before close. (Ivan)
- The busy error is raised `from None`, so the underlying BlockingIOError does not appear as its cause; tests check only the message and type. (Ivan)
- A process-level advisory lock (fcntl.flock) is sufficient for "exclusive"; nothing requires additional in-process thread-level locking beyond the existing contention test. (Devon, confirmed by Tess's strengthen)

## 4: Canonical self-match exclusion in pack.py

- Spans are `(path, start, end)` tuples, matching `set[tuple[str, int, int]]`. (Tess)
- Line ranges are inclusive on both the hit and the span side; a hit touching a span's boundary line counts as overlapping. (Tess, confirmed by Devon's exploit 7)
- `_exclude` keeps the original order of the hits it returns. (Tess)
- `os.path.realpath` is the canonical form to use (resolves symlinks, leaves nonexistent paths as normalized-but-unresolved strings), so two equal raw path strings for paths that don't exist on disk still match after realpath. (Ivan)

## 5: Decode C-quoted diff paths in diffmap.py

- Decoded names use NFC composed Unicode (U+00E9 é, U+00EF ï), matching Python's native `codecs.escape_decode(...).decode("utf-8")` output. (Tess)
- Only the `+++`/`---` lines are parsed for the path; the `diff --git` header's own path is not. (Tess, Ivan)
- A path counts as C-quoted only when the whole path text is wrapped in double quotes. (Ivan)
- Decoding must happen BEFORE the outside-repository traversal check, so a C-quoted escape-encoded traversal path (e.g. `"b/\056\056/\056\056/etc/passwd"`) is caught after decoding, not bypassed by it. (Devon, confirmed by Tess's strengthen and Ivan's implementation)
- **Noted deviation (Pat review, LOW, not retried):** the implementation uses a hand-rolled regex/escape-table decoder instead of the PRD-named `codecs.escape_decode(inner.encode("utf-8"))[0].decode("utf-8")`. It passes every test and arguably handles escapes `codecs.escape_decode` mishandles, but departs from the literal contract text without being flagged as a deliberate substitution.
- Invalid UTF-8 after octal decoding is replaced (`errors="replace"`), not raised, matching how the module already reads the diff file; also noted LOW by Pat as a possible silent-mangling risk. (Ivan)
