## 1: Add main checkout fallback and registry_root in harvest.py

- I imported `registry_root` inside its own test, not at the top of the file. A top-level import would break collection of the whole file before the change, which would hide the real behavior failure of the first test.
- The bare-repo check sits inside `test_resolve_repo_for_path_worktree_of_unregistered_repo_returns_none`. The task fixes the list of test names, and that repo's main checkout is effectively unregistered.
- `registry_root` returns the recorded path as a `Path`. The fixture paths sit under pytest's already-resolved `tmp_path`, so the test passes whether or not the function resolves the path.
- When a name appears twice, the first row wins (from "first row whose name field equals name"). The fixture has a duplicate `proj` row to check this.
- `registry_root` returns the row's recorded path as written in the CSV, not a resolved or canonical form. It is compared with `==` against tmp_path-based paths, as the original test already did.
- `_resolve_repo_for_path` resolves paths in a worktree nested inside the main checkout's own folder (`main/.worktrees/x`) by that worktree's own toplevel, as git reports it.
- Weak point 7 (Devon's registry-default exploit) reads "default registry" as the declared default in the contract signature, not as looking up the module attribute at call time.
- The installed git supports `--path-format=absolute`, which needs git 2.31 or later.
- When several rows share a name, the first row wins. The test expects `b/checkout` over `d/proj`.
- `registry_root` returns the path exactly as written in the CSV, not resolved.

## 2: Add index_root to build() in pack.py for worktree self-match exclusion

- `changed_symbols` returns the spans `big.py` 1-2 and 5-6 for `_write_many_function_diff(worktree, 2)`, as the helper's comment says.
- Store chunks need distinct `chunk_ordinal` values when they share a path, so they do not overwrite each other on upsert.
- With all 5 seeded chunks tied on score, `RETRIEVAL_K=5` returns every one, so no expected chunk is cut by top-k.
- For `index_root == repo_root`, exclusion behavior is checked only as unchanged; whether a duplicate span gets added cannot be observed, because `_exclude` compares canonical paths.
- Added a new parametrized test instead of growing the original one, since the original already has 5 chunks (the most `RETRIEVAL_K` reliably returns when all scores tie); the new test's name contains `main_checkout` so the PRD's `-k main_checkout` check still selects it.
- Keeping a `main/big.py` chunk in the non-sibling `index_root` case is within the PRD: only spans under `index_root` are added, so a `main` copy stays when `main` is not the index root.
- `Symbol.path` is an absolute path under `repo_root`, so `relative_to(repo_root)` works; if the two ever differ by a symlink, `relative_to` raises `ValueError`.
- `index_root` only changes which spans count as self-matches; it does not change the reindex scope or where symbol text is read from.
- The project's line-length convention is 88 characters (used when collapsing `build()`'s call arguments to fit the 50-line function limit).

## 3: Pass index_root from _run_pack in cli.py

- `_resolve_scope("repo")` takes the name from `_resolve_repo_name` without checking it against the registry. The existing "claude-home" test points that way, and the unregistered-main-checkout test case relies on it.
- The "unregistered main checkout" case is read as: the repo name resolves (patched `_resolve_repo_name`) but is not in `repos.csv`, so `registry_root` returns None and `index_root` must be None. A truly unregistered checkout with no name override would fail repo resolution and never reach `build()`.
- Comparing `index_root` via `Path(...).resolve()` allows `registry_root` to return the csv string as a `Path`, unresolved.
- The `index_root` contract is "equals `registry_root(repo_name, GITA_REPOS_CSV)`", i.e. first exact match wins, matching the existing unregistered test and the `registry_root` implementation.
- `index_root` is always the registry lookup result in both main-checkout and linked-worktree invocations: it equals the registered path for a registered repo, and is `None` for an unregistered one.
- `_resolve_pack_repo` is left untouched because `lookup --file` also depends on it, and the task only asked to change `_run_pack`'s `build()` call.
