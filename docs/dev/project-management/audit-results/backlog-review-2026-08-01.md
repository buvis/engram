# Backlog review - engram - 2026-08-01

Verdict: GO (0 Blocking open; both resolved by applied edits, none waived)

Second pass. The 2026-07-31 review (`backlog-review-2026-07-31.md`) closed GO with
12 decisions applied. This pass re-runs all eight lenses against the current tree
and finds two Blocking defects that pass missed, both in the cross-PRD CLI
contract rather than in any single PRD's prose.

## Operational context (not a PRD finding)

The 22:01:50 autopilot launch was started prematurely and died 37s in,
mid-bootstrap, before writing `state.json` (`wrapper.log`, `loop-metrics.jsonl`
signal `died`). It had already moved `00001-engram-core-v1.md` from `backlog/` to
`wip/`, leaving that PRD parked in `wip/` with zero implementation.

**Reset applied (22:21):** 00001 moved back to `backlog/`. Nothing else needed -
no `state.json`, `park-requested` marker, deferred record, or report was ever
written, and `last-session.log` / `wrapper.log` are overwritten by the next launch.
The ledger's `died` entry is left intact as a truthful record. Even without the
reset the next run would have resumed correctly (Phase 0 checks `wip/` before
`backlog/`, `phase-build.md:58`); the move just makes the folder state honest.
A bootstrap death stops the wrapper loud and does not self-relaunch, so autopilot
has to be restarted by hand.

## Map

| # | PRD | template | lines | subsystems | depends on | verdict |
|---|-----|----------|-------|------------|------------|---------|
| 00001 | engram-core-v1 | standard | 312 | engram (client, store, indexer, query, cli, eval) | - | READY |
| 00002 | engram-heavy-corpora-v1 | standard | 200 | engram (transcripts, symbols) + claude-git-ferry | 00001 | READY |
| 00003 | engram-findings-corpus-v1 | standard | 201 | engram (findings, harvest) + purge-devlocal + claude-git-ferry | 00001 (00002 sequencing only) | READY |
| 00004 | engram-review-packs-v1 | standard | 205 | engram (diffmap, pack) + review-work-completion | 00002, 00003 | READY |

(Verdicts post-apply. 00002 was FIX and 00004 FIX before the apply pass; the
00002 finding was resolved in 00001, which owns the CLI contract, so 00002 itself
needed no edit.)

(00001 was in `wip/` during the review - reviewed for cross-PRD contract
consistency - and returned to `backlog/` by the reset above, so all four PRDs are
back in this gate's target directory.)

Lens A: all three match `standard.md` heading-for-heading (four RPG sections
present, repository tree AND per-`Module:` blocks, layer headings, `Test Strategy`
+ `Critical Scenarios`, `Risks`). Every task carries `Acceptance:` (7/5/7 tasks).
`#### Feature:` headings unique and stably named. No frontmatter (all fields
optional), no stubs, no `(guess)`/TBD/TODO markers. Phase titles are
domain-named rather than the template's `Foundation`/`Core`/`Integration` filler -
the template's fill-in slots, not a drift finding.

## Findings

### Blocking

- [00002, 00003, 00004] **B/G: Nothing installs `engram` on PATH.** All three PRDs
  invoke a bare `engram` verb from *outside* the engram repo - catchup SKILL.md
  runs `engram index` + `engram query` in whatever repo it is called from (00002
  L84-85, Phase 2 task), `purge_devlocal.py` runs `engram harvest` from
  `~/.claude` (00003 L77-78), reviewer wiring runs `engram pack` (00004 L67,
  Phase 1 task). No PRD in the set, and no line of the source discovery doc, ever
  states how `engram` becomes globally invokable. 00001 says only
  `pyproject.toml # uv-managed single package`; its CLI acceptance
  (`engram query --scope repo <q>`) is satisfiable by `uv run engram` inside the
  project, which resolves to the *wrong* project everywhere else.
  -> fails as: **rework thrash** at 00002 Phase 2 (`engram: command not found`
  when catchup runs in a sample repo), and worse if the implementer patches around
  it by hardcoding `uv run --project ~/git/src/github.com/buvis/engram` into a
  released claude-git-ferry skill and a global `~/.claude` script.
  Fix: pin the install contract (`uv tool install`, bare `engram` on PATH) in
  00001's Phase 2 CLI task - 00001's own Risks section makes it the owner of the
  CLI contract ("this repo owns the CLI contract; later PRDs edit their own
  consumers").

- [00004] **B/C: The blind-lens assertion requires a toggle no feature defines.**
  Success metric L30 ("Blind-lens prompt is byte-identical with and without pack
  generation") and the Phase 2 task acceptance L180 ("blind prompt byte-identical
  with packs enabled and disabled") both presuppose a way to disable pack
  generation. No Feature in the PRD defines one - the Behavior at L87-88 states the
  real intent instead: "the wiring change must include a check that the blind
  prompt path has no pack reference". The PRD contradicts itself.
  -> fails as: **wrong-TDD lock-in** - the test author sees only the task text,
  invents a `--no-pack` flag or env var to make the criterion writable, and freezes
  unrequested surface into the tests; or the criterion is unwritable and the task
  thrashes to the rework cap.
  Fix: reword both to the grep-able assertion the Behavior already names -
  `references/blind-lens-prompt.md` and the blind lens assembly path contain zero
  pack references (verified: that file exists,
  `~/.claude/skills/review-work-completion/references/blind-lens-prompt.md`).

### Non-blocking

- [00003] B: `purge_devlocal.py` gains a hard dependency on `engram` for every
  repo's GC. The stated failure policy ("If harvest fails for a file, that file is
  NOT trashed this run") is per-file; a *missing binary* would therefore fail every
  file in every purge run across all repos rather than skipping the sweep once with
  one warning. Downstream of Blocking 1; worth one clause distinguishing
  "engram absent -> skip the sweep, warn once, purge normally" from "harvest failed
  for this file -> keep the file".
- [00001] F: 312 lines, well over the ~200 split bar and up from 262 when the
  2026-07-31 review judged it "keep whole" (the growth is that review's own
  mandated contract additions, chiefly the Server ensure feature). The judgment
  still stands and is not re-litigated here: one cohesive pipeline, 10 tasks over
  3 phases, and splitting would manufacture the cross-PRD contract drift the
  discovery explicitly avoids. At ~4-5K tokens the PRD prose tax is noise against
  the 150K per-task budget, so there is no stall mechanism.
- [00002] Phase 0 task 3 (initial ~900MB transcript index) remains the batch's
  longest unattended step. Already mitigated at the last review (acceptance names
  the 10-min Bash ceiling and the repeat-until-fresh pattern); no new action.
- check_links: 2 hits in `backlog/` (00002 L81 `dev/local/project-capsule.md`,
  00004 L50 `dev/local/tmp/engram-pack-{id}.md`) are declared outputs and exempt by
  rule. 1 hit in `wip/` (00001 L292 `[[embedding]]`) is a TOML table header parsed
  as a wikilink - a false positive. A `link-ok:` token on each would silence future
  gate runs; none is a real dangling pointer.
- engram is not registered in `~/.config/gita/repos.csv`, so its own code and prose
  are outside the corpora it indexes. Harmless for the batch (the repo is new and
  nearly empty); register it once 00001 ships if self-retrieval is wanted.

### Questions

None. No genuine authorial ambiguity surfaced - both Blocking findings have one
correct answer each.

## Reshapes

None. All three PRDs are 198-202 lines, 3 phases, 5-7 tasks, one subsystem plus its
declared external consumers. Ordering is ascending-safe (00004 -> 00002, 00003;
00003 -> 00001 only). Same-file contention on catchup SKILL.md between 00002 and
00003 stays explicitly sequenced.

## Gaps

- The install/PATH gap above is the set's only producer/consumer hole, and it
  originates upstream: the discovery doc's Constraints and Codebase Context never
  cover distribution either.
- Ad-hoc mid-task `engram query` still has no discoverability wiring (no AGENTS.md
  or rule tells agents the tool exists). Carried unchanged from the 2026-07-31
  review; deliberate deferral, one-line AGENTS.md entry after 00002 ships.
- Distill loop, MCP wrapper, LLM symbol enrichment, transcript summarization: named
  upgrade paths in Risks, deliberately out of scope. No orphaned deprecations, no
  half-migrations.

## End state after this batch

Engram becomes a working local context engine: scoped hybrid retrieval over
memories, PRDs, decisions, discovery docs, transcripts, and cross-repo code;
catchup feeds a Related-context capsule section; review findings survive GC as a
queryable precedent corpus; every non-blind review lane gets a bounded
diff-selective pack, with the blind lens provably untouched. Still lacking after
the batch: agent-facing discoverability of ad-hoc query, and the distill loop that
turns precedent into skills - both deliberate deferrals with named homes.

## Frontmatter tuning

| PRD | suggestion | why |
|-----|------------|-----|
| 00002 | none | 3 phases, clear contracts; defaults fit |
| 00003 | none | smallest of the three |
| 00004 | `catchup: force` | it runs last, after 00002/00003 reshape both engram and `~/.claude`; a forced re-catchup re-grounds its references - APPLIED |

## Decisions applied

1. **Install contract (Blocking 1) - pin it in 00001 - APPLIED.** 00001's CLI
   Feature Behavior gains "Installed with `uv tool install .` so a bare `engram`
   sits on PATH; later PRDs' consumers (catchup, purge-devlocal, reviewer wiring)
   invoke it bare from other repos, never via `uv run`", and its Phase 2 CLI task
   acceptance gains "`uv tool install .` puts a bare `engram` on PATH and
   `engram --help` runs from a directory outside this repo". Chosen over adding
   the task to 00002 because 00001's own Risks section declares this repo the
   owner of the CLI contract. The edit landed while 00001 was still parked in
   `wip/` by the premature launch; the reset has since returned it to `backlog/`.
2. **Blind-lens assertion (Blocking 2) - grep assertion - APPLIED.** 00004's
   success metric and Phase 2 task acceptance both replaced. The metric now reads
   "The blind lens path carries zero pack references: `blind-lens-prompt.md` and
   the blind prompt assembly in review-work-completion contain no engram-pack
   path, section, or variable"; the task acceptance now reads "blind prompt
   assembly asserted pack-free by a grep over blind-lens-prompt.md + the blind
   invocation path (zero hits)". The Behavior line at L87-88 already stated this
   intent and needed no change. Rejected: building a `--no-pack` toggle purely to
   serve a test.
3. **engram-absent clause (Non-blocking) - APPLIED.** 00003's pre-trash sweep
   Behavior and its Phase 2 task acceptance now separate "no `engram` on PATH ->
   skip the sweep once with one warning, purge proceeds normally" from "harvest
   failed for this file -> keep the file".
4. **00004 `catchup: force` (Non-blocking) - APPLIED** as frontmatter.

Post-apply lens A re-run on all three touched PRDs (00001, 00003, 00004): heading
order intact and template-matching, task count equals `Acceptance:` count in every
PRD (00001 10/10, 00002 7/7, 00003 5/5, 00004 7/7), 00004's new frontmatter is a
recognized field with a valid value, zero stub markers. check_links re-run: the
same three PRD-scoped hits remain, all exempt or false-positive (see Non-blocking).

## Gate honesty

- All eight lenses run inline; no subagents (3 PRDs, well under the ~8 threshold),
  so no subagent failures to report.
- Lens D re-verified against the live filesystem, not trusted from prose: every
  external premise path exists and is unchanged since the last review
  (`purge_devlocal.py` Jul 20, `agent-invocation.md` Jul 22, `agent-prompts.md`
  Jul 14, `blind-lens-prompt.md` Jul 9, `gather-context.sh` Jul 12, catchup
  `SKILL.md` May 31, `dev/bin/release`, `repos.csv`, discovery doc Jul 31 - all
  predate the 2026-07-31 review, so its grounding conclusions still hold).
  Newly checked this pass: `.claude/settings.json` additionalDirectories (grants
  claude-git-ferry + `~/.claude`, committed d5eb18b), `phase-build.md` wip-first
  selection, gita registration, engram git remotes (none - local only).
- Surprise test: passed. The PATH/install hole and the blind-lens toggle
  contradiction both survived the first review's twelve applied decisions.
- Settled items from the 2026-07-31 review were not re-litigated.
