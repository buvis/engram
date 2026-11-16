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
