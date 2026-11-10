# Assumptions ledger (PRD 00011)

## 1: Add plan_migration and MigrationLine in src/engram/migrate.py

- Orchestrator: a file linked as `[[SK_...]]` whose own slug is a credential stops at skip-credential in pass A, so it never enters the rename map; the referring file migrates with the link unrewritten (contract wins over the planner's test instruction).
- Tess: an invalid-target `MigrationError` message names only the failing files.
- Tess: the `slug memory collides with MEMORY.md` check's order relative to the other rule-5 checks is unpinned.
- Tess: an unresolved path such as `repo/sub/..` overlaps the repo root after `resolve()`.
- Tess: index byte and line limits apply to the full would-be `MEMORY.md`, trailing newline included.
- Tess: source files list in plain sorted path order (uppercase before lowercase).
- Ivan: sources are read as bytes then decoded as UTF-8, so `\r\n` in a body survives byte for byte.
- Ivan: rule 5 order is name, description, type, slug pattern, `memory` slug, host path.
- Ivan: the slug check uses `NAME_RE.fullmatch`.
- Ivan: imports the private `_ABSENT` sentinel from `engram.memory` so a missing type matches `_type_violations`.
- Ivan: host-path checks get the original `src`, so `src.absolute()` catches the unresolved form.
- Ivan: the index-limit `MigrationError` message is not passed through `redact` (integers only; Pat LOW).
- Pat (LOW, not fixed, task 1): a directory named `<slug>.md` in the memory dir makes `read_bytes()` raise `IsADirectoryError`; a description with `\r` or ` ` passes the one-line check.

## 2: Add apply_migration, AGENTS_SECTION and repository wiring in src/engram/migrate.py

- Orchestrator: `tests/test_memory_migrate.py` exceeds 800 lines (1054) by accepted exception; the PRD acceptance commands pin it.
- Tess: an empty wiring file (0 bytes) gets just the line or `AGENTS_SECTION`, with no leading newline.
- Tess: `AGENTS_SECTION` says "read `MEMORY.md` before ..." in that word order.
- Tess: apply with an empty source returns `[]`, still writes wiring and an empty `MEMORY.md`.
- Tess: the write order inside each stage (memory files, `MEMORY.md`, wiring) is not part of the contract.
- Ivan: check-failure cause text is "postcondition failed: ..."; non-UTF-8 wiring refusal is "<path>: not UTF-8 text".
- Ivan: restore deletes newly created files and empty directories directly; only original bytes go back through `_write_if_changed`.
- Ivan: new files get `0o666 & ~umask` (umask probed at call time); existing files keep their mode.
- Pat (LOW, not fixed): `_plan_wiring` reads each wiring file twice; a raw `OSError` from pre-write reads escapes as `OSError` rather than `MigrationError` (nothing written yet); task 1 code got formatting-only churn; the umask probe briefly sets the process umask to 0.

## 3: Add engram memory migrate --from --to [--apply] subcommand in src/engram/cli.py

- Ivan: `MigrationError` messages print as-is (already redacted at construction); `OSError` messages go through `redact`.
- Tess: missing `--from`/`--to` exits through argparse's `SystemExit(2)`.
- Tess: in `--apply` mode, skip-only or empty sources return the plan's lines without raising.
