import json
import tomllib

import pytest

from engram import transcripts
from engram.corpora import CorpusFile
from engram.store import Chunk


# --- turn filter + chunking: happy path ---


def test_two_text_turns_yield_two_chunks_in_file_order_with_1_indexed_lines(tmp_path):
    path = tmp_path / "session.jsonl"
    records = [
        {"type": "user", "message": {"role": "user", "content": "how do I x?"}},
        {
            "type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "do y"}]},
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    chunks = transcripts.chunk(path, repo="cellar", content_hash="hash-abc", error_patterns=[])

    assert chunks == [
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="user turn",
            body="how do I x?",
            line_start=1,
            line_end=1,
            content_hash="hash-abc",
            chunk_ordinal=1,
        ),
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="assistant turn",
            body="do y",
            line_start=2,
            line_end=2,
            content_hash="hash-abc",
            chunk_ordinal=2,
        ),
    ]


# --- turn filter: tool chatter without text or error match is dropped ---


def test_tool_chatter_only_turns_yield_no_chunks(tmp_path):
    path = tmp_path / "session.jsonl"
    records = [
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "name": "bash", "input": {"command": "ls"}}],
            },
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "content": "file1.txt\nfile2.txt"}],
            },
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    chunks = transcripts.chunk(
        path,
        repo="cellar",
        content_hash="hash-abc",
        error_patterns=transcripts.DEFAULT_ERROR_PATTERNS,
    )

    assert chunks == []


# --- turn filter: error-bearing tool_result is kept even without text ---


def test_tool_result_matching_error_pattern_is_kept_with_empty_body_at_correct_line(tmp_path):
    path = tmp_path / "session.jsonl"
    records = [
        {"type": "user", "message": {"role": "user", "content": "run the tests"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "name": "bash", "input": {"command": "pytest"}}],
            },
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_result",
                        "content": 'Traceback (most recent call last):\n  File "x.py"\nKeyError',
                    }
                ],
            },
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    chunks = transcripts.chunk(
        path,
        repo="cellar",
        content_hash="hash-abc",
        error_patterns=transcripts.DEFAULT_ERROR_PATTERNS,
    )

    # line 2 (tool_use only, no text, no error match) is excluded; line 3's
    # tool_result carries a traceback so it is kept despite contributing no body text.
    assert chunks == [
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="user turn",
            body="run the tests",
            line_start=1,
            line_end=1,
            content_hash="hash-abc",
            chunk_ordinal=1,
        ),
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="assistant turn",
            body="",
            line_start=3,
            line_end=3,
            content_hash="hash-abc",
            chunk_ordinal=3,
        ),
    ]


# --- malformed JSON lines are skipped, not raised ---


def test_malformed_json_line_is_skipped_and_surrounding_lines_keep_correct_line_numbers(tmp_path):
    path = tmp_path / "session.jsonl"
    line1 = json.dumps({"type": "user", "message": {"role": "user", "content": "first turn"}})
    line2 = "{not valid json,,,"
    line3 = json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "second turn"}],
            },
        }
    )
    path.write_text(f"{line1}\n{line2}\n{line3}\n")

    chunks = transcripts.chunk(path, repo="cellar", content_hash="hash-abc", error_patterns=[])

    # the malformed line 2 must not raise and must not shift the line numbering
    # of the valid chunk that follows it: chunk_ordinal jumps 1 -> 3, never renumbered.
    assert chunks == [
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="user turn",
            body="first turn",
            line_start=1,
            line_end=1,
            content_hash="hash-abc",
            chunk_ordinal=1,
        ),
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="assistant turn",
            body="second turn",
            line_start=3,
            line_end=3,
            content_hash="hash-abc",
            chunk_ordinal=3,
        ),
    ]


# --- line splitting: Unicode line separators inside JSON strings don't over-split ---


def test_unicode_line_separator_char_in_text_does_not_shift_following_line_numbers(tmp_path):
    path = tmp_path / "session.jsonl"
    line1 = json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "first second"}],
            },
        }
    )
    line2 = json.dumps({"type": "user", "message": {"role": "user", "content": "next turn"}})
    path.write_text(f"{line1}\n{line2}\n")

    chunks = transcripts.chunk(path, repo="cellar", content_hash="hash-abc", error_patterns=[])

    assert chunks == [
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="assistant turn",
            body="first second",
            line_start=1,
            line_end=1,
            content_hash="hash-abc",
            chunk_ordinal=1,
        ),
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="user turn",
            body="next turn",
            line_start=2,
            line_end=2,
            content_hash="hash-abc",
            chunk_ordinal=2,
        ),
    ]


# --- turn filter: JSON lines that decode to a non-dict are skipped ---


def test_json_line_decoding_to_non_dict_is_skipped_and_surrounding_lines_keep_correct_line_numbers(
    tmp_path,
):
    path = tmp_path / "session.jsonl"
    line1 = json.dumps({"type": "user", "message": {"role": "user", "content": "first turn"}})
    line2 = "null"
    line3 = json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "second turn"}],
            },
        }
    )
    path.write_text(f"{line1}\n{line2}\n{line3}\n")

    chunks = transcripts.chunk(path, repo="cellar", content_hash="hash-abc", error_patterns=[])

    assert chunks == [
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="user turn",
            body="first turn",
            line_start=1,
            line_end=1,
            content_hash="hash-abc",
            chunk_ordinal=1,
        ),
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="assistant turn",
            body="second turn",
            line_start=3,
            line_end=3,
            content_hash="hash-abc",
            chunk_ordinal=3,
        ),
    ]


# --- content list with a non-dict block does not raise and still extracts text ---


def test_non_dict_block_in_content_list_is_skipped_and_text_block_still_extracted(tmp_path):
    path = tmp_path / "session.jsonl"
    record = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": ["a bare string block", {"type": "text", "text": "actual text"}],
        },
    }
    path.write_text(json.dumps(record) + "\n")

    chunks = transcripts.chunk(path, repo="cellar", content_hash="hash-abc", error_patterns=[])

    assert chunks == [
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="assistant turn",
            body="actual text",
            line_start=1,
            line_end=1,
            content_hash="hash-abc",
            chunk_ordinal=1,
        ),
    ]


# --- turn filter: isMeta / isSidechain / non-turn types are excluded ---


def test_excludes_lines_with_truthy_is_meta(tmp_path):
    path = tmp_path / "session.jsonl"
    records = [
        {
            "type": "user",
            "message": {"role": "user", "content": "hidden meta turn"},
            "isMeta": True,
        },
        {
            "type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "visible turn"}]},
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    chunks = transcripts.chunk(path, repo="cellar", content_hash="hash-abc", error_patterns=[])

    assert chunks == [
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="assistant turn",
            body="visible turn",
            line_start=2,
            line_end=2,
            content_hash="hash-abc",
            chunk_ordinal=2,
        ),
    ]


def test_excludes_lines_with_truthy_is_sidechain(tmp_path):
    path = tmp_path / "session.jsonl"
    records = [
        {
            "type": "user",
            "message": {"role": "user", "content": "hidden sidechain turn"},
            "isSidechain": True,
        },
        {
            "type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "visible turn"}]},
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    chunks = transcripts.chunk(path, repo="cellar", content_hash="hash-abc", error_patterns=[])

    assert chunks == [
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="assistant turn",
            body="visible turn",
            line_start=2,
            line_end=2,
            content_hash="hash-abc",
            chunk_ordinal=2,
        ),
    ]


def test_excludes_lines_whose_type_is_not_user_or_assistant(tmp_path):
    path = tmp_path / "session.jsonl"
    records = [
        {"type": "summary", "message": {"role": "user", "content": "session summary"}},
        {"type": "system", "message": {"role": "system", "content": "system message"}},
        {"type": "user", "message": {"role": "user", "content": "actual question"}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    chunks = transcripts.chunk(path, repo="cellar", content_hash="hash-abc", error_patterns=[])

    assert chunks == [
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="user turn",
            body="actual question",
            line_start=3,
            line_end=3,
            content_hash="hash-abc",
            chunk_ordinal=3,
        ),
    ]


# --- turn filter: harness scaffolding turns are excluded ---


@pytest.mark.parametrize(
    "scaffolding",
    [
        "<task-notification>\n<task-id>abc</task-id>\n<status>completed</status>\n</task-notification>",
        "<system-reminder>\nremember to use the task tool\n</system-reminder>",
        "<local-command-stdout>See ya!</local-command-stdout>",
        "Caveat: The messages below were generated by the user while running local commands.",
    ],
)
def test_excludes_turns_that_are_harness_scaffolding(tmp_path, scaffolding):
    path = tmp_path / "session.jsonl"
    records = [
        {"type": "user", "message": {"role": "user", "content": scaffolding}},
        {
            "type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "real answer"}]},
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    chunks = transcripts.chunk(path, repo="cellar", content_hash="hash-abc", error_patterns=[])

    # the scaffolding turn is dropped and does not renumber the turn that follows it
    assert chunks == [
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="assistant turn",
            body="real answer",
            line_start=2,
            line_end=2,
            content_hash="hash-abc",
            chunk_ordinal=2,
        ),
    ]


def test_keeps_prose_that_merely_mentions_a_scaffolding_marker(tmp_path):
    path = tmp_path / "session.jsonl"
    # measured against the live corpus: a substring test drops 6 real analysis
    # turns that quote these markers while discussing them. Only a turn that
    # *is* scaffolding, i.e. leads with the marker, may be dropped.
    body = "That is corpus contamination: rank 1 is a <task-notification> block, pure scaffolding."
    record = {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": body}]},
    }
    path.write_text(json.dumps(record) + "\n")

    chunks = transcripts.chunk(path, repo="cellar", content_hash="hash-abc", error_patterns=[])

    assert chunks == [
        Chunk(
            corpus="transcripts",
            repo="cellar",
            doc_type="turn",
            path=str(path),
            heading="assistant turn",
            body=body,
            line_start=1,
            line_end=1,
            content_hash="hash-abc",
            chunk_ordinal=1,
        ),
    ]


# --- enumerate(): session directory layout ---


def test_enumerate_yields_one_corpusfile_per_jsonl_across_session_dirs(tmp_path):
    projects_dir = tmp_path / "projects"
    session_a = projects_dir / "session-a"
    session_b = projects_dir / "session-b"
    session_a.mkdir(parents=True)
    session_b.mkdir(parents=True)
    file_a = session_a / "a.jsonl"
    file_a.write_text('{"type": "user"}\n')
    file_b1 = session_b / "b1.jsonl"
    file_b1.write_text('{"type": "user"}\n')
    file_b2 = session_b / "b2.jsonl"
    file_b2.write_text('{"type": "user"}\n')

    results = set(transcripts.enumerate(projects_dir=projects_dir))

    assert results == {
        CorpusFile(corpus="transcripts", repo="cellar", path=file_a),
        CorpusFile(corpus="transcripts", repo="cellar", path=file_b1),
        CorpusFile(corpus="transcripts", repo="cellar", path=file_b2),
    }


def test_enumerate_raises_filenotfounderror_for_missing_projects_dir(tmp_path):
    missing_dir = tmp_path / "does-not-exist"

    with pytest.raises(FileNotFoundError, match="not found"):
        list(transcripts.enumerate(projects_dir=missing_dir))


# --- default error patterns: each start-set marker is recognized ---


@pytest.mark.parametrize(
    "marker",
    [
        "Traceback (most recent call last): oops",
        "panic: runtime error: index out of range",
        "connection ERROR while dialing",
        "assertion FAIL: expected 1 got 2",
        "process exited with exit code 7",
    ],
)
def test_default_error_pattern_keeps_tool_result_carrying_each_marker(tmp_path, marker):
    path = tmp_path / "session.jsonl"
    record = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_result", "content": marker}],
        },
    }
    path.write_text(json.dumps(record) + "\n")

    chunks = transcripts.chunk(
        path,
        repo="cellar",
        content_hash="hash-abc",
        error_patterns=transcripts.DEFAULT_ERROR_PATTERNS,
    )

    assert len(chunks) == 1
    assert chunks[0].line_start == 1
    assert chunks[0].line_end == 1
    assert chunks[0].chunk_ordinal == 1


# --- chunk(): a file whose bytes cannot be decoded as UTF-8 is skipped, not raised ---


def test_file_with_undecodable_bytes_is_skipped_not_raised(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_bytes(b"\xff\xfe" + json.dumps({"type": "user"}).encode() + b"\n")

    chunks = transcripts.chunk(path, repo="cellar", content_hash="hash-abc", error_patterns=[])

    assert chunks == []


# --- _load_error_patterns(): config-supplied regexes are validated at load time ---


def test_malformed_regex_in_error_patterns_raises_error_naming_pattern_and_config_key(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text('[transcripts]\nerror_patterns = ["[unclosed"]\n')

    # Today _load_error_patterns() returns the bad pattern untouched; the
    # re.error only surfaces later, from deep inside _has_error_match(), with
    # no mention of the pattern or the config key. This must raise here instead.
    with pytest.raises(Exception) as exc_info:
        transcripts._load_error_patterns(config_path=config_path)

    message = str(exc_info.value)
    assert "[unclosed" in message
    assert "error_patterns" in message


def test_valid_custom_error_patterns_from_config_replace_the_defaults(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text('[transcripts]\nerror_patterns = ["CUSTOM_MARKER"]\n')

    patterns = transcripts._load_error_patterns(config_path=config_path)

    assert patterns == ["CUSTOM_MARKER"]


def test_config_without_transcripts_table_falls_back_to_default_error_patterns(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text('[pinned]\nid = ""\n')

    patterns = transcripts._load_error_patterns(config_path=config_path)

    assert patterns == transcripts.DEFAULT_ERROR_PATTERNS


def test_missing_config_file_falls_back_to_default_error_patterns(tmp_path):
    config_path = tmp_path / "does-not-exist.toml"

    patterns = transcripts._load_error_patterns(config_path=config_path)

    assert patterns == transcripts.DEFAULT_ERROR_PATTERNS


# --- _load_error_patterns(): the config is parsed once per run, not once per file ---


def test_repeated_loader_calls_with_the_same_config_path_parse_the_toml_file_only_once(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "config.toml"
    config_path.write_text('[transcripts]\nerror_patterns = ["ONCE_MARKER"]\n')

    parse_count = 0
    real_load = tomllib.load

    def counting_load(f):
        nonlocal parse_count
        parse_count += 1
        return real_load(f)

    monkeypatch.setattr(transcripts.tomllib, "load", counting_load)

    # chunk() calls _load_error_patterns() with this same config path once per
    # transcript file in a real run; simulate several such calls here.
    results = [transcripts._load_error_patterns(config_path=config_path) for _ in range(5)]

    assert results == [["ONCE_MARKER"]] * 5
    assert parse_count == 1
