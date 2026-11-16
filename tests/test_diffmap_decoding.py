import subprocess
from pathlib import Path

import pytest

from engram.diffmap import Symbol, changed_symbols


def _write_diff(tmp_path: Path, lines: list[str]) -> Path:
    diff_path = tmp_path / "changes.diff"
    diff_path.write_text("\n".join(lines) + "\n")
    return diff_path


def _git_commit_all(tmp_path: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-m", message],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )


# --- changed_symbols(): a non-UTF-8 source file is decoded with replacement, not crashed on (worktree mode) ---


def test_non_utf8_source_file_is_parsed_with_replacement_not_crashed_on(tmp_path):
    (tmp_path / "weird.py").write_bytes(b'def foo():\n    return "\xe9"\n')
    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/weird.py b/weird.py",
            "index 1111111..2222222 100644",
            "--- a/weird.py",
            "+++ b/weird.py",
            "@@ -1,2 +1,2 @@",
            " def foo():",
            "-    return 0",
            "+    return 1",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert result == [
        Symbol(
            path=str(tmp_path / "weird.py"),
            name="foo",
            kind="function",
            line_start=1,
            line_end=2,
        ),
    ]


# --- changed_symbols(): a non-UTF-8 source file is decoded with replacement, not crashed on (historical mode) ---


def test_non_utf8_source_file_at_source_ref_is_parsed_with_replacement_not_crashed_on(
    tmp_path,
):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "weird.py").write_bytes(b'def foo():\n    return "\xe9"\n')
    _git_commit_all(tmp_path, "older")
    older_ref = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    (tmp_path / "weird.py").write_text(
        "def beta():\n    return 2\n",
    )
    _git_commit_all(tmp_path, "newer")

    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/weird.py b/weird.py",
            "index 1111111..2222222 100644",
            "--- a/weird.py",
            "+++ b/weird.py",
            "@@ -1,2 +1,2 @@",
            " def foo():",
            "-    return 0",
            "+    return 1",
        ],
    )

    result = changed_symbols(diff_path, tmp_path, source_ref=older_ref)

    assert result == [
        Symbol(
            path=str(tmp_path / "weird.py"),
            name="foo",
            kind="function",
            line_start=1,
            line_end=2,
        ),
    ]


# --- changed_symbols(): non-UTF-8 bytes in the diff file itself are decoded with replacement, not crashed on ---


def test_non_utf8_bytes_in_the_diff_file_are_decoded_with_replacement_not_crashed_on(
    tmp_path,
):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    module_path = tmp_path / "mod.py"
    module_path.write_bytes(b'def foo():\n    return "x"\n')
    _git_commit_all(tmp_path, "initial")
    module_path.write_bytes(b'def foo():\n    return "\xe9"\n')

    diff_result = subprocess.run(
        ["git", "diff"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    diff_path = tmp_path / "changes.diff"
    diff_path.write_bytes(diff_result.stdout)

    result = changed_symbols(diff_path, tmp_path)

    assert result == [
        Symbol(
            path=str(tmp_path / "mod.py"),
            name="foo",
            kind="function",
            line_start=1,
            line_end=2,
        ),
    ]


# --- changed_symbols(): git's C-quoted header path ("b/caf\303\251.py") is decoded to the real name ---

_C_QUOTED_CASES = pytest.mark.parametrize(
    ("quoted_stem", "decoded_stem", "ascii_stem"),
    [
        (r"caf\303\251", "café", "cafe"),
        (r"na\303\257ve", "naïve", "naive"),
        (r"\302\265s", "µs", "us"),
        (r"\346\227\245\350\250\230", "日記", "nikki"),
        (r"\360\237\220\215", "🐍", "snake"),
    ],
    ids=["e_acute", "i_diaeresis", "micro_sign_c2_lead", "cjk_3_byte", "emoji_4_byte"],
)


@_C_QUOTED_CASES
def test_changed_symbols_decodes_c_quoted_non_ascii_path(
    tmp_path, quoted_stem, decoded_stem, ascii_stem
):
    (tmp_path / f"{decoded_stem}.py").write_text("def foo():\n    return 1\n")
    (tmp_path / f"{ascii_stem}.py").write_text("def bar():\n    return 2\n")
    diff_path = _write_diff(
        tmp_path,
        [
            f'diff --git "a/{quoted_stem}.py" "b/{quoted_stem}.py"',
            "index 1111111..2222222 100644",
            f'--- "a/{quoted_stem}.py"',
            f'+++ "b/{quoted_stem}.py"',
            "@@ -1,2 +1,2 @@",
            " def foo():",
            "-    return 0",
            "+    return 1",
            f"diff --git a/{ascii_stem}.py b/{ascii_stem}.py",
            "index 1111111..2222222 100644",
            f"--- a/{ascii_stem}.py",
            f"+++ b/{ascii_stem}.py",
            "@@ -1,2 +1,2 @@",
            " def bar():",
            "-    return 0",
            "+    return 2",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert result == [
        Symbol(
            path=str(tmp_path / f"{decoded_stem}.py"),
            name="foo",
            kind="function",
            line_start=1,
            line_end=2,
        ),
        Symbol(
            path=str(tmp_path / f"{ascii_stem}.py"),
            name="bar",
            kind="function",
            line_start=1,
            line_end=2,
        ),
    ]


@_C_QUOTED_CASES
def test_changed_symbols_decodes_c_quoted_deleted_path(
    tmp_path, quoted_stem, decoded_stem, ascii_stem
):
    diff_path = _write_diff(
        tmp_path,
        [
            f'diff --git "a/{quoted_stem}.py" "b/{quoted_stem}.py"',
            "deleted file mode 100644",
            "index 1111111..0000000 100644",
            f'--- "a/{quoted_stem}.py"',
            "+++ /dev/null",
            "@@ -1,2 +0,0 @@",
            "-def gone():",
            "-    return 1",
            f"diff --git a/{ascii_stem}.py b/{ascii_stem}.py",
            "deleted file mode 100644",
            "index 1111111..0000000 100644",
            f"--- a/{ascii_stem}.py",
            "+++ /dev/null",
            "@@ -1,1 +0,0 @@",
            "-X = 1",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert result == [
        Symbol(
            path=str(tmp_path / f"{decoded_stem}.py"),
            name=f"{decoded_stem}.py",
            kind="file",
            line_start=1,
            line_end=1,
        ),
        Symbol(
            path=str(tmp_path / f"{ascii_stem}.py"),
            name=f"{ascii_stem}.py",
            kind="file",
            line_start=1,
            line_end=1,
        ),
    ]


@pytest.mark.parametrize(
    ("quoted_rel", "decoded_rel"),
    [
        (r"a\"b\\c.py", 'a"b\\c.py'),
        (r"tab\there.py", "tab\there.py"),
        (r"dir/a\"b.py", 'dir/a"b.py'),
    ],
    ids=["quote_and_backslash", "tab", "quote_in_subdirectory"],
)
def test_changed_symbols_c_quoted_path_unescapes_c_escapes_to_exact_relative_path(
    tmp_path, quoted_rel, decoded_rel
):
    target = tmp_path / decoded_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def foo():\n    return 1\n")
    diff_path = _write_diff(
        tmp_path,
        [
            f'diff --git "a/{quoted_rel}" "b/{quoted_rel}"',
            "index 1111111..2222222 100644",
            f'--- "a/{quoted_rel}"',
            f'+++ "b/{quoted_rel}"',
            "@@ -1,2 +1,2 @@",
            " def foo():",
            "-    return 0",
            "+    return 1",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert result == [
        Symbol(
            path=str(tmp_path / decoded_rel),
            name="foo",
            kind="function",
            line_start=1,
            line_end=2,
        ),
    ]
    assert Path(result[0].path).relative_to(tmp_path).as_posix() == decoded_rel


@pytest.mark.parametrize(
    "raw_rel",
    ["café.py", r"back\nslash.py", r"caf\303\251.py"],
    ids=["raw_utf8", "literal_backslash_n", "literal_backslash_octal"],
)
def test_changed_symbols_leaves_unquoted_path_unchanged_not_c_quoted_decoded(
    tmp_path, raw_rel
):
    (tmp_path / raw_rel).write_text("def foo():\n    return 1\n")
    diff_path = _write_diff(
        tmp_path,
        [
            f"diff --git a/{raw_rel} b/{raw_rel}",
            "index 1111111..2222222 100644",
            f"--- a/{raw_rel}",
            f"+++ b/{raw_rel}",
            "@@ -1,2 +1,2 @@",
            " def foo():",
            "-    return 0",
            "+    return 1",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert result == [
        Symbol(
            path=str(tmp_path / raw_rel),
            name="foo",
            kind="function",
            line_start=1,
            line_end=2,
        ),
    ]


@pytest.mark.parametrize(
    "header_lines",
    [
        [
            r'diff --git "a/\056\056/\056\056/etc/passwd" "b/\056\056/\056\056/etc/passwd"',
            "index 1111111..2222222 100644",
            r'--- "a/\056\056/\056\056/etc/passwd"',
            r'+++ "b/\056\056/\056\056/etc/passwd"',
            "@@ -1,1 +1,1 @@",
            "-x",
            "+y",
        ],
        [
            r'diff --git "a/\056\056/\056\056/etc/passwd" "b/\056\056/\056\056/etc/passwd"',
            "deleted file mode 100644",
            "index 1111111..0000000 100644",
            r'--- "a/\056\056/\056\056/etc/passwd"',
            "+++ /dev/null",
            "@@ -1,1 +0,0 @@",
            "-x",
        ],
    ],
    ids=["modified_plus_line", "deleted_minus_line"],
)
def test_changed_symbols_rejects_c_quoted_traversal_path_after_decoding(
    tmp_path, header_lines
):
    diff_path = _write_diff(tmp_path, header_lines)

    with pytest.raises(ValueError, match="outside repository"):
        changed_symbols(diff_path, tmp_path)


def test_changed_symbols_c_quoted_grammarless_file_symbol_uses_decoded_name(
    tmp_path,
):
    (tmp_path / "café.bin").write_text("first line\n")
    diff_path = _write_diff(
        tmp_path,
        [
            r'diff --git "a/caf\303\251.bin" "b/caf\303\251.bin"',
            "index 1111111..2222222 100644",
            r'--- "a/caf\303\251.bin"',
            r'+++ "b/caf\303\251.bin"',
            "@@ -1,1 +1,2 @@",
            " first line",
            "+second line",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert result == [
        Symbol(
            path=str(tmp_path / "café.bin"),
            name="café.bin",
            kind="file",
            line_start=2,
            line_end=2,
        ),
    ]
