import subprocess
from pathlib import Path

import pytest

from engram import corpora, symbols
from engram.corpora import CorpusFile
from engram.store import Chunk


def _init_git_repo(repo_dir: Path, files: dict[str, str | bytes]) -> Path:
    repo_dir.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    for name, content in files.items():
        file_path = repo_dir / name
        if isinstance(content, bytes):
            file_path.write_bytes(content)
        else:
            file_path.write_text(content)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-m", "x"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    return repo_dir


# --- chunk(): recursive pre-order symbol walk with 1-indexed lines ---


def test_function_and_class_symbols_yield_preorder_chunks_with_correct_body_and_lines(tmp_path):
    path = tmp_path / "shapes.py"
    path.write_text(
        'def greet(name):\n'
        '    """Say hello."""\n'
        '    return "hi " + name\n'
        '\n'
        '\n'
        'class Shape:\n'
        '    """A shape."""\n'
        '\n'
        '    def area(self):\n'
        '        return 0\n'
    )

    chunks = symbols.chunk(path, "widget", "h1")

    assert chunks == [
        Chunk(
            corpus="code",
            repo="widget",
            doc_type="function",
            path=str(path),
            heading="Function greet",
            body='def greet(name):\n    """Say hello."""\n    return "hi " + name',
            line_start=1,
            line_end=3,
            content_hash="h1",
            chunk_ordinal=1,
        ),
        Chunk(
            corpus="code",
            repo="widget",
            doc_type="class",
            path=str(path),
            heading="Class Shape",
            body='class Shape:\n    """A shape."""\n\n    def area(self):\n        return 0',
            line_start=6,
            line_end=10,
            content_hash="h1",
            chunk_ordinal=2,
        ),
        Chunk(
            corpus="code",
            repo="widget",
            doc_type="function",
            path=str(path),
            heading="Function area",
            body="    def area(self):\n        return 0",
            line_start=9,
            line_end=10,
            content_hash="h1",
            chunk_ordinal=3,
        ),
    ]


# --- chunk(): files whose extension has no grammar are skipped, not parsed ---


@pytest.mark.parametrize("filename", ["data.bin", "Makefile"])
def test_file_with_no_grammar_yields_no_chunks_and_is_recorded_as_skipped(tmp_path, filename):
    symbols.skipped_files.clear()
    path = tmp_path / filename
    path.write_bytes(b"some content\n")

    chunks = symbols.chunk(path, "widget", "h1")

    assert chunks == []
    assert str(path) in symbols.skipped_files


# --- chunk(): a file that cannot be read is skipped, not raised ---


def test_unreadable_path_yields_no_chunks_and_is_recorded_as_skipped(tmp_path):
    symbols.skipped_files.clear()
    path = tmp_path / "phantom.py"
    path.mkdir()  # a directory where a file is expected: reading it raises OSError

    chunks = symbols.chunk(path, "widget", "h1")

    assert chunks == []
    assert str(path) in symbols.skipped_files


# --- chunk(): non-UTF-8 bytes are replaced, not treated as unreadable ---


def test_file_with_invalid_utf8_bytes_is_parsed_with_replacement_and_not_skipped(tmp_path):
    symbols.skipped_files.clear()
    path = tmp_path / "weird.py"
    path.write_bytes(b'def greet():\n    return "\xff\xfe"\n')

    chunks = symbols.chunk(path, "widget", "h1")

    assert str(path) not in symbols.skipped_files
    assert len(chunks) == 1
    assert chunks[0].doc_type == "function"
    assert chunks[0].heading == "Function greet"
    assert "�" in chunks[0].body


# --- chunk(): empty / whitespace-only source has no symbols and is not a skip ---


@pytest.mark.parametrize("source", ["", "   \n\t\n\n"])
def test_empty_or_whitespace_only_source_yields_no_chunks_and_is_not_skipped(tmp_path, source):
    symbols.skipped_files.clear()
    path = tmp_path / "empty.py"
    path.write_text(source)

    chunks = symbols.chunk(path, "widget", "h1")

    assert chunks == []
    assert str(path) not in symbols.skipped_files


# --- count_skipped(): cheap re-scan counts only tracked files with no grammar ---


def test_count_skipped_counts_tracked_files_with_no_grammar(tmp_path):
    repo_dir = _init_git_repo(
        tmp_path / "repo",
        {"a.py": "def f():\n    pass\n", "b.bin": b"\x00\x01"},
    )
    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text(f"{repo_dir},widget,,\n")

    assert symbols.count_skipped(repos_csv) == 1


# --- enumerate(): one CorpusFile per HEAD-tracked file, grammar-agnostic ---


def test_enumerate_yields_corpusfile_per_tracked_file_and_resets_skipped_files(tmp_path):
    symbols.skipped_files.append("stale.py")
    repo_dir = _init_git_repo(
        tmp_path / "repo",
        {"a.py": "def f():\n    pass\n", "b.bin": b"\x00\x01"},
    )
    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text(f"{repo_dir},widget,,\n")

    results = set(symbols.enumerate(repos_csv=repos_csv))

    assert results == {
        CorpusFile(corpus="code", repo="widget", path=repo_dir / "a.py"),
        CorpusFile(corpus="code", repo="widget", path=repo_dir / "b.bin"),
    }
    assert "stale.py" not in symbols.skipped_files


# --- enumerate(): a repo dir that git can't read is recorded as missing, not raised ---


def test_enumerate_appends_missing_repo_to_missing_dirs_and_does_not_raise(tmp_path):
    corpora.missing_dirs.clear()
    missing_repo_dir = tmp_path / "does-not-exist"
    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text(f"{missing_repo_dir},ghost,,\n")

    results = list(symbols.enumerate(repos_csv=repos_csv))

    assert results == []
    assert "code:ghost" in corpora.missing_dirs


# --- enumerate(): a submodule gitlink is a directory on disk, not a regular file, and must not be yielded ---


def test_submodule_gitlink_path_is_not_yielded(tmp_path):
    repo_dir = _init_git_repo(
        tmp_path / "repo",
        {"a.py": "def f():\n    pass\n"},
    )
    subprocess.run(
        [
            "git",
            "update-index",
            "--add",
            "--cacheinfo",
            "160000,4b825dc642cb6eb9a060e54bf8d69288fbee4904,sub",
        ],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    (repo_dir / "sub").mkdir()
    tracked = subprocess.run(
        ["git", "-C", str(repo_dir), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert "sub" in tracked

    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text(f"{repo_dir},widget,,\n")

    results = set(symbols.enumerate(repos_csv=repos_csv))

    assert results == {
        CorpusFile(corpus="code", repo="widget", path=repo_dir / "a.py"),
    }
    assert str(repo_dir / "sub") not in symbols.skipped_files


# --- enumerate(): a tracked file deleted from the working tree does not exist on disk and must not be yielded ---


def test_tracked_but_deleted_file_is_not_yielded(tmp_path):
    repo_dir = _init_git_repo(
        tmp_path / "repo",
        {"a.py": "def f():\n    pass\n", "b.py": "def g():\n    pass\n"},
    )
    (repo_dir / "b.py").unlink()

    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text(f"{repo_dir},widget,,\n")

    results = set(symbols.enumerate(repos_csv=repos_csv))

    assert results == {
        CorpusFile(corpus="code", repo="widget", path=repo_dir / "a.py"),
    }
    assert str(repo_dir / "b.py") not in symbols.skipped_files
