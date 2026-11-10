import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from _migrate_helpers import (
    AWS_KEY,
    DEST,
    GITATTRS,
    HOST,
    IMPORT,
    REFUSALS,
    ROLLBACK_STAGES,
    SETTINGS,
    SK_SLUG,
    SK_STEM,
    TOKEN,
    USER_SKIP,
    WIRING,
    identities,
    index_bytes,
    memory_text,
    mtimes,
    rendered,
    snapshot,
    triples,
    valid,
    write,
    write_target,
)

from engram import migrate
from engram.memory import (
    INDEX_MAX_BYTES,
    INDEX_MAX_LINES,
    check_directory,
    memory_dir,
    parse_memory,
    redact,
)
from engram.migrate import (
    ACTIONS,
    AGENTS_SECTION,
    OK_ACTIONS,
    MigrationError,
    MigrationLine,
    apply_migration,
    contains_host_path,
    plan_migration,
)


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: path))
    return path


@pytest.fixture
def src(tmp_path: Path) -> Path:
    path = tmp_path / "claude-memory"
    path.mkdir()
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    (path / "AGENTS.md").write_text("# Agents\n")
    return path


def test_plan_constants_match_contract() -> None:
    assert ACTIONS == (
        "migrate",
        "skip-user",
        "skip-credential",
        "skip-invalid",
        "skip-exists",
        "skip-identical",
    )
    assert frozenset({"migrate", "skip-identical"}) == OK_ACTIONS


def test_plan_migrates_valid_memories_under_lowercased_hyphen_slugs(
    tmp_path: Path,
    src: Path,
    repo: Path,
) -> None:
    write(src, "Feedback_Foo_Bar.md", valid(kind="feedback"))
    write(src, "project-notes.md", valid(description="Other fact"))
    before = snapshot(tmp_path)

    lines = plan_migration(src, repo)

    assert triples(lines) == [
        ("Feedback_Foo_Bar.md", "migrate", DEST + "feedback-foo-bar.md"),
        ("project-notes.md", "migrate", DEST + "project-notes.md"),
    ]
    assert snapshot(tmp_path) == before
    assert not memory_dir(repo).exists()


def test_plan_resolves_relative_paths_against_cwd(
    tmp_path: Path,
    src: Path,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write(src, "rel_note.md", valid())
    write_target(repo, "existing")
    write(src, "existing.md", valid(description="Changed"))
    monkeypatch.chdir(tmp_path)

    lines = plan_migration(Path(src.name), Path(repo.name))

    assert triples(lines) == [
        ("existing.md", "skip-exists", DEST + "existing.md"),
        ("rel_note.md", "migrate", DEST + "rel-note.md"),
    ]


def test_plan_lists_every_source_markdown_file_in_sorted_order(
    src: Path,
    repo: Path,
) -> None:
    write(src, "b.md", valid())
    write(src, "a.md", valid(name="other"))
    write(src, "c.md", valid(kind="user"))
    write(src, "notes.txt", valid())
    write(src, "MEMORY.md", "- [a](a.md) — A fact\n")
    (src / "sub.md").mkdir()
    write(src / "sub.md", "inner.md", valid())

    lines = plan_migration(src, repo)

    assert triples(lines) == [
        ("a.md", "migrate", DEST + "a.md"),
        ("b.md", "migrate", DEST + "b.md"),
        ("c.md", "skip-user", USER_SKIP),
    ]


def test_plan_returns_no_lines_for_empty_source(
    tmp_path: Path,
    src: Path,
    repo: Path,
) -> None:
    before = snapshot(tmp_path)

    assert plan_migration(src, repo) == []
    assert snapshot(tmp_path) == before
    assert not memory_dir(repo).exists()


def test_plan_skips_user_memory_but_migrates_project_memory(
    tmp_path: Path,
    src: Path,
    repo: Path,
) -> None:
    write(src, "user_role.md", valid(kind="user"))
    write(src, "project_role.md", valid(kind="project"))
    before = snapshot(tmp_path)

    lines = plan_migration(src, repo)

    assert triples(lines) == [
        ("project_role.md", "migrate", DEST + "project-role.md"),
        ("user_role.md", "skip-user", USER_SKIP),
    ]
    assert snapshot(tmp_path) == before


def test_plan_falls_back_to_metadata_type(src: Path, repo: Path) -> None:
    front = {"name": "m", "description": "Meta fact", "metadata": {"type": "feedback"}}
    top_wins = {**front, "type": "project", "metadata": {"type": "user"}}
    write(src, "meta_feedback.md", memory_text(front))
    write(src, "meta_user.md", memory_text({**front, "metadata": {"type": "user"}}))
    write(src, "meta_scalar.md", memory_text({**front, "metadata": "feedback"}))
    write(src, "top_wins.md", memory_text(top_wins))
    identical = rendered(
        "meta-feedback",
        "Meta fact",
        "feedback",
        "meta_feedback.md",
        "Body.\n",
    )
    write_target(repo, "meta-feedback", identical)

    lines = plan_migration(src, repo)

    assert triples(lines) == [
        ("meta_feedback.md", "skip-identical", DEST + "meta-feedback.md"),
        ("meta_scalar.md", "skip-invalid", "type missing"),
        ("meta_user.md", "skip-user", USER_SKIP),
        ("top_wins.md", "migrate", DEST + "top-wins.md"),
    ]


def test_plan_reports_credential_labels_without_the_secret(
    tmp_path: Path,
    src: Path,
    repo: Path,
) -> None:
    write(src, "token.md", valid(body=f"Use {TOKEN} here.\n"))
    write(src, "both.md", valid(body=f"{AWS_KEY} and {TOKEN}\n"))
    write(src, "desc.md", valid(description=f"Key {AWS_KEY}"))
    write(src, "near.md", valid(body=f"Almost {TOKEN[:-1]}.\n"))
    write(src, "nameless.md", memory_text({"type": "project"}, f"{TOKEN}\n"))
    write(src, "user_secret.md", valid(kind="user", body=f"{TOKEN}\n"))
    before = snapshot(tmp_path)

    lines = plan_migration(src, repo)

    assert triples(lines) == [
        ("both.md", "skip-credential", "github-token,aws-access-key"),
        ("desc.md", "skip-credential", "aws-access-key"),
        ("nameless.md", "skip-credential", "github-token"),
        ("near.md", "migrate", DEST + "near.md"),
        ("token.md", "skip-credential", "github-token"),
        ("user_secret.md", "skip-user", USER_SKIP),
    ]
    for line in lines:
        assert TOKEN not in line.tsv()
        assert AWS_KEY not in line.tsv()
    assert snapshot(tmp_path) == before


def test_plan_redacts_credential_file_name_in_tsv(src: Path, repo: Path) -> None:
    write(src, f"{TOKEN}.md", valid())
    write(src, "plain.md", valid())

    lines = plan_migration(src, repo)

    assert triples(lines) == [
        (f"{TOKEN}.md", "skip-credential", "github-token"),
        ("plain.md", "migrate", DEST + "plain.md"),
    ]
    assert [line.tsv() for line in lines] == [
        "[redacted:github-token].md\tskip-credential\tgithub-token",
        f"plain.md\tmigrate\t{DEST}plain.md",
    ]


def test_plan_line_tsv_flattens_control_characters_and_redacts() -> None:
    assert (
        MigrationLine("a\tb.md", "skip-invalid", "x\ny\rz\tw").tsv()
        == "a b.md\tskip-invalid\tx y z w"
    )
    assert (
        MigrationLine("n.md", "skip-invalid", f"saw {AWS_KEY}").tsv()
        == "n.md\tskip-invalid\tsaw [redacted:aws-access-key]"
    )
    assert MigrationLine("n.md", "migrate", "plain").tsv() == "n.md\tmigrate\tplain"


TYPE_ONE_OF = "type must be one of feedback, project, reference"
INVALID_SOURCES = [
    ("unreadable.md", b"---\nname: \xff\xfe\n---\n", "unreadable"),
    ("nofront.md", "just text\n", "frontmatter missing"),
    ("open.md", "---\nname: open\n", "frontmatter unterminated"),
    ("broken.md", "---\nname: [\n---\nb\n", "frontmatter unparseable"),
    ("listfront.md", "---\n- a\n---\nb\n", "frontmatter not a mapping"),
    ("noname.md", memory_text({"description": "d", "type": "project"}), "name missing"),
    ("blankname.md", valid(name=""), "name missing"),
    ("noboth.md", memory_text({"type": "project"}), "name missing"),
    ("nodesc.md", memory_text({"name": "n", "type": "project"}), "description missing"),
    ("blankdesc.md", valid(description="   "), "description empty"),
    ("twoline.md", valid(description="a\nb"), "description must be one line"),
    ("notype.md", memory_text({"name": "n", "description": "d"}), "type missing"),
    ("other.md", valid(kind="other"), TYPE_ONE_OF),
    (
        "listtype.md",
        memory_text({"name": "n", "description": "d", "type": ["project"]}),
        TYPE_ONE_OF,
    ),
    ("a.b.md", valid(), "slug a.b must match ^[a-z0-9][a-z0-9-]*$"),
    ("memory.md", valid(), "slug memory collides with MEMORY.md"),
]


@pytest.mark.parametrize(("filename", "content", "detail"), INVALID_SOURCES)
def test_plan_marks_invalid_source_with_first_failing_detail(
    tmp_path: Path,
    src: Path,
    repo: Path,
    filename: str,
    content: str | bytes,
    detail: str,
) -> None:
    write(src, filename, content)
    write(src, "zz_good.md", valid())
    before = snapshot(tmp_path)

    lines = plan_migration(src, repo)

    assert triples(lines) == [
        (filename, "skip-invalid", detail),
        ("zz_good.md", "migrate", DEST + "zz-good.md"),
    ]
    assert snapshot(tmp_path) == before


def test_plan_skips_every_file_whose_slug_collides(src: Path, repo: Path) -> None:
    write(src, "a_b.md", valid())
    write(src, "a-b.md", valid())
    write(src, "C_D.md", valid(kind="user"))
    write(src, "c-d.md", valid())
    write(src, "solo.md", valid())
    for name in ("X_y-z.md", "x-y-z.md", "x_y_z.md"):
        write(src, name, valid())
    three = "slug collision: X_y-z.md, x-y-z.md, x_y_z.md"

    lines = plan_migration(src, repo)

    assert triples(lines) == [
        ("C_D.md", "skip-user", USER_SKIP),
        ("X_y-z.md", "skip-invalid", three),
        ("a-b.md", "skip-invalid", "slug collision: a-b.md, a_b.md"),
        ("a_b.md", "skip-invalid", "slug collision: a-b.md, a_b.md"),
        ("c-d.md", "migrate", DEST + "c-d.md"),
        ("solo.md", "migrate", DEST + "solo.md"),
        ("x-y-z.md", "skip-invalid", three),
        ("x_y_z.md", "skip-invalid", three),
    ]


def test_plan_skips_sources_naming_absolute_host_paths(
    tmp_path: Path,
    src: Path,
    repo: Path,
    home: Path,
) -> None:
    write(src, "home_body.md", valid(body=f"Notes live in {home}/notes.\n"))
    write(src, "src_desc.md", valid(description=f"Copied from {src}"))
    write(src, "tmp_body.md", valid(body="Scratch in /private/tmp/x.\n"))
    relative = "See docs/dev/x.md, ~/notes, a/tmp/b and https://h/opt/x.\n"
    write(src, "relative.md", valid(body=relative))
    before = snapshot(tmp_path)

    lines = plan_migration(src, repo)

    assert triples(lines) == [
        ("home_body.md", "skip-invalid", HOST),
        ("relative.md", "migrate", DEST + "relative.md"),
        ("src_desc.md", "skip-invalid", HOST),
        ("tmp_body.md", "skip-invalid", HOST),
    ]
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/Users/alice/x", True),
        ("cd /home/bob/work", True),
        ("read /etc/hosts", True),
        ("(/Volumes/disk/a)", True),
        ("https://h/opt/x", False),
        ("https://h/home/x", False),
        ("a/tmp/b", False),
        ("a/Users/b", False),
        ("a/etc/b", False),
        ("~/notes/x", False),
        ("/usr/local/bin", False),
        ("/Usersx/alice", False),
        ("docs/dev/x.md", False),
        ("", False),
    ],
)
def test_plan_contains_host_path_matches_host_roots_only(
    src: Path,
    text: str,
    expected: bool,
) -> None:
    assert contains_host_path(text, src) is expected


def test_plan_contains_host_path_matches_home_and_source_markers(
    src: Path,
    home: Path,
) -> None:
    assert contains_host_path(f"x{home}y", src) is True
    assert contains_host_path(f"x{src}y", src) is True
    assert contains_host_path("x/claude-memory/y", src) is False


def test_plan_contains_host_path_matches_markers_outside_host_roots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = Path("/zz-engram-home/h")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    source = Path("/zz-engram-src/mem")

    assert contains_host_path("x/zz-engram-src/mem/y", source) is True
    assert contains_host_path("see /zz-engram-home/h/notes", source) is True
    assert contains_host_path("/zz-engram-src/other /zz-engram-home/x", source) is False


LONG = " ".join(["word"] * 30)  # 149 chars: default YAML width would fold it
UNICODE = "Café ü naïve"


@pytest.mark.parametrize(
    ("source", "target", "action"),
    [
        ((LONG, "project"), (LONG, "project"), "skip-identical"),
        ((UNICODE, "feedback"), (UNICODE, "feedback"), "skip-identical"),
        (("New fact", "project"), ("Old fact", "project"), "skip-exists"),
        (("Same fact", "feedback"), ("Same fact", "project"), "skip-exists"),
    ],
    ids=["long-description", "non-ascii", "description-changed", "type-changed"],
)
def test_plan_compares_whole_rendered_file_against_target(
    src: Path,
    repo: Path,
    source: tuple[str, str],
    target: tuple[str, str],
    action: str,
) -> None:
    write(src, "fact.md", valid(description=source[0], kind=source[1]))
    write_target(repo, "fact", rendered("fact", *target, "fact.md", "Body.\n"))

    lines = plan_migration(src, repo)

    assert triples(lines) == [("fact.md", action, DEST + "fact.md")]


def test_plan_reports_identical_and_existing_targets(
    tmp_path: Path,
    src: Path,
    repo: Path,
) -> None:
    dropped = {"author": "me", "date": "2026-01-01", "metadata": {"type": "user"}}
    same = valid("Orig Name", "  Trimmed fact  ", "reference", "Exact.\n", **dropped)
    write(src, "Same_Fact.md", same)
    write(src, "changed.md", valid(description="Changed fact", body="New body.\n"))
    write(src, "fresh.md", valid())
    write_target(
        repo,
        "same-fact",
        rendered("same-fact", "Trimmed fact", "reference", "Same_Fact.md", "Exact.\n"),
    )
    write_target(
        repo,
        "changed",
        rendered("changed", "Changed fact", "project", "changed.md", "New body!\n"),
    )
    before = snapshot(tmp_path)

    lines = plan_migration(src, repo)

    assert triples(lines) == [
        ("Same_Fact.md", "skip-identical", DEST + "same-fact.md"),
        ("changed.md", "skip-exists", DEST + "changed.md"),
        ("fresh.md", "migrate", DEST + "fresh.md"),
    ]
    assert snapshot(tmp_path) == before


LINKS = (
    "See [[Feedback_Foo]], [[User_Note]] and [Feedback_Foo](Feedback_Foo.md).\n"
    "Again [[Feedback_Foo]].\n"
)
REWRITTEN = LINKS.replace("[[Feedback_Foo]]", "[[feedback-foo]]")


@pytest.mark.parametrize(
    ("target_body", "action"),
    [
        (REWRITTEN, "skip-identical"),
        (LINKS, "skip-exists"),
        (LINKS.replace("[[Feedback_Foo]]", "[[feedback-foo]]", 1), "skip-exists"),
        (REWRITTEN.replace("[[User_Note]]", "[[user-note]]"), "skip-exists"),
        (LINKS.replace("Feedback_Foo", "feedback-foo"), "skip-exists"),
    ],
    ids=[
        "rewritten",
        "unrewritten",
        "first-link-only-rewritten",
        "skipped-target-rewritten",
        "markdown-link-rewritten",
    ],
)
def test_plan_rewrites_wiki_links_to_renamed_slugs_before_comparing(
    src: Path,
    repo: Path,
    target_body: str,
    action: str,
) -> None:
    write(src, "Feedback_Foo.md", valid())
    write(src, "User_Note.md", valid(kind="user"))
    write(src, "other.md", valid(description="Linker", body=LINKS))
    target = rendered("other", "Linker", "project", "other.md", target_body)
    write_target(repo, "other", target)

    lines = plan_migration(src, repo)

    assert triples(lines) == [
        ("Feedback_Foo.md", "migrate", DEST + "feedback-foo.md"),
        ("User_Note.md", "skip-user", USER_SKIP),
        ("other.md", action, DEST + "other.md"),
    ]


def test_plan_never_prints_secret_from_renamed_link_target(
    tmp_path: Path,
    src: Path,
    repo: Path,
) -> None:
    write(src, f"{SK_STEM}.md", valid())
    referrer = valid(description="Points at it", body=f"See [[{SK_STEM}]].\n")
    write(src, "referrer.md", referrer)
    before = snapshot(tmp_path)

    lines = plan_migration(src, repo)

    assert [line.file for line in lines] == [f"{SK_STEM}.md", "referrer.md"]
    assert triples(lines)[0] == (f"{SK_STEM}.md", "skip-credential", "sk-key")
    for line in lines:
        assert SK_SLUG not in line.tsv().lower()
        assert SK_SLUG not in line.detail.lower()
    assert snapshot(tmp_path) == before


OVERLAPS: list[Callable[[Path], Path]] = [
    lambda repo: repo,
    lambda repo: repo / "sub" / "..",
    memory_dir,
    lambda repo: repo / ".claude",
    lambda repo: repo / "notes",
]


@pytest.mark.parametrize(
    "overlap",
    OVERLAPS,
    ids=[
        "repo-root",
        "repo-root-unresolved",
        "memory-dir",
        "claude",
        "repo-subfolder",
    ],
)
def test_plan_refuses_source_overlapping_repository_write_targets(
    tmp_path: Path,
    repo: Path,
    overlap: Callable[[Path], Path],
) -> None:
    (repo / "sub").mkdir()
    source = overlap(repo)
    source.mkdir(parents=True, exist_ok=True)
    write(source, "note.md", rendered("note", "A fact", "project", "note.md", "B.\n"))
    before = snapshot(tmp_path)

    with pytest.raises(MigrationError):
        plan_migration(source, repo)
    assert snapshot(tmp_path) == before


def test_plan_refuses_source_file_symlinked_into_repository(
    tmp_path: Path,
    src: Path,
    repo: Path,
) -> None:
    (repo / "notes").mkdir()
    real = write(repo / "notes", "real.md", valid())
    (src / "link.md").symlink_to(real)
    before = snapshot(tmp_path)

    with pytest.raises(MigrationError):
        plan_migration(src, repo)
    assert snapshot(tmp_path) == before


def test_plan_accepts_source_beside_repository_with_shared_name_prefix(
    tmp_path: Path,
    repo: Path,
) -> None:
    beside = tmp_path / "repo-memory"
    beside.mkdir()
    (tmp_path / "outside").mkdir()
    write(beside, "note.md", valid())
    (beside / "ext.md").symlink_to(write(tmp_path / "outside", "ext.md", valid()))

    lines = plan_migration(beside, repo)

    assert triples(lines) == [
        ("ext.md", "migrate", DEST + "ext.md"),
        ("note.md", "migrate", DEST + "note.md"),
    ]


@pytest.mark.parametrize(
    "broken",
    ["src-missing", "repo-missing", "src-file", "repo-file"],
)
def test_plan_refuses_paths_that_are_not_directories(
    tmp_path: Path,
    src: Path,
    repo: Path,
    broken: str,
) -> None:
    write(src, "note.md", valid())
    paths = {"src": src, "repo": repo}
    side, problem = broken.split("-")
    paths[side] = tmp_path / f"absent-{side}"
    if problem == "file":
        paths[side].write_text("not a directory\n")

    with pytest.raises(MigrationError):
        plan_migration(paths["src"], paths["repo"])


@pytest.mark.parametrize(
    "content",
    [
        b"no frontmatter\n",
        rendered("bad", "Fine", "project", "bad.md", f"Leaked {TOKEN}\n"),
        rendered("bad", "Fine", "project", "bad.md", "Look in /Users/alice/x.\n"),
        rendered("bad", "Lives in /home/alice/y", "project", "bad.md", "Body.\n"),
    ],
    ids=["no-frontmatter", "credential", "host-path-body", "host-path-description"],
)
def test_plan_refuses_invalid_existing_target_file(
    tmp_path: Path,
    src: Path,
    repo: Path,
    content: bytes,
) -> None:
    write(src, "note.md", valid())
    write_target(repo, "good")
    write_target(repo, "bad", content)
    before = snapshot(tmp_path)

    with pytest.raises(MigrationError) as raised:
        plan_migration(src, repo)
    assert "bad.md" in str(raised.value)
    assert "good.md" not in str(raised.value)
    assert TOKEN not in str(raised.value)
    assert snapshot(tmp_path) == before


def test_plan_existing_target_fixture_is_valid_memory(repo: Path) -> None:
    record, violations = parse_memory(write_target(repo, "good"))
    assert violations == []
    assert record is not None
    assert record.slug == "good"


@pytest.mark.parametrize(
    ("existing", "sources", "refused"),
    [
        (INDEX_MAX_LINES - 1, {"new_a.md": "project"}, False),
        (INDEX_MAX_LINES, {"new_a.md": "project"}, True),
        (INDEX_MAX_LINES - 1, {"new_a.md": "project", "new_b.md": "project"}, True),
        (INDEX_MAX_LINES, {"new_a.md": "user"}, False),
        (INDEX_MAX_LINES, {"m000.md": "identical"}, False),
    ],
    ids=["at-limit", "one-over", "two-new-one-over", "skip-not-counted", "identical"],
)
def test_plan_refuses_index_over_line_limit(
    tmp_path: Path,
    src: Path,
    repo: Path,
    existing: int,
    sources: dict[str, str],
    refused: bool,
) -> None:
    for i in range(existing):
        write_target(repo, f"m{i:03d}")
    for name, kind in sources.items():
        if kind == "identical":
            write(src, name, valid(description="Existing fact", body="Kept.\n"))
        else:
            write(src, name, valid(kind=kind))
    before = snapshot(tmp_path)

    if refused:
        with pytest.raises(MigrationError):
            plan_migration(src, repo)
    else:
        actions = [line.action for line in plan_migration(src, repo)]
        expected = {"project": "migrate", "user": "skip-user"}
        assert actions == [expected.get(k, "skip-identical") for k in sources.values()]
    assert snapshot(tmp_path) == before


HALF = INDEX_MAX_BYTES // 2


@pytest.mark.parametrize(
    ("existing", "sources", "refused"),
    [
        ([], [INDEX_MAX_BYTES - 100], False),
        ([], [INDEX_MAX_BYTES], True),
        ([], [HALF - 100, HALF - 100], False),
        ([], [HALF, HALF], True),
        ([HALF], [HALF], True),
    ],
    ids=["one-under", "one-over", "two-under", "two-over", "existing-plus-new-over"],
)
def test_plan_refuses_index_over_byte_limit(
    tmp_path: Path,
    src: Path,
    repo: Path,
    existing: list[int],
    sources: list[int],
    refused: bool,
) -> None:
    for i, length in enumerate(existing):
        content = rendered(f"old{i}", "y" * length, "project", f"old{i}.md", "Kept.\n")
        write_target(repo, f"old{i}", content)
    for i, length in enumerate(sources):
        write(src, f"big{i}.md", valid(description="x" * length))
    before = snapshot(tmp_path)

    if refused:
        with pytest.raises(MigrationError):
            plan_migration(src, repo)
    else:
        lines = plan_migration(src, repo)
        names = [f"big{i}" for i in range(len(sources))]
        assert triples(lines) == [
            (f"{n}.md", "migrate", f"{DEST}{n}.md") for n in names
        ]
    assert snapshot(tmp_path) == before


def test_apply_migrates_three_types_into_empty_repository_with_wiring(
    tmp_path: Path,
    src: Path,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memories = [
        ("Zeta_Ref.md", "zeta-ref", " Ref fact ", "reference"),
        ("Mid_Note.md", "mid-note", "Feedback fact", "feedback"),
        ("alpha.md", "alpha", "Project fact", "project"),
    ]
    for filename, slug, description, kind in memories:
        write(src, filename, valid(slug[0], description, kind, f"{kind} body.\n"))
    planned = triples(plan_migration(src, repo))
    monkeypatch.chdir(tmp_path)

    lines = apply_migration(Path(src.name), Path(repo.name))

    assert triples(lines) == planned
    assert planned == [
        ("Mid_Note.md", "migrate", DEST + "mid-note.md"),
        ("Zeta_Ref.md", "migrate", DEST + "zeta-ref.md"),
        ("alpha.md", "migrate", DEST + "alpha.md"),
    ]
    target = memory_dir(repo)
    for filename, slug, description, kind in memories:
        expected = rendered(slug, description, kind, filename, f"{kind} body.\n")
        assert (target / f"{slug}.md").read_bytes() == expected
    assert (target / "MEMORY.md").read_bytes() == index_bytes(
        ("alpha", "Project fact"),
        ("mid-note", "Feedback fact"),
        ("zeta-ref", "Ref fact"),
    )
    assert check_directory(target) == []
    assert (repo / ".gitattributes").read_text() == GITATTRS
    assert (repo / "AGENTS.md").read_text() == "# Agents\n\n" + AGENTS_SECTION
    assert (repo / "CLAUDE.md").read_text() == "@AGENTS.md\n" + IMPORT
    settings = (repo / ".claude" / "settings.json").read_text()
    assert json.loads(settings) == {"autoMemoryEnabled": False}
    assert {str(p.relative_to(repo)) for p in repo.rglob("*") if p.is_file()} == {
        ".claude/settings.json",
        ".gitattributes",
        "AGENTS.md",
        "CLAUDE.md",
        *(DEST + n for n in ("MEMORY.md", "alpha.md", "mid-note.md", "zeta-ref.md")),
    }
    assert {p.name for p in tmp_path.iterdir()} == {"claude-memory", "home", "repo"}


def test_apply_mixed_actions_reports_every_action_and_keeps_directory_valid(
    src: Path,
    repo: Path,
) -> None:
    write(src, "fresh_one.md", valid(description="Fresh"))
    write(src, "user_role.md", valid(kind="user"))
    write(src, "token.md", valid(body=f"{TOKEN}\n"))
    write(src, "nofront.md", "just text\n")
    write(src, "kept.md", valid(description="Changed"))
    write(src, "same.md", valid(description="Existing fact", body="Kept.\n"))
    existing = {
        p: p.read_bytes()
        for p in (write_target(repo, "kept"), write_target(repo, "same"))
    }
    planned = triples(plan_migration(src, repo))

    lines = apply_migration(src, repo)

    assert triples(lines) == planned
    assert planned == [
        ("fresh_one.md", "migrate", DEST + "fresh-one.md"),
        ("kept.md", "skip-exists", DEST + "kept.md"),
        ("nofront.md", "skip-invalid", "frontmatter missing"),
        ("same.md", "skip-identical", DEST + "same.md"),
        ("token.md", "skip-credential", "github-token"),
        ("user_role.md", "skip-user", USER_SKIP),
    ]
    assert {line.action for line in lines} == set(ACTIONS)
    target = memory_dir(repo)
    names = sorted(p.name for p in target.iterdir())
    assert names == ["MEMORY.md", "fresh-one.md", "kept.md", "same.md"]
    assert {p: p.read_bytes() for p in existing} == existing
    assert (target / "MEMORY.md").read_bytes() == index_bytes(
        ("fresh-one", "Fresh"), ("kept", "Existing fact"), ("same", "Existing fact")
    )
    assert check_directory(target) == []
    assert all(TOKEN.encode() not in p.read_bytes() for p in target.iterdir())


def test_apply_renames_slugs_and_rewrites_links_to_them(src: Path, repo: Path) -> None:
    write(src, "feedback_foo_bar.md", valid(kind="feedback"))
    body = "See [[feedback_foo_bar]] and [[feedback_foo_bar_v2]].\n"
    write(src, "linker.md", valid(description="Linker", body=body))

    lines = apply_migration(src, repo)

    assert triples(lines) == [
        ("feedback_foo_bar.md", "migrate", DEST + "feedback-foo-bar.md"),
        ("linker.md", "migrate", DEST + "linker.md"),
    ]
    target = memory_dir(repo)
    assert not (target / "feedback_foo_bar.md").exists()
    renamed = rendered(
        "feedback-foo-bar",
        "A fact",
        "feedback",
        "feedback_foo_bar.md",
        "Body.\n",
    )
    assert (target / "feedback-foo-bar.md").read_bytes() == renamed
    new_body = "See [[feedback-foo-bar]] and [[feedback_foo_bar_v2]].\n"
    linker = rendered("linker", "Linker", "project", "linker.md", new_body)
    assert (target / "linker.md").read_bytes() == linker
    assert check_directory(target) == []


@pytest.mark.parametrize(("name", "before", "after"), WIRING)
def test_apply_wiring_adds_one_entry_per_file_and_never_duplicates(
    src: Path,
    repo: Path,
    name: str,
    before: str | None,
    after: str,
) -> None:
    path = repo / name
    path.unlink(missing_ok=True)
    if before is not None:
        path.write_bytes(before.encode())

    for _ in range(2):
        assert apply_migration(src, repo) == []
        assert path.read_bytes() == after.encode()
    assert check_directory(memory_dir(repo)) == []


@pytest.mark.parametrize(("before", "after"), SETTINGS)
def test_apply_wiring_disables_auto_memory_and_keeps_other_settings(
    src: Path,
    repo: Path,
    before: str,
    after: str,
) -> None:
    write(src, "note.md", valid())
    path = repo / ".claude" / "settings.json"
    path.parent.mkdir()
    path.write_text(before, encoding="utf-8")

    for _ in range(2):
        apply_migration(src, repo)
        assert path.read_text(encoding="utf-8") == after


@pytest.mark.parametrize(("name", "content"), REFUSALS)
def test_apply_refuses_unusable_wiring_file_and_changes_nothing(
    tmp_path: Path,
    src: Path,
    repo: Path,
    name: str,
    content: bytes,
) -> None:
    write(src, "note.md", valid())
    path = repo / name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(content)
    before = snapshot(tmp_path)

    with pytest.raises(MigrationError) as raised:
        apply_migration(src, repo)
    if name.endswith(".json"):
        assert "settings.json" in str(raised.value)
        assert "not a JSON object" in str(raised.value)
    assert snapshot(tmp_path) == before


def test_apply_refuses_what_plan_refuses_before_any_wiring(
    tmp_path: Path,
    src: Path,
    repo: Path,
) -> None:
    write(src, "note.md", valid())
    write_target(repo, "bad", b"no frontmatter\n")
    before = snapshot(tmp_path)

    with pytest.raises(MigrationError) as raised:
        apply_migration(src, repo)
    assert "bad.md" in str(raised.value)
    assert snapshot(tmp_path) == before


def test_apply_idempotent_second_run_changes_no_bytes_or_mtimes(
    src: Path,
    repo: Path,
) -> None:
    write(src, "Feedback_Foo.md", valid(kind="feedback"))
    write(src, "other.md", valid(description="Linker", body="See [[Feedback_Foo]].\n"))
    write(src, "user_role.md", valid(kind="user"))
    apply_migration(src, repo)
    for path in repo.rglob("*"):
        os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    before, stamps, ids = snapshot(repo), mtimes(repo), identities(repo)

    lines = apply_migration(src, repo)

    assert triples(lines) == [
        ("Feedback_Foo.md", "skip-identical", DEST + "feedback-foo.md"),
        ("other.md", "skip-identical", DEST + "other.md"),
        ("user_role.md", "skip-user", USER_SKIP),
    ]
    assert snapshot(repo) == before
    assert mtimes(repo) == stamps
    assert identities(repo) == ids


def test_apply_leaves_sources_untouched_and_writes_no_source_path(
    src: Path,
    repo: Path,
) -> None:
    write(src, "note.md", valid())
    write(src, "user_role.md", valid(kind="user"))
    write(src, "host.md", valid(body=f"Copied from {src}/x.\n"))
    write(src, "MEMORY.md", "- [note](note.md) — A fact\n")
    before, stamps = snapshot(src), mtimes(src)

    for _ in range(2):
        apply_migration(src, repo)

    assert snapshot(src) == before
    assert mtimes(src) == stamps
    written = [p for p in repo.rglob("*") if p.is_file()]
    assert len(written) == 6  # note.md, MEMORY.md and four wiring files
    for marker in {str(src), str(src.resolve())}:
        assert all(marker.encode() not in p.read_bytes() for p in written)


@pytest.mark.parametrize("fail", [n for n in ROLLBACK_STAGES if n != "other-fact.md"])
@pytest.mark.parametrize("existing", [False, True], ids=["fresh", "existing-memory"])
def test_apply_rolls_back_every_write_when_a_wiring_write_fails(
    tmp_path: Path,
    src: Path,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    existing: bool,
    fail: str,
) -> None:
    write(src, "note.md", valid())
    write(src, "Other_Fact.md", valid(description="Other"))
    write(repo, ".gitattributes", "*.png binary\n")
    if existing:
        write_target(repo, "good")
        write(memory_dir(repo), "MEMORY.md", "- [good](good.md) — Existing fact\n")
    before = snapshot(tmp_path)
    real = migrate._write_if_changed
    attempted: list[str] = []

    def fail_once(path: Path, data: bytes) -> None:
        attempted.append(Path(path).name)
        if attempted[-1] == fail and attempted.count(fail) == 1:
            raise OSError("disk full")
        real(path, data)

    monkeypatch.setattr("engram.migrate._write_if_changed", fail_once)

    with pytest.raises(MigrationError) as raised:
        apply_migration(src, repo)
    assert str(raised.value).startswith("apply failed, repository restored:")
    assert "disk full" in str(raised.value)
    earlier = set(attempted[: attempted.index(fail)])
    stage = ROLLBACK_STAGES[fail]
    assert {n for n, s in ROLLBACK_STAGES.items() if s < stage} <= earlier
    assert snapshot(tmp_path) == before


def test_apply_rollback_names_paths_it_could_not_restore(
    src: Path,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write(src, "note.md", valid())
    write_target(repo, "good")
    write(memory_dir(repo), "MEMORY.md", "- [good](good.md) — Existing fact\n")
    real = migrate._write_if_changed

    def fail_index(path: Path, data: bytes) -> None:
        if Path(path).name == "MEMORY.md":
            raise OSError("disk full")
        real(path, data)

    monkeypatch.setattr("engram.migrate._write_if_changed", fail_index)

    with pytest.raises(MigrationError) as raised:
        apply_migration(src, repo)
    message = str(raised.value)
    assert message.startswith("apply failed, repository restored: ")
    assert "MEMORY.md" in message[message.index("disk full") + len("disk full") :]


def test_wiring_agents_section_is_short_canonical_and_public_safe(src: Path) -> None:
    lines = AGENTS_SECTION.splitlines()
    assert AGENTS_SECTION.startswith("## Project memory\n")
    assert AGENTS_SECTION.endswith("\n")
    assert 2 <= len(lines) <= 25
    assert [line.strip() for line in lines].count("## Project memory") == 1
    for phrase in (
        DEST,
        "MEMORY.md",
        "evidence",
        "project",
        "feedback",
        "reference",
        "docs(memory): <verb> <slug>",
        "engram memory check",
    ):
        assert phrase in AGENTS_SECTION
    plain = AGENTS_SECTION.lower().replace("`", "")
    assert "read memory.md before" in plain
    for inverted in ("never read", "never run", "do not run", "delete any"):
        assert inverted not in plain
    assert contains_host_path(AGENTS_SECTION, src) is False
    assert redact(AGENTS_SECTION) == AGENTS_SECTION
