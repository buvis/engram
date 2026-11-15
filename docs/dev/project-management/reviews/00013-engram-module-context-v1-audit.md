# Decision Audit Log: 00013-engram-module-context-v1

PRD: `00013-engram-module-context-v1.md`
Started: 2026-11-15T21:52:59Z
Completed: 2026-11-15T21:52:59Z
Autonomous: 5  |  Deferred: 0  |  Doubts: 0

### [autonomous] 2026-11-15T21:52:59Z

**Decision**: Design for PRD 00013; design review blocker: unrestricted rule would index every symbol-less data/doc file (markdown, json, yaml) as a whole-file chunk

**Choice**: Line-set complement inside symbols.chunk plus doc_type filter in Store.lookup_by_name, indexer unchanged; symbol-less files gain context only for the CONTEXT_LANGUAGES allowlist; PRD amended

**Rationale**: User chose code-only scope via AskUserQuestion on 2026-11-15; remaining non-blockers recorded in the design Review log

### [autonomous] 2026-11-15T21:52:59Z

**Decision**: Form-feed and other Unicode line separators (\x0c, \x0b, \x1c-\x1e, \x85, U+2028, U+2029) break the "every nonblank line once" guarantee. `chunk` splits with `str.splitlines()` (src/engram/symbols.py:114), but tree-sitter counts lines at \n only, so the parser's spans and `lines[]` indexes disagree. I ran `chunk` on `import os\n\x0c\nX = 1\n\ndef f():\n    return 2\n\nTAIL = 3\n`. The function chunk came out as lines 5-6 with body '\ndef f():'. The tail context chunk came out as lines 7-9 with body '    return 2\n\nTAIL = 3'. The file has only 8 \n lines, so 9 is past the end. `return 2` appears in the tail chunk and is missing from the function chunk, and the context line numbers point past the end of the file. The skewed symbol bodies already existed in the code. The new gap logic turns them into duplicated or misattributed context lines and wrong line_start/line_end values. Form feeds do occur in GNU C and older Python sources. The fix is to split on \n only, for example `source.split("\n")` with CRLF handling. A test with a form-feed fixture would catch it.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-15T21:52:59Z

**Decision**: `_context_chunks` builds a list of line numbers per run, then filters it again for non-blank lines (`runs: list[list[int]]`, then `kept`). One pass would do: track the run start and the first and last non-blank line, and emit when a covered line or EOF ends the run. Same output, no per-run int lists. Behavior-preserving, so Medium.

**Choice**: auto-fixed

**Rationale**: fixed by review-close

### [autonomous] 2026-11-15T21:52:59Z

**Decision**: R1 splitlines vs tree-sitter line skew on form feeds and Unicode separators (src/engram/symbols.py:114)

**Choice**: fix in rework task 4 (sonnet)

**Rationale**: cycle 1 decision gate: confirmed by reading the code; one-line split change plus regression test, no API or data-model change, so auto-fix

### [autonomous] 2026-11-15T21:52:59Z

**Decision**: R3-R9 single-voice medium/low findings

**Choice**: discarded to the settled-decisions ledger

**Rationale**: cycle 1 decision gate: single-voice Medium/Low rule; Carl unavailable (copilot model rejected, native gemini IneligibleTierError)
