1. Work in `/Users/bob/git/src/github.com/buvis/engram`.
   Read `~/.claude/AGENTS.md` and applicable project instructions.
   Read `docs/dev/project-management/meta/project-capsule.md`.
   Treat PRDs 00001–00007 and the global installation as complete.

2. Execute the next incomplete session below, then stop.
   Recheck current evidence before acting on November 9 observations.
   Preserve unrelated changes and existing rollback backups.
   Apply standing authorization to routine reversible work without requesting approval again.

3. Preserve the production embedding model, configuration, and historical evaluation snapshots.
   Obtain explicit authorization before changing the production model or rebuilding the complete index.
   Leave unrelated model servers running.
   Avoid the frozen `buvis/claude-autopilot` repository.
   Request indispensable input only when no safe progress remains.

4. Finish each session with focused regression checks and appropriate broader verification.
   Run `.venv/bin/python -m pytest -q --ignore=eval` for production changes.
   Run `PYTHONPATH=src:. .venv/bin/python -m pytest -q eval` for evaluation changes.
   Run `git diff --check`.
   Record completed work, test results, remaining defects, and the next session in the capsule.
   Mark the completed session in this plan.
   Commit related changes under the existing Git policy.
   Remove session scratch files and stale session worktrees.
   Preserve every applicable review requirement and fresh-session boundary.
   Use `/autopilot:run-autopilot` for end-to-end PRD execution.
   Hand off before any required fresh-session completion review.

5. **Session 1: repair memory attribution. (COMPLETE — 2026-11-09)**
   Reproduce the mapping defect in `src/engram/corpora.py`.
   Verify the observation that all 295 enumerated memory files receive `_unmapped`.
   Correct path normalization against actual Claude project directory names.
   Cover dotted paths, ambiguous mappings, unknown projects, and repository-scoped recall with regression tests.
   Preserve isolation between repositories.
   Verify migration of existing indexed memory attribution without rebuilding unrelated corpora.
   Verified memory-only migration on a disposable production-index copy; live installation and refresh remain assigned to Session 3.
   Results: 69 focused tests passed; 517 main tests passed with the known Session 2 failure; 30 evaluation tests passed.

6. **Session 2: stabilize evaluation sources. (COMPLETE — 2026-11-10)**
   Reproduce `test_real_goldset_loads_clean_and_covers_transcripts_and_code`.
   Inspect the missing gems transcript `c0e70656-a139-4b1b-8407-f8989807631e.jsonl` in Cellar.
   Treat its working-tree deletion as unrelated user state.
   Recover required evidence into private evaluation storage from Git when available.
   Establish reproducible source retention and validation without silently changing labels or historical scores.
   Keep private transcript bodies outside Git.
   Verify all 55 gold targets and both test suites.
   Record the baseline: 501 main tests passed, one failed; 30 evaluation tests passed.
   Rechecked baseline: 517 main tests passed, one failed; 30 evaluation tests passed.
   Cellar had committed the deletion in `eda46f05`; recovered exact bytes from `e2bc3d7b` without changing Cellar.
   Retained all 55 labels' 53 sources privately with hashes, frozen identities, and available Git provenance.
   Results: 63 focused tests, 519 main tests, and 47 evaluation tests passed; all eight passage-label queries validated.
   Production state, historical snapshots, labels, and scores remain unchanged. Continue with Session 3.

7. **Session 3: restore portfolio index health. (IN PROGRESS — awaiting warrant, 2026-11-10)**
   Investigate the unavailable registered `herdr-plugins` directory before indexing.
   Determine whether the repository moved, retired, or became temporarily unavailable.
   Preserve indexed evidence until its intended disposition is established.
   Back up the index before maintenance.
   Refresh the installed CLI through warrant if preceding fixes require installation.
   Verify installed modules against the tested source.
   Run `engram index --scope portfolio` after resolving source availability.
   Run `engram status --scope portfolio`.
   Investigate remaining degradation without suppressing legitimate failures.
   Compare against the observed 7,072 dead rows and stale memory, transcript, and code sources.
   Retirement confirmed; complete Git archive verified at `4362ef4`. Fresh status: 7,142 dead rows.
   Index and registry backed up under `~/.local/share/engram/backups/session3-20261110/`; integrity passed.
   Tests: 85 focused, 519 main, 47 evaluation passed. No live refresh yet.
   Await installation warrant `ad9e2dd9b263e61c1fccf3ff35f3c082` and registry warrant `d4c165e06b6611f16d5182d147ec42ec`.

8. **Session 4: repair review-pack correctness.**
   Triage PRD 00003/00004 review findings against current source.
   Reproduce hard-cap overflow from omission notices after all section content is removed.
   Reproduce incorrect source selection for `--diff base..`.
   Reproduce reuse-result starvation caused by filtering after top-five retrieval.
   Reproduce filename-based memory queries for unreadable or blank-title PRDs.
   Fix verified defects with focused regressions.
   Check adjacent diff validation and failure reporting within the same scope.
   Record unsupported or separate findings without expanding into general refactoring.
   Record the catchup harvest mismatch: fourteen supported files succeeded; thirteen ordinary reports lacked required frontmatter.

9. **Session 5: review dependencies and establish CI.**
   Review `https://github.com/buvis/engram/pull/2` against current dependency requirements.
   Test the tree-sitter-language-pack update from 1.14.0 to 1.25.0 in an isolated checkout.
   Verify parser compatibility, symbol extraction, exclusions, and index behavior.
   Add CI for portable regression tests.
   Separate private-source acceptance checks from portable tests explicitly.
   Preserve those acceptance checks without claiming CI validates unavailable private evidence.
   Follow the existing Git policy for publishing or merging changes.

10. **Session 6: specify shared project memory.**
    Read `docs/dev/project-management/intake/new/00010-shared-project-memory/idea.md`.
    Define repository paths, file format, evidence fields, migration, concurrent edits, scope, and deletion behavior.
    Keep authoritative memory in repository files and attribution in Git history.
    Define compatible host integration for Claude, Codex, and Copilot.
    Use the requirements and PRD skills to prepare bounded implementation work.
    Record companion work in `agent-plugins` or `agent-skills` where necessary.

11. **Session 7: collect independent retrieval evidence.**
    Follow `docs/dev/project-management/reviews/2026-11-05-independent-evaluation-protocol.md`.
    Start with five to ten genuine user questions collected before answer search.
    Accumulate twenty to thirty questions without manufacturing missing coverage.
    Keep private questions and evidence outside Git.
    Preserve original wording, scope, provenance, and exclusions.
    Label acceptable files and passages before scoring.
    Freeze labels, source snapshots, runtime identities, and comparison variants.
    Report missing independent input explicitly and continue unrelated work while collection remains incomplete.

12. **Session 8: evaluate retrieval changes.**
    Proceed only after independent questions and their evidence are available.
    Compare existing fusion against dense-first AND and OR variants using the established protocol.
    Evaluate Qwen3 Reranker 0.6B without changing production retrieval.
    Report file and passage accuracy, individual regressions, exact identifiers, transcripts, findings coverage, and latency.
    Measure persistent serving latency and unavailable-server fallback only if independent gains justify that work.
    Specify fusion and reranking separately through intakes 00009 and 00008.
    Preserve BGE-M3 unless later evidence and explicit authorization support migration.

13. Archive or remove this executed plan only after all sessions finish and durable outcomes are recorded.

14. Resolve these remaining questions in their assigned sessions.
    Determine the intended disposition of `herdr-plugins` during Session 3.
    Determine the shared-memory file contract during Session 6.
    Obtain genuine independent retrieval questions during Session 7.
    Ask only one indispensable question at a time.
