# Direct delivery of PRDs 00005–00007

Current status: all three PRDs are done after the user-approved closeout below.
The original delivery evidence is retained as history.

The user explicitly authorized implementation without Autopilot on 2026-11-09.
No Autopilot state or frozen plugin repository was modified.

## Implementation

- 00005: exact-first, literal-prefix symbol lookup; file outlines; scope and repo
  filtering; validated extra exclusions; vendor/minified/long-line filtering;
  redundant anonymous-child removal; exclusion counts; resumable per-source
  migration of legacy anonymous headings. Lookup never loads embedding config.
- 00006: shape-based review/audit dispatch, header and per-decision records,
  original rationale text and source lines, loud rejection of empty audits.
  Existing review parsing remains semantically unchanged.
- 00007: configurable positive `[transcripts] in_flight_seconds` (600 by
  default), separate in-flight count, degradation-only status exit, source
  availability errors, and CLI help. Status hashes each source once per stored
  hash rather than once per chunk.

Optional PRD/decision/discovery directories that never existed remain informational,
preserving the existing corpus contract. A missing required transcript root or
failed code-repository enumeration fails status; vanished indexed files count as
dead rows. The new window does not conceal dead rows.

## Verification and live premises

- New regression tests were run red before implementation, then green.
- Full suite: **531 passed, one pre-existing external-fixture failure**.
- The live code index exits zero: 71,527 chunks, zero legacy `None` headings,
  17,776 retained anonymous headings (24.85%), and zero chunks from the two
  named minified bundles. Exact `stop_served` lookup succeeds with embedding
  config access replaced by a failing sentinel. The existing server on port
  8083 was not owned by this task and was left running. The total grew because previously unindexed registered
  repositories now contribute code. PRD 00005 remains on hold for its unmet
  under-5% corpus target; its implementation is complete.
- Ruff's correctness rules (`E4,E7,E9,F`) and `git diff --check` pass.
  The global all-rules Ruff configuration reports extensive existing style debt;
  it was not used to trigger unrelated cleanup.
- The existing gold-set validation fails because this external transcript no
  longer exists:
  `/Users/bob/git/src/github.com/buvis/cellar/.claude/projects/-Users-bob-git-src-github-com-buvis-agent-skills/5a656567-eccb-474e-833a-8ca6a7601e5a.jsonl`.
  This change does not alter `eval/goldset.yaml` or its validator. Repairing the
  evaluation corpus requires recovering that source or collecting a replacement
  labeled question; silently choosing a different file would invalidate the test.
- The code baseline is 67,518 chunks, 18,886 legacy anonymous headings (27.97%),
  and 734 chunks in `easymde.min.js` / `highlight.min.js`, rather than the older
  41,716 / 17,449 baseline in PRD 00005.
- A SQLite backup was created at
  `~/.cache/engram-before-prds-00005-00007.db` before live indexing and harvesting.
- The original six ddb audit fixtures, including 00164, are absent from the
  current checkout; 00164 is also absent from available Git history. Current decision audits are
  used instead. A checked-in fixture excerpts two autonomous decisions and one
  deferred decision from ddb's real 00176 audit.
- All nine current decision audits harvested successfully: 276 records, exit 0.
  “Why does search conformance cover CLI and GraphQL but omit REST?” returns
  the 00176 audit's deferred decision at rank 1, lines 232–237. Three other
  audit-named files lack either supported content shape and still fail parsing.
- The live portfolio is not fresh: before the code index finished it had 5,748
  dead transcript rows, 140 dead PRD rows, and stale memory/transcript sources.
  Requiring exit zero for that store would hide real degradation. A controlled
  fresh store passes ten consecutive CLI status checks while its transcript is
  being appended to; separate cases verify stale, dead, future-mtime, custom
  window, non-transcript, and unavailable-source behavior.

## Skeptical review

1. **Least confidence — migration correctness (VERIFY):** unchanged files would
   ordinarily bypass chunking. A regression seeds legacy headings at the actual
   source hash, migrates them, prunes an excluded file, then asserts the second
   index embeds nothing. Source replacement is transactional and failures retain
   the previous rows; existing failure-preservation tests pass.
2. **Assumptions — parser names and corpus target (KNOWN):** the parser sometimes
   names an arrow after its parameter and leaves exported arrows and test
   callbacks anonymous. The implementation follows the explicit `item.name is
   None` contract and retains anonymous symbols without named ancestors. The
   under-5% prediction cannot justify deleting that required content. IIFEs the
   upstream structure parser does not emit remain outside this change.
3. **Completeness — source fixtures and live state (KNOWN):** historical ddb
   inputs and one gold-set transcript are unavailable. Current real audits and a
   controlled fresh transcript store provide reproducible replacements for the
   functional checks; they are not represented as the original historical test.
4. **Failure paths — CLI scope and missing sources (FIX):** file lookup initially
   ignored name-only scope flags, and failed Git enumeration did not affect
   status. Both now fail explicitly, with regressions. A headerless audit starts
   at line one instead of producing a synthetic invalid 1–0 header pointer.
5. **Alternative approach — migration design (VERIFY):** retaining the existing
   hash contract and replacing affected sources avoids a full portfolio rebuild
   or schema-wide hash-version migration. SQL stays in Store. Exclusions prune
   only after successful enumeration; failed repositories retain their rows.
6. **Missing checks (VERIFY):** exact/prefix/corpus/repo matching, literal `%`,
   file order, no embedding-config access, real audit rationale preservation,
   EOF handling, empty audits, window validation, source grouping, and repeat
   status behavior are exercised. Existing review parser tests remain unchanged.

Slop pass: removed an unused duplicate configuration field; kept SQL ownership
in Store; avoided a migration framework or a second parser dependency. New
helpers each serve a contract boundary or independent test surface. Diff size
is proportional to three features and their regression tests; no framework-only
tests or impossible-state guards were added. A second pass checked the fixes
and found no further supported in-scope defects.

Review outcome: eight doubts across the six questions and two slop findings;
three fixed (failure paths, redundant config, SQL ownership), three verified
(migration, design, checks), and two known limitations (unavailable historical
inputs and the anonymous-percentage prediction).

## Use and remaining work

Use `uv run engram` from this checkout for the updated CLI. The separately
installed global executable is a copied uv tool installation and was not changed.
PRDs 00006 and 00007 are done; 00005 is on hold solely for the numeric target.
No new worktrees or executed plan files were created. The database backup is
intentionally retained for rollback.

## Approved closeout — 2026-11-09

The user approved replacing 00005's speculative percentage target with verified
vendor exclusion, anonymous-child deduplication, and useful-symbol retention.
The total chunk count is an observation, because the registered portfolio grows.
The existing regression and live-index evidence satisfy these criteria; 00005
moved from hold to done without deleting more source content.

The missing gold-set transcript was deleted in cellar sync commit
`ba64775ddd1e25c3628e0a416496e30bccc41780`. The old query was replaced under the
gold set's existing pre-scoring sampling policy: seed 20261109 over sorted current
transcript paths; draws 1–3 were automated reviewer sessions; draw 4 was the first
substantive human session, 5729c201-a2c0-438c-b406-13dea0cc5ef0. Its retained turns
at lines 13 and 389 establish OVCAQ/Herdr pane reporting and headless-session
identity interference. No retrieval scores were consulted or tuned. Historical
retrieval scores are not directly comparable to the revised 55-entry set.

Replacement transcript SHA256:
`455865e5c630014ca07c8ce9eca19d3bd736eb968c9e650fd8631b0580b1b936`.
The source exists, is yielded by the actual transcript enumerator, and its kept
chunks contain the incident. Cellar itself was not modified.

Validation: **532 tests passed**; all 55 gold-set paths exist; `git diff --check`
passed. A wheel was built successfully. No production code changes were needed
for this closeout.

Global installation is prepared through warrant, using the existing managed
Python and dependencies constrained to `uv.lock`. The install uses the durable
repository path, preserving the local-source upgrade workflow. Packaging scratch
under `docs/dev/tmp/closeout-install/` remains live until installation finishes.
The global CLI smoke test is pending installation approval.
