---
prd: docs/dev/project-management/prds/wip/00015-engram-module-context-backfill-v1.md
review: 1
date: 2026-11-16
head_sha: 9b94153f1d975366ae7237354c9ffecb45201538
codex_thread_id: 01a1e4da-4772-7280-8378-c1a4803781f9
reviewers: alice,blake,bob,carl
agents:
  alice: available
  blake: available
  bob: available
  carl: available
dispatch_rows:
  bob: cbdd315b
  carl: 4d42cdf9
---

# Review: 00015-engram-module-context-backfill-v1

Diff range: `60ef6cc281312d55480e98906470e2b3a101c3f9..9b94153f1d975366ae7237354c9ffecb45201538`

codex_rung_guard: not fired

## Review Summary

Reviewed: 4 completed tasks
PRDs checked: 00015-engram-module-context-backfill-v1.md

### Agent Status

- Alice: ✅ Available (native Claude subagent, consensus lens)
- Blake: ✅ Available (native Claude subagent, blind/PRD-only lens)
- Bob: ✅ Available (codex, doubt lens D1-D5 + de-slop)
- Carl: ✅ Available (gemini-run backend=copilot model=gemini-3.8-flash)

Context pack: ok. Mechanical checks: 0 tautological test shapes in 19 checked
test functions; fail-first replay ran 25 touched tests against
`60ef6cc28131` and all 25 failed there, so no test in this change is
non-pinning. No `[MECH]` findings to absorb.

Consolidation note: `consolidate_findings.py` reported suffix-stripped citation
merges on rows R1 (`indexer.py:340 ~ :228 ~ :224`) and R2 (`:348 ~ :232`). R1
and R3 describe the same `_rechunk_source` atomicity region at two different
call sites and are kept separate deliberately — see the decision gate notes.

## Consolidated Findings

| Ref | Consensus | Severity | Issue | File | Task | Found By |
|-----|-----------|----------|-------|------|------|----------|
| R1 | [2/4] | ⚪ | `_rechunk_source` ignores stored rows when `was_empty` (`stored = [] if was_empty else ...`). A crash between `replace_chunks_for_source` (commit) and `unmark_empty_source` (autocommit) leaves a source with both rows and an empty mark. The next run then re-embeds every chunk instead of reusing the stored vectors, which defeats the "safe to repeat" and reuse goals. Calling `store.code_chunks_with_vectors(path)` unconditionally closes that window and drops the conditional. It returns [] for a genuinely empty source. | src/engram/indexer.py:340 | 2 | ALICE, BLAKE |
| R2 | [2/4] | ⚪ | PRD step 6 reuses a vector by the same `(heading, body)`. The code keys on `text_for_embedding`, which is heading plus repo-relative path plus body. The path is identical for every chunk of one source, so behavior is equivalent. It is a literal deviation from the contract and could be noted. | src/engram/indexer.py:348 | 2 | ALICE, BLAKE |
| R3 | [1/4] | 🟠 | Empty-source transition lacks a transaction spanning chunk replacement and empty marking. Interruption between these calls leaves neither chunks nor an empty mark, so subsequent backfills skip the source. Commit both operations atomically and add an interruption regression test. | src/engram/indexer.py:228 | 2 | BOB |
| R4 | [1/4] | 🟡 | The CLI error and scope behaviors the PRD specifies for `--backfill-code` have no test. The untested paths are `StoreModelMismatchError` (rebuild hint, exit 1), `EmbeddingServerError` and `EmbeddingPreflightError` (print, exit 1), `FileNotFoundError`, and `_resolve_scope` returning None (error message, exit 1). The default `--scope repo` is also untested, because both CLI tests pass `--scope portfolio` or conflict flags only. Fix: add parametrized CLI tests that make `backfill_code` raise each error and assert the stderr text and exit code 1, plus one test that omits `--scope` and checks the repo scope reaches `backfill_code`. | src/engram/cli.py:338 | 3 | ALICE |
| R5 | [1/4] | 🟡 | Simplification: `_rechunk_source` returns `tuple[int, int] \| None`, and `backfill_code` reads it as `counts[0]` and `counts[1]`, which hides what each number means. Unpack into named locals instead: `result = _rechunk_source(...)`, `if result is None: continue`, `n_embedded, n_reused = result`. Behavior stays the same. | src/engram/indexer.py:311 | 2 | ALICE |
| R6 | [1/4] | 🟡 | The second-run test checks identical rows and zero embeddings but does not enforce the required zero writes; rewriting identical rows would pass. Capture `store.conn.total_changes` before the second run and assert it remains unchanged. | tests/test_backfill.py:411 | 2 | BOB |
| R7 | [1/4] | 🟡 | Merging dictionaries unnecessarily copies every reusable vector and constructs an intermediate dictionary. Replace the assignment with `vectors.update(zip(missing, embed(missing, entry), strict=True))`. | src/engram/indexer.py:236 | 2 | BOB |
| R8 | [1/4] | ⚪ | `code_chunks_with_vectors` filters on `corpus='code' AND path=?` with no repo term. The only chunks index is `UNIQUE(repo, path, content_hash, chunk_ordinal)`, which leads with `repo`, so each call is likely a full scan of `chunks`. `backfill_code` calls it once per known source (about 16k on the portfolio). The PRD mandates the path-only signature, so this is a performance note for the one-time production run. | src/engram/store.py:581 | 1 | ALICE |
| R9 | [1/4] | ⚪ | The README rewrap leaves short orphan lines ("missing spans. The one exception", "`engram lookup --name` returns symbols only;"). "The one exception" now follows the new sentence flow awkwardly. Cosmetic: reflow the paragraph. | README.md:172 | 4 | ALICE |
| R10 | [1/4] | ⚪ | The diff replaces the whole of `assumptions.md`, dropping the PRD 00014 ledger, and edits `project-capsule.md`. These are autopilot process artifacts outside the PRD's file list. Confirm that overwriting the per-PRD ledger is the intended convention. | docs/dev/project-management/meta/assumptions.md | general | ALICE |
| R11 | [1/4] | ⚪ | `_run_backfill` also catches `FileNotFoundError`, which the spec's error list omits. This mirrors the plain `index` path and is harmless. | src/engram/cli.py:350 | 3 | BLAKE |
| R12 | [1/4] | ⚪ | The backfill takes no `write_lock`, so it could race a concurrent `--rebuild` or `harvest` that swaps or writes the DB. The spec does not ask for a lock, and plain `index` has the same gap. | src/engram/cli.py:343 | 3 | BLAKE |
| R13 | [1/4] | ⚪ | `embed(...)` is zipped with `strict=True`. A wrong-length embed result raises an uncaught `ValueError` that aborts the run. The spec says nothing about this case, and earlier sources stay committed. | src/engram/indexer.py:235 | 2 | BLAKE |

## Alice

Consensus lens, implementation-aware. Seven findings (R1, R2, R4, R5, R8, R9,
R10). She ran `.venv/bin/python -m pytest -q --ignore=eval -x` (clean, no
skips), confirmed the fail-first replay, and measured `backfill_code` at 49
lines, `_run_index` at 48, `tests/test_backfill.py` at 783 lines — all inside
the 50-line / 800-line limits.

R1: fail
R2: pass
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: pass
R10: pass
R11: pass
R12: pass
R13: pass

## Blake

Blind lens, PRD-only prompt (no diff, no file list, no history). He located the
code himself and walked the spec end to end: `BackfillReport` shape,
`backfill_code` steps 1-8, `Store.code_chunks_with_vectors`,
`Store.unmark_empty_source`, the CLI flag wiring and its five error exits, the
README and CHANGELOG entries, and all nine spec-named tests (plus extras);
`pytest -q tests/test_backfill.py` gave 25 passed. Six ⚪ findings (R1, R2, R11,
R12, R13, and the precedence note folded into R1), every blind rubric rule pass.

B1-B19: all pass.

## Bob

Doubt lens (D1-D5 + de-slop), codex, static sandbox.

FIX:
- (high) Empty-source transition lacks a transaction spanning chunk replacement and empty marking (R3).
- (medium) Second-run test does not enforce zero writes (R6).
- (medium) Dictionary merge copies every reusable vector (R7).

VERIFY:
- (none)

KNOWN:
- (none)

R1: fail
R2: pass
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: pass
R10: pass
R11: pass
R12: pass
R13: pass
D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Carl

Frontend & design specialist, generalist here (backend=copilot,
model=gemini-3.8-flash). He read the context, the full diff, the pack, and the
three touched source files, and searched for skips, xfails, TODOs and debug
statements (none found). His one shell attempt (`pytest -q`) was denied by the
non-interactive approval guard, so his verdicts rest on static reading plus the
supplied test-gate line.

[CARL] ✅ No issues found

R1: pass
R2: pass
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: pass
R10: pass
R11: pass
R12: pass
R13: pass

## Decision gate notes

**R3 is confirmed, not Bob's stated scenario twice over.** Bob cited
`indexer.py:228`, which is the `not chunks` branch of `_rechunk_source`:
`replace_chunks_for_source("code", path, [])` commits (removing every row), then
`mark_empty_source(...)` runs as a second autocommit. A crash in that window
leaves the source in neither `known` nor `known_empty`, and `backfill_code`
line 187 (`if not was_empty and key not in known: continue`) then skips it on
every later run — it is never re-added by a backfill, only by a full `index`.
Bob's wording ("leaves neither chunks nor an empty mark, so subsequent
backfills skip the source") is exactly right for that site. 🟠 stands, and it
is the one finding that blocks convergence this cycle.

R1 names the mirror window at the other call site (lines 237-239:
`replace_chunks_for_source` then `unmark_empty_source`). There the rows survive,
so the consequence is only a wasted re-embed and the state self-heals — hence
low severity from both reviewers. Alice's remedy (drop the `was_empty` conditional and
read stored rows unconditionally) closes it. Kept as its own row because the
fix sites and the consequences differ.

Verdict: 13 findings
Tests: 1423 passed, 0 failed, 0 skipped (suite run this cycle)
