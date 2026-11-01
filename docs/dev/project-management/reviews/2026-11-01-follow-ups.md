# Engram follow-up triage — 2026-11-01

Scope: the continuation's five PRD 00001 items, after the PRD 00002 finalization
review. Baseline: `1a3b49f`. No backlog PRD was started.

## Requested items

- **Decision gold entries — resolved.** Added three queries about distinct
  decisions in `agent-plugins/docs/dev/project-management/meta/decisions.md`.
  `load_goldset` accepts all 55 entries and the harness tests pass. The entries
  were authored without scoring. The November 1 live gate covered the previous
  52-entry set; it does not certify the enlarged set. All decision targets point
  to the portfolio's one decision document, so this is file-level coverage.
- **`IndexReport.chunks_updated` — resolved.** Removed the permanently zero
  field and updated every constructor. Changed chunks still count as added and
  pruned. No production consumer read the removed field.
- **Broad `FileNotFoundError` catch — already fixed at baseline.**
  `_run_index` prints `str(e)`, preserving the producer's actual path rather than
  inventing a missing-registry message. The existing
  `test_index_file_not_found_error_prints_the_producer_supplied_message` passes.
  Keeping the broad boundary catch gives missing source files a concise error.
- **Embedding tracebacks — resolved.** Query and ordinary index catch
  `EmbeddingServerError` and `EmbeddingPreflightError`, print the supplied
  message, and return 1. Four command/error combinations failed before the fix
  and pass afterward. Rebuild already reports exceptions as `rebuild failed`.
- **Extra CLI flags — needs the user.** Keep or drop query `-k`/`--k` and index
  `--rebuild`. They remain unchanged pending that choice.

## Runtime-state disposition

The settled decision says autopilot state stays untracked. It is now explicitly
ignored in `.gitignore`. The local deferred file contains 87 historical entries,
including unrelated PRD 00003/00004 work; deleting it after resolving five entries
would lose untriaged evidence. It is retained locally with resolution annotations
on the requested entries. This tracked note is the durable outcome of this pass.

Older audit/review documents remain the tracked record for the other PRDs.
Backlog 00005–00007 remains untouched.

## Out-of-scope review findings retained

The finalization review repeats these pre-existing issues. They are not new
regressions from `7610ef5..1a3b49f`, and this continuation does not implement them:

- Transcript tool-result text is not extracted into chunk bodies; list-form
  tool-result payloads are not matched. See review 2's transcript findings.
- Indexing hashes whole working files even when unchanged; status hashes once
  per chunk. Review 2 C19/C20 records both. The historical 12.6-second index
  satisfies the measured latency bar but not the literal never-read wording.
- Symbol embedding omits the file path (review 2 C18).
- Chunk failures are counted without reporting their path; a failed changed
  source may lose previously indexed rows during pruning (review 2 C1/C3/C4).
- Missing cellar prevents unrelated scoped indexing (review 2 C30).
- Oversized pre-existing index/test modules need a separate structural cleanup
  (review 2 C10). The newly enlarged harness selection was extracted here.
- The production index's credential-shaped strings were previously reported
  without establishing whether they were live credentials (review 2 C22).
  This review did not open, copy, or verify secret values.
- Registering engram for installed `pack` lookup remains unresolved from
  PRD 00004. The completion review recorded the pack failure and continued with
  the required diff, PRD, and test evidence. No registry settings were changed.

The unrelated `buvis/home` merge conflict also remains for the user.
