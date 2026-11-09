from _pack_helpers import (
    _chunk,
    _config,
    _small_budget,
    _vec,
    _write_single_function_diff,
)

from engram.indexer import IndexReport
from engram.pack import _FRESHNESS_LINE, _task_prose_entries, build
from engram.store import ChunkWithVector, open_store

# --- regression: the Task-prose branch, which the contract tests never exercised ---


def _prose_fixture(tmp_path, monkeypatch):
    """Shared setup for the Task-prose regression tests below."""
    _, diff_path = _write_single_function_diff(tmp_path)
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path, _small_budget())
    monkeypatch.setattr(
        "engram.pack.index",
        lambda *a, **k: IndexReport(0, 0, 0, []),
    )
    monkeypatch.setattr(
        "engram.pack.embed",
        lambda texts, entry: [_vec([1.0, 0.0, 0.0, 0.0]) for _ in texts],
    )
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [_vec([0, 0, 0, 1]) for _ in texts],
    )
    return store, config, diff_path


def test_capsule_entry_carries_the_prose_under_the_active_work_heading_not_the_heading(
    tmp_path,
    monkeypatch,
):
    store, config, diff_path = _prose_fixture(tmp_path, monkeypatch)
    capsule_path = tmp_path / "project-capsule.md"
    capsule_path.write_text(
        "# Capsule\n"
        "\n"
        "## Key Invariants\n"
        "- something unrelated\n"
        "\n"
        "## Active Work\n"
        "- PRD 00004 in wip: review packs\n"
        "- next up: the CLI verb\n"
        "\n"
        "## Project Health\n"
        "- green\n",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = build(
        store,
        config,
        "repoA",
        tmp_path,
        "prose-capsule",
        diff_path,
        capsule_path=capsule_path,
        out_dir=out_dir,
    )

    content = report.path.read_text()
    # the heading is a locator, not the payload: the prose beneath it is what a
    # reviewer needs, and it lives on the following lines.
    assert "PRD 00004 in wip: review packs" in content
    # and it must not bleed past the section into the next heading's content
    assert "green" not in content


def test_oversized_prd_is_truncated_into_task_prose_rather_than_dropped_whole(
    tmp_path,
    monkeypatch,
):
    store, config, diff_path = _prose_fixture(tmp_path, monkeypatch)
    prd_path = tmp_path / "00004-prd.md"
    # far beyond prose_cap_tokens (200 tokens == 800 chars) so whole-entry
    # dropping would make the PRD vanish entirely instead of contributing.
    prd_path.write_text(
        "PRD-HEAD-MARKER goal statement\n" + ("prd filler line\n" * 500),
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = build(
        store,
        config,
        "repoA",
        tmp_path,
        "prose-prd",
        diff_path,
        prd_path=prd_path,
        out_dir=out_dir,
    )

    content = report.path.read_text()
    assert "PRD-HEAD-MARKER" in content
    assert report.total_estimated_tokens <= config.pack_budget.hard_cap_tokens


def test_prd_survives_truncation_when_an_earlier_prose_entry_precedes_it(
    tmp_path,
    monkeypatch,
):
    # Regression for the separator off-by-one: the room left for the PRD must
    # account for the "\n\n" that will join it to the entries already present.
    # The capsule section below is 18 chars, so len(joined) % 4 == 2 -- the
    # residue at which naive `cap - estimate(joined)` arithmetic overshoots the
    # cap by exactly one token once the separator is added, and _cap_items then
    # pops the PRD entirely, reinstating the very bug this pins.
    store, config, diff_path = _prose_fixture(tmp_path, monkeypatch)
    capsule_path = tmp_path / "project-capsule.md"
    capsule_path.write_text("## Active Work\n- PRD 00004 in wip\n")
    assert len("- PRD 00004 in wip") % 4 == 2

    prd_path = tmp_path / "00004-prd.md"
    prd_path.write_text(
        "PRD-HEAD-MARKER goal statement\n" + ("prd filler line\n" * 500),
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = build(
        store,
        config,
        "repoA",
        tmp_path,
        "prose-sep",
        diff_path,
        prd_path=prd_path,
        capsule_path=capsule_path,
        out_dir=out_dir,
    )

    content = report.path.read_text()
    assert "- PRD 00004 in wip" in content
    assert "PRD-HEAD-MARKER" in content
    prose = next(s for s in report.sections if s.label == "Task prose")
    assert prose.estimated_tokens <= config.pack_budget.prose_cap_tokens


def test_oversized_capsule_does_not_crowd_out_the_prd_from_task_prose(
    tmp_path,
    monkeypatch,
):
    # The capsule's Active Work section can be far larger than prose_cap_tokens
    # on its own. Appending it at full length used up the whole budget before
    # the PRD was even considered, so _cap_items then popped the memory hits
    # and the capsule entry itself, leaving Task prose empty. Every prose
    # source must be truncated to the room left, and the PRD must keep room.
    store, config, diff_path = _prose_fixture(tmp_path, monkeypatch)
    capsule_path = tmp_path / "project-capsule.md"
    capsule_path.write_text(
        "## Active Work\n"
        + ("capsule filler line far exceeding the prose budget\n" * 60),
    )
    prd_path = tmp_path / "00004-prd.md"
    prd_path.write_text(
        "PRD-HEAD-MARKER goal statement\n" + ("prd filler line\n" * 500),
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = build(
        store,
        config,
        "repoA",
        tmp_path,
        "prose-capsule-starve",
        diff_path,
        prd_path=prd_path,
        capsule_path=capsule_path,
        out_dir=out_dir,
    )

    content = report.path.read_text()
    assert "capsule filler line" in content
    assert "PRD-HEAD-MARKER" in content
    prose = next(s for s in report.sections if s.label == "Task prose")
    assert prose.estimated_tokens <= config.pack_budget.prose_cap_tokens


# --- regression: an unreadable --prd/--capsule path must be disclosed, not swallowed ---


def test_unreadable_prd_path_is_noted_in_the_rendered_pack(tmp_path, monkeypatch):
    store, config, diff_path = _prose_fixture(tmp_path, monkeypatch)
    missing_prd_path = tmp_path / "typo-00004-prd.md"
    assert not missing_prd_path.exists()
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = build(
        store,
        config,
        "repoA",
        tmp_path,
        "prose-prd-unreadable",
        diff_path,
        prd_path=missing_prd_path,
        out_dir=out_dir,
    )

    content = report.path.read_text()
    assert str(missing_prd_path) in content, (
        "an unreadable --prd path must be named in the rendered pack, not dropped"
    )


def test_unreadable_capsule_path_is_noted_in_the_rendered_pack(tmp_path, monkeypatch):
    store, config, diff_path = _prose_fixture(tmp_path, monkeypatch)
    missing_capsule_path = tmp_path / "typo-capsule.md"
    assert not missing_capsule_path.exists()
    prd_path = tmp_path / "00004-prd.md"
    prd_path.write_text("# Some PRD\n\nPRD-BODY-MARKER\n")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = build(
        store,
        config,
        "repoA",
        tmp_path,
        "prose-capsule-unreadable",
        diff_path,
        prd_path=prd_path,
        capsule_path=missing_capsule_path,
        out_dir=out_dir,
    )

    content = report.path.read_text()
    assert str(missing_capsule_path) in content, (
        "an unreadable --capsule path must be named in the rendered pack, not dropped"
    )
    # the rest of the pack keeps rendering: the readable PRD's own content still
    # lands in Task prose despite the capsule being unreadable
    assert "PRD-BODY-MARKER" in content


def test_both_unreadable_paths_are_each_noted_in_the_rendered_pack(
    tmp_path,
    monkeypatch,
):
    store, config, diff_path = _prose_fixture(tmp_path, monkeypatch)
    missing_prd_path = tmp_path / "typo-prd.md"
    missing_capsule_path = tmp_path / "typo-capsule.md"
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = build(
        store,
        config,
        "repoA",
        tmp_path,
        "prose-both-unreadable",
        diff_path,
        prd_path=missing_prd_path,
        capsule_path=missing_capsule_path,
        out_dir=out_dir,
    )

    content = report.path.read_text()
    assert str(missing_prd_path) in content
    assert str(missing_capsule_path) in content


def test_omission_note_is_a_top_of_pack_disclosure_not_inside_task_prose_section(
    tmp_path,
    monkeypatch,
):
    store, config, diff_path = _prose_fixture(tmp_path, monkeypatch)
    missing_prd_path = tmp_path / "typo-prd.md"
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = build(
        store,
        config,
        "repoA",
        tmp_path,
        "prose-note-placement",
        diff_path,
        prd_path=missing_prd_path,
        out_dir=out_dir,
    )

    content = report.path.read_text()
    # "## Similar code" is always the first rendered section heading (it is
    # first in _SECTION_ORDER and is emitted whether or not it has items), so
    # everything before it is the top-of-pack disclosure block that also holds
    # the "n changed symbol(s) omitted" line.
    top_of_pack, _, _rest = content.partition("## Similar code")
    assert str(missing_prd_path) in top_of_pack, (
        "the omission note must render above the section headings, in the same "
        "disclosure block as the symbols-omitted line"
    )

    prose_section = next(s for s in report.sections if s.label == "Task prose")
    assert str(missing_prd_path) not in prose_section.body, (
        "a note placed inside a capped section can be trimmed away by that "
        "section's own cap, which is not a disclosure"
    )


def test_omission_note_survives_task_prose_truncation_under_budget_pressure(
    tmp_path,
    monkeypatch,
):
    # Pair an unreadable capsule with a PRD large enough to force Task-prose
    # truncation (see test_oversized_prd_is_truncated_into_task_prose_rather_
    # than_dropped_whole above), so the disclosure has to survive the same
    # budget pressure that trims the section it is not part of.
    store, config, diff_path = _prose_fixture(tmp_path, monkeypatch)
    missing_capsule_path = tmp_path / "typo-capsule.md"
    prd_path = tmp_path / "00004-prd.md"
    prd_path.write_text(
        "PRD-HEAD-MARKER goal statement\n" + ("prd filler line\n" * 500),
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = build(
        store,
        config,
        "repoA",
        tmp_path,
        "prose-note-survives-trim",
        diff_path,
        prd_path=prd_path,
        capsule_path=missing_capsule_path,
        out_dir=out_dir,
    )

    content = report.path.read_text()
    prose = next(s for s in report.sections if s.label == "Task prose")
    # confirm truncation pressure was actually exercised, not sidestepped
    assert prose.estimated_tokens <= config.pack_budget.prose_cap_tokens
    assert "PRD-HEAD-MARKER" in content
    assert str(missing_capsule_path) in content


def test_capsule_with_no_active_work_section_produces_no_omission_note(
    tmp_path,
    monkeypatch,
):
    # A capsule that reads fine but has no "## Active Work" heading is absence
    # of content, not an unreadable path -- existing documented behavior that
    # must not start emitting a disclosure line.
    store, config, diff_path = _prose_fixture(tmp_path, monkeypatch)
    capsule_path = tmp_path / "project-capsule.md"
    capsule_path.write_text("# Capsule\n\n## Key Invariants\n- something unrelated\n")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = build(
        store,
        config,
        "repoA",
        tmp_path,
        "prose-capsule-no-heading",
        diff_path,
        capsule_path=capsule_path,
        out_dir=out_dir,
    )

    content = report.path.read_text()
    assert str(capsule_path) not in content


def test_absent_prd_and_capsule_paths_produce_no_omission_note(tmp_path, monkeypatch):
    # Neither flag was supplied at all (both None) -- nothing failed to read,
    # so nothing should be disclosed. The top-of-pack block must be exactly
    # the freshness line, unchanged from today's baseline.
    store, config, diff_path = _prose_fixture(tmp_path, monkeypatch)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = build(
        store,
        config,
        "repoA",
        tmp_path,
        "prose-no-paths",
        diff_path,
        out_dir=out_dir,
    )

    assert report.symbols_omitted == 0
    content = report.path.read_text()
    top_of_pack, _, _rest = content.partition("## Similar code")
    assert top_of_pack == f"{_FRESHNESS_LINE}\n\n"


# --- regression: build() must not require its out_dir to exist ---


def test_build_creates_a_missing_out_dir_instead_of_crashing(tmp_path, monkeypatch):
    store, config, diff_path = _prose_fixture(tmp_path, monkeypatch)
    missing_out_dir = tmp_path / "never" / "created"

    report = build(
        store,
        config,
        "repoA",
        tmp_path,
        "mkdir",
        diff_path,
        out_dir=missing_out_dir,
    )

    assert report.path.exists()
    assert report.path.parent == missing_out_dir


# --- B15: foreign-repo chunks must never leak into "Similar code" ---


def test_a_high_scoring_foreign_repo_chunk_never_reaches_the_similar_code_section(
    tmp_path,
    monkeypatch,
):
    _, diff_path = _write_single_function_diff(tmp_path)

    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path, _small_budget())
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    query_vector = _vec([1.0, 0.0, 0.0, 0.0])
    monkeypatch.setattr(
        "engram.pack.index",
        lambda *a, **k: IndexReport(0, 0, 0, []),
    )
    monkeypatch.setattr(
        "engram.pack.embed",
        lambda texts, entry: [query_vector for _ in texts],
    )
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [_vec([0, 0, 0, 1]) for _ in texts],
    )

    # Both chunks share the exact same vector as the query, so both are
    # maximally similar and ranking cannot explain either one's absence.
    foreign_chunk = _chunk(
        repo="repoB",
        path=str(tmp_path / "foreign.py"),
        line_start=1,
        line_end=1,
        body="FOREIGN-REPO-MARKER-xyz",
        content_hash="h-foreign",
    )
    local_chunk = _chunk(
        repo="repoA",
        path=str(tmp_path / "unrelated.py"),
        line_start=9001,
        line_end=9002,
        body="LOCAL-REPO-MARKER-xyz",
        content_hash="h-local",
    )
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=foreign_chunk, vector=query_vector),
            ChunkWithVector(chunk=local_chunk, vector=query_vector),
        ],
    )

    report = build(store, config, "repoA", tmp_path, "b15", diff_path, out_dir=out_dir)

    similar_section = next(s for s in report.sections if s.label == "Similar code")
    reuse_section = next(s for s in report.sections if s.label == "Reuse precedent")

    # Regression guard: foreign repo must not appear in Similar code
    assert "FOREIGN-REPO-MARKER-xyz" not in similar_section.body
    # Local repo must appear, otherwise the exclusion above is vacuous
    assert "LOCAL-REPO-MARKER-xyz" in similar_section.body
    # Foreign chunk is retrievable and high-scoring (proves scope filter, not
    # reachability, is responsible for its absence from Similar code)
    assert "FOREIGN-REPO-MARKER-xyz" in reuse_section.body


# --- regression: Task-prose memory retrieval is keyed on the PRD title, not the cycle id ---


def test_memory_query_text_is_the_prds_first_top_level_heading(tmp_path, monkeypatch):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path, _small_budget())
    prd_path = tmp_path / "00004-engram-review-packs-v1.md"
    prd_path.write_text(
        "# Engram Review Packs: Diff-Selective Reviewer Context\n"
        "\n"
        "Some PRD body text that is not the title.\n",
    )

    query_calls = []

    def fake_query(*args, **kwargs):
        query_calls.append((args, kwargs))
        return []

    monkeypatch.setattr("engram.pack.query", fake_query)

    _task_prose_entries(store, config, "cyc1", prd_path, None, 200)

    assert len(query_calls) == 1
    args, _kwargs = query_calls[0]
    assert args[2] == "Engram Review Packs: Diff-Selective Reviewer Context"


def test_memory_query_is_skipped_when_no_heading_exists(
    tmp_path,
    monkeypatch,
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path, _small_budget())
    prd_path = tmp_path / "00004-engram-review-packs-v1.md"
    prd_path.write_text("This file has no top-level markdown heading at all.\n")

    query_calls = []

    def fake_query(*args, **kwargs):
        query_calls.append((args, kwargs))
        return []

    monkeypatch.setattr("engram.pack.query", fake_query)

    _task_prose_entries(store, config, "cyc1", prd_path, None, 200)

    assert query_calls == []


def test_memory_query_is_skipped_entirely_when_no_prd_path_is_resolved(
    tmp_path,
    monkeypatch,
):
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path, _small_budget())

    query_calls = []

    def fake_query(*args, **kwargs):
        query_calls.append((args, kwargs))
        return []

    monkeypatch.setattr("engram.pack.query", fake_query)

    _task_prose_entries(store, config, "cyc1", None, None, 200)

    assert query_calls == []
