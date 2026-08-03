import dataclasses
from pathlib import Path

import pytest

from engram.findings import FINDINGS_CORPUS, Record, parse


def _frontmatter_lines(reviewers: str = "alice,bob,carl") -> list[str]:
    return [
        "---",
        "prd: 00001-test",
        f"reviewers: {reviewers}",
        "---",
    ]


def _write_review(
    tmp_path: Path,
    body_lines: list[str],
    reviewers: str = "alice,bob,carl",
    filename: str = "review.md",
) -> tuple[Path, list[str]]:
    lines = _frontmatter_lines(reviewers) + body_lines
    path = tmp_path / filename
    path.write_text("\n".join(lines) + "\n")
    return path, lines


def _line_no(lines: list[str], text: str) -> int:
    return lines.index(text) + 1


def _find_by_body(records: list[Record], body: str) -> Record:
    return next(r for r in records if r.body == body)


# --- module constant ---


def test_findings_corpus_constant_is_literal_string_findings():
    assert FINDINGS_CORPUS == "findings"


# --- Record immutability ---


def test_record_is_immutable():
    record = Record(heading="h", body="b", line_start=1, line_end=1, structured=False)

    with pytest.raises(dataclasses.FrozenInstanceError):
        record.body = "changed"


# --- total-parse-failure: frontmatter completeness ---


def test_parse_raises_when_no_frontmatter_block_present(tmp_path):
    path = tmp_path / "review.md"
    path.write_text(
        "# Review: PRD 00001\n"
        "\n"
        "Verdict: 9 findings\n"
        "Tests: 142 passed, 0 failed, 0 skipped\n"
    )

    with pytest.raises(ValueError):
        parse(path)


def test_parse_raises_when_frontmatter_is_invalid_yaml(tmp_path):
    path = tmp_path / "review.md"
    path.write_text(
        "---\n"
        "reviewers: [alice, bob\n"
        "---\n"
        "\n"
        "Verdict: 9 findings\n"
        "Tests: 142 passed, 0 failed, 0 skipped\n"
    )

    with pytest.raises(ValueError):
        parse(path)


def test_parse_raises_when_frontmatter_is_not_a_mapping(tmp_path):
    path = tmp_path / "review.md"
    path.write_text(
        "---\n"
        "- alice\n"
        "- bob\n"
        "---\n"
        "\n"
        "Verdict: 9 findings\n"
        "Tests: 142 passed, 0 failed, 0 skipped\n"
    )

    with pytest.raises(ValueError):
        parse(path)


def test_parse_raises_when_frontmatter_has_no_reviewers_key(tmp_path):
    path = tmp_path / "review.md"
    path.write_text(
        "---\n"
        "prd: 00001-test\n"
        "cycle: 3\n"
        "---\n"
        "\n"
        "Verdict: 9 findings\n"
        "Tests: 142 passed, 0 failed, 0 skipped\n"
    )

    with pytest.raises(ValueError):
        parse(path)


def test_parse_raises_when_reviewers_value_is_empty(tmp_path):
    path = tmp_path / "review.md"
    path.write_text(
        "---\n"
        "prd: 00001-test\n"
        'reviewers: ""\n'
        "---\n"
        "\n"
        "Verdict: 9 findings\n"
        "Tests: 142 passed, 0 failed, 0 skipped\n"
    )

    with pytest.raises(ValueError):
        parse(path)


# --- total-parse-failure: verdict/tests completeness ---


def test_parse_raises_when_no_verdict_line_in_body(tmp_path):
    path, _lines = _write_review(
        tmp_path,
        [
            "",
            "# Review",
            "",
            "Tests: 142 passed, 0 failed, 0 skipped",
        ],
    )

    with pytest.raises(ValueError):
        parse(path)


def test_parse_raises_when_no_tests_line_in_body(tmp_path):
    path, _lines = _write_review(
        tmp_path,
        [
            "",
            "# Review",
            "",
            "Verdict: 9 findings",
        ],
    )

    with pytest.raises(ValueError):
        parse(path)


# --- total-parse-failure: unreadable file ---


def test_parse_raises_when_file_does_not_exist(tmp_path):
    missing = tmp_path / "does-not-exist.md"

    with pytest.raises(ValueError):
        parse(missing)


# --- shape A: consolidated-findings table rows ---


def test_table_data_rows_become_structured_records_with_issue_column_heading(tmp_path):
    header = "| Consensus | Severity | Issue | File | Task | Found By |"
    separator = "|-----------|----------|-------|------|------|----------|"
    row1 = "| [1/4] | \U0001f7e0 | Gold set covers only 3 of 4 corpora | eval/goldset.yaml | Phase 2 | BLAKE |"
    row2 = "| [2/4] | \U0001f7e1 | CLI flags beyond PRD contract | src/engram/cli.py | Phase 2 | BLAKE |"
    path, lines = _write_review(
        tmp_path,
        [
            "",
            "# Review: PRD 00001 - Cycle 1",
            "",
            "## Consolidated findings",
            "",
            header,
            separator,
            row1,
            row2,
            "",
            "Verdict: 9 findings",
            "Tests: 142 passed, 0 failed, 0 skipped",
        ],
    )

    records = parse(path)

    record1 = _find_by_body(records, row1)
    assert record1.heading == "Gold set covers only 3 of 4 corpora"
    assert record1.structured is True
    assert record1.line_start == record1.line_end == _line_no(lines, row1)

    record2 = _find_by_body(records, row2)
    assert record2.heading == "CLI flags beyond PRD contract"
    assert record2.structured is True
    assert record2.line_start == record2.line_end == _line_no(lines, row2)

    assert not any(r.body in (header, separator) for r in records)


def test_table_row_without_header_uses_whole_row_stripped_as_heading(tmp_path):
    row = "| some cell text | another cell |"
    path, lines = _write_review(
        tmp_path,
        [
            "",
            "Some prose with no table header at all.",
            row,
            "",
            "Verdict: 9 findings",
            "Tests: 142 passed, 0 failed, 0 skipped",
        ],
    )

    records = parse(path)

    record = _find_by_body(records, row)
    assert record.heading == row
    assert record.structured is True
    assert record.line_start == record.line_end == _line_no(lines, row)


def test_table_header_matching_is_case_insensitive(tmp_path):
    header = "| Consensus | Severity | ISSUE | File |"
    separator = "|-----------|----------|-------|------|"
    row = "| [3/4] | \U0001f534 | Case insensitive issue text | some/file.py |"
    path, lines = _write_review(
        tmp_path,
        [
            "",
            header,
            separator,
            row,
            "",
            "Verdict: 9 findings",
            "Tests: 142 passed, 0 failed, 0 skipped",
        ],
    )

    records = parse(path)

    record = _find_by_body(records, row)
    assert record.heading == "Case insensitive issue text"


# --- shape B: severity-emoji bullets ---


def test_bullet_with_bold_title_and_continuation_becomes_structured_record(tmp_path):
    bullet_line = (
        "- [4/4] \U0001f7e0 **Exit-code contract escapes in records.py**: "
        "`wip_path.rename()` unguarded."
    )
    continuation_line = "  | Found by: Bob, Alice, Blake, Carl -> task #12"
    path, lines = _write_review(
        tmp_path,
        [
            "",
            "## Deferred this cycle",
            "",
            bullet_line,
            continuation_line,
            "",
            "Verdict: 9 findings",
            "Tests: 142 passed, 0 failed, 0 skipped",
        ],
    )

    records = parse(path)

    expected_body = bullet_line + "\n" + continuation_line
    record = _find_by_body(records, expected_body)
    assert record.heading == "Exit-code contract escapes in records.py"
    assert record.structured is True
    assert record.line_start == _line_no(lines, bullet_line)
    assert record.line_end == _line_no(lines, continuation_line)


def test_bullet_without_bold_title_strips_tag_and_emoji_for_heading(tmp_path):
    bullet_line = "- \U0001f7e1 [2/5] Memory-corpus repo attribution is always `_unmapped`."
    path, lines = _write_review(
        tmp_path,
        [
            "",
            bullet_line,
            "",
            "Verdict: 9 findings",
            "Tests: 142 passed, 0 failed, 0 skipped",
        ],
    )

    records = parse(path)

    record = _find_by_body(records, bullet_line)
    assert record.structured is True
    assert record.heading == "Memory-corpus repo attribution is always `_unmapped`."
    assert record.line_start == record.line_end == _line_no(lines, bullet_line)


def test_bullet_continuation_stops_before_next_top_level_bullet(tmp_path):
    bullet1 = "- \U0001f534 First finding with a continuation line below."
    continuation1 = "  extra context for the first finding"
    bullet2 = "- ⚪ Second finding with no continuation of its own."
    path, lines = _write_review(
        tmp_path,
        [
            "",
            bullet1,
            continuation1,
            bullet2,
            "",
            "Verdict: 9 findings",
            "Tests: 142 passed, 0 failed, 0 skipped",
        ],
    )

    records = parse(path)

    record1 = _find_by_body(records, bullet1 + "\n" + continuation1)
    assert record1.line_start == _line_no(lines, bullet1)
    assert record1.line_end == _line_no(lines, continuation1)

    record2 = _find_by_body(records, bullet2)
    assert record2.line_start == record2.line_end == _line_no(lines, bullet2)


def test_bullet_continuation_stops_at_blank_line(tmp_path):
    bullet = "- \U0001f7e0 Finding followed by a blank line then unrelated prose."
    trailing_prose = "This line is not part of the bullet."
    path, lines = _write_review(
        tmp_path,
        [
            "",
            bullet,
            "",
            trailing_prose,
            "",
            "Verdict: 9 findings",
            "Tests: 142 passed, 0 failed, 0 skipped",
        ],
    )

    records = parse(path)

    bullet_record = _find_by_body(records, bullet)
    assert bullet_record.line_start == bullet_record.line_end == _line_no(lines, bullet)
    assert bullet_record.structured is True

    prose_record = _find_by_body(records, trailing_prose)
    assert prose_record.structured is False


# --- shape C: unstructured fallback ---


def test_unstructured_records_resolve_heading_from_nearest_preceding_heading_line(tmp_path):
    intro = "Intro line before any heading."
    heading1 = "# First Heading"
    under1 = "Line under first heading."
    heading2 = "## Second Heading"
    under2 = "Line under second heading."
    path, lines = _write_review(
        tmp_path,
        [
            intro,
            heading1,
            under1,
            heading2,
            under2,
            "",
            "Verdict: 9 findings",
            "Tests: 142 passed, 0 failed, 0 skipped",
        ],
    )

    records = parse(path)

    intro_record = _find_by_body(records, intro)
    assert intro_record.heading == ""
    assert intro_record.structured is False

    heading1_record = _find_by_body(records, heading1)
    assert heading1_record.heading == ""

    under1_record = _find_by_body(records, under1)
    assert under1_record.heading == "First Heading"

    heading2_record = _find_by_body(records, heading2)
    assert heading2_record.heading == "First Heading"

    under2_record = _find_by_body(records, under2)
    assert under2_record.heading == "Second Heading"


def test_blank_and_whitespace_only_lines_produce_no_records(tmp_path):
    prose = "Only this line should become a record."
    path, _lines = _write_review(
        tmp_path,
        [
            "",
            "   ",
            prose,
            "\t",
            "",
            "Verdict: 9 findings",
            "Tests: 142 passed, 0 failed, 0 skipped",
        ],
    )

    records = parse(path)

    bodies = [r.body for r in records]
    assert bodies == [
        prose,
        "Verdict: 9 findings",
        "Tests: 142 passed, 0 failed, 0 skipped",
    ]


def test_body_with_no_recognized_shapes_returns_all_unstructured_records(tmp_path):
    line1 = "This paragraph has no table rows or bullets at all."
    line2 = "Neither does this second paragraph line."
    path, _lines = _write_review(
        tmp_path,
        [
            line1,
            line2,
            "",
            "Verdict: 9 findings",
            "Tests: 142 passed, 0 failed, 0 skipped",
        ],
    )

    records = parse(path)

    assert len(records) == 4
    assert all(r.structured is False for r in records)
    assert [r.body for r in records] == [
        line1,
        line2,
        "Verdict: 9 findings",
        "Tests: 142 passed, 0 failed, 0 skipped",
    ]


def test_malformed_table_row_missing_trailing_pipe_falls_back_to_unstructured(tmp_path):
    malformed_row = "| Almost a table row but missing the trailing pipe"
    path, lines = _write_review(
        tmp_path,
        [
            "",
            "## Notes",
            "",
            malformed_row,
            "",
            "Verdict: 9 findings",
            "Tests: 142 passed, 0 failed, 0 skipped",
        ],
    )

    records = parse(path)

    record = _find_by_body(records, malformed_row)
    assert record.structured is False
    assert record.heading == "Notes"
    assert record.line_start == record.line_end == _line_no(lines, malformed_row)


# --- record ordering ---


def test_records_are_returned_in_ascending_line_start_order(tmp_path):
    prose = "unstructured prose finding"
    row = "| [1/2] | table finding |"
    bullet = "- \U0001f534 bullet finding"
    path, lines = _write_review(
        tmp_path,
        [
            "",
            prose,
            "",
            row,
            "",
            bullet,
            "",
            "Verdict: 9 findings",
            "Tests: 142 passed, 0 failed, 0 skipped",
        ],
    )

    records = parse(path)

    line_starts = [r.line_start for r in records]
    assert line_starts == sorted(line_starts)
    assert line_starts[0] == _line_no(lines, prose)
    assert line_starts[-1] == _line_no(lines, "Tests: 142 passed, 0 failed, 0 skipped")
    assert len(records) == 5


# --- verdict/tests line text variants ---


def test_parse_succeeds_with_passing_verdict_text(tmp_path):
    path, _lines = _write_review(
        tmp_path,
        [
            "",
            "Verdict: PASS - no blocking issues",
            "Tests: 142 passed, 0 failed, 0 skipped",
        ],
    )

    records = parse(path)

    record = _find_by_body(records, "Verdict: PASS - no blocking issues")
    assert record.structured is False


def test_parse_succeeds_with_failing_verdict_text(tmp_path):
    path, _lines = _write_review(
        tmp_path,
        [
            "",
            "Verdict: FAIL - 3 blocking issues found",
            "Tests: 12 passed, 2 failed, 0 skipped",
        ],
    )

    records = parse(path)

    record = _find_by_body(records, "Verdict: FAIL - 3 blocking issues found")
    assert record.structured is False


def test_tests_line_accepts_docs_only_none_value(tmp_path):
    path, _lines = _write_review(
        tmp_path,
        [
            "",
            "Verdict: PASS - documentation only change",
            "Tests: none (docs-only)",
        ],
    )

    records = parse(path)

    record = _find_by_body(records, "Tests: none (docs-only)")
    assert record.structured is False


# --- real review file fixture ---

REAL_REVIEW_FIXTURE = (
    Path(__file__).parent / "fixtures" / "00001-engram-core-v1-review-5.md"
)


def test_real_review_file_parses_without_raising():
    records = parse(REAL_REVIEW_FIXTURE)

    assert records


def test_real_review_file_table_rows_produce_structured_records_with_issue_column_heading():
    records = parse(REAL_REVIEW_FIXTURE)

    goldset_record = next(
        r
        for r in records
        if r.structured
        and r.heading == "Gold set covers only 3 of 4 corpora; `decision` corpus empty (SETTLED)"
    )
    assert goldset_record.body.startswith("|")
    assert goldset_record.heading != goldset_record.body


def test_real_review_file_emoji_bullets_produce_structured_records():
    records = parse(REAL_REVIEW_FIXTURE)

    assert any(
        r.structured
        and r.body.startswith("- ")
        and "Memory-corpus repo attribution is always `_unmapped`" in r.heading
        for r in records
    )


def test_real_review_file_unmatched_prose_lands_in_unstructured_records():
    records = parse(REAL_REVIEW_FIXTURE)

    assert any(
        not r.structured and "dismisses Bob's" in r.body for r in records
    )


def test_real_review_file_specific_finding_is_present():
    records = parse(REAL_REVIEW_FIXTURE)

    assert any(
        "Chunker `path.read_text()` has no per-file guard" in r.heading
        for r in records
    )
