import re
from functools import partial
from pathlib import Path

import pytest
import yaml
from _cli_helpers import _init_git_repo, _refuse
from test_cli_index_status import _FakeStoreForStatus

from engram import corpora, transcripts
from engram.cli import main
from engram.client import EmbeddingEntry, EngramConfig, Vector
from engram.corpora import CorpusFile, enumerate_corpora
from engram.indexer import index as run_index
from engram.memory import (
    CREDENTIAL_PATTERNS,
    MEMORY_SUBDIR,
    MemoryFile,
    check_directory,
    memory_dir,
    memory_files,
    parse_memory,
    redact,
)
from engram.store import CorpusStatus, Scope, StatusReport, open_store

DROP = object()

# Tokens are assembled at runtime so no literal credential sits in the repo.
GITHUB_TOKEN = "ghp_" + "A1b2C3d4E5" * 3 + "F6g7H8"
GITHUB_PAT = "github_pat_" + "11ABCDEFG0_abcdefghijk"
SK_KEY = "sk-" + "projZ9y8X7w6V5u4T3s2R1q0"
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
SLACK_TOKEN = "xoxb-" + "1234567890-abcdefghij"
PRIVATE_KEY = "-----BEGIN " + "RSA PRIVATE KEY-----"

TOKENS = [
    ("private-key", PRIVATE_KEY),
    ("private-key", "-----BEGIN " + "OPENSSH PRIVATE KEY-----"),
    ("private-key", "-----BEGIN " + "PRIVATE KEY-----"),
    ("private-key", "-----BEGIN " + "EC PRIVATE KEY-----"),
    ("private-key", "-----BEGIN " + "DSA PRIVATE KEY-----"),
    ("github-token", GITHUB_TOKEN),
    ("github-token", "ghp_" + "Z" * 36),
    ("github-pat", GITHUB_PAT),
    ("github-pat", "github_pat_" + "b" * 40),
    ("sk-key", SK_KEY),
    ("sk-key", "sk-" + "Q" * 20),
    ("aws-access-key", AWS_KEY),
    ("aws-access-key", "AKIA" + "Z9Y8X7W6V5U4T3S2"),
    ("slack-token", SLACK_TOKEN),
    ("slack-token", "xoxp-" + "abcdefghijkl"),
    ("slack-token", "xoxa-" + "2-abcdefghij"),
    ("slack-token", "xoxr-" + "abcdefghij12"),
    ("slack-token", "xoxs-" + "0123456789ab"),
]

NEAR_MISSES = [
    "ghp_" + "a" * 35,
    "github_pat_" + "a" * 21,
    "sk-" + "a" * 19,
    "task-tools-flag-until-something",
    "x" + SK_KEY,
    "9" + SK_KEY,
    "AKIA" + "ABCDEFGHIJ12345",
    "xoxb-" + "123456789",
    "-----BEGIN " + "PUBLIC KEY-----",
]


def write_memory(directory, slug, body="Body text.\n", **overrides):
    front = {
        "name": slug,
        "description": "One line about " + slug + ".",
        "type": "project",
        "source": "PRD 00010",
        "evidence": ["src/engram/memory.py"],
    }
    for key, value in overrides.items():
        if value is DROP:
            front.pop(key, None)
        else:
            front[key] = value
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{slug}.md"
    text = "---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n" + body
    path.write_text(text, encoding="utf-8")
    return path


def write_index(directory, lines):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "MEMORY.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def violations_of(path):
    record, violations = parse_memory(path)
    assert record is None
    return violations


# --- constants and paths ---


def test_index_memory_dir_joins_repo_root_with_memory_subdir_without_existence_check():
    assert MEMORY_SUBDIR == ("docs", "dev", "project-management", "memory")
    assert memory_dir(Path("/repos/alpha")) == Path(
        "/repos/alpha/docs/dev/project-management/memory",
    )
    assert memory_dir(Path("/srv/beta")) == Path(
        "/srv/beta/docs/dev/project-management/memory",
    )


def test_credential_patterns_expose_six_labels_in_contract_order():
    labels = [label for label, _ in CREDENTIAL_PATTERNS]

    assert labels == [
        "private-key",
        "github-token",
        "github-pat",
        "sk-key",
        "aws-access-key",
        "slack-token",
    ]


# --- memory_files: sorted *.md regular files directly in dir, minus MEMORY.md ---


def test_index_memory_files_lists_sorted_md_files_excluding_memory_index(tmp_path):
    for name in [
        "beta.md",
        "alpha.md",
        "MEMORY.md",
        "MEMORY-notes.md",
        "notes.txt",
        "notes.mdx",
    ]:
        (tmp_path / name).write_text("x\n", encoding="utf-8")
    (tmp_path / "folder.md").mkdir()
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "inner.md").write_text("x\n", encoding="utf-8")

    assert memory_files(tmp_path) == [
        tmp_path / "MEMORY-notes.md",
        tmp_path / "alpha.md",
        tmp_path / "beta.md",
    ]


def test_index_memory_files_returns_empty_for_empty_missing_or_non_directory(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    regular = tmp_path / "file.md"
    regular.write_text("x\n", encoding="utf-8")

    assert memory_files(empty) == []
    assert memory_files(tmp_path / "absent") == []
    assert memory_files(regular) == []


# --- schema: valid records ---


def test_schema_valid_file_returns_record_with_every_field(tmp_path):
    path = write_memory(
        tmp_path,
        "alpha-note",
        body="First paragraph.\n---\nSecond paragraph.\n",
        description="a --- b",
        evidence=["src/engram/memory.py", "tests/test_repo_memory.py"],
    )

    record, violations = parse_memory(path)

    assert violations == []
    assert record == MemoryFile(
        slug="alpha-note",
        name="alpha-note",
        description="a --- b",
        type="project",
        source="PRD 00010",
        evidence=("src/engram/memory.py", "tests/test_repo_memory.py"),
        body=record.body,
    )
    assert record.body.strip() == "First paragraph.\n---\nSecond paragraph."
    assert "---" in record.body.splitlines()


def test_schema_accepts_claude_metadata_type_when_top_level_type_absent(tmp_path):
    path = write_memory(
        tmp_path,
        "0day",
        body="Other body.\n",
        type=DROP,
        description="Claude style memory.",
        source="session 2026-11-09",
        evidence=["docs/x.md"],
        metadata={"type": "feedback", "origin": "claude"},
    )

    record, violations = parse_memory(path)

    assert violations == []
    assert record.slug == "0day"
    assert record.type == "feedback"
    assert record.description == "Claude style memory."
    assert record.source == "session 2026-11-09"
    assert record.evidence == ("docs/x.md",)
    assert record.body.strip() == "Other body."


@pytest.mark.parametrize("memory_type", ["project", "feedback", "reference"])
def test_schema_accepts_each_allowed_type(tmp_path, memory_type):
    record, violations = parse_memory(write_memory(tmp_path, "alpha", type=memory_type))

    assert violations == []
    assert record.type == memory_type


def test_schema_top_level_type_wins_over_invalid_metadata_type(tmp_path):
    path = write_memory(tmp_path, "alpha", type="reference", metadata={"type": "bogus"})

    record, violations = parse_memory(path)

    assert violations == []
    assert record.type == "reference"


def test_schema_description_with_only_trailing_newline_is_one_line(tmp_path):
    path = tmp_path / "alpha.md"
    path.write_text(
        "---\nname: alpha\ndescription: >\n  folded single line\n"
        "type: project\nsource: s\nevidence:\n  - e\n---\nbody\n",
        encoding="utf-8",
    )

    record, violations = parse_memory(path)

    assert violations == []
    assert record.description.strip() == "folded single line"


# --- schema: read and frontmatter violations suppress field checks ---


def test_schema_unreadable_file_reports_read_violation_with_exception_class(tmp_path):
    bad_utf8 = tmp_path / "alpha.md"
    bad_utf8.write_bytes(b"---\nname: alpha\n\xff\x80\n---\n")
    as_dir = tmp_path / "beta.md"
    as_dir.mkdir()

    assert violations_of(bad_utf8) == ["read\tunreadable: UnicodeDecodeError"]
    assert violations_of(as_dir) == ["read\tunreadable: IsADirectoryError"]
    assert violations_of(tmp_path / "gone.md") == [
        "read\tunreadable: FileNotFoundError",
    ]


@pytest.mark.parametrize(
    ("text", "detail"),
    [
        ("", "missing"),
        ("name: alpha\n---\nbody\n", "missing"),
        ("\n---\nname: alpha\n---\nbody\n", "missing"),
        ("---\nname: alpha\ndescription: d\n", "unterminated"),
        ("---\nname: [unclosed\n---\nbody\n", "unparseable"),
        ("---\nname: alpha\nsource: 2026-13-45\n---\nbody\n", "unparseable"),
        ("---\n- a\n- b\n---\nbody\n", "not a mapping"),
        ("---\njust a scalar\n---\nbody\n", "not a mapping"),
    ],
)
def test_schema_frontmatter_violation_suppresses_field_checks(tmp_path, text, detail):
    path = tmp_path / "alpha.md"
    path.write_text(text, encoding="utf-8")

    assert violations_of(path) == [f"frontmatter\t{detail}"]


# --- schema: field rules (one violation per fixture) ---


@pytest.mark.parametrize(
    ("slug", "overrides", "expected"),
    [
        ("alpha", {"name": DROP}, "name\tmissing"),
        ("alpha", {"name": 123}, "name\tmissing"),
        ("Alpha_Note", {}, "name\tmust match ^[a-z0-9][a-z0-9-]*$"),
        ("-lead", {}, "name\tmust match ^[a-z0-9][a-z0-9-]*$"),
        ("alpha", {"name": "alpha-2"}, "name\tdoes not match file stem alpha"),
        ("beta-9", {"name": "beta"}, "name\tdoes not match file stem beta-9"),
        ("alpha", {"description": DROP}, "description\tmissing"),
        ("alpha", {"description": 42}, "description\tmissing"),
        ("alpha", {"description": ""}, "description\tempty"),
        ("alpha", {"description": "   "}, "description\tempty"),
        (
            "alpha",
            {"description": "line one\nline two"},
            "description\tmust be one line",
        ),
        ("alpha", {"type": DROP}, "type\tmissing"),
        ("alpha", {"type": DROP, "metadata": {"kind": "project"}}, "type\tmissing"),
        ("alpha", {"type": DROP, "metadata": "project"}, "type\tmissing"),
        (
            "alpha",
            {"type": "note"},
            "type\tmust be one of feedback, project, reference",
        ),
        (
            "alpha",
            {"type": "projects"},
            "type\tmust be one of feedback, project, reference",
        ),
        (
            "alpha",
            {"type": "note", "metadata": {"type": "project"}},
            "type\tmust be one of feedback, project, reference",
        ),
        ("alpha", {"type": "user"}, "type\tuser memory belongs in host-global memory"),
        (
            "alpha",
            {"type": DROP, "metadata": {"type": "user"}},
            "type\tuser memory belongs in host-global memory",
        ),
        ("alpha", {"source": DROP}, "source\tmissing"),
        ("alpha", {"source": ["PRD 00010"]}, "source\tmissing"),
        ("alpha", {"source": ""}, "source\tempty"),
        ("alpha", {"source": "  "}, "source\tempty"),
        ("alpha", {"evidence": DROP}, "evidence\tmissing"),
        ("alpha", {"evidence": "src/engram/memory.py"}, "evidence\tmust be a list"),
        ("alpha", {"evidence": []}, "evidence\tempty"),
        (
            "alpha",
            {"evidence": ["src/a.py", "  "]},
            "evidence\titem 1 empty or not a string",
        ),
        (
            "alpha",
            {"evidence": [5, "src/a.py"]},
            "evidence\titem 0 empty or not a string",
        ),
    ],
)
def test_schema_field_rule_reports_exact_violation(tmp_path, slug, overrides, expected):
    path = write_memory(tmp_path, slug, **overrides)

    assert violations_of(path) == [expected]


def test_schema_unknown_extra_keys_and_near_miss_forbidden_keys_are_allowed(tmp_path):
    path = write_memory(
        tmp_path,
        "alpha",
        authors=["a"],
        dated="2026",
        author_note="x",
        metadata={"type": "project", "role": "author", "nested": [{"dates": 1}]},
    )

    record, violations = parse_memory(path)

    assert violations == []
    assert record.name == "alpha"


def test_schema_forbidden_keys_reported_at_every_depth_with_dotted_path(tmp_path):
    path = write_memory(
        tmp_path,
        "alpha",
        author="someone",
        metadata={"type": "project", "date": "2026-11-10"},
        extra=[[{"author": "x"}], {"inner": {"author": "x"}}],
    )

    assert sorted(violations_of(path)) == sorted(
        [
            "forbidden-key\tauthor: Git records it",
            "forbidden-key\tmetadata.date: Git records it",
            "forbidden-key\textra.0.0.author: Git records it",
            "forbidden-key\textra.1.inner.author: Git records it",
        ],
    )


def test_schema_forbidden_key_inside_list_item_uses_zero_based_index(tmp_path):
    path = write_memory(tmp_path, "alpha", extra=[{"date": "d"}])

    assert violations_of(path) == ["forbidden-key\textra.0.date: Git records it"]


def test_schema_cyclic_yaml_alias_does_not_recurse_forever(tmp_path):
    path = tmp_path / "alpha.md"
    path.write_text(
        "---\nname: alpha\ndescription: d\ntype: project\nsource: s\n"
        "evidence:\n  - e\n"
        "extra: &loop\n  self: *loop\n  author: someone\n"
        "---\nbody\n",
        encoding="utf-8",
    )

    assert violations_of(path) == ["forbidden-key\textra.author: Git records it"]


def test_schema_field_values_are_never_echoed_in_details(tmp_path):
    path = write_memory(
        tmp_path,
        "alpha",
        name="zz-unique-name-value",
        type="zz-unique-type-value",
    )

    violations = violations_of(path)

    assert "name\tdoes not match file stem alpha" in violations
    assert "type\tmust be one of feedback, project, reference" in violations
    assert not any("zz-unique" in v for v in violations)


# --- credential: redact() ---


@pytest.mark.parametrize(("label", "token"), TOKENS)
def test_credential_redact_replaces_token_with_label_marker(label, token):
    assert redact(f"before {token} after") == f"before [redacted:{label}] after"


def test_credential_redact_replaces_every_token_and_keeps_surrounding_text():
    text = f"a={GITHUB_TOKEN}\nb={AWS_KEY} c={GITHUB_TOKEN}"

    assert redact(text) == (
        "a=[redacted:github-token]\nb=[redacted:aws-access-key] c=[redacted:github-token]"
    )


def test_credential_redact_leaves_clean_and_near_miss_text_unchanged():
    clean = "\n".join(NEAR_MISSES)

    assert redact(clean) == clean
    assert redact("") == ""


def test_credential_sk_key_matches_at_line_start_and_after_separators():
    assert redact(SK_KEY + " tail") == "[redacted:sk-key] tail"
    assert redact("key=" + SK_KEY) == "key=[redacted:sk-key]"
    assert redact("risk-" + "a" * 25) == "risk-" + "a" * 25
    assert redact('"' + SK_KEY + '"') == '"[redacted:sk-key]"'
    assert redact("key:" + SK_KEY) == "key:[redacted:sk-key]"
    assert redact("(" + SK_KEY) == "([redacted:sk-key]"


# --- credential: parse_memory scan ---


def test_credential_in_body_blocks_record_and_reports_label_only(tmp_path):
    path = write_memory(tmp_path, "alpha", body=f"token {GITHUB_TOKEN}\n")

    violations = violations_of(path)

    assert violations == ["credential\tgithub-token"]
    assert not any(GITHUB_TOKEN in v for v in violations)


def test_credential_near_misses_in_body_still_return_record(tmp_path):
    path = write_memory(tmp_path, "alpha", body="\n".join(NEAR_MISSES) + "\n")

    record, violations = parse_memory(path)

    assert violations == []
    assert "task-tools-flag-until-something" in record.body


def test_credential_one_violation_per_matching_label(tmp_path):
    body = f"{GITHUB_TOKEN}\n{GITHUB_TOKEN}\nkey={SK_KEY}\n{AWS_KEY}\n"
    path = write_memory(tmp_path, "alpha", body=body)

    assert sorted(violations_of(path)) == [
        "credential\taws-access-key",
        "credential\tgithub-token",
        "credential\tsk-key",
    ]


def test_credential_scan_runs_when_frontmatter_missing(tmp_path):
    path = tmp_path / "alpha.md"
    path.write_text(f"no frontmatter\n{AWS_KEY}\n", encoding="utf-8")

    assert violations_of(path) == ["frontmatter\tmissing", "credential\taws-access-key"]


def test_credential_in_name_field_never_appears_in_details(tmp_path):
    path = write_memory(tmp_path, "alpha", name=SK_KEY.lower())

    violations = violations_of(path)

    assert violations == ["name\tdoes not match file stem alpha", "credential\tsk-key"]
    assert not any(SK_KEY.lower() in v for v in violations)


# --- check_directory: per-file and directory rules ---


def test_index_check_directory_reports_missing_directory(tmp_path):
    regular = tmp_path / "file.md"
    regular.write_text("x\n", encoding="utf-8")

    assert check_directory(tmp_path / "absent") == [
        f"{tmp_path / 'absent'}\tdirectory\tnot found",
    ]
    assert check_directory(regular) == [f"{regular}\tdirectory\tnot found"]


def test_index_check_directory_clean_when_every_file_indexed_and_valid(tmp_path):
    directory = tmp_path / "elsewhere"
    write_memory(directory, "alpha")
    write_memory(directory, "beta")
    write_index(
        directory,
        [
            "# Memory index",
            "",
            "Prose about these memories.",
            "- [Alpha note](alpha.md) — trailing hook text",
            "- [Beta](beta.md)",
            "* [Star bullet](ghost.md)",
            "-[No space](ghost.md)",
            "  - [Indented](ghost.md)",
            "- [Nested](sub/ghost.md)",
        ],
    )

    assert check_directory(directory) == []


def test_index_check_directory_empty_directory_has_no_violations(tmp_path):
    assert check_directory(tmp_path) == []


def test_index_check_directory_prefixes_per_file_violations_with_passed_path(tmp_path):
    directory = tmp_path / "custom-dir"
    write_memory(directory, "alpha", description=DROP)
    write_memory(directory, "beta", source="")
    write_index(directory, ["- [Alpha](alpha.md)", "- [Beta](beta.md)"])

    assert check_directory(directory) == [
        f"{directory / 'alpha.md'}\tdescription\tmissing",
        f"{directory / 'beta.md'}\tsource\tempty",
    ]


# --- check_directory: MEMORY.md index rules ---


def test_index_missing_file_reported_for_entry_without_memory_file(tmp_path):
    write_memory(tmp_path, "alpha")
    index = write_index(tmp_path, ["- [Alpha](alpha.md)", "- [Alpha X](alpha-x.md)"])

    assert check_directory(tmp_path) == [f"{index}\tindex-missing-file\talpha-x.md"]


def test_index_missing_entry_reported_on_the_memory_file_path(tmp_path):
    write_memory(tmp_path, "alpha")
    write_memory(tmp_path, "alpha-2")
    write_index(tmp_path, ["- [Alpha](alpha.md)"])

    assert check_directory(tmp_path) == [
        f"{tmp_path / 'alpha-2.md'}\tindex-missing-entry\talpha-2.md",
    ]


def test_index_absent_reports_only_missing_entry_for_every_file(tmp_path):
    write_memory(tmp_path, "alpha")
    write_memory(tmp_path, "beta")

    assert check_directory(tmp_path) == [
        f"{tmp_path / 'alpha.md'}\tindex-missing-entry\talpha.md",
        f"{tmp_path / 'beta.md'}\tindex-missing-entry\tbeta.md",
    ]


def test_index_duplicate_reported_once_per_duplicated_slug(tmp_path):
    write_memory(tmp_path, "alpha")
    write_memory(tmp_path, "beta")
    write_memory(tmp_path, "gamma")
    index = write_index(
        tmp_path,
        [
            "- [A](alpha.md)",
            "- [A again](alpha.md)",
            "- [A third](alpha.md)",
            "- [B](beta.md)",
            "- [B again](beta.md)",
            "- [G](gamma.md)",
        ],
    )

    assert check_directory(tmp_path) == [
        f"{index}\tindex-duplicate\talpha.md",
        f"{index}\tindex-duplicate\tbeta.md",
    ]


def test_index_unsorted_reported_when_entries_out_of_slug_order(tmp_path):
    write_memory(tmp_path, "alpha")
    write_memory(tmp_path, "beta")
    index = write_index(tmp_path, ["- [Zed title](beta.md)", "- [Aaa title](alpha.md)"])

    assert check_directory(tmp_path) == [
        f"{index}\tindex-unsorted\tentries must be sorted by slug",
    ]


def test_index_unsorted_counts_duplicates_in_file_order(tmp_path):
    write_memory(tmp_path, "alpha")
    write_memory(tmp_path, "beta")
    index = write_index(
        tmp_path,
        ["- [A](alpha.md)", "- [B](beta.md)", "- [A](alpha.md)"],
    )

    assert check_directory(tmp_path) == [
        f"{index}\tindex-duplicate\talpha.md",
        f"{index}\tindex-unsorted\tentries must be sorted by slug",
    ]


@pytest.mark.parametrize(
    ("total_lines", "final_newline", "expected"),
    [
        (200, True, []),
        (201, True, ["201 lines > 200"]),
        (250, True, ["250 lines > 200"]),
        (200, False, []),
        (201, False, ["201 lines > 200"]),
    ],
)
def test_index_too_long_flags_more_than_200_lines(
    tmp_path,
    total_lines,
    final_newline,
    expected,
):
    write_memory(tmp_path, "alpha")
    lines = ["# Memory", "- [Alpha](alpha.md)"] + ["prose"] * (total_lines - 2)
    index = tmp_path / "MEMORY.md"
    text = "\n".join(lines) + ("\n" if final_newline else "")
    index.write_text(text, encoding="utf-8")

    assert check_directory(tmp_path) == [
        f"{index}\tindex-too-long\t{d}" for d in expected
    ]


@pytest.mark.parametrize(
    ("total_bytes", "flagged"),
    [(25_000, False), (25_001, True), (25_900, True)],
)
def test_index_too_large_counts_raw_bytes_not_characters(
    tmp_path,
    total_bytes,
    flagged,
):
    write_memory(tmp_path, "alpha")
    base = "# Memory\n- [Alpha](alpha.md)\n"
    fill = total_bytes - len(base.encode("utf-8")) - 1
    text = base + "é" * (fill // 2) + "x" * (fill % 2) + "\n"
    assert len(text.encode("utf-8")) == total_bytes
    index = tmp_path / "MEMORY.md"
    index.write_text(text, encoding="utf-8")

    expected = (
        [f"{index}\tindex-too-large\t{total_bytes} bytes > 25000"] if flagged else []
    )
    assert check_directory(tmp_path) == expected


def test_index_too_long_precedes_too_large(tmp_path):
    write_memory(tmp_path, "alpha")
    lines = ["- [Alpha](alpha.md)"] + ["y" * 200] * 210
    index = write_index(tmp_path, lines)
    size = len(index.read_bytes())

    assert check_directory(tmp_path) == [
        f"{index}\tindex-too-long\t211 lines > 200",
        f"{index}\tindex-too-large\t{size} bytes > 25000",
    ]


@pytest.mark.parametrize(
    ("as_directory", "error"),
    [(False, "UnicodeDecodeError"), (True, "IsADirectoryError")],
)
def test_index_unreadable_memory_index_reports_read_only(
    tmp_path,
    as_directory,
    error,
):
    write_memory(tmp_path, "alpha", description=DROP)
    index = tmp_path / "MEMORY.md"
    if as_directory:
        index.mkdir()
    else:
        index.write_bytes(b"# Memory\n\xff\x80\n- [Ghost](ghost.md)\n")

    assert check_directory(tmp_path) == [
        f"{tmp_path / 'alpha.md'}\tdescription\tmissing",
        f"{index}\tread\tunreadable: {error}",
    ]


def test_index_violation_order_is_files_then_index_credential_then_index_rules(
    tmp_path,
):
    write_memory(tmp_path, "alpha", description=DROP, body=f"{SK_KEY}\n")
    write_memory(tmp_path, "beta")
    index = write_index(
        tmp_path,
        [
            f"Leaked {GITHUB_TOKEN} here.",
            "- [Ghost](ghost.md)",
            "- [Alpha](alpha.md)",
            "- [Alpha again](alpha.md)",
        ],
    )

    assert check_directory(tmp_path) == [
        f"{tmp_path / 'alpha.md'}\tdescription\tmissing",
        f"{tmp_path / 'alpha.md'}\tcredential\tsk-key",
        f"{index}\tcredential\tgithub-token",
        f"{index}\tindex-missing-file\tghost.md",
        f"{tmp_path / 'beta.md'}\tindex-missing-entry\tbeta.md",
        f"{index}\tindex-duplicate\talpha.md",
        f"{index}\tindex-unsorted\tentries must be sorted by slug",
    ]


# --- credential: check_directory never leaks a token ---


def test_credential_slug_in_index_entry_is_redacted(tmp_path):
    index = write_index(tmp_path, [f"- [Key]({GITHUB_TOKEN}.md)"])

    output = check_directory(tmp_path)

    assert output == [
        f"{index}\tcredential\tgithub-token",
        f"{index}\tindex-missing-file\t[redacted:github-token].md",
    ]
    assert not any(GITHUB_TOKEN in line for line in output)


def test_credential_in_file_name_is_redacted_in_file_column_and_detail(tmp_path):
    slug = SK_KEY.lower()
    write_memory(tmp_path, slug)

    output = check_directory(tmp_path)

    redacted_path = f"{tmp_path}/[redacted:sk-key].md"
    assert output == [
        f"{redacted_path}\tcredential\tsk-key",
        f"{redacted_path}\tindex-missing-entry\t[redacted:sk-key].md",
    ]
    assert not any(slug in line for line in output)


# --- corpora: repository memory enumeration and legacy shadowing ---

SIDE_CHANNELS = ("missing_dirs", "repo_memory_dirs", "legacy_shadowed")


def legacy_dir(projects, repo_path):
    return projects / re.sub(r"[^a-zA-Z0-9]", "-", str(repo_path)) / "memory"


def write_notes(directory, *names, text="# Note\nmarker\n"):
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_text(text, encoding="utf-8")
    return [directory / name for name in names]


def write_registry(path, rows):
    path.write_text("".join(f"{root},{name}\n" for root, name in rows), "utf-8")
    return path


def files_of(files, repo):
    return [f for f in files if f.repo == repo]


def legacy_file(projects, repo_path, name):
    return legacy_dir(projects, repo_path).resolve() / name


@pytest.fixture
def side_channels(monkeypatch):
    for name in SIDE_CHANNELS:
        monkeypatch.setattr(corpora, name, [])


@pytest.fixture
def portfolio(tmp_path, side_channels):
    repos, projects = tmp_path / "repos", tmp_path / "projects"
    repos.mkdir()
    (tmp_path / "real-alpha").mkdir()
    (repos / "alpha").symlink_to(tmp_path / "real-alpha")
    paths = {n: repos / n for n in ("alpha", "beta", "gamma", "delta", "omega")}
    paths["first"], paths["second"] = tmp_path / "c/a/b", tmp_path / "c/a-b"
    write_notes(memory_dir(paths["alpha"]), "zeta-note.md", "alpha-note.md")
    write_notes(memory_dir(paths["alpha"]), "broken.md", text="no frontmatter\n")
    write_notes(memory_dir(paths["alpha"]), "MEMORY.md", text="- [Z](zeta-note.md)\n")
    write_notes(memory_dir(paths["alpha"]), "notes.txt", "x.mdx")
    write_notes(memory_dir(paths["alpha"]) / "sub", "nested.md")
    write_notes(memory_dir(paths["beta"]), "beta-note.md")
    write_notes(memory_dir(paths["gamma"]), "MEMORY.md")
    paths["delta"].mkdir()
    memory_dir(paths["omega"]).parent.mkdir(parents=True)
    memory_dir(paths["omega"]).write_text("not a directory\n", encoding="utf-8")
    write_notes(memory_dir(paths["first"]), "first.md")
    paths["empty"] = repos / "empty"
    memory_dir(paths["empty"]).mkdir(parents=True)
    write_notes(legacy_dir(projects, paths["alpha"]), "old.md")
    write_notes(legacy_dir(projects, paths["beta"]), "MEMORY.md")
    for repo in ("gamma", "delta", "omega"):
        write_notes(legacy_dir(projects, paths[repo]), f"{repo}-old.md")
    write_notes(legacy_dir(projects, paths["first"]), "shared.md")
    write_notes(legacy_dir(projects, f"{paths['alpha']}-old"), "kept.md")
    registry = write_registry(tmp_path / "repos.csv", [(paths[n], n) for n in paths])
    return registry, projects, paths


def test_enumerate_yields_repo_memory_per_repo_unresolved_without_memory_index(
    portfolio,
):
    registry, projects, paths = portfolio

    files = list(enumerate_corpora(registry, projects))

    alpha = memory_dir(paths["alpha"])
    assert files_of(files, "alpha") == [
        CorpusFile("memory", "alpha", alpha / name)
        for name in ("alpha-note.md", "broken.md", "zeta-note.md")
    ]
    assert files_of(files, "beta") == [
        CorpusFile("memory", "beta", memory_dir(paths["beta"]) / "beta-note.md"),
    ]
    assert files_of(files, "first") == [
        CorpusFile("memory", "first", memory_dir(paths["first"]) / "first.md"),
    ]
    assert files_of(files, "second") == []
    assert not any(f.path.name == "MEMORY.md" for f in files)


def test_enumerate_legacy_skips_shadowed_slugs_and_keeps_others(portfolio):
    registry, projects, paths = portfolio

    files = list(enumerate_corpora(registry, projects))

    for repo in ("gamma", "delta", "omega"):
        assert files_of(files, repo) == [
            CorpusFile(
                "memory",
                repo,
                legacy_file(projects, paths[repo], f"{repo}-old.md"),
            ),
        ]
    assert sorted(f.path for f in files_of(files, "_unmapped")) == sorted(
        [
            legacy_file(projects, paths["first"], "shared.md"),
            legacy_file(projects, f"{paths['alpha']}-old", "kept.md"),
        ],
    )
    shadowed = {
        legacy_dir(projects, paths[repo]).resolve() for repo in ("alpha", "beta")
    }
    assert not any(f.path.parent in shadowed for f in files)
    assert [(f.repo, f.path.name) for f in files] == [
        ("_unmapped", "shared.md"),
        ("_unmapped", "kept.md"),
        ("delta", "delta-old.md"),
        ("gamma", "gamma-old.md"),
        ("omega", "omega-old.md"),
        ("alpha", "alpha-note.md"),
        ("alpha", "broken.md"),
        ("alpha", "zeta-note.md"),
        ("beta", "beta-note.md"),
        ("first", "first.md"),
    ]


def test_enumerate_records_repo_memory_dirs_and_legacy_shadowed(portfolio):
    registry, projects, paths = portfolio

    list(enumerate_corpora(registry, projects))

    assert sorted(corpora.repo_memory_dirs) == [
        (name, memory_dir(paths[name]))
        for name in ("alpha", "beta", "empty", "first", "gamma")
    ]
    assert corpora.legacy_shadowed == ["alpha", "beta"]


def test_enumerate_legacy_shadowed_is_sorted_deduped_and_needs_a_legacy_md_file(
    tmp_path,
    side_channels,
):
    root, projects = tmp_path / "r", tmp_path / "projects"
    rows = [
        (root / "one", "zulu"),
        (root / "two", "dup"),
        (root / "three", "dup"),
        (root / "four", "able"),
        (root / "five", "bravo"),
        (root / "six", "alpha"),
        (root / "seven", "charlie"),
        (root / "eight", "dup"),
    ]
    for name in ("one", "two", "four", "five", "eight"):
        write_notes(memory_dir(root / name), "note.md")
    write_notes(memory_dir(root / "seven"), "MEMORY.md")
    for name in ("two", "three", "six", "seven", "eight"):
        write_notes(legacy_dir(projects, root / name), "legacy.md")
    write_notes(legacy_dir(projects, root / "one"), "MEMORY.md")
    write_notes(legacy_dir(projects, root / "four"), "notes.txt", "notes.mdx")
    write_notes(legacy_dir(projects, root / "four") / "sub", "x.md")
    registry = write_registry(tmp_path / "repos.csv", rows)

    files = list(enumerate_corpora(registry, projects))

    assert corpora.legacy_shadowed == ["dup", "zulu"]
    legacy = [
        (f.repo, f.path) for f in files if f.path.is_relative_to(projects.resolve())
    ]
    assert legacy == [
        (repo, legacy_file(projects, root / name, "legacy.md"))
        for name, repo in (("seven", "charlie"), ("six", "alpha"), ("three", "dup"))
    ]


def test_enumerate_absent_repo_memory_dir_adds_no_missing_dirs_entry(
    tmp_path,
    side_channels,
):
    root, projects = tmp_path / "repo", tmp_path / "projects"
    root.mkdir()
    projects.mkdir()
    registry = write_registry(tmp_path / "repos.csv", [(root, "solo")])

    assert list(enumerate_corpora(registry, projects)) == []
    absent = list(corpora.missing_dirs)
    assert not any(e.startswith("memory:") for e in absent)
    assert corpora.repo_memory_dirs == []

    write_notes(memory_dir(root), "note.md")
    files = list(enumerate_corpora(registry, projects))

    assert files == [CorpusFile("memory", "solo", memory_dir(root) / "note.md")]
    assert corpora.missing_dirs == absent
    assert corpora.repo_memory_dirs == [("solo", memory_dir(root))]


def test_enumerate_clears_side_channels_in_place_on_each_run(tmp_path, monkeypatch):
    stale = {name: [f"stale-{name}"] for name in SIDE_CHANNELS}
    for name, value in stale.items():
        monkeypatch.setattr(corpora, name, value)
    root, projects = tmp_path / "repo", tmp_path / "projects"
    write_notes(memory_dir(root), "note.md")
    (legacy,) = write_notes(legacy_dir(projects, root), "legacy.md")
    registry = write_registry(tmp_path / "repos.csv", [(root, "solo")])

    list(enumerate_corpora(registry, projects))
    list(enumerate_corpora(registry, projects))

    assert stale["repo_memory_dirs"] == [("solo", memory_dir(root))]
    assert stale["legacy_shadowed"] == ["solo"]
    assert "stale-missing_dirs" not in stale["missing_dirs"]

    registry.write_text("", encoding="utf-8")
    files = list(enumerate_corpora(registry, projects))

    assert files == [CorpusFile("memory", "_unmapped", legacy.resolve())]
    assert stale["repo_memory_dirs"] == []
    assert stale["legacy_shadowed"] == []


@pytest.fixture
def index_store(tmp_path):
    db = open_store(tmp_path / "engram.db")
    yield db
    db.conn.close()


def fake_embed(texts, entry):
    return [Vector([1.0, 0.0], entry.id, 2) for _ in texts]


def test_enumerate_incremental_index_replaces_shadowed_legacy_rows_with_repo_memory(
    tmp_path,
    side_channels,
    index_store,
    monkeypatch,
):
    projects = tmp_path / "projects"
    alpha, beta = tmp_path / "repos" / "alpha", tmp_path / "repos" / "beta"
    registry = write_registry(
        tmp_path / "repos.csv",
        [(alpha, "alpha"), (beta, "beta")],
    )
    write_notes(memory_dir(beta), "MEMORY.md")
    (old,) = write_notes(
        legacy_dir(projects, alpha),
        "old.md",
        text="# Old\nlegacymarker\n",
    )
    (kept,) = write_notes(
        legacy_dir(projects, beta),
        "kept.md",
        text="# Kept\nlegacymarker\n",
    )
    monkeypatch.setattr(
        "engram.indexer.enumerate_corpora",
        partial(enumerate_corpora, registry, projects),
    )
    monkeypatch.setattr("engram.indexer.embed", fake_embed)
    config = EngramConfig(
        embeddings=[EmbeddingEntry("test-model", "http://127.0.0.1:8081/v1")],
        pinned_id="test-model",
        config_path=tmp_path / "config.toml",
    )
    portfolio_scope = Scope("portfolio", None)

    run_index(index_store, config, portfolio_scope, corpus="memory")
    rows = {(c.repo, c.path) for c in index_store.chunks_for_corpus("memory")}
    assert rows == {("alpha", str(old.resolve())), ("beta", str(kept.resolve()))}

    (note,) = write_notes(memory_dir(alpha), "note.md", text="# Note\nrepomarker\n")
    report = run_index(index_store, config, portfolio_scope, corpus="memory")

    assert (report.chunks_added, report.chunks_pruned) == (1, 1)
    rows = {(c.repo, c.path) for c in index_store.chunks_for_corpus("memory")}
    assert rows == {("alpha", str(note)), ("beta", str(kept.resolve()))}
    alpha_scope = Scope("repo", "alpha")
    assert index_store.search_bm25("legacymarker", alpha_scope, "memory", 10) == []
    hits = index_store.search_bm25("repomarker", alpha_scope, "memory", 10)
    assert [h.chunk.path for h in hits] == [str(note)]
    assert corpora.legacy_shadowed == ["alpha"]


# --- cli_check: engram memory check [PATH] ---

NOT_IN_GIT = "engram memory check: not inside a git worktree; pass PATH"


@pytest.fixture
def no_store(monkeypatch):
    monkeypatch.setattr("engram.cli.open_store", _refuse)
    monkeypatch.setattr("engram.cli.load_config", _refuse)


def run_check(capsys, *argv):
    exit_code = main(["memory", "check", *map(str, argv)])
    captured = capsys.readouterr()
    return exit_code, captured.out.splitlines(), captured.err


def test_cli_check_clean_memory_dir_exits_zero_with_no_output(
    tmp_path,
    capsys,
    no_store,
):
    directory = memory_dir(tmp_path / "repo")
    write_memory(directory, "alpha")
    write_memory(directory, "beta")
    write_index(directory, ["# Memory", "- [Alpha](alpha.md)", "- [Beta](beta.md)"])
    empty = memory_dir(tmp_path / "bare")
    empty.mkdir(parents=True)

    assert run_check(capsys, directory) == (0, [], "")
    assert run_check(capsys, empty) == (0, [], "")


@pytest.mark.parametrize(
    ("overrides", "index", "expected"),
    [
        ({"description": DROP}, None, [("alpha.md", "description\tmissing")]),
        (
            {"type": "user"},
            None,
            [("alpha.md", "type\tuser memory belongs in host-global memory")],
        ),
        (
            {"body": f"t {GITHUB_TOKEN}\n"},
            None,
            [("alpha.md", "credential\tgithub-token")],
        ),
        ({}, ["- [Beta](beta.md)"], [("alpha.md", "index-missing-entry\talpha.md")]),
        (
            {"source": ""},
            ["- [Alpha](alpha.md)", "- [Beta](beta.md)", "- [Ghost](ghost.md)"],
            [
                ("alpha.md", "source\tempty"),
                ("MEMORY.md", "index-missing-file\tghost.md"),
            ],
        ),
    ],
)
def test_cli_check_invalid_fixture_exits_one_and_prints_file_and_rule(
    tmp_path,
    capsys,
    no_store,
    overrides,
    index,
    expected,
):
    directory = memory_dir(tmp_path / "repo")
    write_memory(directory, "alpha", **overrides)
    write_memory(directory, "beta")
    write_index(directory, index or ["- [Alpha](alpha.md)", "- [Beta](beta.md)"])

    exit_code, out, err = run_check(capsys, directory)

    assert exit_code == 1
    assert out == [f"{directory / name}\t{rule}" for name, rule in expected]
    assert err == ""
    assert not any(GITHUB_TOKEN in line for line in out)


def test_cli_check_absent_or_non_memory_target_prints_single_not_found_line(
    tmp_path,
    capsys,
    no_store,
):
    absent_memory = memory_dir(tmp_path / "gone")
    unrelated = tmp_path / "unrelated"
    write_memory(unrelated, "alpha", description=DROP)
    (unrelated / "README.md").write_text("# Readme\n", encoding="utf-8")
    near_miss = tmp_path / "other" / "dev" / "project-management" / "memory"
    write_memory(near_miss, "beta")
    write_index(near_miss, ["- [Beta](beta.md)"])
    docs_notes = tmp_path / "docs" / "notes" / "memory"
    write_memory(docs_notes, "gamma")
    write_index(docs_notes, ["- [Gamma](gamma.md)"])

    for target, expected in [
        (absent_memory, absent_memory),
        (tmp_path / "missing", memory_dir(tmp_path / "missing")),
        (unrelated, memory_dir(unrelated)),
        (near_miss, memory_dir(near_miss)),
        (docs_notes, memory_dir(docs_notes)),
    ]:
        line = f"{expected}\tdirectory\tnot found"
        assert run_check(capsys, target) == (1, [line], "")

    secret = memory_dir(tmp_path / GITHUB_TOKEN)
    exit_code, out, err = run_check(capsys, secret)
    assert (exit_code, err) == (1, "")
    assert out == [f"{redact(str(secret))}\tdirectory\tnot found"]
    assert GITHUB_TOKEN not in out[0]
    assert "[redacted:github-token]" in out[0]


def test_cli_check_explicit_repo_root_or_memory_dir_resolves_to_memory_dir(
    tmp_path,
    capsys,
    no_store,
):
    alpha_repo, memory_repo = tmp_path / "alpha", tmp_path / "memory"
    alpha_dir, named_dir = memory_dir(alpha_repo), memory_dir(memory_repo)
    write_memory(alpha_dir, "alpha", description=DROP)
    write_index(alpha_dir, ["- [Alpha](alpha.md)"])
    write_memory(named_dir, "beta", source="")
    write_index(named_dir, ["- [Beta](beta.md)"])
    write_memory(memory_repo, "stray", type="note")
    alpha_line = f"{alpha_dir / 'alpha.md'}\tdescription\tmissing"
    beta_line = f"{named_dir / 'beta.md'}\tsource\tempty"

    assert run_check(capsys, alpha_repo) == (1, [alpha_line], "")
    assert run_check(capsys, alpha_dir) == (1, [alpha_line], "")
    assert run_check(capsys, memory_repo) == (1, [beta_line], "")
    assert run_check(capsys, named_dir) == (1, [beta_line], "")


def test_cli_check_dot_inside_index_less_memory_dir_checks_that_dir(
    tmp_path,
    capsys,
    monkeypatch,
    no_store,
):
    directory = memory_dir(tmp_path / "repo").resolve()
    write_memory(directory, "alpha")
    write_memory(directory, "beta")
    monkeypatch.chdir(directory)
    expected = (
        1,
        [
            f"{directory / 'alpha.md'}\tindex-missing-entry\talpha.md",
            f"{directory / 'beta.md'}\tindex-missing-entry\tbeta.md",
        ],
        "",
    )

    assert run_check(capsys, ".") == expected
    assert run_check(capsys, "../memory") == expected
    monkeypatch.chdir(tmp_path)
    assert run_check(capsys, "repo") == expected


def test_cli_check_without_path_checks_memory_dir_of_git_toplevel_of_cwd(
    tmp_path,
    capsys,
    monkeypatch,
    no_store,
):
    alpha = _init_git_repo(tmp_path / "alpha")
    beta = _init_git_repo(tmp_path / "beta")
    gamma = _init_git_repo(tmp_path / "gamma")
    write_memory(memory_dir(alpha), "alpha", description=DROP)
    write_index(memory_dir(alpha), ["- [Alpha](alpha.md)"])
    write_memory(memory_dir(beta), "beta")
    write_index(memory_dir(beta), ["- [Beta](beta.md)"])
    write_memory(alpha / "src", "stray", type="note")

    nested = alpha / "pkg" / "deep" / "nested"
    nested.mkdir(parents=True)

    alpha_line = f"{memory_dir(alpha) / 'alpha.md'}\tdescription\tmissing"
    for cwd in (alpha / "src", nested, memory_dir(alpha)):
        monkeypatch.chdir(cwd)
        assert run_check(capsys) == (1, [alpha_line], "")
    monkeypatch.chdir(beta)
    assert run_check(capsys) == (0, [], "")
    monkeypatch.chdir(gamma)
    gamma_line = f"{memory_dir(gamma)}\tdirectory\tnot found"
    assert run_check(capsys) == (1, [gamma_line], "")


def test_cli_check_without_path_outside_git_worktree_fails_with_hint(
    tmp_path,
    capsys,
    monkeypatch,
    no_store,
):
    plain = tmp_path / "plain"
    write_memory(memory_dir(plain), "alpha")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.chdir(plain)

    exit_code, out, err = run_check(capsys)

    assert (exit_code, out) == (1, [])
    assert err.splitlines() == [NOT_IN_GIT]

    repo = _init_git_repo(tmp_path / "r")
    write_memory(memory_dir(repo), "alpha", description=DROP)
    write_index(memory_dir(repo), ["- [Alpha](alpha.md)"])
    monkeypatch.chdir(repo)
    repo_line = f"{memory_dir(repo) / 'alpha.md'}\tdescription\tmissing"
    assert run_check(capsys) == (1, [repo_line], "")


@pytest.mark.parametrize(
    ("argv", "reason"),
    [
        (["bogus"], "invalid choice: 'bogus'"),
        (["check", "a", "b"], "unrecognized arguments: b"),
    ],
)
def test_cli_check_rejects_unknown_memory_subcommand_and_extra_paths(
    capsys,
    no_store,
    argv,
    reason,
):
    with pytest.raises(SystemExit) as raised:
        main(["memory", *argv])

    captured = capsys.readouterr()
    assert raised.value.code == 2
    assert captured.out == ""
    assert reason in captured.err


# --- status: memory invalid and legacy-shadowed lines ---

# Invalid files: alpha/broken, alpha-2/{bad-one,bad-two,broken}, beta/fine2 and
# epsilon/MEMORY.md (index lists a missing ghost.md). b-ok is valid.
STATUS_NOTES = {
    "alpha": [("b-ok", {}), ("broken", {"description": DROP}), ("good", {})],
    "alpha-2": [
        ("bad-one", {"description": DROP, "source": ""}),
        ("bad-two", {"type": "note"}),
        ("broken", {"description": DROP}),
    ],
    "beta": [("fine", {}), ("fine2", {"type": "note"})],
    "delta": [("fine", {})],
    "epsilon": [("fine", {})],
    "omega": [("fine", {})],
}
STATUS_INDEX_ONLY = {"epsilon": ["ghost"]}
STATUS_LEGACY = ("alpha", "alpha-2", "delta", "gamma", "omega")
STALE_REPORT = StatusReport(
    per_corpus={"docs": CorpusStatus(row_count=1, stale_files=["a.md"], dead_rows=0)},
)


@pytest.fixture
def status_run(tmp_path, side_channels, monkeypatch, capsys):
    repos, projects = tmp_path / "repos", tmp_path / "projects"
    for name, notes in STATUS_NOTES.items():
        for slug, overrides in notes:
            write_memory(memory_dir(repos / name), slug, **overrides)
        slugs = sorted([s for s, _ in notes] + STATUS_INDEX_ONLY.get(name, []))
        write_index(memory_dir(repos / name), [f"- [{s}]({s}.md)" for s in slugs])
    for name in STATUS_LEGACY:
        write_notes(legacy_dir(projects, repos / name), "old.md")
    monkeypatch.setattr("engram.cli.symbols.count_excluded", lambda: 0)
    monkeypatch.setattr(transcripts, "enumerate", lambda *a, **k: iter([]))
    seen = []

    def run(
        scope,
        names=(*STATUS_NOTES, "gamma"),
        rows=None,
        report=None,
        skipped=0,
        keep="memory\t",
    ):
        report = StatusReport(per_corpus={}) if report is None else report
        rows = [(repos / n, n) for n in names] if rows is None else rows
        registry = write_registry(tmp_path / "repos.csv", rows)
        monkeypatch.setattr("engram.cli.GITA_REPOS_CSV", registry)
        monkeypatch.setattr("engram.cli._resolve_repo_name", lambda: scope)
        monkeypatch.setattr(
            "engram.cli.open_store",
            lambda *a, **k: _FakeStoreForStatus(report),
        )
        monkeypatch.setattr(
            "engram.cli.symbols.count_skipped",
            lambda *a, **k: skipped,
            raising=False,
        )

        def recording_enumerate(*args, **kwargs):
            for corpus_file in enumerate_corpora(registry, projects):
                seen.append(corpus_file)
                yield corpus_file

        monkeypatch.setattr("engram.cli.enumerate_corpora", recording_enumerate)
        exit_code = main(["status", "--scope", "repo" if scope else "portfolio"])
        out = capsys.readouterr().out.splitlines()
        return exit_code, [line for line in out if line.startswith(keep)]

    return run, repos, seen


def test_status_portfolio_counts_distinct_invalid_files_and_lists_shadowed(status_run):
    run, repos, seen = status_run

    result = run(None)

    broken = memory_dir(repos / "alpha") / "broken.md"
    assert CorpusFile("memory", "alpha", broken) in seen
    assert result == (
        1,
        [
            "memory\tinvalid=6",
            "memory\tlegacy-shadowed=alpha",
            "memory\tlegacy-shadowed=alpha-2",
            "memory\tlegacy-shadowed=delta",
            "memory\tlegacy-shadowed=omega",
        ],
    )
    exit_code, lines = run(None, skipped=2, keep=("memory\tinvalid", "code\tskipped"))
    assert exit_code == 1
    assert sorted(lines) == ["code\tskipped=2", "memory\tinvalid=6"]


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        ("alpha", (1, ["memory\tinvalid=1", "memory\tlegacy-shadowed=alpha"])),
        ("alpha-2", (1, ["memory\tinvalid=3", "memory\tlegacy-shadowed=alpha-2"])),
        ("beta", (1, ["memory\tinvalid=1"])),
        ("epsilon", (1, ["memory\tinvalid=1"])),
        ("gamma", (0, [])),
    ],
)
def test_status_repo_scope_reports_only_that_repos_memory_lines(
    status_run,
    scope,
    expected,
):
    run, _, _ = status_run

    assert run(scope) == expected


def test_status_legacy_shadowed_alone_prints_line_and_keeps_exit_zero(status_run):
    run, _, _ = status_run

    assert run("delta") == (0, ["memory\tlegacy-shadowed=delta"])
    assert run(None, names=("delta", "omega")) == (
        0,
        ["memory\tlegacy-shadowed=delta", "memory\tlegacy-shadowed=omega"],
    )
    assert run(None, names=()) == (0, [])
    # valid memory never clears the failure owed to stale index rows
    assert run("delta", report=STALE_REPORT) == (1, ["memory\tlegacy-shadowed=delta"])


def test_status_duplicate_registry_rows_count_shared_invalid_file_once(status_run):
    run, repos, _ = status_run
    alpha = repos / "alpha"

    exit_code, lines = run(None, rows=[(alpha, "alpha"), (alpha, "alpha")])

    assert corpora.repo_memory_dirs.count(("alpha", memory_dir(alpha))) == 2
    assert exit_code == 1
    assert [line for line in lines if "invalid" in line] == ["memory\tinvalid=1"]
    renamed = run(None, rows=[(alpha, "alpha"), (alpha, "alpha-copy")])
    assert renamed[0] == 1
    assert [line for line in renamed[1] if "invalid" in line] == ["memory\tinvalid=1"]
