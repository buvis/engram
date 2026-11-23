---
default_model: opus
model_tier_rationale: cross-cutting model validation and error contracts across CLI, retrieval, and the client
---

# Verify the served embedding model before use

Source: 2026-11-16 #1, 2026-11-16 #19, 2026-11-16 #30, 2026-11-15 run 2 #5, 2026-11-15 run 2 #9. Original packets: docs/dev/project-management/audit-results/agoge-2026-11-16.md and docs/dev/project-management/audit-results/agoge-2026-11-15-2.md.
Decision: docs/dev/project-management/audit-results/agoge-triage-2026-11-23.md. This is a bounded QA correction, not a replacement of the completed feature PRDs.

## Overview

### Problem Statement
The server can echo the requested model ID while serving another model. A store can therefore contain vectors under a false model label. Query checks the stored model too late, status omits that check, and several CLI paths expose tracebacks.

### Target Users
The solo developer and local agents using Engram to index repositories and recall prior work.

### Success Metrics
Every Critical Scenario passes with synthetic data in isolated temporary roots. Historical evidence below is from the QA run, not a fresh measurement. No suite-wide test count or timing target is imposed.

## Functional Decomposition

### Capability: Verify the served embedding model before use
Apply the recorded disposition without changing unrelated behavior.

#### Feature: Verify authoritative identity
- **Description**: Verify authoritative identity.
- **Inputs**: Configured model and the local server model listing.
- **Outputs**: A verified lease or a typed identity error before real input is embedded.
- **Behavior**: Compare the configured ID to the single served ID from GET /v1/models. Refuse missing, malformed, ambiguous, or mismatched identity; never fall back to the request echo. Keep vector dimension and finite-value checks. Make the test server echo the requested model in embedding replies while retaining its served ID in the listing. A startup 503 remains retryable under the existing startup timeout.

#### Feature: Check stored identity before work
- **Description**: Check stored identity before work.
- **Inputs**: Store metadata and selected configuration.
- **Outputs**: Early failure without spawning or embedding; useful status.
- **Behavior**: Call the existing store model assertion before query embedding, including MCP. Status reports configured and indexed IDs and exits 1 on mismatch without contacting the server. An empty store with no model metadata is valid. Handle identity errors in query, index, backfill and re-embed consistently, with one rebuild hint only when the store itself differs.

#### Feature: Validate endpoint syntax consistently
- **Description**: Validate endpoint syntax consistently.
- **Inputs**: Configured endpoint and redirect targets.
- **Outputs**: Only supported loopback HTTP URLs reach the opener.
- **Behavior**: Allow http and https with existing loopback hosts and an explicit valid port; reject user information, fragments and other schemes. Apply the same syntax restrictions to redirect targets. This is hardening of a mocked probe, not a claim of remote exfiltration. Keep per-call preflight for now; do not add a health cache.

## Structural Decomposition

### Repository Structure

```text
src/engram/client.py
src/engram/query.py
src/engram/cli.py
src/engram/mcp_server.py
tests/_embedding_server.py
tests/test_client.py
tests/test_client_embed.py
tests/test_cli_embedding_errors.py
tests/test_cli_index_status.py
tests/test_query.py
tests/test_mcp_server_search.py
README.md
CHANGELOG.md
```

### Module: Product correction
- **Maps to capability**: Verify the served embedding model before use
- **Responsibility**: Implement the Features in the existing modules; no new public API is required.
- **Location**: `src/engram/client.py`, `src/engram/query.py`, `src/engram/cli.py`, `src/engram/mcp_server.py`
- **Exports**: `preflight`, `EmbeddingEntry`, `query`, `main`

### Module: Verification and guidance
- **Maps to capability**: Verify the served embedding model before use
- **Responsibility**: Prove the regression, preserve compatibility, and explain changed behavior.
- **Location**: `tests/_embedding_server.py`, `tests/test_client.py`, `tests/test_client_embed.py`, `tests/test_cli_embedding_errors.py`, `tests/test_cli_index_status.py`, `tests/test_query.py`, `tests/test_mcp_server_search.py`, `README.md`, `CHANGELOG.md`
- **Exports**: Existing test entry points and user documentation; no runtime exports.

## Dependency Graph

### Foundation Layer (Phase 0)
- **Verification and guidance**: No internal dependencies; establish reproductions and current premises first.
- External prerequisites: None.

### Core Layer (Phase 1)
- **Product correction**: Depends on Phase 0 evidence and the external prerequisites above.

### Integration Layer (Phase 2)
- **Verification and guidance**: Depends on Product correction for final checks and user guidance.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Establish the precise existing failure or documentation premise.

**Tasks**:
- [ ] Add regressions from Critical Scenarios in the listed test files; run each bug regression against old code and record the expected failure once. (no internal deps) - Acceptance: record command, expected failure or premise, and output for each applicable Critical Scenario. Use only planted markers and temporary data.

**Exit Criteria**: Failure evidence or current documentation premises are recorded; no secrets or live stores are involved.

### Phase 1: Core
**Goal**: Deliver the Functional Decomposition.

**Tasks**:
- [ ] Implement the specified behavior in the listed production modules, preserving the stated safety and compatibility rules. (depends on: Phase 0) - Acceptance: uv run --no-sync python -m pytest -q tests/test_client.py tests/test_client_embed.py tests/test_cli_embedding_errors.py tests/test_cli_index_status.py tests/test_query.py tests/test_mcp_server_search.py

**Exit Criteria**: All Critical Scenarios pass; required negative checks fail clearly and preserve data as specified.

### Phase 2: Integration
**Goal**: Verify the complete correction and record its limits.

**Tasks**:
- [ ] Update README and add scoped CHANGELOG entries for the implemented behavior; run the selected tests. (depends on: Phase 1) - Acceptance: review the diff against each Feature, confirm all listed scenarios, and run git diff --check.

**Exit Criteria**: Run the repository main gate once: uv run --no-sync python -m pytest -q --ignore=eval -m "not private". Then run the evaluation gate once: PYTHONPATH=src:. uv run --no-sync python -m pytest -q eval -m "not private". Report deselected private tests explicitly. No real portfolio or live database mutation is permitted.

## Test Strategy

### Critical Scenarios
- A local HTTP fixture echoes the requested wrong ID yet advertises another served ID; indexing and querying fail before storing or sending source text.
- Matching IDs still embed; unavailable/malformed listings fail clearly; startup retries stay bounded; owned-server recycling still works.
- Stored mismatch produces no embed or spawn call, status exits 1, and every affected CLI command emits no traceback.
- User-info and non-HTTP endpoints and redirects are refused; valid HTTP and HTTPS loopback endpoints remain accepted.

### Original QA evidence
Verbatim evidence follows. Mocked observations retain that status; local fixture tests do not turn them into real-server measurements. Isolate fixture setup from the user's actual HOME and store.

````text
2026-11-16 #1
Config set to `id = "acme/other-embed:Q8"` on a port where Qwen was serving: `engram index`, `query`, `index --rebuild` and `harvest` all returned rc 0, and the store meta read `embedding_model_id = acme/other-embed:Q8` with Qwen vectors inside. `GET /v1/models` on the same server reports the true id. The test fake in `tests/_embedding_server.py` answers with its own id, so the tests pass on a belief the real server does not hold. Confidence: confirmed.
2026-11-16 #19
Fake server on the lane port reporting `some/other-model`: `engram index --reembed-code` and `engram query --scope repo "retry backoff"` gave rc 1 with a traceback ending in `EmbeddingModelIdentityError`. `--rebuild`, `harvest` and `pack` handle it in one line. The one-line message also repeats itself: "run `engram index --rebuild`; run `engram index --rebuild` to rebuild the store". Confidence: suspected until finding 1 is fixed and the path can run live.
2026-11-16 #30
`endpoint = "http://evil.invalid@127.0.0.1:18104/v1"` was accepted, and the client then tried to resolve `evil.invalid@127.0.0.1`. `file://localhost:1/etc/hosts`, `ftp://127.0.0.1:1/x` and `gopher://localhost:1/` were accepted; the `file` one tried to open a local path. No route to an attacker-chosen host was seen: the mangled name is not a valid hostname. Confidence: suspected (mocked, and no exploit shown).
2026-11-15 run 2 #5
With the pin changed to nomic: `index --scope repo` rc 1, `query` rc 1 (`vector model 'nomic…'/768 does not match indexed model 'Qwen…'/1024`), and `status --scope repo` printed `prd 2 stale=0 dead=0 / code 6 stale=0 dead=0`, rc 0. The index error also says "run `engram index --rebuild`" twice in one message. Confidence: confirmed.
2026-11-15 run 2 #9
With the pin on nomic, `query` printed the 768/1024 mismatch, rc 1. Then `pgrep` showed pid 2711 `llama-server --embedding -hf nomic-ai/nomic-embed-text-v1.5-GGUF:Q8_0 … --port 18110`. Confidence: confirmed.
````

## Risks

- Aliases must match configuration. Existing poisoned stores cannot be identified from their metadata alone; document rebuilding a store known to have used the wrong server. Do not rewrite the user's live store.
- Requirements are resolved. Implementation must not ask for a preference, touch a real store, or weaken assertions to obtain a pass.
