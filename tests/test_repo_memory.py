from pathlib import Path

import pytest
import yaml
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
        "/repos/alpha/docs/dev/project-management/memory"
    )
    assert memory_dir(Path("/srv/beta")) == Path(
        "/srv/beta/docs/dev/project-management/memory"
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
        "read\tunreadable: FileNotFoundError"
    ]


@pytest.mark.parametrize(
    ("text", "detail"),
    [
        ("", "missing"),
        ("name: alpha\n---\nbody\n", "missing"),
        ("\n---\nname: alpha\n---\nbody\n", "missing"),
        ("---\nname: alpha\ndescription: d\n", "unterminated"),
        ("---\nname: [unclosed\n---\nbody\n", "unparseable"),
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
        ]
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
        f"{tmp_path / 'absent'}\tdirectory\tnot found"
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
        f"{tmp_path / 'alpha-2.md'}\tindex-missing-entry\talpha-2.md"
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
        f"{index}\tindex-unsorted\tentries must be sorted by slug"
    ]


def test_index_unsorted_counts_duplicates_in_file_order(tmp_path):
    write_memory(tmp_path, "alpha")
    write_memory(tmp_path, "beta")
    index = write_index(
        tmp_path, ["- [A](alpha.md)", "- [B](beta.md)", "- [A](alpha.md)"]
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
    tmp_path, total_lines, final_newline, expected
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
    ("total_bytes", "flagged"), [(25_000, False), (25_001, True), (25_900, True)]
)
def test_index_too_large_counts_raw_bytes_not_characters(
    tmp_path, total_bytes, flagged
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
    tmp_path, as_directory, error
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
