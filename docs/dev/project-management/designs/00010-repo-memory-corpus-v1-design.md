# Design: Repository memory corpus and validator (PRD 00010)

## Architecture fit

Three existing layers take the work, no new layer:

- **Contract layer (new leaf module).** `src/engram/memory.py` sits beside
  `findings.py`: a pure parser/validator over files on disk, importing only
  stdlib and `yaml` (already a dependency, `pyproject.toml` `pyyaml>=6`, used by
  `findings.py`). It never touches the store, registry, or embedding client, so
  `engram memory check` needs no registry, index, or server (PRD requirement).
- **Enumeration layer.** `src/engram/corpora.py` already owns both memory paths:
  `_enumerate_memory_corpora` (Claude auto-memory, slug-mapped) and
  `_enumerate_repo_corpora` (per-registered-repo corpora). Repository memory is a
  per-repo corpus, so it joins `_enumerate_repo_corpora`; the legacy skip is a
  filter on `_enumerate_memory_corpora`. `corpora.py` already reports side-channel
  facts through module globals (`missing_dirs`), which `cli._run_status` reads
  after calling `enumerate_corpora()`. The two new status facts use the same
  channel, so status does no extra registry read.
- **CLI layer.** `src/engram/cli.py` gains one subcommand (`memory check`) and two
  status lines. Indexing (`indexer.py`), chunking (`chunker.chunk_markdown`), the
  store, and query need **no change**: repository memory files are `CorpusFile`s
  with corpus `"memory"` and are chunked by the existing markdown path; skipped
  legacy rows disappear through the indexer's existing prune of sources not seen
  this run (`store.prune(scope, corpus, active_sources)`).

Capsule invariants honored: no rebuild, no model change, index commits per file,
read failures retried (an unreadable memory file is reported by `hash_source`
`OSError` as a failed source exactly like other corpora).

## Module placement

| Path | Kind | Change |
|------|------|--------|
| `src/engram/memory.py` | new | `MemoryFile`, `parse_memory`, `check_directory`, `memory_dir`, `memory_files`, constants |
| `src/engram/corpora.py` | edit | yield repository memory in `_enumerate_repo_corpora`; legacy skip in `_enumerate_memory_corpora`; new globals `repo_memory_dirs`, `legacy_shadowed`; slug mapping extracted into `_unique_slugs` |
| `src/engram/cli.py` | edit | `memory check` parser + `_run_memory_check`; status lines in `_run_status`; dispatch in `main` |
| `tests/test_repo_memory.py` | new | every scenario in PRD Test Strategy |
| `tests/test_cli_index_status.py` | edit | autouse fixture also resets `corpora.repo_memory_dirs` and `corpora.legacy_shadowed` to fresh empty lists |
| `README.md` | edit | memory corpus row lists both sources; new "Repository memory" section |

`tests/test_memory_attribution.py` is **not edited**; it must pass unchanged.

## Interfaces & contracts

### `src/engram/memory.py`

```python
from dataclasses import dataclass
from pathlib import Path

MEMORY_SUBDIR: tuple[str, ...] = ("docs", "dev", "project-management", "memory")
INDEX_NAME = "MEMORY.md"
INDEX_MAX_LINES = 200
INDEX_MAX_BYTES = 25_000
ALLOWED_TYPES = frozenset({"project", "feedback", "reference"})
FORBIDDEN_KEYS = ("author", "date")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
INDEX_ENTRY_RE = re.compile(r"^- \[(?P<title>[^\]]*)\]\((?P<slug>[^()/\s]+)\.md\)")
CREDENTIAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github-token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("github-pat", re.compile(r"github_pat_[A-Za-z0-9_]{22,}")),
    ("sk-key", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
)
```

One deliberate amendment to the PRD's literal patterns, and only one: `sk-`
must not follow an ASCII letter or digit (`(?<![A-Za-z0-9])`). Unanchored, it
matches inside ordinary hyphenated words (`task-tools-flag-until-...`,
`risk-...`, `disk-...`); dispatch-1 review measured 3 such false hits in the
real legacy memory corpus PRD 00011 migrates, which would make valid memories
fail `memory check` and status. A key after space, quote, `=`, `:`, `-`, `_`,
`/` or line start still matches. The other five patterns stay byte-identical
to the PRD (no measured false positives; anchoring them would only narrow
detection). Tests pin both sides: `task-tools-flag-until-something` clean,
`sk-` + 20 chars at line start and after `key=` flagged.

```python
def redact(text: str) -> str:
    """Replace every CREDENTIAL_PATTERNS match in text with '[redacted:<label>]'.
    Applied to every detail string and every <file> column before it leaves
    parse_memory/check_directory, so no diagnostic can carry a token (a
    credential-shaped slug in a MEMORY.md entry or a file name included)."""
```

```python


@dataclass(frozen=True)
class MemoryFile:
    slug: str            # file stem
    name: str
    description: str
    type: str            # one of ALLOWED_TYPES (resolved from top-level or metadata.type)
    source: str
    evidence: tuple[str, ...]
    body: str            # text after the closing '---' line


def memory_dir(repo_root: Path) -> Path:
    """repo_root / docs/dev/project-management/memory (no existence check)."""


def memory_files(directory: Path) -> list[Path]:
    """Sorted regular files matching '*.md' directly in directory, excluding
    MEMORY.md. [] when directory is not a directory."""


def parse_memory(path: Path) -> tuple[MemoryFile | None, list[str]]:
    """Return (record, violations). record is None iff violations is non-empty.
    Each violation string is '<rule>\t<detail>'."""


def check_directory(path: Path) -> list[str]:
    """All violations for one memory directory, each '<file>\t<rule>\t<detail>',
    where <file> is str(path / filename). Order: per-file violations for each
    file in memory_files(path) order (schema first, then credential), then
    MEMORY.md violations (credential, then index rules in the order listed
    below). Not a directory -> [f'{path}\tdirectory\tnot found']."""
```

Violation rules (the `<rule>` column; exact strings, consumed by PRD 00011 and
tests):

| rule | raised when | detail (exact form) |
|------|-------------|---------------------|
| `read` | `OSError`/`UnicodeDecodeError` reading the file | `unreadable: <exc class name>` |
| `frontmatter` | first line is not `---`, no closing `---` line, YAML error, or the YAML is not a mapping | `missing`, `unterminated`, `unparseable`, `not a mapping` |
| `name` | key absent/not a string, not matching `NAME_RE`, or not equal to the file stem | `missing`, `must match ^[a-z0-9][a-z0-9-]*$`, `does not match file stem <stem>` |
| `description` | absent, not a string, empty after strip, or contains `\n` | `missing`, `empty`, `must be one line` |
| `type` | top-level `type` absent and `metadata.type` absent; value not in `ALLOWED_TYPES`; value `user` | `missing`, `must be one of feedback, project, reference`, `user memory belongs in host-global memory` |
| `source` | absent, not a string, or empty after strip | `missing`, `empty` |
| `evidence` | absent, not a list, empty list, or any item not a non-empty (after strip) string | `missing`, `must be a list`, `empty`, `item <i> empty or not a string` |
| `forbidden-key` | a key named `author` or `date` at any depth of the frontmatter (top level, nested mappings, and mappings inside lists; one violation per occurrence) | `<dotted path>: Git records it`, e.g. `author: Git records it`, `metadata.date: Git records it`, `evidence.0.author: Git records it` |
| `credential` | a `CREDENTIAL_PATTERNS` regex matches anywhere in the full file text (one violation per matching label) | `<label>` only — the matched text is **never** included |
| `index-missing-file` | a `MEMORY.md` entry names `<slug>.md` that is not in `memory_files` | `<slug>.md` |
| `index-missing-entry` | a memory file has no `MEMORY.md` entry (also every file when `MEMORY.md` is absent) | `<slug>.md` |
| `index-duplicate` | a slug appears in more than one entry (one violation per duplicated slug) | `<slug>.md` |
| `index-unsorted` | entry slugs (in file order, duplicates included) differ from `sorted(...)` of themselves | `entries must be sorted by slug` |
| `index-too-long` | `len(text.splitlines()) > INDEX_MAX_LINES` | `<n> lines > 200` |
| `index-too-large` | `len(raw bytes) > INDEX_MAX_BYTES` | `<n> bytes > 25000` |
| `directory` | `check_directory` path is not a directory | `not found` |

Schema rules:

- `type` resolution: if top-level `type` key is present, it alone is validated
  (even if invalid); otherwise `metadata.type` is used when `metadata` is a mapping
  containing `type`.
- Schema checks run only when frontmatter parsed to a mapping; a `frontmatter`
  or `read` violation suppresses the field checks for that file. The credential
  check runs whenever the text was readable, regardless of frontmatter.
- Unknown extra keys (including `metadata` itself) are allowed.
- Index-rule violations use `<file>` = `str(path / "MEMORY.md")` for
  `index-missing-file`, `index-duplicate`, `index-unsorted`, `index-too-long`,
  `index-too-large`; `index-missing-entry` uses the memory file's own path.
  `MEMORY.md` absent: no `MEMORY.md` violations except `index-missing-entry` per
  memory file. `MEMORY.md` is also credential-scanned when present.
- **No field value is ever echoed** in a detail string (only the file stem in
  `does not match file stem <stem>` and slugs in index details). Every detail
  and `<file>` column passes through `redact()` as the final step, so PRD Test
  Strategy's "token value never appears in output" holds even for a token in
  `name`, `type`, a file name, or a `MEMORY.md` entry slug.
- `parse_memory` includes `credential` violations (raw full-text scan), so a
  file holding a token never returns a record. `check_directory` scans
  `MEMORY.md` with the same private helper `_credential_violations(text) -> list[str]`
  (returns `credential\t<label>` strings, one per matching label).
- Lines of `MEMORY.md` not matching `INDEX_ENTRY_RE` (headings, blanks, prose)
  are ignored. `INDEX_ENTRY_RE` is a prefix match (`re.match`), so Claude-style
  trailing ` — hook` text is allowed.

### `src/engram/corpora.py`

```python
from engram.memory import memory_dir, memory_files

missing_dirs: list[str] = []                      # unchanged
repo_memory_dirs: list[tuple[str, Path]] = []     # NEW: (repo name, memory dir) for every registered repo whose memory dir is a directory
legacy_shadowed: list[str] = []                   # NEW: repo names with repository memory AND a legacy Claude memory dir holding >=1 *.md file


def _unique_slugs(rows: list[tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """slug -> (repo_path, name) for slugs produced by exactly one distinct
    (repo_path, name) row. Extracted verbatim from enumerate_corpora's current
    slug_to_rows/slug_to_name logic (same regex [^a-zA-Z0-9] -> '-')."""


def _enumerate_memory_corpora(
    projects_dir: Path,
    slug_to_name: dict[str, str],
    skip_slugs: frozenset[str] = frozenset(),
) -> Iterator[CorpusFile]:
    """Unchanged, except project dirs whose name is in skip_slugs yield nothing."""


def _enumerate_repo_corpora(root: Path, name: str) -> Iterator[CorpusFile]:
    """Unchanged PRD/decision/discovery behavior, plus, after discovery:
    for each p in memory_files(memory_dir(root)): yield CorpusFile("memory", name, p).
    An absent memory dir appends nothing to missing_dirs. When memory_dir(root)
    is a directory, append (name, memory_dir(root)) to repo_memory_dirs."""


def enumerate_corpora(
    repos_csv: Path = GITA_REPOS_CSV,
    projects_dir: Path = CLAUDE_PROJECTS_DIR,
) -> Iterator[CorpusFile]:
    """Signature unchanged. Clears missing_dirs, repo_memory_dirs, legacy_shadowed
    in place on first iteration. skip_slugs = {slug for slug, (path, _) in
    _unique_slugs(rows).items() if memory_files(memory_dir(Path(path)))}.
    For each skipped slug whose projects_dir/<slug>/memory holds >=1 '*.md' file
    (MEMORY.md counts), append its repo name to legacy_shadowed (deduped, sorted).
    Then yields legacy memory (with skip_slugs), then per-repo corpora."""
```

Paths yielded for repository memory are `memory_dir(Path(repo_path)) / filename`
unresolved, matching how the other per-repo corpora are yielded (legacy memory
keeps its existing `.resolve()`).

Invalid memory files are still yielded (indexed); validation never gates indexing.

### `src/engram/cli.py`

```python
# _build_parser additions
memory_parser = subparsers.add_parser("memory")
memory_sub = memory_parser.add_subparsers(dest="memory_command", required=True)
check_parser = memory_sub.add_parser("check")
check_parser.add_argument("path", nargs="?", type=Path, default=None)

def _run_memory_check(args: argparse.Namespace) -> int: ...

# main(): before the final `return _run_status(args)`
if args.command == "memory":
    return _run_memory_check(args)
```

`_run_memory_check` contract:

1. `args.path is None` → `git rev-parse --show-toplevel` with `cwd=Path.cwd()`
   (same call shape as `_resolve_pack_repo`); non-zero exit → print
   `engram memory check: not inside a git worktree; pass PATH` to stderr, return 1.
   Target = `memory_dir(Path(stripped stdout))`, always.
2. Explicit PATH: `resolved = PATH.resolve()`; target = `resolved` when
   `resolved.parts[-len(MEMORY_SUBDIR):] == MEMORY_SUBDIR` (it already is a
   memory directory, including `.` from inside one, with or without
   `MEMORY.md`); otherwise `memory_dir(resolved)` (a repository root, including
   a repository whose own name is `memory`). The memory directory location is
   fixed by the contract, so the path itself decides; no file sniffing. A repo
   root without a memory dir, or any unrelated directory, yields the single
   `directory\tnot found` line rather than validating README.md and friends.
3. `lines = check_directory(target)`; print each line to stdout; return
   `1 if lines else 0`. Never opens the store, config, registry, or embedding server.

`_run_status` addition, placed after the `code\texcluded=` block and before
`_print_missing(corpora.missing_dirs, scope)`:

```python
in_scope = lambda name: scope.kind == "portfolio" or name == scope.repo
invalid = len({
    line.split("\t", 1)[0]
    for d in {d for name, d in corpora.repo_memory_dirs if in_scope(name)}
    for line in check_directory(d)
})
if invalid > 0:
    print(f"memory\tinvalid={invalid}")
    exit_code = 1
for name in corpora.legacy_shadowed:
    if in_scope(name):
        print(f"memory\tlegacy-shadowed={name}")
```

(`in_scope` written as a nested `def` in the implementation.) Directories and
file paths are deduplicated, so duplicate registry rows never double-count.
`n` = number of distinct `<file>` values with at least one violation across in-scope repository
memory directories. `legacy-shadowed` never changes the exit code.

## Data flow

1. **Index:** `indexer.index` → `enumerate_corpora()` → per registered repo,
   `_enumerate_repo_corpora` yields `CorpusFile("memory", <repo>, <file>)` for each
   repository memory file → existing hash/chunk(`chunk_markdown`)/embed/upsert path.
   Legacy Claude dirs whose slug maps to a repo with repository memory yield
   nothing → their old rows are absent from `active_sources` → `store.prune`
   deletes them on the next incremental index of a scope that includes that repo
   (repo scope filters by `f.repo`, and legacy rows were attributed to that same
   repo name, so a repo-scoped index also prunes them).
2. **Check:** `engram memory check [PATH]` → `_run_memory_check` → resolve target →
   `memory.check_directory` → `memory_files` + `parse_memory` per file + index
   checks on `MEMORY.md` → lines to stdout → exit 0/1.
3. **Status:** `_run_status` → existing `list(enumerate_corpora())` populates
   `corpora.repo_memory_dirs` / `corpora.legacy_shadowed` as a side effect →
   scope filter → `check_directory` per in-scope dir → `memory\tinvalid=` and
   `memory\tlegacy-shadowed=` lines.

## Reuse inventory

- `src/engram/corpora.py:enumerate_corpora` slug mapping (`re.sub(r"[^a-zA-Z0-9]", "-", repo_path)` + collision set): extracted into `_unique_slugs` and reused for the skip set; behavior unchanged.
- `src/engram/corpora.py:missing_dirs` global side channel read by `cli._run_status`: same pattern for `repo_memory_dirs`, `legacy_shadowed`.
- `src/engram/findings.py:parse` frontmatter split (`lines[0] != "---"`, `lines.index("---", 1)`, `yaml.safe_load`): same approach in `parse_memory` (not imported; findings' version raises on its own reviewer rules).
- `src/engram/chunker.py:chunk_markdown` via `indexer._chunk_file` default branch: chunks repository memory with no change.
- `src/engram/store.py:Store.prune` / `prune_empty_sources` via `indexer.index`: removes skipped legacy rows; no new code.
- `src/engram/cli.py:_resolve_pack_repo` `git rev-parse --show-toplevel` call shape: copied for the default PATH.
- `tests/test_memory_attribution.py` fixture pattern (`partial(enumerate_corpora, registry, projects)` patched into `engram.indexer`, fake embed): reused for the fixture-portfolio index test.
- `agent-skills/skills/distil-memory/scripts/test_proposal.py` (portfolio): another memory-file validator exists outside this repo; not importable here (different repo, script not a package). Nothing reused; schemas kept compatible (Claude `metadata.type` accepted).
- Credential scanning: greps `rg -n "secret|credential|ghp_|PRIVATE KEY|redact" src/engram` found nothing; control grep `rg -n "yaml" src/engram` hits `findings.py`, proving the search works. New code.

## Alternatives considered

1. **Smallest diff: validate inside `corpora.py`, status reads registry itself.**
   No new module; status re-reads `GITA_REPOS_CSV`. Rejected: mixes the contract
   (consumed by PRD 00011's migrate command) into enumeration, and a second
   registry read in status would hit the real `~/.config/gita/repos.csv` in every
   existing status test that stubs only `enumerate_corpora`, failing under CI's
   empty `HOME`.
2. **Chosen: leaf `memory.py` + side-channel globals in `corpora.py`.** One new
   module the PRD already names; status gets its facts from the enumeration it
   already runs, consistent with `missing_dirs`. Extra size over (1) is the
   separate module (~150 lines), which buys a registry-free `memory check` and a
   reusable contract for PRD 00011.
3. **Structured `Violation` dataclass instead of tab-joined strings.** Cleaner
   typing, but the PRD fixes `parse_memory` as returning `list[str]`, and the
   CLI output is exactly the tab-joined line, so strings avoid a translation
   layer. Rejected to stay on the PRD contract.

## Risks & edge cases

- **Module-global pollution across tests.** `repo_memory_dirs`/`legacy_shadowed`
  persist after a test calls the real `enumerate_corpora`; a later status test that
  stubs `enumerate_corpora` would read stale entries (and `check_directory` on a
  deleted tmp dir reports `directory\tnot found` → spurious `invalid=1`). Mitigation:
  `tests/test_cli_index_status.py` autouse fixture and every new test that calls
  the real enumeration monkeypatch both globals to fresh lists. `tests/test_backlog_delivery.py`
  status tests stub `enumerate_corpora` without resetting globals; new tests in
  `test_repo_memory.py` must use `monkeypatch.setattr(corpora, "repo_memory_dirs", [])`
  and the same for `legacy_shadowed` so mutation lands on a restored object.
- **Slug collisions:** colliding slugs are absent from `_unique_slugs`, so their
  legacy dirs are never skipped and stay `_unmapped` (PRD requirement).
- **Index-only directory** (only `MEMORY.md`): `memory_files` is empty → no skip,
  but the dir is still in `repo_memory_dirs`, so stale index entries are reported.
- **YAML coercion:** `date: 2026-11-10` parses to `datetime.date`; it is still a
  `forbidden-key` violation (key check, not value). `name: 123` → `name\tmust match ^[a-z0-9][a-z0-9-]*$`.
- **Credential match in YAML-invalid file:** still reported (credential runs on raw text).
- **Symlinked memory files:** `memory_files` uses `is_file()` (follows symlinks);
  out-of-repo symlink targets are read. Accepted: memory dirs are agent-authored
  inside the repo; not a trust boundary in this PRD.
- **Status cost:** `check_directory` reads every repository memory file on each
  status call; ~160 files portfolio-wide today, negligible.
- **Likely next changes:** (a) PRD 00011 `memory migrate` writes files that must
  pass `check_directory` — it can call `parse_memory`/`check_directory` directly;
  (b) a `--json` output mode for `memory check`; (c) blind-role recall exclusion
  (agent-plugins intake 00065) filtering corpus `memory` at query time. None is
  boxed in: rules are plain strings, the module is store-free, and corpus name
  `memory` is shared by both sources so a query-time filter covers both.

## Test strategy outline

All in `tests/test_repo_memory.py`, fixtures built under `tmp_path`; test names
carry the `-k` selectors the PRD acceptance uses (`schema`, `index`, `credential`,
`enumerat`, `legacy`, `cli_check`, `status`).

- **schema:** a valid file parses; one failing fixture per rule row (`frontmatter`
  missing/unterminated/unparseable/not-a-mapping, `name` missing/invalid/stem
  mismatch, `description` empty/multiline, `type` missing/invalid/`user`, `source`,
  `evidence` missing/not-list/empty/blank item, `forbidden-key` author and date),
  `metadata: {type: feedback}` accepted, unknown keys allowed.
- **index:** sorted complete index clean; missing file, missing entry, absent
  `MEMORY.md`, duplicate, unsorted, 201 lines, >25,000 bytes, non-entry lines
  ignored, trailing ` — hook` accepted.
- **credential:** one fixture per pattern; assert the rule and label appear and
  the token text does not appear in any returned string; a token placed in
  `name`, a file name, or a `MEMORY.md` entry slug is not echoed either
  (`[redacted:<label>]`); `task-tools-flag-until-something` is clean, while
  `sk-` + 20 chars at line start and after `key=` still match.
- **schema (forbidden-key depth):** `metadata: {date: ...}` and an `author`
  inside a list item mapping each yield `forbidden-key` with the dotted path.
- **status (dedupe):** two registry rows for the same path with one invalid
  file → `memory\tinvalid=1`.
- **enumerat / legacy:** attribution to repo name; `MEMORY.md` excluded; absent
  dir adds nothing to `missing_dirs`; populated dir skips the legacy slug and sets
  `legacy_shadowed`; index-only dir does not skip; colliding slugs stay `_unmapped`;
  fixture-portfolio incremental index (fake embed, real store in `tmp_path`) holds
  repository memory rows and, after adding repository memory, prunes the legacy rows.
- **cli_check:** clean dir exit 0 with no output; each invalid fixture exit 1 with
  file and rule printed; absent dir exit 1; explicit repo root, explicit memory
  dir, `.` from inside an index-less memory dir, and a repo whose root is named
  `memory` each resolve correctly; default path via a `git init` tmp repo
  and `monkeypatch.chdir`; store/config refused (`_refuse`) to prove no dependency.
- **status:** invalid file → `memory\tinvalid=1`, exit 1; legacy-shadowed only →
  line printed, exit 0; repo scope filters out other repos.
- Regression: `tests/test_memory_attribution.py` unchanged and passing; full
  `.venv/bin/python -m pytest -q --ignore=eval`.

## Review log

dispatch 1 (claude): cardinal-sin 0, blocker 1, non-blocker 4, question 2
- fixed (blocker): `sk-` pattern matched inside hyphenated words; all token prefixes now left-anchored (PRD amendment recorded in Interfaces).
- fixed (raised from non-blocker, violates PRD "token never appears in output"): `name`/`type` details no longer echo values.
- non-blocker: `memory check PATH` on a non-root, non-memory dir validates that dir itself (e.g. `docs/`) and reports misleading violations; consider targeting `memory_dir(PATH)` unless PATH holds `MEMORY.md` or is named `memory`.
- non-blocker: global reset lives only in `test_cli_index_status.py`; a `tests/conftest.py` autouse fixture resetting `missing_dirs`, `repo_memory_dirs`, `legacy_shadowed` would cover all status tests.
- non-blocker: no stated rollback for pruned legacy rows; rollback = revert code or empty repo memory dir, then `engram index --scope portfolio --corpus memory` (legacy files stay on disk; rows are derived).
- question: does `parse_memory` include credential violations (so a token file never returns a record), and what helper scans `MEMORY.md`?
- question: unpinned detail details: evidence `<i>` base, newline check vs strip for folded YAML, non-string description/source → `missing` or `empty`, `read` rule on unreadable `MEMORY.md`, whether `metadata.date` counts as forbidden.
dispatch 2 (codex): cardinal-sin 0, blocker 3, non-blocker 2, question 0
- note: first codex attempt could not read files (nested sandbox `sandbox_apply: Operation not permitted`); re-run with all inputs inlined succeeded. A Claude fallback was started on a misread of the partial output and stopped unused once codex finished.
- fixed (blocker): credential-shaped slugs could leak through index details; all details and file columns now pass through `redact()`.
- fixed (blocker): `forbidden-key` now covers `author`/`date` at any depth (PRD "any author or date key"); also answers dispatch-1's `metadata.date` question.
- fixed (blocker): credential amendment narrowed to the one measured false positive: only `sk-` keeps a left boundary; the other five patterns are byte-identical to the PRD. Tests pin both sides.
- fixed (non-blocker, trivial contract correction): status `invalid` now unions dirs and files across registry rows, so duplicate rows never double-count.
- fixed (non-blocker, also covers dispatch-1's PATH non-blocker): default PATH always targets `memory_dir(git root)`; explicit PATH is a memory dir only when named `memory` or holding `MEMORY.md`, else `memory_dir(PATH)`.
dispatch 3 (codex): cardinal-sin 0, blocker 1, non-blocker 2, question 0
- fixed (blocker): explicit PATH heuristic misread a repo named `memory` and `.` inside an index-less memory dir; target is now decided by whether the resolved path ends with `MEMORY_SUBDIR`.
- non-blocker: nested forbidden-key traversal over `yaml.safe_load` output can recurse forever on cyclic YAML aliases; track container ids on the current path.
- non-blocker: status counts distinct redacted file columns, so two credential-shaped filenames that redact identically count once; dedupe on raw paths before redacting (edge case, credential-named files already fail).
