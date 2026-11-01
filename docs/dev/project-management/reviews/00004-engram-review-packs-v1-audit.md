# Decision Audit Log: 00004-engram-review-packs-v1

PRD: `00004-engram-review-packs-v1.md`
Started: 2026-08-03T10:59:53Z
Completed: 2026-08-03T16:56:33Z
Autonomous: 11  |  Deferred: 2  |  Doubts: 0

### [autonomous] 2026-08-03T16:56:33Z

**Decision**: dependency-check on PRD 00002 (code corpus)

**Recommendation**: N/A (research-backed autonomous decision)

**Choice**: Proceed with 00004 build using the existing partial index/fixtures for its own tests.

**Rationale**: PRD 00004 lists Depends on PRD 00002, which is stalled in hold/ with only its full-scale index run blocked. Verified the actual code dependency (symbols.py tree-sitter chunker, corpora registration, store/indexer/query) is already implemented and committed - the 00002 stall is an operational/runtime issue (embedding server instability under sustained load), not a missing-code blocker.

### [autonomous] 2026-08-03T16:56:33Z

**Decision**: design-decision - PRD 00004 design (diffmap.py symbol-diff mapping + pack.py retrieval/budget composer + engram pack CLI verb + review-work-completion reviewer wiring)

**Recommendation**: N/A (design gate decision)

**Choice**: Batch-embed all changed symbols in one client.embed() call; pre-pack reindex stays repo-scope only with portfolio staleness disclosed loudly; retrieved-hit bodies hydrated from the store's own already-indexed Chunk.body via a new query() include_body flag.

**Rationale**: Avoids replaying PRD 00002's measured embedding-server failure; re-reading files breaks for portfolio-scope and historical --diff hits. Design went through 3 adversarial review dispatches plus one retry fix-pass; all resolved except one documented, accepted limitation (Bob's doubt-rubric portion cannot be fully content-isolated from his own consensus portion, since both share one CLI dispatch/model context - pre-existing architecture, not introduced by this PRD). Full reasoning in dev/local/designs/00004-engram-review-packs-v1-design.md Review log.

### [autonomous] 2026-08-03T16:56:33Z

**Decision**: catchup-skip on build-gate re-entry

**Recommendation**: N/A (artifact-freshness skip)

**Choice**: Skipped the PRD's `catchup: force` frontmatter on this cap-rotation resume.

**Rationale**: The prior session in this same batch already ran the forced full catchup; batch.catchup_head_sha still equaled current HEAD and the capsule artifact was fresh. Re-running would cost ~50K tokens for zero information gain and risk re-tripping the context cap before Phase 3 work started.

### [autonomous] 2026-08-03T16:56:33Z

**Decision**: FRAMING_OVERHEAD_TOKENS ownership - pack.py or client.py?

**Recommendation**: client.py owns it, pack.py imports it from engram.client.

**Choice**: client.py owns it, next to PackBudget.

**Rationale**: The doc-literal reading (define in pack.py, import into client.py) is a circular import, since pack.py must import EngramConfig/embed/Vector from client.py. client.py is also the natural home as a budget constant living next to PackBudget. No behaviour differs; only the definition site.

### [autonomous] 2026-08-03T16:56:33Z

**Decision**: Task-prose overflow priority when PRD content + capsule Active Work line + memory hits exceed prose_cap_tokens

**Recommendation**: Fill in ascending order of size-boundedness so the naturally-truncatable component absorbs the remainder.

**Choice**: Order: (1) capsule Active Work line, (2) 1-2 memory hits, (3) PRD content, truncated to whatever room is left.

**Rationale**: Filling PRD-first would blow the 500-token prose cap on the PRD alone (00004 is ~209 lines) and make the capsule line and memory retrieval permanently dead code. The design already describes PRD content as the truncated component.

### [autonomous] 2026-08-03T16:56:33Z

**Decision**: design-deviation - pack.py filters Reuse precedent to hits whose repo differs from the build repo

**Recommendation**: N/A (forced by test B8a)

**Choice**: Filter Reuse precedent to cross-repo hits only, deviating from the PRD/design's literal "portfolio scope includes current repo" wording.

**Rationale**: Without the filter, every repo-local hit renders twice (once under Similar code, once under Reuse precedent), duplicating content inside the 4000-token hard cap and mislabeling local code as cross-repo precedent - the mirror of the PRD's own stated concern that foreign conventions must never read as local precedent. Flagged for the review lenses to overrule if they disagree.

### [autonomous] 2026-08-03T16:56:33Z

**Decision**: catchup-run (cycle 1, build/1) - re-run full catchup instead of carrying forward the prior catchup-skip

**Recommendation**: N/A (session-recovery decision)

**Choice**: Ran the full catchup this session, honoring the PRD frontmatter `catchup: force` literally.

**Rationale**: The prior skip was justified on token cost, but that session was killed mid-task-4 and left 257 lines of uncommitted formatter churn in pack.py/test_pack.py. The catchup found it and it was stashed rather than committed into task 5. Baseline re-verified at 340 passed, 0 skips.

### [autonomous] 2026-08-03T16:56:33Z

**Decision**: assumed-ambiguity (task 7) - what happens when `engram pack` fails at review time?

**Recommendation**: Pack failure is non-fatal.

**Choice**: Retry at most once, then substitute the literal text "(no pack available this cycle)" for PACK_FILE and PACK_FINDINGS and note the failure in the review file.

**Rationale**: The pack is additive retrieval context, so a pack failure must never block a review cycle, and no unsubstituted placeholder may reach a dispatched reviewer prompt.

### [autonomous] 2026-08-03T16:56:33Z

**Decision**: design-deviation (task 7) - PACK_FILE persona sentence enumerates four pack sections, not the three the design doc pinned verbatim

**Recommendation**: N/A (raised by Pat, verified against code)

**Choice**: Updated the persona sentence to name all four sections including task prose.

**Rationale**: pack.py's `_SECTION_ORDER` renders four sections, and the step passes --prd/--capsule so Task prose is routinely populated. The design wording was inaccurate against the shipped composer; fixed in 310e9a45.

### [autonomous] 2026-08-03T16:56:33Z

**Decision**: review-decision-gate tiering (cycle 1) - classify findings as [D1] decision-gate follow-ups vs [C1] review-flagged retries

**Recommendation**: N/A (tier classification)

**Choice**: Classified as [D1], no tier escalation applied.

**Rationale**: Findings were predominantly targeted follow-ups (path anchoring, a wrong query key, missing error handling, file-size splits, a missed external edit target) rather than evidence that any implementer lacked capability on a correctly-specified task. Several were spec-transmission gaps where the design named a contract the task description never carried. Escalating tiers would cost more without addressing the cause.

### [autonomous] 2026-08-03T16:56:33Z

**Decision**: Quinn (qwen) unavailability and consolidation fallback (cycle 1)

**Recommendation**: N/A (retry-policy decision)

**Choice**: Marked Quinn unavailable after one retry; proceeded with 5 reviewers. Ran consolidation model-side after consolidate-findings.sh exited 1.

**Rationale**: Retry policy allows one retry per agent; both Quinn dispatches failed with an endpoint error while the backend probed healthy, so pi is misrouting the provider. Quinn is advisory weight so no follow-up tasks are lost. consolidate-findings.sh crashed on its own dedup key (a literal pipe the IFS read-back splits on), not a fixable invocation problem, so the SKILL.md step 6 model-side fallback applied.

### [deferred] 2026-08-03T16:56:33Z

**Decision**: task 5 - `engram pack` builds diff_path as a bare cwd-relative path in both --cycle and --diff branches, while prd_path/capsule_path are anchored to repo_root

**Recommendation**: Anchor diff_path to repo_root in both branches; update the two tests that pin the relative shape.

**Choice**: Deferred to batch end / follow-up.

**Rationale**: Found at Pat review cycle 3, the 3-cycle cap, so any fix would ship unreviewed. It also changes a contract the committed tests pin (diff_path as relative), and that contract traces to the orchestrator task spec rather than to an implementor choice. Masked today because the review harness and Claude Code sessions both keep cwd at the repo root.

### [deferred] 2026-08-03T16:56:33Z

**Decision**: task 7 - codex no-edit probe in ~/.claude/skills/work/SKILL.md step 5.5 uses a cwd-relative pathspec

**Recommendation**: Document absolute pathspecs for the probe, or run it with -C pointed at the work-tree.

**Choice**: Deferred - external skill defect, not this PRD's code.

**Rationale**: Observed live on task 7: before/after captures both returned empty (exit 0) while codex had modified 5 files, which would false-latch codex_no_edit true. Re-running with absolute pathspecs correctly reported all 5 modifications. Out of scope for this PRD's diff.
