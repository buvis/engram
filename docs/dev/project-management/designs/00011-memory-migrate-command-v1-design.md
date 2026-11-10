# Design: 00011-memory-migrate-command-v1

PRD: `docs/dev/project-management/prds/wip/00011-memory-migrate-command-v1.md`

## Architecture fit

Engram is a standalone uv-managed Python CLI (`src/engram/`). PRD 00010 added the
repository-memory layer in `src/engram/memory.py` (schema validator, index check,
credential guard) and the `engram memory check` subcommand in `src/engram/cli.py`
(`_add_memory_parser`, `_run_memory_check`). This PRD adds a sibling module
`src/engram/migrate.py` that sits on top of `memory.py` (one-way dependency:
`migrate -> memory`), and one more `memory` subcommand in `cli.py`. No store, index,
embedding, or corpus code is touched. The command is pure filesystem I/O on two
caller-named directories; it never runs git, never commits, never pushes.

## Module placement

- **New** `src/engram/migrate.py`: `MigrationLine`, `MigrationError`,
  `AGENTS_SECTION`, `plan_migration`, `apply_migration`, private helpers
  (`_slug`, `_convert`, `_render`, `_render_index`, `_plan_wiring`, `_write_if_changed`).
- **Edit** `src/engram/cli.py`: `_add_memory_parser` gains a `migrate` subparser;
  new `_run_memory_migrate`; `main()` dispatches on `args.memory_command`.
- **Edit** `src/engram/memory.py`: none. `migrate.py` imports the module-private
  `_split_frontmatter` and `_credential_violations` (same package; making them
  public would be churn with no second caller).
- **New** `tests/test_memory_migrate.py`: every Test Strategy scenario.
- **Edit** `README.md`: new `## Migrating Claude auto-memory` section after
  `## Repository memory`.

## Interfaces & contracts

### `src/engram/migrate.py`

```python
ACTIONS = ("migrate", "skip-user", "skip-credential", "skip-invalid",
           "skip-exists", "skip-identical")
OK_ACTIONS = frozenset({"migrate", "skip-identical"})
EVIDENCE_PLACEHOLDER = "none recorded before migration"
SOURCE_PREFIX = "migrated:claude-auto-memory/"
GITATTRIBUTES_LINE = "docs/dev/project-management/memory/MEMORY.md merge=union"
CLAUDE_IMPORT_LINE = "@docs/dev/project-management/memory/MEMORY.md"
AGENTS_HEADING = "## Project memory"
AGENTS_SECTION: str  # starts with AGENTS_HEADING + "\n", ends with "\n", <= 25 lines

@dataclass(frozen=True)
class MigrationLine:
    file: str     # source file NAME only (e.g. "feedback_foo.md"), never a path
    action: str   # one of ACTIONS
    detail: str   # one line
    def tsv(self) -> str: ...
    # memory.redact(f"{clean(file)}\t{action}\t{clean(detail)}"), where clean()
    # replaces "\t", "\r", "\n" with " ". Redaction covers the file name too, so
    # a credential-bearing file name never prints. Every MigrationError message
    # is built with memory.redact as well.

class MigrationError(Exception): ...  # refusal before any write (CLI -> exit 1)

def plan_migration(src: Path, repo_root: Path) -> list[MigrationLine]: ...
def apply_migration(src: Path, repo_root: Path) -> list[MigrationLine]: ...
```

`plan_migration` writes nothing (no directory creation either). It resolves
`src` and `repo_root` once at entry (`Path.resolve()`). Raises `MigrationError`
(the dry run reports it the same way apply does) when:

- `src` or `repo_root` is not a directory;
- **overlap**: `src` equals any directory apply writes into:
  `repo_root`, `memory_dir(repo_root)`, or `repo_root / ".claude"` (all resolved).
  Only direct children of `src` are read, so equality is the full overlap test;
- **source alias**: any `p.resolve()` for `p` in `memory_files(src)` lies inside
  `repo_root` (a symlinked source would see apply's writes);
- **invalid target state**: any existing file in `memory_files(memory_dir(repo_root))`
  fails `memory.parse_memory`, or its index line or whole text satisfies
  `contains_host_path` (message lists the files, details redacted). Existing
  files flow into `MEMORY.md`, so they get the same final-output safety check
  as migrated ones;
- **index limits**: the would-be `MEMORY.md` (existing valid files plus every
  `migrate` file) exceeds `memory.INDEX_MAX_LINES` lines or
  `memory.INDEX_MAX_BYTES` bytes.

These three refusals guarantee that a successful apply leaves a directory
`memory.check_directory` reports clean.
`apply_migration` returns exactly the lines `plan_migration` returns for the same
input state, and raises `MigrationError` (having written nothing) when
`plan_migration` would raise or `.claude/settings.json` exists and is not valid
JSON or not a JSON object.

**Source files**: `memory.memory_files(src)` (sorted regular `*.md`, excluding
`MEMORY.md`). One `MigrationLine` per file, in that order. Nothing else in `src`
is read.

**Slug**: `stem.lower().replace("_", "-")`.

**Classification** runs in two deterministic passes. **Pass A** applies rules
1-8 below to each source file, first matching rule wins, using only the source
text and the generated frontmatter (never the link-rewritten body). The rename
map (see Link rewriting) is built once from pass A's results. **Pass B** renders
every pass-A `migrate`/`skip-identical`/`skip-exists` file with link rewriting
and its index line, then re-scans that final text: a credential pattern hit
downgrades the line to `skip-credential` (labels only); a host-path hit
downgrades it to `skip-invalid` `"contains an absolute host path"`. Rule 7's
identical/exists comparison uses the pass-B render. The rename map is never
recomputed after pass B, so pass B cannot change its own input; a link to a
downgraded file stays rewritten and dangles (logged as a known limit).

Detail text in quotes:

1. Read fails (`OSError`/`UnicodeDecodeError`) -> `skip-invalid`, `"unreadable"`.
2. `memory._split_frontmatter` reports a problem -> `skip-invalid`,
   `"frontmatter <problem>"`.
3. Type is `type`, else `metadata.type` (when `metadata` is a dict). Type `== "user"`
   -> `skip-user`, `"user memory stays in host-global memory"`.
4. Any `memory.CREDENTIAL_PATTERNS` pattern matches the whole source text, the
   source file name, or the generated frontmatter (slug, `source` value) ->
   `skip-credential`, the matching labels joined by `,` (labels only, e.g.
   `"github-token"`; never the matched text). Labels come from iterating
   `CREDENTIAL_PATTERNS` directly, not from `_credential_violations` (whose
   strings contain a tab).
5. Field validity -> `skip-invalid` with the first failing detail:
   - `name` not a non-empty string -> `"name missing"`;
   - `description` not a string, blank, or multi-line after strip ->
     `"description missing"` / `"description empty"` / `"description must be one line"`;
   - type missing or not in `memory.ALLOWED_TYPES` -> `"type missing"` /
     `"type must be one of feedback, project, reference"`;
   - slug fails `memory.NAME_RE` -> `"slug <slug> must match ^[a-z0-9][a-z0-9-]*$"`;
   - `contains_host_path(text, src)` is true for the source description or the
     source body (pre-rewrite) -> `"contains an absolute host path"`.

     ```python
     HOST_PATH_RE = re.compile(
         r"(?<![\w.:/~-])/(?:Users|home|root|private|tmp|var|opt|Volumes|mnt|srv|etc)/"
     )
     def contains_host_path(text: str, src: Path) -> bool:
         markers = {str(src.resolve()), str(src.absolute()), str(Path.home())}
         return bool(HOST_PATH_RE.search(text)) or any(m in text for m in markers)
     ```

     This is the design's definition of "absolute host path" for the PRD's
     "No absolute host path is written": any POSIX path rooted at a host
     top-level directory (macOS and Linux user, temp, system and mount roots),
     plus the literal source and home directories. The lookbehind skips URL
     paths (`https://h/opt/x` is preceded by a host character) and relative
     segments (`a/tmp/b`). The body itself is never edited: a hit skips the file.
     Repo-relative paths and `~/...` are allowed.
6. Slug shared with another source file that reached this rule ->
   `skip-invalid`, `"slug collision: <a.md>, <b.md>"` (all colliding names, sorted),
   for every file in the collision group.
7. Target `memory_dir(repo_root) / f"{slug}.md"` exists: bytes equal the rendered
   output -> `skip-identical`, `"docs/dev/project-management/memory/<slug>.md"`;
   otherwise -> `skip-exists`, same detail.
8. Otherwise -> `migrate`, `"docs/dev/project-management/memory/<slug>.md"`.

**Rendered output** (`_render`), UTF-8, written as bytes:

```
---
<yaml.safe_dump({"name": slug, "description": description.strip(), "type": type,
                 "source": SOURCE_PREFIX + <source file name>,
                 "evidence": [EVIDENCE_PLACEHOLDER]},
                sort_keys=False, allow_unicode=True, width=10_000)>---
<body, unchanged except link rewriting>
```

`description` is stored stripped. All other original keys (including
`metadata`, `author`, `date`, original `name`) are dropped. The body is the text
after the closing `---` line, byte-for-byte, except link rewriting.

**Link rewriting**: rename map = `{stem: slug}` for every source file whose
pass-A action is `migrate`, `skip-identical`, or `skip-exists` (target will
exist in the repository) and whose `stem != slug`. In each rendered body, replace every `[[<stem>]]` with
`[[<slug>]]` for map entries. No other link form is touched.

**Index** (`_render_index`): for every file in `memory_files(memory_dir(repo_root))`
after the memory files are written, `memory.parse_memory(file)`; valid records
contribute `f"- [{record.name}]({record.slug}.md) — {record.description}"`
(every file is valid here: plan refuses invalid existing files and only valid
renders are written). Lines sorted by
slug, joined with `"\n"`, trailing `"\n"` when non-empty, `""` when empty.

**Exit rule** (CLI, both dry run and `--apply`): 0 iff every line's action is in
`OK_ACTIONS` (an empty source directory exits 0), else 1.

### Apply order (`apply_migration`)

1. `lines = plan_migration(src, repo_root)` (raises before any write).
2. `_plan_wiring(repo_root)` reads and validates all four wiring files and
   returns `{path: new_bytes}` for the ones that must change; raises
   `MigrationError` on a bad `.claude/settings.json`. Nothing written yet.
3. `memory_dir(repo_root).mkdir(parents=True, exist_ok=True)`; write every
   `migrate` file.
4. Write `MEMORY.md` from `_render_index`.
5. Write the wiring map from step 2.
6. `memory.check_directory(memory_dir(repo_root))` must return `[]`
   (postcondition; the plan refusals make it hold by construction).

**Rollback.** Before step 3, apply records an undo journal in memory: for
every path it may write (each `migrate` target, `MEMORY.md`, each wiring file in
the step-2 map, and the directories `memory_dir(repo_root)` and
`repo_root / ".claude"`), its original bytes, or "absent". If any of steps 3-6
raises (`OSError`, or the step-6 postcondition fails), apply restores every
journaled path in reverse order (rewrite original bytes; unlink files and
`rmdir` directories that were absent), then raises
`MigrationError("apply failed, repository restored: <cause>")`. A failure during
restore is appended to that message, naming the paths left unrestored. After a
successful apply the undo path is git: the target is a git repository, the
command never commits, and the README tells the operator to start from a
clean worktree, so `git restore` plus `git clean` on the reported paths returns
it to the prior state.

Every write goes through `_write_if_changed(path, data: bytes)`: if `path`
exists with equal bytes, do nothing; else create a unique temporary file in the
same directory with `tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")`
(exclusive `O_CREAT|O_EXCL`, never reuses or follows an existing path), write the
bytes, then `os.replace(tmp, path)`; on any exception unlink the temporary file
and re-raise. (Differs from `pack._publish_pack`, whose fixed tmp name could
clobber an existing file.)
Source files are never opened for writing.

### Wiring rules (`_plan_wiring`)

Line comparisons use `line.rstrip("\r\n").strip()`. Appends to a non-empty file
that does not end in `"\n"` first add `"\n"`.

- `.gitattributes`: append `GITATTRIBUTES_LINE + "\n"` when no line equals it;
  create with that line when absent.
- `AGENTS.md`: when no line equals `AGENTS_HEADING`, append `"\n" + AGENTS_SECTION`
  (just `AGENTS_SECTION` when the file is absent or empty).
- `CLAUDE.md`: append `CLAUDE_IMPORT_LINE + "\n"` when no line equals it; create as
  `"@AGENTS.md\n" + CLAUDE_IMPORT_LINE + "\n"` when absent.
- `.claude/settings.json`: absent -> create `{"autoMemoryEnabled": false}`
  (`.claude/` created). Present -> `json.loads`; `JSONDecodeError` or non-dict ->
  `MigrationError("<path>: not a JSON object")`. When `obj.get("autoMemoryEnabled")
  is False` already, unchanged; otherwise set it and write
  `json.dumps(obj, indent=2, ensure_ascii=False) + "\n"` (key order kept).

### `AGENTS_SECTION` content (<= 25 lines)

States: memory lives in `docs/dev/project-management/memory/`, one `<slug>.md`
per fact; frontmatter `name` (= file stem), `description` (one line), `type`
(`project`/`feedback`/`reference`), `source`, non-empty `evidence` list; no
`author`/`date` (git records them); `MEMORY.md` is the sorted index; memory must be
public-safe (no secrets, personal, or host-private facts; those go to host-global
memory); one `docs(memory): <verb> <slug>` commit per change; read `MEMORY.md`
before starting work; validate with `engram memory check`.

### `src/engram/cli.py`

```python
# in _add_memory_parser:
migrate_parser = memory_sub.add_parser("migrate")
migrate_parser.add_argument("--from", dest="src", type=Path, required=True)
migrate_parser.add_argument("--to", dest="repo_root", type=Path, required=True)
migrate_parser.add_argument("--apply", action="store_true")

def _run_memory_migrate(args: argparse.Namespace) -> int: ...
# main(): if args.command == "memory":
#     return _run_memory_migrate(args) if args.memory_command == "migrate" else _run_memory_check(args)
```

`_run_memory_migrate`: calls `apply_migration` when `args.apply`, else
`plan_migration`; prints each `line.tsv()` to stdout; returns the exit rule.
`MigrationError` or `OSError` -> `print(f"engram memory migrate: {exc}", file=sys.stderr)`,
return 1.

## Data flow

```
--from DIR ──memory_files──> [source .md] ──read+_split_frontmatter──> classify (rules 1-8)
                                                    │
                          rename map (stems of rule 7/8 files) ──> _render (frontmatter + rewritten body)
                                                    │
         plan: compare render vs target bytes ──> MigrationLine list ──> stdout TSV, exit rule
         apply: _plan_wiring (validate, no write) -> write migrate files -> MEMORY.md -> wiring
```

Source directory: read-only. Repository: written only under `--apply`, only
after every refusal check passed.

## Reuse inventory

- `memory.memory_files(directory)` - source enumeration and index regeneration.
- `memory._split_frontmatter(text)` - returns `(front, body, problem)`; same parser
  `check` uses, so parse failures agree.
- `memory._credential_violations(text)` / `memory.CREDENTIAL_PATTERNS` - the PRD
  00010 guard; labels only in detail.
- `memory.redact(text)` - applied to every detail string.
- `memory.memory_dir(repo_root)`, `memory.INDEX_NAME`, `memory.NAME_RE`,
  `memory.ALLOWED_TYPES` - paths and schema constants.
- `memory.parse_memory(path)` - reading target files for the index.
- `memory.check_directory(path)` - test oracle for applied output.
- Atomic write: `pack._publish_pack` pattern (`.<name>.tmp` + `os.replace`);
  pattern copied, not imported (that function is pack-specific).
- `yaml` (PyYAML, already a dependency) for frontmatter emission.
- Slug / wiring helpers: nothing found, greps tried: `slug`, `migrat`,
  `gitattributes`, `autoMemoryEnabled`, `safe_dump` across `src/engram` (control:
  `slug` hit `corpora._unique_slugs`, which encodes repo paths, unrelated).

## Alternatives considered

1. **Smallest diff: plan and apply in `cli.py`, string-built frontmatter.** Fewer
   files, but the PRD names `src/engram/migrate.py` and its exports, and
   hand-built YAML breaks on descriptions with `:` or `#`. Rejected.
2. **Chosen: `migrate.py` with one shared classify/render path for plan and
   apply.** `skip-identical` needs the rendered bytes during planning anyway, so
   sharing the render is what makes plan and apply agree and makes idempotence
   automatic (second apply: all `skip-identical`, wiring no-ops, `_write_if_changed`
   touches nothing).
3. **Make `_split_frontmatter`/`_credential_violations` public in `memory.py`.**
   Cleaner API, but edits a shipped module for one caller. Deferred until a
   second caller appears.

## Risks & edge cases

- **Wrong first-match precedence** leaks nothing: every skip writes nothing, and
  credential detail carries labels only.
- **Slug collision** (`a_b.md` and `a-b.md`): both skip-invalid, no arbitrary winner.
- **Absolute host path in a body or description**: skip-invalid via
  `contains_host_path` (pass A on source text, pass B on the final render and
  index line). Measured against the live corpus (dispatch 1): 17 bodies and 2
  descriptions name `/Users/<user>/...` and are skipped; the operator rewrites
  them by hand or leaves them in host memory.
- **settings.json rewrite reformats** a file that needs the key changed (indent 2).
  Acceptable: done once, idempotent after.
- **Partial apply on I/O error mid-way**: the undo journal restores every touched
  path (Apply order, Rollback). A crash of the process itself (SIGKILL) skips the
  journal; git is then the undo, and a rerun is safe because writes are
  idempotent and sources are untouched.
- **Index over 200 lines / 25 KB** or **invalid existing target files**: refused
  before any write, in the dry run too.
- **Host-path regex** misses Windows paths and roots outside its list (e.g.
  `/nix/`); the README rollout review covers those. It may skip a memory that
  quotes a system path such as `/etc/hosts`; the skip is loud and the operator
  edits the source or leaves it in host memory.
- **Agents cannot write `docs/dev/project-management/memory/` via editor tools**
  (autopilot hook); Python writes and `tmp_path` tests are unaffected.
- Likely next changes: (a) a `--repo NAME` mode resolving the Claude project dir
  from the registry; (b) rewriting `[[name]]` links by frontmatter name as well as
  stem; (c) migrating recorded evidence. None is boxed in: classification and
  rendering are separate functions and the rename map is a plain dict.

## Test strategy outline

All tests in `tests/test_memory_migrate.py`, `tmp_path` fixtures, names include
`plan`, `apply`, `wiring`, `idempot`, or `cli` so PRD `-k` filters select them.

- `plan`: one test per action (migrate, skip-user, skip-credential, skip-invalid
  for broken frontmatter / missing name / missing description, skip-exists,
  skip-identical); report lists every source file; exit rule; plan writes nothing
  (snapshot of repo tree bytes before/after; memory dir not created).
- `apply` happy path: three valid memories -> three files, sorted `MEMORY.md`,
  `check_directory` clean, four wiring files created.
- `apply` link rewrite: `feedback_foo_bar.md` -> `feedback-foo-bar.md`; another
  memory's `[[feedback_foo_bar]]` becomes `[[feedback-foo-bar]]`.
- `apply` sources byte-identical afterwards; no written file contains any
  `HOST_PATH_MARKERS(src)` entry. `plan`: a source whose body names the home
  directory, and one whose description names the source dir, both give
  `skip-invalid` `"contains an absolute host path"` (monkeypatch `Path.home` to a
  `tmp_path` subdir).
- `wiring` existing files kept with one addition each; rerun adds nothing.
- `wiring` settings.json array -> `MigrationError`, whole repo tree unchanged.
- `apply` rollback: monkeypatch the wiring write to raise `OSError` after memory
  files were written -> `MigrationError`, repo tree bytes and file set equal the
  pre-apply snapshot.
- `plan` refusals: `--from` equal to `--to`, to the memory dir, or to `.claude`;
  an invalid existing target memory file; an index over the line limit. Each
  raises `MigrationError` and writes nothing.
- `plan` pass B: a file named `sk_` + 20 letters gives `skip-credential`; a body
  with `/private/tmp/x` gives `skip-invalid`; output never contains the matched
  secret.
- `idempot`: second apply changes no bytes (tree snapshot including mtimes).
- `cli`: dry run exit 0/1 per rule and writes nothing; `--apply` writes; settings
  array -> exit 1.

## Review log

dispatch 1 (claude): cardinal-sin 0, blocker 1, non-blocker 12, question 2
- fixed blocker: PRD "No absolute host path is written" unmet; path guard was body-only and src-only. Now rule 5 checks the full render and index line against `HOST_PATH_MARKERS(src)` (resolved/absolute src, home dir); src resolved at entry (also closes the relative `--from` false-match non-blocker).
- non-blocker: dry run never reads wiring, so a bad `settings.json` passes plan and fails apply; consider calling `_plan_wiring` from `plan_migration` and printing would-change wiring files to stderr.
- non-blocker: type check must mirror `memory._type_violations` (key presence; `isinstance(str)` before set membership, else unhashable TypeError).
- non-blocker: `_credential_violations` returns `"credential\t<label>"`; build labels from `CREDENTIAL_PATTERNS` and escape `\t\r\n` in `MigrationLine.tsv`.
- non-blocker: `UnicodeDecodeError` on wiring files escapes the CLI catch; BOM in settings.json reads as "not a JSON object".
- non-blocker: `os.replace` replaces symlinked wiring files (e.g. CLAUDE.md -> AGENTS.md) with regular files.
- non-blocker: links by frontmatter name (gems corpus style) and links to skipped user memories are not rewritten; consider an "unresolved [[links]]" detail suffix.
- non-blocker: `_render_index` should strip `record.description`.
- non-blocker: rollback is only git; README should require a clean worktree before `--apply` and name `git restore`/`git clean`.
- non-blocker: `--from` equal to (or inside) the target memory dir would write into the source; refuse it.
- non-blocker: slug `memory` collides with `MEMORY.md` on case-insensitive APFS; treat as skip-invalid.
- non-blocker: tests missing for AGENTS_SECTION <= 25 lines, secret never in stdout, relative `--from`, dry run on bad settings.json.
- question: broken frontmatter plus credential reports skip-invalid, not skip-credential; scan credentials before rule 2?
- question: should `--apply` wire and write an empty MEMORY.md when nothing migrates?

dispatch 2: first codex run could not read files (nested sandbox `sandbox_apply: Operation not permitted`); re-run with design, PRD and memory.py inlined.
dispatch 2 (codex): cardinal-sin 1, blocker 5, non-blocker 1, question 0
- fixed cardinal sin: no rollback for partial apply. Added an in-memory undo journal (original bytes or absence per path) restored on any failure in steps 3-6; git documented as the post-success undo.
- fixed blocker: host-path guard covered only src and home. Added `HOST_PATH_RE` (host top-level roots) plus src/home markers as the design's definition of "absolute host path".
- fixed blocker: classification was circular (path check after link rewriting fed the rename map). Now pass A classifies on source text, the rename map is built once, pass B re-scans the final render and can only downgrade.
- fixed blocker: rendering could introduce a credential (file `sk_<20 chars>.md` -> name `sk-...`). Rule 4 now scans file name and generated frontmatter; pass B scans the final render and index line.
- fixed blocker: apply could exit 0 with an invalid directory (invalid existing files, index over limits). Plan now refuses both before any write; apply checks `check_directory` as a postcondition.
- fixed blocker: `--from` equal to `--to` would enumerate and then rewrite AGENTS.md/CLAUDE.md. Plan refuses `src` equal to repo root, memory dir, or `.claude` (also closes dispatch 1's memory-dir overlap non-blocker).
- non-blocker: add an apply-named mixed-action fixture test (PRD Phase 0 exit criterion), a collision test and a `metadata.type` fallback test.

dispatch 3 (codex): cardinal-sin 0, blocker 4, non-blocker 2, question 0
- fixed blocker: existing target memories bypassed the final-output host-path check and flowed into MEMORY.md. Plan now refuses existing files whose text or index line has a host path.
- fixed blocker: fixed `.<name>.tmp` could clobber or follow an existing path. `_write_if_changed` now uses `tempfile.mkstemp` in the destination dir and unlinks it on failure.
- fixed blocker: a source symlink into the repository would see apply's writes. Plan refuses any source file resolving inside `repo_root`.
- fixed blocker: credential-bearing file names printed verbatim. `MigrationLine.tsv` and every `MigrationError` message pass through `memory.redact`.
- these four fixes were made after the last allowed dispatch and are not reviewer-verified; the work-completion review must check them.
- non-blocker: rollback journals only `memory_dir` and `.claude`; `mkdir(parents=True)` can leave newly created ancestors (`docs/dev/project-management`). Journal every created directory, remove deepest first.
- non-blocker: the listed pass-B tests are caught by pass A first. Add a fixture where rewriting alone creates a credential: source `SK_ABCDEFGHIJKLMNOPQRST.md` linked as `[[SK_ABCDEFGHIJKLMNOPQRST]]` from another file; the referring file must downgrade to skip-credential.
