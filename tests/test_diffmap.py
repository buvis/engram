import subprocess
from pathlib import Path

import pytest

from engram import symbols
from engram.diffmap import Symbol, changed_symbols


def _write_diff(tmp_path: Path, lines: list[str]) -> Path:
    diff_path = tmp_path / "changes.diff"
    diff_path.write_text("\n".join(lines) + "\n")
    return diff_path


# --- changed_symbols(): an added line resolves to its smallest enclosing symbol ---


def test_added_line_inside_function_or_method_resolves_to_smallest_enclosing_symbol(tmp_path):
    (tmp_path / "mod.py").write_text(
        'def foo():\n'
        '    return 1\n'
        '\n'
        '\n'
        'class Bar:\n'
        '    def method(self):\n'
        '        return 2\n'
    )
    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/mod.py b/mod.py",
            "index 1111111..2222222 100644",
            "--- a/mod.py",
            "+++ b/mod.py",
            "@@ -1,2 +1,2 @@",
            " def foo():",
            "-    pass",
            "+    return 1",
            "@@ -6,2 +6,2 @@",
            "     def method(self):",
            "-        pass",
            "+        return 2",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    expected_path = str(tmp_path / "mod.py")
    assert len(result) == 2
    assert set(result) == {
        Symbol(path=expected_path, name="foo", kind="function", line_start=1, line_end=2),
        Symbol(path=expected_path, name="method", kind="function", line_start=6, line_end=7),
    }


# --- changed_symbols(): only '+' lines are mapped, not the whole @@ span ---


def test_context_line_spillover_in_hunk_span_does_not_pull_in_neighboring_symbol(tmp_path):
    (tmp_path / "mod.py").write_text(
        'def foo():\n'
        '    return 1\n'
        '\n'
        '\n'
        'def bar():\n'
        '    return 2\n'
    )
    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/mod.py b/mod.py",
            "index 1111111..2222222 100644",
            "--- a/mod.py",
            "+++ b/mod.py",
            "@@ -2,5 +2,5 @@",
            "     return 1",
            " ",
            " ",
            " def bar():",
            "-    return 0",
            "+    return 2",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert result == [
        Symbol(
            path=str(tmp_path / "mod.py"),
            name="bar",
            kind="function",
            line_start=5,
            line_end=6,
        ),
    ]


# --- changed_symbols(): a changed line outside every structure item falls back to file-level ---


@pytest.mark.parametrize(
    "hunk_lines",
    [
        ["@@ -1,1 +1,1 @@", "-import sys", "+import os"],
        ["@@ -3,1 +3,1 @@", "-X = 0", "+X = 1"],
    ],
    ids=["import", "top_level_constant"],
)
def test_added_line_touching_only_module_level_code_falls_back_to_file_level(tmp_path, hunk_lines):
    (tmp_path / "mod2.py").write_text(
        'import os\n'
        '\n'
        'X = 1\n'
        '\n'
        '\n'
        'def foo():\n'
        '    return 1\n'
    )
    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/mod2.py b/mod2.py",
            "index 1111111..2222222 100644",
            "--- a/mod2.py",
            "+++ b/mod2.py",
            *hunk_lines,
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert len(result) == 1
    assert result[0].kind == "file"
    assert result[0].path == str(tmp_path / "mod2.py")


# --- changed_symbols(): a pure-deletion hunk has no post-image line to map, falls back to file-level ---


def test_pure_deletion_hunk_falls_back_to_file_level_anchored_at_post_image_start(tmp_path):
    (tmp_path / "mod3.py").write_text(
        'def alpha():\n'
        '    return 1\n'
        '\n'
        '\n'
        'def beta():\n'
        '    return 2\n'
    )
    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/mod3.py b/mod3.py",
            "index 1111111..2222222 100644",
            "--- a/mod3.py",
            "+++ b/mod3.py",
            "@@ -5,2 +5,0 @@",
            "-def old():",
            "-    pass",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert len(result) == 1
    assert result[0].kind == "file"
    assert result[0].line_start == 5
    assert result[0].path == str(tmp_path / "mod3.py")


# --- changed_symbols(): a file section with +++ /dev/null is a deletion, not a diff-relative path guess ---


def test_file_section_with_dev_null_target_is_deletion_and_yields_file_level_symbol(tmp_path):
    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/deleted.py b/deleted.py",
            "deleted file mode 100644",
            "index 1111111..0000000 100644",
            "--- a/deleted.py",
            "+++ /dev/null",
            "@@ -1,2 +0,0 @@",
            "-def gone():",
            "-    return 1",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert len(result) == 1
    assert result[0].kind == "file"
    assert result[0].path == str(tmp_path / "deleted.py")


# --- changed_symbols(): multiple changed lines in the same symbol dedup to one entry ---


def test_multiple_changed_lines_in_same_function_dedup_to_one_symbol(tmp_path):
    (tmp_path / "mod4.py").write_text(
        'def calc():\n'
        '    a = 1\n'
        '    b = 2\n'
        '    return a + b\n'
    )
    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/mod4.py b/mod4.py",
            "index 1111111..2222222 100644",
            "--- a/mod4.py",
            "+++ b/mod4.py",
            "@@ -1,2 +1,2 @@",
            " def calc():",
            "-    a = 0",
            "+    a = 1",
            "@@ -3,1 +3,1 @@",
            "-    b = 0",
            "+    b = 2",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert result == [
        Symbol(
            path=str(tmp_path / "mod4.py"),
            name="calc",
            kind="function",
            line_start=1,
            line_end=4,
        ),
    ]


# --- changed_symbols(): Symbol.path is absolute and matches what symbols.chunk() stores ---


def test_symbol_path_is_absolute_and_matches_chunk_path_for_same_file(tmp_path):
    (tmp_path / "pkg").mkdir()
    source_path = tmp_path / "pkg" / "mod.py"
    source_path.write_text(
        'def only():\n'
        '    return 1\n'
    )
    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/pkg/mod.py b/pkg/mod.py",
            "index 1111111..2222222 100644",
            "--- a/pkg/mod.py",
            "+++ b/pkg/mod.py",
            "@@ -1,2 +1,2 @@",
            " def only():",
            "-    return 0",
            "+    return 1",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert len(result) == 1
    symbol = result[0]
    assert symbol.name == "only"
    assert symbol.kind == "function"
    assert symbol.line_start == 1
    assert symbol.line_end == 2
    assert Path(symbol.path).is_absolute()

    chunks = symbols.chunk(source_path, "repo", "hash")
    assert symbol.path == chunks[0].path


# --- changed_symbols(): a commit-ish source_ref reads that commit's content via git show, not the worktree ---


def test_historical_source_ref_reads_that_commits_content_not_the_worktree(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "mod.py").write_text(
        'def alpha():\n'
        '    return 1\n'
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-m", "older"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    older_ref = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    (tmp_path / "mod.py").write_text(
        'def beta():\n'
        '    return 2\n'
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-m", "newer"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/mod.py b/mod.py",
            "index 1111111..2222222 100644",
            "--- a/mod.py",
            "+++ b/mod.py",
            "@@ -1,2 +1,2 @@",
            " def alpha():",
            "-    return 0",
            "+    return 1",
        ],
    )

    result = changed_symbols(diff_path, tmp_path, source_ref=older_ref)

    assert result == [
        Symbol(
            path=str(tmp_path / "mod.py"),
            name="alpha",
            kind="function",
            line_start=1,
            line_end=2,
        ),
    ]


# --- changed_symbols(): a file whose extension has no grammar yields a file-level symbol ---


@pytest.mark.parametrize("filename", ["data.bin", "Makefile"])
def test_grammarless_file_yields_file_level_symbol(tmp_path, filename):
    (tmp_path / filename).write_text("first line\n")
    diff_path = _write_diff(
        tmp_path,
        [
            f"diff --git a/{filename} b/{filename}",
            "index 1111111..2222222 100644",
            f"--- a/{filename}",
            f"+++ b/{filename}",
            "@@ -1,1 +1,2 @@",
            " first line",
            "+second line",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert len(result) == 1
    assert result[0].kind == "file"
    assert result[0].path == str(tmp_path / filename)


# --- changed_symbols(): a binary-file diff section yields no symbol and does not crash the parse ---


def test_binary_file_section_yields_no_symbol_and_does_not_crash_the_parse(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    image_path = tmp_path / "img.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01\x02\x03")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x09\x08\x07")

    diff_text = subprocess.run(
        ["git", "diff"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout
    diff_path = tmp_path / "changes.diff"
    diff_path.write_text(diff_text)

    result = changed_symbols(diff_path, tmp_path)

    assert result == []


# --- changed_symbols(): a mode-only diff section yields no symbol and does not crash the parse ---


def test_mode_only_section_yields_no_symbol_and_does_not_crash_the_parse(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "core.fileMode", "true"], cwd=tmp_path, check=True, capture_output=True
    )
    script_path = tmp_path / "run.sh"
    script_path.write_text("echo hi\n")
    script_path.chmod(0o644)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    script_path.chmod(0o755)

    diff_text = subprocess.run(
        ["git", "diff"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout
    diff_path = tmp_path / "changes.diff"
    diff_path.write_text(diff_text)

    result = changed_symbols(diff_path, tmp_path)

    assert result == []


# --- changed_symbols(): binary and mode-only sections before a text change don't abort mapping the rest of the diff ---


def test_binary_and_mode_sections_before_text_change_do_not_abort_the_rest_of_the_parse(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "core.fileMode", "true"], cwd=tmp_path, check=True, capture_output=True
    )
    image_path = tmp_path / "aaa_img.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01\x02\x03")
    script_path = tmp_path / "aab_run.sh"
    script_path.write_text("echo hi\n")
    script_path.chmod(0o644)
    module_path = tmp_path / "mod.py"
    module_path.write_text(
        'def foo():\n'
        '    return 1\n'
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x09\x08\x07")
    script_path.chmod(0o755)
    module_path.write_text(
        'def foo():\n'
        '    return 2\n'
    )

    diff_text = subprocess.run(
        ["git", "diff"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout
    diff_path = tmp_path / "changes.diff"
    diff_path.write_text(diff_text)

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


def test_non_utf8_source_file_at_source_ref_is_parsed_with_replacement_not_crashed_on(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "weird.py").write_bytes(b'def foo():\n    return "\xe9"\n')
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-m", "older"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    older_ref = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    (tmp_path / "weird.py").write_text(
        'def beta():\n'
        '    return 2\n'
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-m", "newer"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

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


def test_non_utf8_bytes_in_the_diff_file_are_decoded_with_replacement_not_crashed_on(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    module_path = tmp_path / "mod.py"
    module_path.write_bytes(b'def foo():\n    return "x"\n')
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    module_path.write_bytes(b'def foo():\n    return "\xe9"\n')

    diff_result = subprocess.run(
        ["git", "diff"], cwd=tmp_path, check=True, capture_output=True
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


# --- changed_symbols(): a multi-line change to a grammarless file yields one file-level symbol anchored at the first changed line ---


def test_multiline_change_to_grammarless_file_yields_one_file_level_symbol_anchored_at_first_changed_line(
    tmp_path,
):
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n- existing entry\n")
    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/CHANGELOG.md b/CHANGELOG.md",
            "index 1111111..2222222 100644",
            "--- a/CHANGELOG.md",
            "+++ b/CHANGELOG.md",
            "@@ -1,3 +1,6 @@",
            " # Changelog",
            " ",
            " - existing entry",
            "+- new entry one",
            "+- new entry two",
            "+- new entry three",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert result == [
        Symbol(
            path=str(tmp_path / "CHANGELOG.md"),
            name="CHANGELOG.md",
            kind="file",
            line_start=4,
            line_end=4,
        ),
    ]


# --- changed_symbols(): separate hunks in one grammarless file dedup to one file-level symbol per file, not per hunk ---


def test_multiple_hunks_in_grammarless_file_dedup_to_one_file_level_symbol(tmp_path):
    (tmp_path / "Makefile").write_text("build:\n\tgo build ./...\n\ntest:\n\tgo test ./...\n")
    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/Makefile b/Makefile",
            "index 1111111..2222222 100644",
            "--- a/Makefile",
            "+++ b/Makefile",
            "@@ -1,2 +1,2 @@",
            " build:",
            "-\tgo build ./...",
            "+\tgo build ./cmd/...",
            "@@ -4,2 +4,2 @@",
            " test:",
            "-\tgo test ./...",
            "+\tgo test ./cmd/...",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert len(result) == 1
    assert result[0].kind == "file"
    assert result[0].path == str(tmp_path / "Makefile")


# --- changed_symbols(): several module-level edits in one Python file dedup to one file-level symbol ---


def test_multiple_module_level_edits_in_python_file_dedup_to_one_file_level_symbol(tmp_path):
    (tmp_path / "mod6.py").write_text(
        'import os\n'
        'import sys\n'
        '\n'
        'def foo():\n'
        '    return 1\n'
    )
    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/mod6.py b/mod6.py",
            "index 1111111..2222222 100644",
            "--- a/mod6.py",
            "+++ b/mod6.py",
            "@@ -1,1 +1,1 @@",
            "-import osx",
            "+import os",
            "@@ -2,1 +2,1 @@",
            "-import sysx",
            "+import sys",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert len(result) == 1
    assert result[0].kind == "file"
    assert result[0].path == str(tmp_path / "mod6.py")
    assert result[0].line_start == 1
    assert result[0].line_end == 1


# --- changed_symbols(): the file-level dedup key is per file, not global across the whole diff ---


def test_dedup_is_per_file_not_global_across_two_grammarless_files(tmp_path):
    (tmp_path / "data.bin").write_text("first line\nsecond line\nthird line\n")
    (tmp_path / "Makefile").write_text("build:\n\tgo build\n\techo done\n")
    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/data.bin b/data.bin",
            "index 1111111..2222222 100644",
            "--- a/data.bin",
            "+++ b/data.bin",
            "@@ -1,1 +1,3 @@",
            " first line",
            "+second line",
            "+third line",
            "diff --git a/Makefile b/Makefile",
            "index 1111111..2222222 100644",
            "--- a/Makefile",
            "+++ b/Makefile",
            "@@ -1,2 +1,3 @@",
            " build:",
            " \tgo build",
            "+\techo done",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    assert len(result) == 2
    assert set(result) == {
        Symbol(path=str(tmp_path / "data.bin"), name="data.bin", kind="file", line_start=2, line_end=2),
        Symbol(path=str(tmp_path / "Makefile"), name="Makefile", kind="file", line_start=3, line_end=3),
    }


# --- changed_symbols(): deduping the file-level fallback does not swallow real function symbols ---


def test_function_and_module_level_edits_in_same_file_yield_functions_plus_one_file_symbol(tmp_path):
    (tmp_path / "mod5.py").write_text(
        'import os\n'
        'import sys\n'
        '\n'
        '\n'
        'def foo():\n'
        '    return 1\n'
        '\n'
        '\n'
        'def bar():\n'
        '    return 2\n'
    )
    diff_path = _write_diff(
        tmp_path,
        [
            "diff --git a/mod5.py b/mod5.py",
            "index 1111111..2222222 100644",
            "--- a/mod5.py",
            "+++ b/mod5.py",
            "@@ -1,2 +1,2 @@",
            "-import osx",
            "+import os",
            "-import sysx",
            "+import sys",
            "@@ -5,2 +5,2 @@",
            " def foo():",
            "-    return 0",
            "+    return 1",
            "@@ -9,2 +9,2 @@",
            " def bar():",
            "-    return 0",
            "+    return 2",
        ],
    )

    result = changed_symbols(diff_path, tmp_path)

    expected_path = str(tmp_path / "mod5.py")
    assert len(result) == 3
    assert set(result) == {
        Symbol(path=expected_path, name="mod5.py", kind="file", line_start=1, line_end=1),
        Symbol(path=expected_path, name="foo", kind="function", line_start=5, line_end=6),
        Symbol(path=expected_path, name="bar", kind="function", line_start=9, line_end=10),
    }
