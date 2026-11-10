# Assumptions ledger (PRD 00010)

## 1: Add src/engram/memory.py memory file validator

- Tess: an empty file (no first line) gives `frontmatter\tmissing`.
- Tess: `parse_memory` lists schema violations before credential ones; order among several schema rules in one file is unspecified (multi-rule tests compare sorted lists).
- Tess: an unreadable `MEMORY.md` (bad UTF-8 or a directory) suppresses every index rule, `index-missing-entry` included; per-file violations are still reported.
- Tess: a non-string `name` and a list `source` give `missing`.
- Ivan: `evidence` reports one `item <i>` violation per bad item.
- Ivan: `index-missing-file` is reported once per distinct slug, in file order.
- Ivan: forbidden-key walk tracks only the current container path, so cycles stop; an alias shared in two places is reported once per place.
- Ivan: frontmatter delimiters must be exactly `---` (no trailing spaces).
- Ivan: `type: null` and non-string `type` values give `must be one of feedback, project, reference`.
- Ivan: whole diagnostic lines are redacted rather than each column (no pattern can span a tab).

## 2: Enumerate repository memory and skip shadowed legacy Claude memory in corpora.py

- Tess: legacy project dirs iterate in plain sorted name order; per-repo corpora follow registry row order.
- Tess: a repo with no PRD/decision/discovery dirs yields only its memory files.
- Tess/Ivan: a legacy dir counts for `legacy_shadowed` only when a top-level `*.md` regular file exists (`MEMORY.md` counts; subdirectories are not searched).
- Tess: an empty registry is valid input and yields only `_unmapped` legacy files.

## 3: Add engram memory check [PATH] subcommand in cli.py

- Tess: pytest's `tmp_path` is already resolved, so expected paths match `PATH.resolve()` output.
- Tess: the not-found line for a credential-shaped absent path equals `redact(str(path))` + `\tdirectory\tnot found`.
- Tess: parser errors use argparse's standard stderr text (`invalid choice`, `unrecognized arguments`).
- Tess: `GIT_CEILING_DIRECTORIES=tmp_path` still lets git find a repo whose `.git` sits below the ceiling.

## 4: Add memory invalid and legacy-shadowed lines to engram status

- Tess: the `invalid=` line precedes the `legacy-shadowed=` lines; shadowed lines follow the sorted `corpora.legacy_shadowed` order.
- Tess: "still queryable" is read as "still yielded by enumerate_corpora during status"; no index or query runs in the test.
- Tess: a `MEMORY.md` with index violations counts as one invalid file.
