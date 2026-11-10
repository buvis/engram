---
name: recall-prior-work
description: Use before a broad search for prior decisions, past sessions, history, or cross-repo "where/why" questions. Triggers on "have we done this before", "why did we", "where else", "which repo".
---

Ask engram before you sweep repositories with `rg`, `grep`, or `git log`.

```bash
engram query --scope repo "<question in plain words>" -k 5
engram query --scope portfolio "<question in plain words>" -k 5
```

- Use `--scope repo` for this repository, `--scope portfolio` for all of them.
- Each hit is `rank score path:start-end heading`. Read the cited lines before you rely on them.
- Engram indexes code, PRDs, memory, and past agent sessions. It does not replace `rg` inside a file you already know.
- A nonzero `engram status --scope portfolio` means the index is stale. Say so when you cite a hit.
