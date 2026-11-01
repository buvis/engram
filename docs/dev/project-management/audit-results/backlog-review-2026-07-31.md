# Backlog review - engram - 2026-07-31

Verdict: GO - unconditional (2026-08-01 final state). The original condition
(attended embedding-model provisioning) was dissolved by decision 12:
engram ensures its own servers spawn-on-demand; the only precondition is
`llama-server` on PATH, verified installed (Homebrew llama.cpp). Every
Blocking finding is resolved by an applied edit; none waived.

## Map

| # | PRD | template | lines | subsystems | depends on | verdict |
|---|-----|----------|-------|------------|------------|---------|
| 00001 | engram-core-v1 | standard | 273 | engram (new repo) | - | READY* |
| 00002 | engram-heavy-corpora-v1 | standard | 200 | engram + claude-git-ferry | 00001 | READY |
| 00003 | engram-findings-corpus-v1 | standard | 198 | engram + ~/.claude + claude-git-ferry | 00001 (00002 sequencing only) | READY |
| 00004 | engram-review-packs-v1 | standard | 202 | engram + ~/.claude | 00002, 00003 | READY |

*READY once the attended embedding-model precondition is met; the PRD's preflight
premise re-check fails loud if it is not.

Template compliance (lens A): all four match `standard.md` heading-for-heading, all
tasks carry `Acceptance:`, Feature headings unique, no frontmatter (all fields
optional), no stubs beyond the two declared `(guess)` markers in 00003. Cross-PRD
order is ascending-safe; 00002/00003 same-file contention on catchup SKILL.md is
explicitly sequenced (00003 extends 00002's section). All 12 discovery must-haves
trace into the set; no invented scope beyond the harvest-verb mechanism (Q1).

## Findings

### Blocking

- [00001] B/D: No embedding model exists on this machine. `~/.pi/agent/models.json`
  registers only chat models (Qwen3 Coder / Qwen3.6, ports 8080/8001); the HF hub
  cache holds zero embedding GGUFs; the eval harness needs THREE shortlist models
  served, and engram may never launch a server (discovery constraint). -> fails as:
  unattended hang/stall - preflight fails on Phase 0 task 2, and no headless
  mechanism exists to switch LlamaBarn-served models between harness runs. Fix:
  attended pre-provisioning (download + serve shortlist port-per-model, register in
  models.json) + PRD edit pinning the "endpoint-entry-per-model" contract and naming
  the config file that records the pinned winner.
- [00003] D: Review-file parser's guessed finding shape contradicts reality. Real
  review files (e.g. `~/.claude/dev/local/reviews/00077-...-review-1.md`) carry
  findings as a markdown table (`| # | Consensus | Severity | Issue | File |`) plus
  emoji-severity bullets (🔴/🟠/🟡) in a Deferred section - not "a line starting
  with a severity tier". -> fails as: wrong-TDD lock-in - tests encode the guessed
  shape, ALL real files fall through to the unstructured fallback, structured fields
  (severity/file/pattern) stay empty while tests pass. Fix: rewrite the Behavior to
  the observed contract; fixtures copied from real review files.
- [00004] B: "Sampled past review cycles" have no data. Zero `review-diff-*.diff`
  (zero `.diff` at all) survive anywhere under `~/git/src/github.com/buvis` - tmp/
  GCs at 7 days. The success metric and Phase 1 exit criteria are unverifiable at
  execution time. -> fails as: stall/rework thrash. Fix: reword to historical
  commit ranges via `engram pack --diff <range>` (real past PRD implementation
  commits), which the verb already supports.
- [00002, 00003, 00004] B: Unattended sessions cannot write the external consumer
  paths. `autoclaude` launches `claude -p --permission-mode auto` with no
  `--add-dir`; the only global `additionalDirectories` entry is
  `~/.local/tmp/claude-dev`. Every Phase 2 (catchup SKILL.md edit + release,
  purge_devlocal.py sweep, reviewer template wiring) edits `claude-git-ferry` or
  `~/.claude` - denied headlessly. -> fails as: unattended hang / task-fail thrash
  at each PRD's integration phase. Related hazard: 00004 edits the review templates
  used by its own review cycle (loop self-harm; mitigated by being last in batch +
  the blind byte-identical assertion). Fix: decide grant vs restructure (walkthrough).
- [00001 L65-66, 00003 L82, 00004 L37/L43] step-1 citations: 5 dangling-path hits
  from check_links.py. All are per-repo patterns or runtime staging artifacts, not
  real dangling pointers; 00002 L81 and 00004 L49 are declared outputs (exempt).
  -> fails as: stall (mechanical premise-check rule). Fix mandated by the gate:
  `link-ok:` waiver tokens on the five citing lines. Applied without asking
  (settled by rule).

### Non-blocking

- [00003] C: Structural decomposition says "(00001 modules unchanged; cli.py gains
  the harvest verb)" but the prune-exemption for findings rows requires touching
  store.py/indexer.py prune logic. Planner may misplace the exemption. Fix: one-line
  amendment to the structure note.
- [00001] F: 262 lines, over the ~200 split-candidate bar. Judgment: keep whole -
  one cohesive pipeline, 10 tasks/3 phases, splitting would create cross-PRD
  contract-drift risk the discovery explicitly avoids. Optional prose trim.
- [00002] B: "Initial transcript index" embeds ~900MB/1,681 transcripts in one task;
  a single foreground run exceeds the 10-min Bash ceiling. Incrementality makes
  re-invocation safe; acceptance should say resumable runs are expected.
- [00001] A: eval harness "pins the winner in engram config" but no config artifact
  exists in the structure tree (folded into the embedding-endpoint edit).

### Questions

- [00003] `engram harvest` as a new 5th CLI verb is marked `(guess)` - discovery's
  surface is query|index|status|pack. Confirm or fold.
- [00003] Dedup key = content hash of the source review file: a file amended
  between catchup harvest and purge harvest produces two overlapping record sets.
  Key on path (replace-on-reharvest) instead?

## Reshapes

None proposed. 00001 stays whole (see Non-blocking).

## Gaps

- Ad-hoc mid-task agent use of `engram query` (a discovery target user) has no
  discoverability wiring - no AGENTS.md/rule tells agents the tool exists. Not a
  dropped must-have (discovery wired only capsule + packs); note for a future
  one-line AGENTS.md entry after 00002 ships.
- Distill loop, MCP wrapper, LLM symbol enrichment, transcript summarization:
  deliberately deferred nice-to-haves, named as upgrade paths in Risks. No orphaned
  deprecations, no half-migrations.

## End state after this batch

Engram becomes a working local context engine: scoped hybrid retrieval over
memories, PRDs, decisions, discovery docs, transcripts, and cross-repo code;
catchup feeds a Related-context capsule section; review findings survive GC as a
queryable precedent corpus; every non-blind review lane gets a bounded
diff-selective pack. Still lacking after the batch: agent-facing discoverability of
ad-hoc query, and the distill loop that turns precedent into skills - both
deliberate deferrals with named homes.

## Frontmatter tuning

| PRD | suggestion | why |
|-----|------------|-----|
| 00001 | `rework_cap: 5` (optional) | eval-gate tuning may need extra review cycles; insurance against a pause at cap 3 |

## Decisions applied

1. Embedding models (00001, Blocking): pre-provision attended - APPLIED, then
   CORRECTED (2026-08-01 follow-up): the first fix named LlamaBarn +
   models.json registration, but LlamaBarn is not installed anywhere on this
   machine (no app, no cask; :8080 dead) - the name was doc drift inherited
   from the discovery doc and use-qwen SKILL.md; models are actually served by
   bare Homebrew `llama-server` (the `start_qwen` pattern). Final contract:
   one `llama-server --embedding -hf <model> --port <port>` per shortlist
   model, endpoints + model ids listed in engram-owned
   `~/.local/share/engram/config.toml` (user authors it; harness writes the
   `pinned` entry back); `~/.pi/agent/models.json` stays chat-only. USER
   ACTION before launch: start the three embedding servers and author the
   initial config.toml.
2. External-edit permissions (00002-04, Blocking): grant both paths - APPLIED.
   `.claude/settings.json` created with additionalDirectories for
   claude-git-ferry and ~/.claude; committed (d5eb18b). Accepted drawback:
   engram sessions gain standing write access to ~/.claude (loop-self-harm
   surface); 00004 stays last in the batch as mitigation.
3. Parser shape (00003, Blocking): rewrite to observed contract - APPLIED.
   Behavior now names the Consolidated Findings table + emoji-severity deferred
   bullets; fixtures are copies of real files in ~/.claude/dev/local/reviews/.
4. Pack metric (00004, Blocking): historical commit ranges - APPLIED. Success
   metric, Phase 1 exit criteria, and happy-path scenario reworded to >=3
   ranges via `engram pack --diff <range>`.
5. Dangling citations (Blocking, rule-settled): link-ok waiver tokens - APPLIED
   on 00001 (enumerator patterns line), 00003 L82, 00004 L37/L43. Re-run of
   check_links: only declared-output forward references remain (exempt).
6. Harvest verb (00003, Question): confirmed fifth verb - APPLIED (guess marker
   dropped).
7. Dedup key (00003, Question): path-keyed replace-on-reharvest - APPLIED
   (Behavior, success metric, and harvest task acceptance all bind it).
8. 00003 structure amendment - APPLIED (store/indexer prune-exemption named).
9. 00002 resumable-index note - APPLIED (task acceptance names the 10-min Bash
   ceiling and the repeat-until-fresh pattern).
10. 00001 prose trim - APPLIED (light: 4 lines of restatement cut; net +10 vs
    original because mandated contract additions outweigh it - deeper cuts
    would remove contracts).
11. 00001 `rework_cap: 5` frontmatter - APPLIED.
12. Server lifecycle (2026-08-01, user-raised portability requirement):
    ensure-on-demand - APPLIED. Reverses the discovery's "never launches a
    server" constraint, justified twice over: the constraint's LlamaBarn
    premise was dead (see Decision 1 correction), and portability to fresh
    setups demands zero manual server management. 00001 gains a Server ensure
    feature (probe -> spawn detached -> preflight-readiness; missing binary
    fails loud naming `brew install llama.cpp`; missing config.toml written
    with the default shortlist), client module + Phase 0 task extended, the
    harness ensures each eval leg and stops what it started except the pinned
    winner, the zero-network metric gains the first-ensure GGUF-download
    exception, and the attended precondition collapses to "llama-server on
    PATH" (verified installed). The start_embed/stop_embed bash helpers from
    the interim design were reverted in the dotfiles repo (751f2b98a) as
    redundant.

Post-apply lens A re-run on all four touched PRDs: headings intact, all tasks
carry Acceptance:, zero guess/TBD markers remain, frontmatter valid
(`rework_cap: 5` on 00001 only).

## Gate honesty

- Lens D dispatched inline (4 PRDs, under the subagent threshold); all grounding
  claims verified with rg/ls against the live filesystem, none trusted from
  prose. Verified: models.json (no embedding entries - finding), HF cache (no
  embedding GGUFs - finding), cellar transcripts (1,681 files), catchup
  SKILL.md capsule flow, gather-context.sh staging contract + TMP_DIR, real
  review-file shapes (16 files), purge_devlocal.py review handling,
  agent-prompts.md / agent-invocation.md, dev/bin/release, autoclaude launch
  flags, settings.json additionalDirectories, tree-sitter in hooks tests.
- Surprise test: passed - the zero-embedding-models finding and the
  headless-write-denial finding were both structural surprises.
- No lens skipped; no subagents used, so no subagent failures to report.
- Missed on the first pass, caught by the user: "LlamaBarn" itself was never
  verified - I checked the registry and GGUF cache around it but took the
  serving mechanism on faith from the discovery doc. It is not installed;
  finding 1's fix was corrected accordingly (see Decisions applied 1).

## Flagged external drift (not this repo's scope)

- `~/.claude/skills/use-qwen/SKILL.md` says models are "served via LlamaBarn on
  :8080" and calls LlamaBarn "a convenient llama.cpp manager"; the machine
  serves via bare `llama-server` (Homebrew) and no LlamaBarn exists. Same drift
  in `~/.claude/dev/local/discovery/00090-engram-context-engine.md` (must-have
  2, Constraints, Conventions). Fix in a ~/.claude session, not here.
