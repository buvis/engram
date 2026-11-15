# Decision Audit Log: 00012-agent-recall-surfaces-v1

PRD: `00012-agent-recall-surfaces-v1.md`
Started: 2026-11-15T19:50:33Z
Completed: 2026-11-15T19:50:33Z
Autonomous: 4  |  Deferred: 0  |  Doubts: 0

### [autonomous] 2026-11-15T19:50:33Z

**Decision**: design approach for 00012 agent recall surfaces

**Choice**: mcp_server.py owns search_pointers and format_pointer_lines (shared with engram query); nudge.py imports mcp_server; cli.py dispatches both; in-process query, stdlib only

**Rationale**: 2 design dispatches (claude, claude-fallback after codex nested-sandbox read failure); 0 cardinal sins, 0 blockers; 19 non-blockers and 8 questions in design Review log, correctness ones adopted into task contracts at planning

### [autonomous] 2026-11-15T19:50:33Z

**Decision**: planning 00012: task order and adopted design review non-blockers

**Choice**: 4 tasks: mcp_server (1) before nudge (2, imports search_pointers), cli (3), docs+spike delete (4); adopted into Details: shlex newline/comment/operator handling, lexists .git probe, expandvars, cwd normalization and outside-repo broadness, store close, RecursionError parse guard, stdin errors=replace, extra isError types, gita-aware RepoScopeError text, stdout flush, __main__ block, env cleanup in CLI tests, real search_pointers test

**Rationale**: PRD lists nudge and mcp_server as independent; design layering makes nudge depend on mcp_server. Adopted items are cheap correctness fixes that would otherwise surface as review findings; PRD behavior unchanged

### [autonomous] 2026-11-15T19:50:33Z

**Decision**: 8 single-voice medium/low findings (R2,R3,R4,R6,R7,R8,R9,R10) discarded per the single-voice rule; recorded in the settled-decisions ledger

**Choice**: discard

**Rationale**: Consensus cell [1/4] on every one; the single-voice Medium/Low rule discards rather than tasks them, and the ledger auto-dismisses a re-raise next cycle

### [autonomous] 2026-11-15T19:50:33Z

**Decision**: New behavior in `main`, the `sys.stdin.reconfigure(errors="replace")` call in the `mcp` branch, has no test. Both CLI tests replace stdin with `StringIO` or `_LiveStdin`, neither of which has `reconfigure`, so the branch never runs. Add one test that feeds `cli.main(["mcp"])` an `io.TextIOWrapper` over invalid UTF-8 bytes and asserts the ping reply plus a -32700 reply for the bad line. Bob raises the same defect as R5 (tests/test_mcp_server.py:627): add a TextIOWrapper over invalid UTF-8 bytes followed by a valid ping, and assert error recovery and continued serving.

**Choice**: auto-fixed

**Rationale**: fixed by review-close
