# Decision Audit Log: 00010-repo-memory-corpus-v1

PRD: `00010-repo-memory-corpus-v1.md`
Started: 2026-11-10T18:45:56Z
Completed: 2026-11-10T18:45:56Z
Autonomous: 5  |  Deferred: 0  |  Doubts: 0

### [autonomous] 2026-11-10T18:45:56Z

**Decision**: design approach for PRD 00010

**Choice**: leaf memory.py validator returning tab-joined violation strings; repo memory via _enumerate_repo_corpora; legacy skip by unique slug; status facts via corpora side-channel globals like missing_dirs; sk- credential pattern left-anchored (only PRD amendment, measured false positives); all diagnostics redacted

**Rationale**: smallest design matching PRD contracts; open non-blockers: cyclic YAML alias guard, redacted-filename status undercount, conftest-wide global reset, detail pinning

### [autonomous] 2026-11-10T18:45:56Z

**Decision**: tests/test_repo_memory.py exceeds the 800-line style limit (about 1000 lines after task 2; tasks 3-4 add more)

**Choice**: keep all PRD 00010 tests in the one file; record style_gate failed for that file, no split dispatch

**Rationale**: every PRD acceptance command names pytest tests/test_repo_memory.py -k <selector>; splitting would make those commands select nothing (pytest exit 5). PRD-owned acceptance criteria outrank the style guideline

### [autonomous] 2026-11-10T18:45:56Z

**Decision**: cycle 1 decision gate: 14 consolidated findings

**Choice**: fix R2 (yaml ValueError crash) and R4+R13 (memory_dir shadowing, same defect from two reviewers); discard R1 (settled: PRD acceptance pins test file), R5 (settled: sk- anchor is design decision), all other single-voice medium/low

**Rationale**: R2 is the only unresolved high; R4/R13 merge to two voices; ledger at reviews/00010-repo-memory-corpus-v1-ledger.json records every discard

### [autonomous] 2026-11-10T18:45:56Z

**Decision**: `yaml.safe_load` can raise `ValueError` (not `yaml.YAMLError`) for date-shaped scalars such as `source: 2026-13-45` or `name: 0000-00-00`. I reproduced it: `yaml.safe_load('x: 2026-13-45')` raises `ValueError: month must be in 1..12`. `_split_frontmatter` catches only `yaml.YAMLError`, so one such memory file crashes `engram memory check` with a traceback instead of `frontmatter<TAB>unparseable`. It also crashes `engram status` through `check_directory`, which turns one bad memory file into a failure of the whole status run. The PRD makes unparseable frontmatter a reported violation. Fix: catch `(yaml.YAMLError, ValueError)` at src/engram/memory.py:163 and add a regression test for an invalid calendar date.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-10T18:45:56Z

**Decision**: cycle 2 decision gate: 5 consolidated findings, all single-voice medium/low

**Choice**: discard all 5 (3 spike-only from Bob, 2 low from Blake); constraint gate exit 0; converged with no tail sweep

**Rationale**: no CRITICAL/HIGH; every row [1/4] so the tail sweep selects nothing; ledger records each discard
