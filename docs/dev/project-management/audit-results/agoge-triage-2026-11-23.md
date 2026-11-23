# Agoge disposition: 2026-11-23

Status: QA disposition complete; implementation queued, not performed.

Authority: the user's standing AGENTS.md instructions authorize routine review adjudication, reversible documentation and backlog work. These are agent decisions under that authority, not individual human approvals and not a scripted --decisions test run. Agoge resume dispatches no lanes and repeats no product probes. The older skill's ask-first and cluster-approval steps are superseded by the user's standing authorization.

Scope: resume the 2026-11-16 drained-batch report and close its predecessor's pending packets. Original evidence and verification labels remain unchanged. No live store, model server, registry, credential, or installed plugin was modified.

Measured source: HEAD 0003560ff29f732bcd048e505e11c7fc12c12c69, observed 2026-11-23T22:21:07+00:00. The source tree has no production-code changes since QA HEAD fba09676699e5b440200b8a17bd0cfccc7d1878a; intervening changes are QA/profile files, CI action pins and the dependency lockfile. The worktree was clean at entry. This is source inspection plus backlog validation, not a new QA run.

## Result

- 47 source packets dispositioned: 43 accepted or accepted-and-merged, 4 deferred packet entries. Duplicate packet numbers remain traceable below.
- 11 bounded PRDs emitted, 00017 through 00027. Both HIGH findings are in the first two PRDs.
- Three distinct optimization deferrals remain: preflight caching, unchanged harvest caching, and name-miss lookup optimization. Preflight caching occurs in both reports.
- Vector partition layout, module-context language expansion and automatic server shutdown remain unchanged by design; their documentation is queued.
- The first 2026-11-15 report aborted with zero findings. Its observations are superseded by the two completed reports; it has no independent unresolved packet.

## Backlog and order

Run these through the normal autopilot pipeline. This session prepares the backlog; it does not start a PRD build or bypass its fresh-session review. Use serial execution because several PRDs share CLI, store and rendering modules.

| PRD | Work | Prerequisites |
|---|---|---|
| [00017](../prds/backlog/00017-verify-embedding-model-identity-v1.md) | Verify the served embedding model before use | None |
| [00018](../prds/backlog/00018-index-chunks-by-source-v1.md) | Index chunk lookups by corpus and path | None |
| [00019](../prds/backlog/00019-validate-repository-registry-v1.md) | Validate repository registration before indexing | None |
| [00020](../prds/backlog/00020-bound-indexing-to-repositories-v1.md) | Index tracked paths without reading outside repositories | 00019 |
| [00021](../prds/backlog/00021-unify-worktree-source-identity-v1.md) | Use one source identity across linked worktrees | 00019 |
| [00022](../prds/backlog/00022-exclude-worktree-self-matches-v1.md) | Exclude changed code from worktree packs after line shifts | 00019 |
| [00023](../prds/backlog/00023-protect-store-write-lifecycle-v1.md) | Protect rebuilds and concurrent store writes | None |
| [00024](../prds/backlog/00024-sanitize-retrieved-context-v1.md) | Sanitize retrieved context before publication | None |
| [00025](../prds/backlog/00025-isolate-malformed-input-failures-v1.md) | Isolate malformed input failures and clarify diagnostics | 00019, 00017 |
| [00026](../prds/backlog/00026-reject-imports-in-migrated-memory-v1.md) | Reject import paths in migrated memory metadata | None |
| [00027](../prds/backlog/00027-correct-operating-documentation-v1.md) | Correct operating and upgrade documentation | None |

Priority: identity correctness and the source index first, then registry and containment, then worktree correctness and store lifecycle. Output redaction and migration guards belong in this batch, not a cosmetic follow-up. Do not run the new recovery option against the user's store during implementation.

## Review choices

The original packets retain their alternatives, benefits, drawbacks and recommendations. The table below records the selected option or the justified change. Important choices are explicit:

- **Recommended: validate served identity from the model listing.** This prevents an echoed request ID from blessing a wrong model. Alias mismatches now require matching configuration. Checking only the embedding response leaves the defect, while refusing every externally started server breaks the supported shared-server case.
- **Recommended: keep detached reuse and correct the docs.** This preserves the recorded server design and warm calls. Memory stays resident until a PID-specific shutdown. Exit-time shutdown would slow hooks; an idle watchdog adds timing and ownership state without a demonstrated requirement.
- **Recommended: redact on publication and create new private artifacts.** This protects all current context surfaces without rebuilding vectors. Existing raw stores and their permissions stay unchanged. Ingest redaction needs a migration and changes retained evidence; permissions alone do not stop agents receiving secrets.
- **Recommended: canonicalize future findings and retain differing historical variants.** This prevents new same-source worktree copies. Last-write-wins remains the current source-update rule. Query-time dedup alone leaves storage growth; bulk historical deletion could lose branch-specific evidence.
- **Recommended: hold the writer lock and make findings discard explicit with a backup.** This closes the write/rebuild race and keeps recovery reversible. Concurrent hooks can receive a busy error. A check without a held lock races, while silent findings loss is unacceptable; general SQLite salvage is beyond this bounded repair.
- **Recommended: accept current storage and low-latency lookup costs.** Existing evidence does not establish a failed user budget. The costs remain documented below. Partition redesign needs measured recall/search tradeoffs; an extra lookup index needs a demonstrated hot path.

## Latest report: 2026-11-16

Source: [original packets](agoge-2026-11-16.md). Accepted means queued, not fixed.

| Packet | Disposition | PRD | Decision and evidence limits |
|---|---|---|---|
| 1 | accepted | [00017](../prds/backlog/00017-verify-embedding-model-identity-v1.md) | Accept option 1: use the served model listing; retain per-call validation. |
| 2 | accepted | [00018](../prds/backlog/00018-index-chunks-by-source-v1.md) | Accept option 1: add the corpus/path index without rebuilding vectors. |
| 3 | accepted | [00020](../prds/backlog/00020-bound-indexing-to-repositories-v1.md) | Accept option 1: NUL-delimited Git paths; retain unmerged-stage deduplication. |
| 4 | accepted | [00021](../prds/backlog/00021-unify-worktree-source-identity-v1.md) | Accept option 1: map worktree-relative file paths to the registered checkout; document indexed line positions. |
| 5 | accepted | [00027](../prds/backlog/00027-correct-operating-documentation-v1.md) | Accept option 1: document intentional detached reuse; no automatic shutdown or watchdog. |
| 6 | accepted | [00019](../prds/backlog/00019-validate-repository-registry-v1.md) | Accept option 1 with legacy-memory slug preservation and safe re-indexing of alias code/prose. |
| 7 | accepted | [00021](../prds/backlog/00021-unify-worktree-source-identity-v1.md) | Accept canonical identity for future harvests; remove only proven identical legacy aliases and retain differing history. |
| 8 | accepted | [00022](../prds/backlog/00022-exclude-worktree-self-matches-v1.md) | Accept name/kind identity across distinct checkouts with a reported conservative fallback for ambiguous files. |
| 9 | accepted | [00019](../prds/backlog/00019-validate-repository-registry-v1.md) | Accept option 1: refuse an empty registry before pruning or rebuild replacement. The report title overstates loss: findings survive. |
| 10 | accepted | [00023](../prds/backlog/00023-protect-store-write-lifecycle-v1.md) | Accept explicit discard recovery only, with a retained database backup; default remains loss-averse. |
| 11 | accepted | [00020](../prds/backlog/00020-bound-indexing-to-repositories-v1.md) | Accept option 1 across enumerators and direct pack inputs; explicit diff input remains permitted. |
| 12 | accepted | [00024](../prds/backlog/00024-sanitize-retrieved-context-v1.md) | Accept output redaction and private creation modes, extended to full PEM blocks and quoted credential assignments. Raw existing stores remain. |
| 13 | accepted | [00022](../prds/backlog/00022-exclude-worktree-self-matches-v1.md) | Accept option 1: canonicalize each distinct path once. |
| 14 | accepted | [00020](../prds/backlog/00020-bound-indexing-to-repositories-v1.md) | Accept option 1 before code and prose enumeration; retain scope-safe pruning. |
| 15 | accepted | [00023](../prds/backlog/00023-protect-store-write-lifecycle-v1.md) | Accept finally cleanup under the acquired lock; do not touch another writer's temp. |
| 16 | accepted | [00019](../prds/backlog/00019-validate-repository-registry-v1.md) | Accept registry validation with path-specific diagnostics and per-file harvest failures. |
| 17 | accepted | [00023](../prds/backlog/00023-protect-store-write-lifecycle-v1.md) | Choose option 2: hold the lock through writes. A fail-fast precheck alone has a race. |
| 18 | accepted | [00023](../prds/backlog/00023-protect-store-write-lifecycle-v1.md) | Accept atomic schema/vector initialization or clean busy refusal; retain a two-process regression. |
| 19 | accepted | [00017](../prds/backlog/00017-verify-embedding-model-identity-v1.md) | Accept with model-identity work as mocked error-path coverage; no promotion to live-server verification. |
| 20 | accepted | [00027](../prds/backlog/00027-correct-operating-documentation-v1.md) | Accept option 1: document model and per-version grammar downloads. |
| 21 | accepted | [00027](../prds/backlog/00027-correct-operating-documentation-v1.md) | Accept option 2: merge unreleased categories and correct the pin; do not invent a release/tag. |
| 22 | deferred | Retained here | Defer probe caching. Identity correctness comes first; revisit only after model/restart tests and a current workload measurement. |
| 23 | accepted | [00019](../prds/backlog/00019-validate-repository-registry-v1.md) | Accept one validated registry snapshot per harvest, shared with the registry fix. |
| 24 | deferred | Retained here | Defer unchanged-harvest caching. First measure whether the actual caller resubmits unchanged files; parser-version invalidation would add state. |
| 25 | accepted | [00021](../prds/backlog/00021-unify-worktree-source-identity-v1.md) | Accept option 1: require membership in Git's own worktree list. |
| 26 | accepted | [00024](../prds/backlog/00024-sanitize-retrieved-context-v1.md) | Accept control filtering and data framing. This does not guarantee prompt-injection prevention. |
| 27 | accepted | [00026](../prds/backlog/00026-reject-imports-in-migrated-memory-v1.md) | Accept conservative migration validation; the downstream import effect remains unverified. |
| 28 | accepted | [00019](../prds/backlog/00019-validate-repository-registry-v1.md) | Accept absolute-row validation in the registry reader. |
| 29 | accepted | [00022](../prds/backlog/00022-exclude-worktree-self-matches-v1.md), [00023](../prds/backlog/00023-protect-store-write-lifecycle-v1.md), [00025](../prds/backlog/00025-isolate-malformed-input-failures-v1.md) | Split by boundary: lock/rebuild issues to 00023; diff physical lines to 00022; parser/config errors to 00025. Narrow transcript claim: ordinary invalid JSON already continues per record. |
| 30 | accepted | [00017](../prds/backlog/00017-verify-embedding-model-identity-v1.md) | Accept syntax hardening from a mocked probe. Allow HTTP and HTTPS loopback, reject userinfo/unknown schemes, and validate redirects too. |
| 31 | accepted | [00027](../prds/backlog/00027-correct-operating-documentation-v1.md) | Accept documentation; retain current vector partitions. Reconsider layout only with disk pressure and measured search/rebuild tradeoffs. |

## Previous report: 2026-11-15 run 2

Source: [original packets](agoge-2026-11-15-2.md). Merged entries point to the same PRD as their later counterpart.

| Packet | Disposition | PRD | Decision and evidence limits |
|---|---|---|---|
| 1 | accepted | [00027](../prds/backlog/00027-correct-operating-documentation-v1.md) | Merge into latest #5; document the intentionally persistent server. |
| 2 | accepted | [00027](../prds/backlog/00027-correct-operating-documentation-v1.md) | Choose documented backfill repair rather than a new automatic migration. The current backfill re-chunks unchanged sources and compares stored chunks; no fresh product run was made. |
| 3 | accepted | [00024](../prds/backlog/00024-sanitize-retrieved-context-v1.md) | Merge into latest #12, with assignment redaction included so this older finding is fully covered. |
| 4 | accepted | [00019](../prds/backlog/00019-validate-repository-registry-v1.md) | Partly superseded by PRD 00016's resolved-root comparison. The remaining producer/lookup mismatch is latest #6 and belongs to 00019. |
| 5 | accepted | [00017](../prds/backlog/00017-verify-embedding-model-identity-v1.md) | Accept status model identity and nonzero mismatch result under 00017. |
| 6 | accepted | [00027](../prds/backlog/00027-correct-operating-documentation-v1.md) | Merge into latest #20. |
| 7 | accepted | [00027](../prds/backlog/00027-correct-operating-documentation-v1.md) | The claim that rebuild is the only backfill route is superseded by completed PRD 00015. Retain the synthetic rebuild cost as documentation, not a new performance budget. |
| 8 | accepted | [00024](../prds/backlog/00024-sanitize-retrieved-context-v1.md) | Accept fenced excerpts with budget accounting under 00024. |
| 9 | accepted | [00017](../prds/backlog/00017-verify-embedding-model-identity-v1.md) | Accept the pre-embed stored-model check under 00017. |
| 10 | accepted | [00027](../prds/backlog/00027-correct-operating-documentation-v1.md) | Accept explicit language coverage documentation. Expanding the allowlist or changing to a denylist is outside this correction. |
| 11 | accepted | [00027](../prds/backlog/00027-correct-operating-documentation-v1.md) | Accept the corrected corpus table under 00027. |
| 12 | accepted | [00025](../prds/backlog/00025-isolate-malformed-input-failures-v1.md) | Accept labeled optional-directory diagnostics under 00025. |
| 13 | deferred | Retained here | Merge into latest #22's deferral; preserve identity and recycling checks before any optimization. |
| 14 | deferred | Retained here | Defer index changes for lookup misses. Historical wall time was 3-8 ms; revisit if a measured user workload makes this material. |
| 15 | accepted | [00027](../prds/backlog/00027-correct-operating-documentation-v1.md) | Merge into latest #21; later packet supplies the missing command evidence. |
| 16 | accepted | [00027](../prds/backlog/00027-correct-operating-documentation-v1.md) | Merge into latest #31; retain partitions and document the measured allocation cost. |

## Evidence checked in this session

Source inspection corroborated the implementation gaps at these existing entry points:

- client.preflight checks the embedding response model; the test server already serves /v1/models but its embedding response uses its own model ID. Query embeds before store identity rejection; status omits model identity.
- store.open_store creates a symbol-name index but no corpus/path index. Backfill reads vectors per source and replaces by corpus/path.
- symbols.enumerate uses line-split git ls-files output. CorpusFile producers retain registry spelling; lookup resolves paths. Index and backfill filter after enumeration.
- harvest resolves common-dir ownership without checking listed worktrees; upsert stores the physical checkout path. Registry reads occur per file.
- pack compares indexed/main paths using worktree line numbers and calls realpath in the nested comparison. Its body renderer indents only the first line.
- write_lock covers harvest and rebuild only; rebuild catches Exception rather than placing cleanup in finally. Lock creation follows symlinks and does not specify private mode.
- Output formatters publish raw headings/bodies. Existing redact handles token patterns but only the BEGIN marker of a PEM key, so the output PRD explicitly requires whole-block masking.
- transcripts.chunk already continues after JSONDecodeError. The broad bad-line claim is narrowed to errors such as deep nesting; no new product reproduction is claimed.
- README and CHANGELOG retain the reported lifecycle, download, corpus and category discrepancies. The current backfill algorithm provides a repair route for unchanged stored code bodies; that route is not claimed as runtime-tested here.

## Deferred work and closure conditions

| Item | Decision | What reopens or closes it |
|---|---|---|
| Latest #22 / previous #13: repeated preflight | Defer caching | After 00017, measure a real repeated workload; add caching only with restart/model-change invalidation tests. |
| Latest #24: unchanged harvest embedding | Defer caching | Measure caller behavior; if repeated unchanged files dominate, specify parser-version invalidation and a forced refresh. |
| Previous #14: name-miss lookup scan | Accept current milliseconds; defer optimization | Revisit when lookup misses are a measured hot path; validate collation before changing prefix search. |
| Latest #31 / previous #16: vector partition size | Retain layout; document in 00027 | Revisit on measured disk pressure with scoped-search and rebuild comparisons. |
| Latest #7: divergent historical worktree copies | Retain differing history in 00021 | A later cleanup requires a report of exact candidate rows and a recoverable migration; no bulk deletion is authorized by this triage. |
| Previous #10: unsupported top-level languages | Document in 00027 | Add languages only when the portfolio needs them and parser/recall fixtures establish the benefit. |
| Prior QA gaps | Preserve historical skipped/mock labels | A later clean-tree QA run must cover install/upgrade, concurrent rebuild/harvest and any live-server behavior it claims. No hostile remote model download is required. |

## Validation

The PRD grounding gate passed on all drafts: 0 blocking, 0 unverified, 0 declared-new references. Structural, dependency, link, packet-coverage and sequence checks are recorded at closeout below. No runtime suite, real-server probe or new Agoge lane ran in this documentation-only resume. All implementation tests and fresh-session reviews remain part of the queued PRDs.

### Closeout checks

- PASS: all 11 PRDs follow the standard template order, list existing target files, contain three bounded tasks, and contain no unresolved guess markers.
- PASS: dependency and report links resolve; PRD numbers 00017-00027 are unique across lifecycle files and do not collide with intake items.
- PASS: all 47 packet numbers have one disposition; every accepted packet links to at least one emitted PRD. Original sidecar finding objects are byte-equivalent after JSON decoding.
- PASS: final grounding gate reports 0 blocking, 0 unverified, 0 declared-new references.
- PASS: git diff --check. Runtime suites and Agoge reruns were not executed because only documentation and QA metadata changed.
