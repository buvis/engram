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
- **Extra CLI flags — resolved by the user, 2026-11-01.** Keep query `-k`/`--k`
  and index `--rebuild` as supported interfaces. This does not authorize running
  a production rebuild.

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
  The subsequent redacted audit below resolves the observed pattern matches;
  broader ingestion hardening remains separate.
- Registering engram for installed `pack` lookup remains unresolved from
  PRD 00004. The completion review recorded the pack failure and continued with
  the required diff, PRD, and test evidence. No registry settings were changed.

The unrelated `buvis/home` merge conflict also remains for the user.

## Installation and stash inspection — 2026-11-01

The user approved warrant request `647ba547e2dbd03c22d079945d5668a2` and reported
installation completed. The installed `cli.py`, `harness.py`, `indexer.py`,
`store.py`, and `symbols.py` were then compared byte-for-byte with the checkout;
all five match. No installation action remains.

Both stashes were compared with their own base commits, without applying them:

- `stash@{0}` (`2e4a5ffc63bf81adff2350f78aae08d0bf0dca55`): line wrapping and
  trailing commas in `src/engram/pack.py` and `tests/test_pack.py`. Both ASTs
  and all comments are identical to their base versions.
- `stash@{1}` (`cdaa759e64468062b6c1b853696a2e2511883b61`): formatting in
  `src/engram/cli.py`, `src/engram/client.py`, `tests/test_cli.py`,
  `tests/test_client.py`, and `tests/test_indexer.py`. The only AST changes
  are `import engram.corpora as corpora` becoming `from engram import corpora`,
  sorting names within one store import, and swapping the order of the pytest
  and corpora imports. No function logic, assertions, or comments changed.

Neither stash contains staged changes or a third-parent untracked-file snapshot.
There is no unfinished feature to recover. Applying these old formatting patches
to the evolved files offers no functional benefit. The user authorized removal.
Both entries were dropped after creating and verifying a complete-history bundle:
`~/.local/state/engram/stash-archive/20261101-214310/formatting-stashes.bundle`.
The bundle is owner-readable only; the archive directory is owner-accessible only.
`git stash list` is now empty. No stash was applied.

## Next-session scope — user decisions, 2026-11-01

The user selected “Fix these next” for three deferred correctness defects:

1. Extract error-bearing transcript tool-result text, including list-form content.
2. Preserve existing indexed rows after source read/hash/parse failures, and
   report the affected sources instead of silently treating them as deleted.
3. Allow unrelated scoped indexing when the cellar corpus is absent; retain a
   clear failure when the requested scope actually requires transcripts.
4. Include file paths in code embeddings. The user selected “Include path
   enrichment next” after being told this requires regenerating existing code
   vectors and rechecking retrieval quality. Include that refresh and evaluation
   in the fresh-session scope; preserve the production bge-m3 pin. A whole-index
   `engram index --rebuild` remains unauthorized.

Implement these in a fresh session. Keep performance tuning and broad structural
cleanup separate. Reproduce each defect against current HEAD before editing.

## Redacted production-index audit — 2026-11-01

The user requested this audit. SQLite was opened read-only with `query_only=ON`;
163,739 chunk bodies were scanned. No index contents, configuration, permissions,
or external services were changed. Candidate values were neither printed nor
saved; evidence contains source pointers, lengths, and classifications only.

Broad case-sensitive markers occur in 12 rows for `ghp_`, 5 for `AKIA`, and
71 for `Bearer `. Stricter GitHub/AWS/Bearer expressions yielded 21 occurrences
of eight distinct candidates: six synthetic fixtures/examples and two prose
false positives. Source-context inspection established:

- C001: mocked GitHub headers in `feedback/src/lib/github.test.ts`.
- C002: positive/negative authorization unit tests in `ddb-server/src/auth.rs`.
- C003: hardcoded authentication fixtures in `ddb/tests/e2e/`.
- C004/C005: ordinary words following “bearer” in review/PRD prose.
- C006: credential-redaction test sentinels embedded in ovcaq transcripts,
  including `test_claude_diagnostic_detail_redacts_credentials_and_bounds_length`.
- C007/C008: AWS example identifier and synthetic Bearer input passed to
  `find_secret` assertions in `claude-checkup`'s `test_checks.py`.

No full-length GitHub token matched. Short GitHub markers were separately
checked: bare detection prefixes, test fixtures, and a documented scratch-repo
secret-detection experiment in agent-skills PRD 00092. Remaining AWS markers
were bare detection prefixes.

No plausible live credential was identified among these matches. This is a
pattern-limited audit of indexed bodies, not proof that every credential format
is absent. No candidate was submitted to a service for validity testing.
The database file has mode `0644`; actual accessibility also depends on parent
permissions and ACLs. Permission hardening remains separate; this audit did not
change access controls.

Redacted evidence is retained outside the repository at
`~/.local/state/engram/reviews/00002-20261101-205601/redacted-index-audit-20261101.json`
with mode `0600`.

## Implementation of the four approved defects — 2026-11-01

Each defect was reproduced against `4cbac26` with a failing test before any fix
(`tests/test_followup_fixes.py`): empty bodies for error tool results and
list-form results unmatched; hash/chunk failures pruning or hiding rows
(`IndexReport.failed_sources` added; CLI prints `failed (existing rows kept):
PATH` to stderr); absent cellar failing `--corpus prd` and non-cellar repo scope;
code embedding text lacking the path (now `heading\nrepo/rel/path\nbody`).
Scopes that include transcripts (portfolio, `--corpus transcripts`, repo
`cellar`) still fail with the producer's clear message.

Migration: new `engram index --reembed-code` replaces code vectors per source
without touching rows or hashes. Run on production after a `0600` backup at
`~/.local/state/engram/db-backup/engram-pre-reembed-20261101.db`: 65,529 chunks
re-embedded in about 40 minutes; chunk count unchanged (163,739); no rebuild.

Retrieval recheck on production (55-entry set, corpus-scoped, top-5): before and
after both 52/55 — code 4/5, decision 3/3, discovery 2/2, memory 20/20, prd 11/13,
transcripts 12/12. Same three misses: one code query (unchanged), the engram core
PRD query, and the gems 00112 query (PRD moved backlog→wip; gold re-anchored,
index not yet refreshed by a normal index). Path enrichment is neutral on this set.

Harness isolation: `eval/harness.py` now runs on a copy of the config under the
work dir, so a gate pass cannot repoint production. The full cold harness run
(~75 min) was not repeated; the production pin is unchanged. Gita registration
remains deferred.

## Post-fix index and harness run — 2026-11-02

A normal `engram index --scope portfolio` (144 s, no failed sources) refreshed the
moved gems 00112 PRD: production retrieval is 53/55 (prd 12/13; remaining misses:
engram core PRD query, one code query).

Cold harness run on the 55-entry set, isolated config, gate_passed True,
rg baseline 0.509:

```
Qwen3-Embedding-0.6B  0.945  code 0.800 decision 1.0 discovery 1.0 memory 1.0 prd 0.923 transcripts 0.917
nomic-embed-text-v1.5 0.927  code 0.800 decision 1.0 discovery 1.0 memory 1.0 prd 0.846 transcripts 0.917
bge-m3 (production)   0.927  code 0.800 decision 1.0 discovery 1.0 memory 1.0 prd 0.846 transcripts 0.917
winner                Qwen3-Embedding-0.6B
```

Qwen leads by one gold entry (prd 12/13 vs 11/13) on a 55-entry set: not a
meaningful margin. The isolated copy was repointed to Qwen; the production
`config.toml` is unchanged (bge-m3). Switching models needs a whole-index rebuild,
which is not authorized; the user decides whether the one-entry lead is worth it.
