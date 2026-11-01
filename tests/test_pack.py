import re

from engram.client import PackBudget
from engram.diffmap import changed_symbols
from engram.findings import FINDINGS_CORPUS
from engram.indexer import IndexReport
from engram.pack import MAX_SYMBOLS_PER_PACK, build
from engram.store import ChunkWithVector, Scope, open_store

from _pack_helpers import (
    _chunk,
    _config,
    _small_budget,
    _vec,
    _write_many_function_diff,
    _write_single_function_diff,
)


# --- B1: reindex runs before retrieval, and its report is carried through ---


def test_reindex_runs_before_the_first_retrieval_and_its_report_is_carried_through(
    tmp_path,
    monkeypatch,
):
    _, diff_path = _write_single_function_diff(tmp_path)
    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path, _small_budget())
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    events = []
    known_report = IndexReport(
        files_scanned=3,
        chunks_added=2,
        chunks_pruned=0,
        corpora_missing=["x"],
    )

    def fake_index(store_arg, config_arg, scope):
        assert store_arg is store
        assert config_arg is config
        assert scope == Scope("repo", "repoA")
        events.append("reindex")
        return known_report

    def spy_embed(texts, entry):
        events.append("embed")
        return [_vec([1.0, 0.0, 0.0, 0.0]) for _ in texts]

    monkeypatch.setattr("engram.pack.index", fake_index)
    monkeypatch.setattr("engram.pack.embed", spy_embed)
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [_vec([0, 0, 0, 1]) for _ in texts],
    )

    report = build(store, config, "repoA", tmp_path, "b1", diff_path, out_dir=out_dir)

    assert events == ["reindex", "embed"]
    assert report.index_report == known_report


# --- B3: symbols beyond the cap are counted and noted, never used as query subjects ---


def test_symbols_beyond_the_cap_are_counted_and_noted_in_the_rendered_pack(
    tmp_path, monkeypatch
):
    count = MAX_SYMBOLS_PER_PACK + 3
    _, diff_path = _write_many_function_diff(tmp_path, count)
    all_symbols = changed_symbols(diff_path, tmp_path)
    assert len(all_symbols) == count

    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path, _small_budget())
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    monkeypatch.setattr(
        "engram.pack.index", lambda *a, **k: IndexReport(0, 0, 0, [])
    )
    monkeypatch.setattr(
        "engram.pack.embed",
        lambda texts, entry: [_vec([1.0, 0.0, 0.0, 0.0]) for _ in texts],
    )
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [_vec([0, 0, 0, 1]) for _ in texts],
    )

    report = build(store, config, "repoA", tmp_path, "b3", diff_path, out_dir=out_dir)

    assert report.symbols_omitted == 3
    content = report.path.read_text()
    assert re.search(r"\b3\b", content), (
        "omitted count must be noted somewhere in the rendered file"
    )


# --- B4: exactly one batched embed call covers every capped symbol's query text ---


def test_all_capped_symbol_query_texts_are_embedded_in_exactly_one_batched_call(
    tmp_path,
    monkeypatch,
):
    count = MAX_SYMBOLS_PER_PACK + 3
    _, diff_path = _write_many_function_diff(tmp_path, count)

    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path, _small_budget())
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    embed_calls = []

    def spy_embed(texts, entry):
        embed_calls.append(list(texts))
        return [_vec([1.0, 0.0, 0.0, 0.0]) for _ in texts]

    monkeypatch.setattr(
        "engram.pack.index", lambda *a, **k: IndexReport(0, 0, 0, [])
    )
    monkeypatch.setattr("engram.pack.embed", spy_embed)
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [_vec([0, 0, 0, 1]) for _ in texts],
    )

    build(store, config, "repoA", tmp_path, "b4", diff_path, out_dir=out_dir)

    assert len(embed_calls) == 1
    assert len(embed_calls[0]) == MAX_SYMBOLS_PER_PACK


# --- B6: self / sibling-capped / beyond-cap changed-symbol hits are excluded everywhere ---


def test_self_sibling_and_beyond_cap_changed_symbol_hits_are_excluded_from_every_section(
    tmp_path,
    monkeypatch,
):
    count = MAX_SYMBOLS_PER_PACK + 1
    _, diff_path = _write_many_function_diff(tmp_path, count)
    all_symbols = changed_symbols(diff_path, tmp_path)
    capped = all_symbols[:MAX_SYMBOLS_PER_PACK]
    beyond = all_symbols[MAX_SYMBOLS_PER_PACK]
    symbol_a = capped[0]
    symbol_b = capped[1]

    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path, _small_budget())
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    query_vector = _vec([1.0, 0.0, 0.0, 0.0])
    monkeypatch.setattr(
        "engram.pack.index", lambda *a, **k: IndexReport(0, 0, 0, [])
    )
    monkeypatch.setattr(
        "engram.pack.embed", lambda texts, entry: [query_vector for _ in texts]
    )
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [_vec([0, 0, 0, 1]) for _ in texts],
    )

    self_chunk = _chunk(
        path=symbol_a.path,
        line_start=symbol_a.line_start,
        line_end=symbol_a.line_end,
        body="self-match-exclusion-marker",
        content_hash="h-self",
    )
    sibling_chunk = _chunk(
        path=symbol_b.path,
        line_start=symbol_b.line_start,
        line_end=symbol_b.line_end,
        body="sibling-capped-exclusion-marker",
        content_hash="h-sibling",
    )
    beyond_chunk = _chunk(
        path=beyond.path,
        line_start=beyond.line_start,
        line_end=beyond.line_end,
        body="beyond-cap-exclusion-marker",
        content_hash="h-beyond",
    )
    unrelated_chunk = _chunk(
        path=str(tmp_path / "unrelated.py"),
        line_start=9001,
        line_end=9002,
        body="unrelated-surviving-marker",
        content_hash="h-unrelated",
    )
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=self_chunk, vector=query_vector),
            ChunkWithVector(chunk=sibling_chunk, vector=query_vector),
            ChunkWithVector(chunk=beyond_chunk, vector=query_vector),
            ChunkWithVector(chunk=unrelated_chunk, vector=query_vector),
        ],
    )

    report = build(store, config, "repoA", tmp_path, "b6", diff_path, out_dir=out_dir)

    content = report.path.read_text()
    assert "self-match-exclusion-marker" not in content
    assert "sibling-capped-exclusion-marker" not in content
    assert "beyond-cap-exclusion-marker" not in content
    assert "unrelated-surviving-marker" in content


# --- B7: a code hit's rendered body is the stored Chunk.body, never a disk re-read ---


def test_similar_code_hit_body_comes_from_the_stored_chunk_not_the_worktree_file(
    tmp_path,
    monkeypatch,
):
    _, diff_path = _write_single_function_diff(tmp_path)
    disk_only_path = tmp_path / "other.py"
    disk_only_path.write_text("DISK-ONLY-MARKER-xyz should never be rendered\n")

    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path, _small_budget())
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    query_vector = _vec([1.0, 0.0, 0.0, 0.0])
    monkeypatch.setattr(
        "engram.pack.index", lambda *a, **k: IndexReport(0, 0, 0, [])
    )
    monkeypatch.setattr(
        "engram.pack.embed", lambda texts, entry: [query_vector for _ in texts]
    )
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [_vec([0, 0, 0, 1]) for _ in texts],
    )

    stored_chunk = _chunk(
        path=str(disk_only_path),
        line_start=1,
        line_end=1,
        body="STORE-BODY-MARKER-xyz stored text",
        content_hash="h-store",
    )
    store.upsert_chunks([ChunkWithVector(chunk=stored_chunk, vector=query_vector)])

    report = build(store, config, "repoA", tmp_path, "b7", diff_path, out_dir=out_dir)

    content = report.path.read_text()
    assert "STORE-BODY-MARKER-xyz" in content
    assert "DISK-ONLY-MARKER-xyz" not in content


# --- B8a: a section over its cap drops the lowest-scored item and is flagged ---


def test_section_over_its_cap_drops_the_lowest_scored_item_and_is_flagged_as_trimmed(
    tmp_path,
    monkeypatch,
):
    _, diff_path = _write_single_function_diff(tmp_path)

    store = open_store(tmp_path / "engram.db")
    tight_similar_budget = PackBudget(
        hard_cap_tokens=2000,
        similar_cap_tokens=25,
        reuse_cap_tokens=300,
        findings_cap_tokens=300,
        prose_cap_tokens=200,
    )
    config = _config(tmp_path, tight_similar_budget)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    monkeypatch.setattr(
        "engram.pack.index", lambda *a, **k: IndexReport(0, 0, 0, [])
    )
    monkeypatch.setattr(
        "engram.pack.embed",
        lambda texts, entry: [_vec([1.0, 0.0, 0.0, 0.0]) for _ in texts],
    )
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [_vec([0, 0, 0, 1]) for _ in texts],
    )

    vectors = [
        _vec([1.0, 0.0, 0.0, 0.0]),
        _vec([0.9, 0.436, 0.0, 0.0]),
        _vec([0.7, 0.7, 0.0, 0.0]),
        _vec([0.436, 0.9, 0.0, 0.0]),
        _vec([0.0, 1.0, 0.0, 0.0]),
    ]
    items = []
    for rank, vec in enumerate(vectors, start=1):
        chunk = _chunk(
            path=f"rank{rank}.py",
            line_start=1,
            line_end=1,
            body=f"rank{rank}-marker filler filler filler filler text here now",
            content_hash=f"h-rank{rank}",
        )
        items.append(ChunkWithVector(chunk=chunk, vector=vec))
    store.upsert_chunks(items)

    report = build(
        store, config, "repoA", tmp_path, "b8trim", diff_path, out_dir=out_dir
    )

    content = report.path.read_text()
    assert "Similar code" in report.trimmed_sections
    assert "rank1-marker" in content
    assert "rank5-marker" not in content


# --- B8b: tied scores break the tie via the full (score, repo, path, ...) tuple ---


def test_tied_score_items_are_ordered_by_the_full_tiebreak_tuple(tmp_path, monkeypatch):
    _, diff_path = _write_single_function_diff(tmp_path)

    store = open_store(tmp_path / "engram.db")
    config = _config(tmp_path, _small_budget())
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    query_vector = _vec([1.0, 0.0, 0.0, 0.0])
    monkeypatch.setattr(
        "engram.pack.index", lambda *a, **k: IndexReport(0, 0, 0, [])
    )
    monkeypatch.setattr(
        "engram.pack.embed", lambda texts, entry: [query_vector for _ in texts]
    )
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [_vec([0, 0, 0, 1]) for _ in texts],
    )

    # identical body/heading -> identical BM25 and KNN legs -> a genuine score tie.
    # path is set the *opposite* way from repo (repo "aaa" gets the alphabetically
    # later path, repo "zzz" gets the earlier one) so sorting by path instead of
    # repo first would flip the expected order -- a real discriminator.
    tied_body = "tie-break-shared-body-text-filler"
    chunk_low_repo = _chunk(
        repo="aaa-repo",
        path="zzz-path.py",
        line_start=1,
        line_end=1,
        heading="H",
        body=tied_body,
        content_hash="h-tie-a",
    )
    chunk_high_repo = _chunk(
        repo="zzz-repo",
        path="aaa-path.py",
        line_start=1,
        line_end=1,
        heading="H",
        body=tied_body,
        content_hash="h-tie-b",
    )
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=chunk_low_repo, vector=query_vector),
            ChunkWithVector(chunk=chunk_high_repo, vector=query_vector),
        ],
    )

    report = build(
        store, config, "repoX", tmp_path, "b8tie", diff_path, out_dir=out_dir
    )

    content = report.path.read_text()
    label_a = "aaa-repo:zzz-path.py:1-1"
    label_b = "zzz-repo:aaa-path.py:1-1"
    assert label_a in content
    assert label_b in content
    assert content.index(label_a) < content.index(label_b)


# --- B11: the hard cap on the rendered file is enforced even when the first render overshoots ---


def test_hard_cap_is_enforced_by_dropping_items_when_the_first_render_overshoots(
    tmp_path,
    monkeypatch,
):
    _, diff_path = _write_single_function_diff(tmp_path)

    store = open_store(tmp_path / "engram.db")
    tight_budget = PackBudget(
        hard_cap_tokens=400,
        similar_cap_tokens=300,
        reuse_cap_tokens=300,
        findings_cap_tokens=300,
        prose_cap_tokens=100,
    )
    config = _config(tmp_path, tight_budget)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    query_vector = _vec([1.0, 0.0, 0.0, 0.0])
    monkeypatch.setattr(
        "engram.pack.index", lambda *a, **k: IndexReport(0, 0, 0, [])
    )
    monkeypatch.setattr(
        "engram.pack.embed", lambda texts, entry: [query_vector for _ in texts]
    )
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [_vec([0, 0, 0, 1]) for _ in texts],
    )

    filler = "overshoot-filler-text " * 40
    similar_chunk = _chunk(
        corpus="code",
        repo="repoA",
        path="a.py",
        line_start=1,
        line_end=1,
        body=f"similar-marker {filler}",
        content_hash="h-sim",
    )
    reuse_chunk = _chunk(
        corpus="code",
        repo="repoB",
        path="b.py",
        line_start=1,
        line_end=1,
        body=f"reuse-marker {filler}",
        content_hash="h-reuse",
    )
    findings_chunk = _chunk(
        corpus=FINDINGS_CORPUS,
        repo="repoA",
        path="findings/f.md",
        line_start=1,
        line_end=1,
        body=f"findings-marker {filler}",
        content_hash="h-find",
    )
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=similar_chunk, vector=query_vector),
            ChunkWithVector(chunk=reuse_chunk, vector=query_vector),
            ChunkWithVector(chunk=findings_chunk, vector=query_vector),
        ],
    )

    report = build(store, config, "repoA", tmp_path, "b11", diff_path, out_dir=out_dir)

    content = report.path.read_text()
    assert report.total_estimated_tokens == len(content) // 4
    assert report.total_estimated_tokens <= tight_budget.hard_cap_tokens


# --- B12: freshness line, section headings, and origin label shapes are present ---


def test_rendered_pack_carries_freshness_line_section_headings_and_origin_labels(
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
        "engram.pack.index", lambda *a, **k: IndexReport(0, 0, 0, [])
    )
    monkeypatch.setattr(
        "engram.pack.embed", lambda texts, entry: [query_vector for _ in texts]
    )
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [_vec([0, 0, 0, 1]) for _ in texts],
    )

    other_path = tmp_path / "other.py"
    code_chunk = _chunk(
        corpus="code",
        repo="repoA",
        path=str(other_path),
        line_start=5,
        line_end=6,
        body="origin-label-code-marker",
        content_hash="h-code-b12",
    )
    findings_chunk = _chunk(
        corpus=FINDINGS_CORPUS,
        repo="repoA",
        path="findings/note.md",
        line_start=1,
        line_end=1,
        body="origin-label-findings-marker",
        content_hash="h-find-b12",
    )
    store.upsert_chunks(
        [
            ChunkWithVector(chunk=code_chunk, vector=query_vector),
            ChunkWithVector(chunk=findings_chunk, vector=query_vector),
        ],
    )

    report = build(store, config, "repoA", tmp_path, "b12", diff_path, out_dir=out_dir)

    content = report.path.read_text()

    assert (
        "Portfolio freshness: NOT refreshed this cycle (PRD 00002 pending)" in content
    )

    for label in (
        "Similar code",
        "Reuse precedent",
        "Findings precedent",
        "Task prose",
    ):
        assert re.search(rf"^##.*{re.escape(label)}", content, re.MULTILINE), label
    assert {s.label for s in report.sections} == {
        "Similar code",
        "Reuse precedent",
        "Findings precedent",
        "Task prose",
    }

    assert f"repoA:{other_path}:5-6" in content
    assert f"{FINDINGS_CORPUS}:findings/note.md" in content


# --- B14: two builds over identical fixture state are byte-identical ---


def test_two_builds_over_identical_fixture_state_produce_byte_identical_output(
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
        "engram.pack.index", lambda *a, **k: IndexReport(0, 0, 0, [])
    )
    monkeypatch.setattr(
        "engram.pack.embed", lambda texts, entry: [query_vector for _ in texts]
    )
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [_vec([0, 0, 0, 1]) for _ in texts],
    )

    code_chunk = _chunk(
        corpus="code",
        repo="repoA",
        path=str(tmp_path / "other.py"),
        line_start=5,
        line_end=6,
        body="determinism-marker",
        content_hash="h-det",
    )
    store.upsert_chunks([ChunkWithVector(chunk=code_chunk, vector=query_vector)])

    first = build(store, config, "repoA", tmp_path, "b14", diff_path, out_dir=out_dir)
    first_bytes = first.path.read_bytes()

    second = build(store, config, "repoA", tmp_path, "b14", diff_path, out_dir=out_dir)
    second_bytes = second.path.read_bytes()

    assert first_bytes == second_bytes
