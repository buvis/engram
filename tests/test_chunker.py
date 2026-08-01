from engram.chunker import chunk_markdown
from engram.store import Chunk


# --- flat heading split ---


def test_multi_heading_document_yields_one_chunk_per_heading_with_sequential_ordinals(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text(
        "# First\n"
        "first body\n"
        "## Second\n"
        "second body\n"
        "### Third\n"
        "third body\n"
    )

    chunks = chunk_markdown(path, corpus="docs", repo="repoA", content_hash="hash1")

    assert [c.heading for c in chunks] == ["First", "Second", "Third"]
    assert [c.body for c in chunks] == ["first body", "second body", "third body"]
    assert [c.chunk_ordinal for c in chunks] == [0, 1, 2]
    assert [c.line_start for c in chunks] == [1, 3, 5]
    assert [c.line_end for c in chunks] == [2, 4, 6]


def test_nested_headings_split_flatly_into_separate_chunks(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("# A\nbody a\n## B\nbody b\n### C\nbody c\n")

    chunks = chunk_markdown(path, corpus="docs", repo="repoA", content_hash="hash1")

    assert len(chunks) == 3
    assert [c.heading for c in chunks] == ["A", "B", "C"]
    # the level-3 heading must be its own chunk, never absorbed into the level-2 section
    assert chunks[1].body == "body b"
    assert chunks[2].heading == "C"
    assert chunks[2].body == "body c"


def test_non_atx_heading_patterns_are_not_treated_as_headings(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text(
        "#nospace not a heading\n"
        "####### seven hashes not a heading\n"
        "Setext Style\n"
        "---\n"
        "# Real Heading\n"
        "body\n"
    )

    chunks = chunk_markdown(path, corpus="docs", repo="repoA", content_hash="hash1")

    assert len(chunks) == 2
    assert chunks[0].heading == ""
    assert chunks[0].line_start == 1
    assert chunks[0].line_end == 4
    assert chunks[0].body == (
        "#nospace not a heading\n"
        "####### seven hashes not a heading\n"
        "Setext Style\n"
        "---"
    )
    assert chunks[1].heading == "Real Heading"
    assert chunks[1].line_start == 5
    assert chunks[1].line_end == 6


# --- preamble ---


def test_preamble_text_becomes_ordinal_zero_chunk_with_empty_heading(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("intro text\nmore intro\n# Heading\nbody\n")

    chunks = chunk_markdown(path, corpus="docs", repo="repoA", content_hash="hash1")

    assert chunks[0].heading == ""
    assert chunks[0].chunk_ordinal == 0
    assert chunks[0].line_start == 1
    assert chunks[0].body == "intro text\nmore intro"
    assert chunks[1].heading == "Heading"
    assert chunks[1].chunk_ordinal == 1


def test_document_starting_with_heading_has_no_preamble_chunk(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("# Heading\nbody\n")

    chunks = chunk_markdown(path, corpus="docs", repo="repoA", content_hash="hash1")

    assert len(chunks) == 1
    assert all(c.heading != "" for c in chunks)


def test_file_with_only_preamble_text_yields_single_chunk(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("just some text\nno headings here\n")

    chunks = chunk_markdown(path, corpus="docs", repo="repoA", content_hash="hash1")

    assert len(chunks) == 1
    assert chunks[0].heading == ""
    assert chunks[0].body == "just some text\nno headings here"


# --- empty sections and empty files ---


def test_heading_immediately_followed_by_next_heading_yields_empty_body(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("# First\n## Second\nbody\n")

    chunks = chunk_markdown(path, corpus="docs", repo="repoA", content_hash="hash1")

    assert chunks[0].body == ""


def test_empty_or_whitespace_only_file_yields_no_chunks(tmp_path):
    empty_path = tmp_path / "empty.md"
    empty_path.write_text("")
    whitespace_path = tmp_path / "whitespace.md"
    whitespace_path.write_text("   \n\n\t\n")

    assert chunk_markdown(empty_path, corpus="docs", repo="repoA", content_hash="hash1") == []
    assert chunk_markdown(whitespace_path, corpus="docs", repo="repoA", content_hash="hash1") == []


# --- field mapping ---


def test_corpus_repo_content_hash_pass_through_and_doc_type_and_path_are_set(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("# Heading\nbody\n")

    chunks = chunk_markdown(path, corpus="mycorpus", repo="myrepo", content_hash="myhash")

    assert len(chunks) == 1
    chunk = chunks[0]
    assert isinstance(chunk, Chunk)
    assert chunk.corpus == "mycorpus"
    assert chunk.repo == "myrepo"
    assert chunk.content_hash == "myhash"
    assert chunk.doc_type == "md"
    assert chunk.path == str(path)


def test_heading_strips_hash_markers_and_surrounding_whitespace(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("#   Title  \nbody\n")

    chunks = chunk_markdown(path, corpus="docs", repo="repoA", content_hash="hash1")

    assert chunks[0].heading == "Title"


# --- oversized sections ---


def test_section_body_exceeding_8000_chars_is_not_truncated(tmp_path):
    path = tmp_path / "doc.md"
    long_line = "x" * 9000
    path.write_text(f"# Heading\n{long_line}\n")

    chunks = chunk_markdown(path, corpus="docs", repo="repoA", content_hash="hash1")

    assert len(chunks[0].body) == 9000
    assert chunks[0].body == long_line


# --- exact line spans ---


def test_exact_line_span_for_known_fixture_with_blank_line_before_next_heading(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("# Title\nbody line 1\n\n## Sub\nsub body\n")

    chunks = chunk_markdown(path, corpus="docs", repo="repoA", content_hash="hash1")

    assert len(chunks) == 2
    assert chunks[0].line_start == 1
    assert chunks[0].line_end == 3
    assert chunks[0].body == "body line 1"
    assert chunks[1].line_start == 4
    assert chunks[1].line_end == 5
    assert chunks[1].body == "sub body"
