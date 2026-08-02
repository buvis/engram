import types

from pathlib import Path

import pytest

from engram.client import EmbeddingEntry, EngramConfig, ServerLease, load_config
from engram.corpora import CorpusFile
from engram.harness import (
    RRF_DEDUP_POOL,
    GoldEntry,
    HarnessReport,
    ModelScore,
    _sanitize_for_filename,
    _write_pinned,
    load_goldset,
    run_harness,
)
from engram.indexer import IndexReport
from engram.query import Pointer

_VALID_CORPORA = ("memory", "prd", "decision", "discovery")


# --- fixture builders ---


def _dummy_files(tmp_path, count, prefix="doc"):
    files = []
    for i in range(count):
        f = tmp_path / f"{prefix}{i}.md"
        f.write_text(f"# Doc {i}\ncontent {i}\n")
        files.append(f)
    return files


def _valid_goldset_entries(files):
    return [
        {
            "query": f"query text {i}",
            "expected_path": str(f),
            "corpus": _VALID_CORPORA[i % len(_VALID_CORPORA)],
        }
        for i, f in enumerate(files)
    ]


def _write_goldset(path, entries):
    lines = []
    for e in entries:
        lines.append(f'- query: "{e["query"]}"')
        lines.append(f'  expected_path: "{e["expected_path"]}"')
        lines.append(f'  corpus: {e["corpus"]}')
    path.write_text("\n".join(lines) + "\n")


def _entry(id_, port):
    return EmbeddingEntry(id=id_, endpoint=f"http://127.0.0.1:{port}/v1")


def _harness_config(tmp_path, entries, pinned_id=None):
    return EngramConfig(
        embeddings=entries, pinned_id=pinned_id, config_path=tmp_path / "config.toml"
    )


def _write_config_toml(path, entries):
    lines = []
    for e in entries:
        lines.append("[[embedding]]")
        lines.append(f'id = "{e.id}"')
        lines.append(f'endpoint = "{e.endpoint}"')
        lines.append("")
    lines.append("[pinned]")
    lines.append('id = ""')
    lines.append("")
    path.write_text("\n".join(lines))


def _pointer(path, rank=1, score=1.0, corpus="memory", repo="repoA"):
    return Pointer(
        rank=rank,
        score=score,
        path=path,
        line_start=1,
        line_end=1,
        heading="H",
        corpus=corpus,
        repo=repo,
    )


def _pointers_from_paths(paths):
    return [_pointer(path=p, rank=i + 1, score=1.0 / (i + 1)) for i, p in enumerate(paths)]


def _hit_or_miss_query(expected_by_query, hit_predicate):
    """Build a `query.query` stub: returns a hit Pointer at the expected path
    when hit_predicate(config) is True for that call's isolated per-candidate
    config, otherwise a Pointer at a path that never matches any gold entry."""

    def scripted_query(store, config, text, scope, corpus=None, k=5):
        if hit_predicate(config):
            return [_pointer(path=expected_by_query[text], rank=1)]
        return [_pointer(path="/never/matches.md", rank=1)]

    return scripted_query


def _noop_index(store, config, scope, corpus=None):
    return IndexReport(
        files_scanned=0, chunks_added=0, chunks_updated=0, chunks_pruned=0, corpora_missing=[]
    )


def _make_ensure_served():
    def fake_ensure_served(entry):
        pid = 10000 + abs(hash(entry.id)) % 1000
        return ServerLease(entry=entry, spawned=True, pid=pid)

    return fake_ensure_served


def _make_stop_served(stopped_list):
    def fake_stop_served(lease):
        stopped_list.append(lease)

    return fake_stop_served


def _harmless_enumerate_corpora(tmp_path):
    # A single real file with vocabulary that never overlaps any distinctive
    # query token used elsewhere in this file, so the rg baseline pass (which
    # is NOT stubbed — its exact internals aren't part of the public API
    # under test) always has something harmless, real, and fast to search
    # instead of falling back to scanning an unknown working directory.
    baseline_file = tmp_path / "_baseline_probe.md"
    if not baseline_file.exists():
        baseline_file.write_text("# Baseline probe\nlorem ipsum dolor sit amet\n")

    def fake_enum(*a, **k):
        yield CorpusFile("memory", "repoBase", baseline_file)

    return fake_enum


def _patch_common(
    monkeypatch,
    tmp_path,
    query_fn,
    enumerate_fn=None,
    ensure_served_fn=None,
    stop_served_fn=None,
):
    monkeypatch.setattr(
        "engram.harness.ensure_served", ensure_served_fn or _make_ensure_served()
    )
    monkeypatch.setattr(
        "engram.harness.stop_served", stop_served_fn or _make_stop_served([])
    )
    monkeypatch.setattr("engram.harness.index", _noop_index)
    monkeypatch.setattr("engram.harness.query", query_fn)
    monkeypatch.setattr(
        "engram.harness.enumerate_corpora", enumerate_fn or _harmless_enumerate_corpora(tmp_path)
    )
    # _baseline_hit_rate now also chains in the transcripts and symbols
    # producers; default them to no-ops so existing tests (written before
    # those producers existed) don't hit the real filesystem or spawn git.
    monkeypatch.setattr("engram.harness.transcripts.enumerate", lambda *a, **k: iter(()))
    monkeypatch.setattr("engram.harness.symbols.enumerate", lambda *a, **k: iter(()))


# --- load_goldset: entry count ---


def test_load_goldset_rejects_fewer_than_30_entries(tmp_path):
    files = _dummy_files(tmp_path, 10)
    entries = _valid_goldset_entries(files)
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries)

    with pytest.raises(ValueError):
        load_goldset(goldset_path)


# --- load_goldset: corpus validation ---


def test_load_goldset_rejects_entry_with_unrecognized_corpus(tmp_path):
    files = _dummy_files(tmp_path, 30)
    entries = _valid_goldset_entries(files)
    entries[0]["corpus"] = "not-a-real-corpus"
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries)

    with pytest.raises(ValueError):
        load_goldset(goldset_path)


# --- load_goldset: expected_path existence ---


def test_load_goldset_rejects_entry_with_missing_expected_path(tmp_path):
    files = _dummy_files(tmp_path, 30)
    entries = _valid_goldset_entries(files)
    entries[0]["expected_path"] = str(tmp_path / "does-not-exist.md")
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries)

    with pytest.raises(ValueError):
        load_goldset(goldset_path)


# --- load_goldset: valid fixture accepted and normalized ---


def test_load_goldset_accepts_valid_fixture_and_normalizes_expected_path(tmp_path):
    files = _dummy_files(tmp_path, 32)
    entries = _valid_goldset_entries(files)
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries)

    result = load_goldset(goldset_path)

    assert len(result) == 32
    for gold_entry, file, entry in zip(result, files, entries):
        assert isinstance(gold_entry, GoldEntry)
        assert gold_entry.query == entry["query"]
        assert gold_entry.corpus == entry["corpus"]
        assert gold_entry.expected_path == str(file.resolve())
        assert Path(gold_entry.expected_path).is_absolute()


def test_load_goldset_accepts_transcripts_and_code_corpora(tmp_path):
    files = _dummy_files(tmp_path, 30)
    entries = _valid_goldset_entries(files)
    entries[0]["corpus"] = "transcripts"
    entries[1]["corpus"] = "code"
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries)

    result = load_goldset(goldset_path)

    assert len(result) == 30
    assert result[0].corpus == "transcripts"
    assert result[1].corpus == "code"


# --- run_harness: scores each configured entry independently ---


def test_run_harness_scores_each_configured_entry_independently(tmp_path, monkeypatch):
    files = _dummy_files(tmp_path, 30)
    entries_meta = _valid_goldset_entries(files)
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries_meta)

    entry_a = _entry("model-a", 8091)
    entry_b = _entry("model-b", 8092)
    config = _harness_config(tmp_path, [entry_a, entry_b])
    _write_config_toml(config.config_path, [entry_a, entry_b])

    expected_by_query = {e["query"]: e["expected_path"] for e in entries_meta}
    scripted_query = _hit_or_miss_query(
        expected_by_query, lambda c: c.embeddings[0].id == "model-a"
    )

    _patch_common(monkeypatch, tmp_path, scripted_query)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    report = run_harness(config, goldset_path, work_dir)

    assert report.per_model["model-a"].hit_rate == 1.0
    assert report.per_model["model-b"].hit_rate == 0.0
    assert report.per_model["model-a"].hit_rate != report.per_model["model-b"].hit_rate


# --- run_harness: dedup by path ---


def test_run_harness_dedup_counts_hit_when_expected_file_present_lower_in_dominated_pool(
    tmp_path, monkeypatch
):
    expected_file = tmp_path / "dedup-expected.md"
    expected_file.write_text("# Expected\ncontent\n")

    entries_meta = [
        {"query": f"dedup hit query {i}", "expected_path": str(expected_file), "corpus": "memory"}
        for i in range(30)
    ]
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries_meta)

    entry = _entry("dedup-model", 8100)
    config = _harness_config(tmp_path, [entry])
    _write_config_toml(config.config_path, [entry])

    def scripted_query(store, config, text, scope, corpus=None, k=5):
        # top RRF_DEDUP_POOL candidates dominated by one repeated file's
        # chunks, with the expected file present lower down, followed by a
        # few more distinct filler paths.
        paths = (
            ["dominant.md"] * 21
            + [str(expected_file), "filler-c.md", "filler-d.md", "filler-e.md"]
        )
        assert len(paths) == RRF_DEDUP_POOL
        return _pointers_from_paths(paths)

    _patch_common(monkeypatch, tmp_path, scripted_query)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    report = run_harness(config, goldset_path, work_dir)

    assert report.per_model["dedup-model"].hit_rate == 1.0


def test_run_harness_dedup_counts_miss_when_expected_file_beyond_fifth_distinct_path(
    tmp_path, monkeypatch
):
    expected_file = tmp_path / "dedup-miss-expected.md"
    expected_file.write_text("# Expected\ncontent\n")

    entries_meta = [
        {
            "query": f"dedup miss query {i}",
            "expected_path": str(expected_file),
            "corpus": "memory",
        }
        for i in range(30)
    ]
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries_meta)

    entry = _entry("dedup-miss-model", 8101)
    config = _harness_config(tmp_path, [entry])
    _write_config_toml(config.config_path, [entry])

    def scripted_query(store, config, text, scope, corpus=None, k=5):
        # 5 distinct filler paths occupy every one of the top 5 distinct
        # ranks; the expected file only appears as the 6th distinct path.
        fillers = [f"filler-{i}.md" for i in range(5)]
        paths = fillers + [str(expected_file)]
        return _pointers_from_paths(paths)

    _patch_common(monkeypatch, tmp_path, scripted_query)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    report = run_harness(config, goldset_path, work_dir)

    assert report.per_model["dedup-miss-model"].hit_rate == 0.0


# --- run_harness: micro-averaged hit_rate, pooled across corpora ---


def test_run_harness_computes_micro_averaged_hit_rate_pooled_across_corpora(
    tmp_path, monkeypatch
):
    hit_files = _dummy_files(tmp_path, 20, prefix="memhit")
    miss_files = _dummy_files(tmp_path, 10, prefix="prdmiss")
    entries_meta = [
        {"query": f"memory-hit-query-{i}", "expected_path": str(f), "corpus": "memory"}
        for i, f in enumerate(hit_files)
    ] + [
        {"query": f"prd-miss-query-{i}", "expected_path": str(f), "corpus": "prd"}
        for i, f in enumerate(miss_files)
    ]
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries_meta)

    entry = _entry("solo-model", 8093)
    config = _harness_config(tmp_path, [entry])
    _write_config_toml(config.config_path, [entry])

    expected_by_query = {e["query"]: e["expected_path"] for e in entries_meta}

    def scripted_query(store, config, text, scope, corpus=None, k=5):
        if text.startswith("memory-hit"):
            return [_pointer(path=expected_by_query[text], rank=1)]
        return [_pointer(path="/never/matches.md", rank=1)]

    _patch_common(monkeypatch, tmp_path, scripted_query)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    report = run_harness(config, goldset_path, work_dir)

    # 20 hits out of 30 total queries pooled = 2/3, NOT the naive per-corpus
    # average of (1.0 + 0.0) / 2 = 0.5 the two corpora's individual rates
    # would give.
    assert report.per_model["solo-model"].hit_rate == pytest.approx(20 / 30)


# --- run_harness: gate_passed ---


def test_run_harness_gate_passes_when_winner_meets_threshold_and_beats_baseline(
    tmp_path, monkeypatch
):
    files = _dummy_files(tmp_path, 30, prefix="gatepass")
    entries_meta = [
        {
            "query": f"gatepasswinnerprobe{i}",
            "expected_path": str(f),
            "corpus": _VALID_CORPORA[i % len(_VALID_CORPORA)],
        }
        for i, f in enumerate(files)
    ]
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries_meta)

    entry = _entry("only-model", 8102)
    config = _harness_config(tmp_path, [entry])
    _write_config_toml(config.config_path, [entry])

    expected_by_query = {e["query"]: e["expected_path"] for e in entries_meta}
    scripted_query = _hit_or_miss_query(expected_by_query, lambda c: True)

    # Default harmless enumerate_corpora stub: its content shares no tokens
    # with the "gatepasswinnerprobeN" queries, so the rg baseline finds
    # nothing for any query -> baseline_hit_rate == 0.0.
    _patch_common(monkeypatch, tmp_path, scripted_query)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    report = run_harness(config, goldset_path, work_dir)

    assert report.per_model["only-model"].hit_rate == 1.0
    assert report.baseline_hit_rate == 0.0
    assert report.gate_passed is True


def test_run_harness_gate_fails_when_winner_ties_baseline(tmp_path, monkeypatch):
    files = []
    entries_meta = []
    for i in range(30):
        f = tmp_path / f"tie{i}.md"
        f.write_text(f"# Doc {i}\ndistinctivekeyword{i} appears here\n")
        files.append(f)
        entries_meta.append(
            {
                "query": f"distinctivekeyword{i}",
                "expected_path": str(f),
                "corpus": _VALID_CORPORA[i % len(_VALID_CORPORA)],
            }
        )
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries_meta)

    entry = _entry("tied-model", 8103)
    config = _harness_config(tmp_path, [entry])
    _write_config_toml(config.config_path, [entry])

    expected_by_query = {e["query"]: e["expected_path"] for e in entries_meta}
    scripted_query = _hit_or_miss_query(expected_by_query, lambda c: True)

    def fake_enum(*a, **k):
        # Each query's own file carries a unique token findable by rg, so
        # the scripted baseline scores every query exactly the same way the
        # (perfect) stubbed model does -> baseline_hit_rate == 1.0, tying
        # the winner's own 1.0 hit_rate.
        for f, meta in zip(files, entries_meta):
            yield CorpusFile(meta["corpus"], "repoTie", f)

    _patch_common(monkeypatch, tmp_path, scripted_query, enumerate_fn=fake_enum)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    report = run_harness(config, goldset_path, work_dir)

    assert report.per_model["tied-model"].hit_rate == 1.0
    assert report.baseline_hit_rate == 1.0
    # a tie does NOT count as beating baseline
    assert report.gate_passed is False


# --- run_harness: winner pinning ---


def test_run_harness_writes_winner_id_to_real_config_path_only(tmp_path, monkeypatch):
    files = _dummy_files(tmp_path, 30)
    entries_meta = _valid_goldset_entries(files)
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries_meta)

    entry_a = _entry("winner-model", 8094)
    entry_b = _entry("loser-model", 8095)
    config = _harness_config(tmp_path, [entry_a, entry_b])
    _write_config_toml(config.config_path, [entry_a, entry_b])

    expected_by_query = {e["query"]: e["expected_path"] for e in entries_meta}
    scripted_query = _hit_or_miss_query(
        expected_by_query, lambda c: c.embeddings[0].id == "winner-model"
    )

    _patch_common(monkeypatch, tmp_path, scripted_query)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    report = run_harness(config, goldset_path, work_dir)

    assert report.winner_id == "winner-model"

    reloaded = load_config(config.config_path)
    assert reloaded.pinned_id == "winner-model"
    # the two real embedding entries are untouched, in their original order
    assert [e.id for e in reloaded.embeddings] == ["winner-model", "loser-model"]

    # no per-candidate throwaway config was ever written anywhere under
    # tmp_path -- the only .toml file that exists is the real config_path
    assert list(tmp_path.rglob("*.toml")) == [config.config_path]


# --- run_harness: lease lifecycle ---


def test_run_harness_stops_every_lease_except_the_winners(tmp_path, monkeypatch):
    files = _dummy_files(tmp_path, 30)
    entries_meta = _valid_goldset_entries(files)
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries_meta)

    entry_a = _entry("model-a", 8096)
    entry_b = _entry("model-b", 8097)
    config = _harness_config(tmp_path, [entry_a, entry_b])
    _write_config_toml(config.config_path, [entry_a, entry_b])

    expected_by_query = {e["query"]: e["expected_path"] for e in entries_meta}
    scripted_query = _hit_or_miss_query(
        expected_by_query, lambda c: c.embeddings[0].id == "model-a"
    )

    stopped = []
    _patch_common(
        monkeypatch, tmp_path, scripted_query, stop_served_fn=_make_stop_served(stopped)
    )

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    report = run_harness(config, goldset_path, work_dir)

    assert report.winner_id == "model-a"
    stopped_ids = {lease.entry.id for lease in stopped}
    assert stopped_ids == {"model-b"}


def test_run_harness_stops_lease_of_candidate_that_raises_mid_scoring(tmp_path, monkeypatch):
    files = _dummy_files(tmp_path, 30)
    entries_meta = _valid_goldset_entries(files)
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries_meta)

    entry_good = _entry("good-model", 8098)
    entry_bad = _entry("bad-model", 8099)
    config = _harness_config(tmp_path, [entry_good, entry_bad])
    _write_config_toml(config.config_path, [entry_good, entry_bad])

    expected_by_query = {e["query"]: e["expected_path"] for e in entries_meta}

    def scripted_query(store, config, text, scope, corpus=None, k=5):
        if config.embeddings[0].id == "bad-model":
            raise RuntimeError("scoring exploded")
        return [_pointer(path=expected_by_query[text], rank=1)]

    stopped = []
    _patch_common(
        monkeypatch, tmp_path, scripted_query, stop_served_fn=_make_stop_served(stopped)
    )

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    with pytest.raises(RuntimeError):
        run_harness(config, goldset_path, work_dir)

    stopped_ids = {lease.entry.id for lease in stopped}
    assert "bad-model" in stopped_ids


# --- _sanitize_for_filename ---


def test_sanitize_for_filename_replaces_slash_and_colon_in_hf_locator():
    result = _sanitize_for_filename("Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0")

    assert result == "Qwen_Qwen3-Embedding-0.6B-GGUF_Q8_0"


def test_sanitize_for_filename_leaves_allowed_characters_and_replaces_arbitrary_others():
    allowed = "AZaz09._-"
    assert _sanitize_for_filename(allowed) == allowed

    assert _sanitize_for_filename("a b@c#d") == "a_b_c_d"


# --- rg baseline: empty corpus must not fall through to an unscoped cwd scan ---


def test_run_harness_baseline_skips_rg_when_no_corpus_files(tmp_path, monkeypatch):
    # Regression: when enumerate_corpora yields no files for the goldset's
    # corpora, the baseline must short-circuit to 0.0 and NEVER invoke rg with an
    # empty path list (which makes rg recursively scan the cwd and corrupt the
    # gate's baseline_hit_rate).
    files = _dummy_files(tmp_path, 30, prefix="norg")
    entries_meta = _valid_goldset_entries(files)
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries_meta)

    entry = _entry("no-corpus-model", 8110)
    config = _harness_config(tmp_path, [entry])
    _write_config_toml(config.config_path, [entry])

    expected_by_query = {e["query"]: e["expected_path"] for e in entries_meta}
    scripted_query = _hit_or_miss_query(expected_by_query, lambda c: True)

    def empty_enum(*a, **k):
        return iter(())

    rg_calls = []

    def forbidden_run(*args, **kwargs):
        rg_calls.append(args)
        raise AssertionError("rg must not run when corpus_files is empty")

    _patch_common(monkeypatch, tmp_path, scripted_query, enumerate_fn=empty_enum)
    monkeypatch.setattr("engram.harness.subprocess.run", forbidden_run)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    report = run_harness(config, goldset_path, work_dir)

    assert report.baseline_hit_rate == 0.0
    assert rg_calls == []


# --- rg baseline: includes files from the transcripts producer ---


def test_baseline_hit_rate_includes_files_from_transcripts_producer(tmp_path, monkeypatch):
    files = _dummy_files(tmp_path, 30, prefix="basetranscript")
    entries_meta = _valid_goldset_entries(files)

    transcript_file = tmp_path / "unique-transcript-source.md"
    transcript_file.write_text("# Transcript\nuniquetranscripttoken appears here\n")
    entries_meta.append(
        {
            "query": "uniquetranscripttoken",
            "expected_path": str(transcript_file),
            "corpus": "transcripts",
        }
    )
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries_meta)

    entry = _entry("transcript-baseline-model", 8120)
    config = _harness_config(tmp_path, [entry])
    _write_config_toml(config.config_path, [entry])

    # The model always misses, so any hit in the report can only come from
    # the rg baseline seeing the transcripts producer's file.
    def scripted_query(store, config, text, scope, corpus=None, k=5):
        return [_pointer(path="/never/matches.md", rank=1)]

    _patch_common(monkeypatch, tmp_path, scripted_query)
    monkeypatch.setattr(
        "engram.harness.transcripts.enumerate",
        lambda *a, **k: iter([CorpusFile("transcripts", "cellar", transcript_file)]),
    )

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    report = run_harness(config, goldset_path, work_dir)

    assert report.per_model["transcript-baseline-model"].hit_rate == 0.0
    assert report.baseline_hit_rate > 0.0


# --- rg baseline: rg error codes must not be swallowed as "no match" ---


def test_baseline_raises_when_rg_returns_error_code(tmp_path, monkeypatch):
    # Regression: `_baseline_hit_rate` only special-cases returncode 0 (match)
    # and 1 (no match); any other rg returncode (e.g. 2 for a real error) is
    # silently treated as "no match found" today, which zeroes out matches
    # for that term instead of surfacing the failure -- a false-positive eval
    # gate, since a broken baseline can never legitimately be beaten.
    files = _dummy_files(tmp_path, 30, prefix="rgerr")
    entries_meta = _valid_goldset_entries(files)
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries_meta)

    entry = _entry("rg-error-model", 8111)
    config = _harness_config(tmp_path, [entry])
    _write_config_toml(config.config_path, [entry])

    expected_by_query = {e["query"]: e["expected_path"] for e in entries_meta}
    scripted_query = _hit_or_miss_query(expected_by_query, lambda c: True)

    # Default _harmless_enumerate_corpora stub gives a non-empty corpus_files
    # list, so the baseline pass actually reaches subprocess.run instead of
    # short-circuiting.
    _patch_common(monkeypatch, tmp_path, scripted_query)

    def erroring_run(*args, **kwargs):
        return types.SimpleNamespace(returncode=2, stdout="", stderr="")

    monkeypatch.setattr("engram.harness.subprocess.run", erroring_run)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    with pytest.raises(RuntimeError):
        run_harness(config, goldset_path, work_dir)


# --- _score_candidate: sqlite store lifecycle ---


def test_score_candidate_closes_store_connection(tmp_path, monkeypatch):
    # Regression: _score_candidate opens a fresh sqlite store per candidate
    # via open_store but never closes the connection it opens, leaking one
    # sqlite connection per configured embedding entry per harness run.
    files = _dummy_files(tmp_path, 30, prefix="connleak")
    entries_meta = _valid_goldset_entries(files)
    goldset_path = tmp_path / "goldset.yaml"
    _write_goldset(goldset_path, entries_meta)

    entry_a = _entry("conn-model-a", 8112)
    entry_b = _entry("conn-model-b", 8113)
    config = _harness_config(tmp_path, [entry_a, entry_b])
    _write_config_toml(config.config_path, [entry_a, entry_b])

    expected_by_query = {e["query"]: e["expected_path"] for e in entries_meta}
    scripted_query = _hit_or_miss_query(expected_by_query, lambda c: True)

    _patch_common(monkeypatch, tmp_path, scripted_query)

    class _FakeConn:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class _FakeStore:
        def __init__(self):
            self.conn = _FakeConn()

    opened = []

    def fake_open_store(path):
        s = _FakeStore()
        opened.append(s)
        return s

    monkeypatch.setattr("engram.harness.open_store", fake_open_store)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    run_harness(config, goldset_path, work_dir)

    assert opened
    assert all(s.conn.closed for s in opened)


# --- format_report: per-model, per-corpus hit rates ---


def test_format_report_emits_per_corpus_hit_rates():
    from engram.harness import format_report

    report = HarnessReport(
        per_model={
            "m1": ModelScore(hit_rate=0.8, per_corpus_hit_rate={"memory": 0.9, "prd": 0.7})
        },
        winner_id="m1",
        baseline_hit_rate=0.5,
        gate_passed=True,
    )

    lines = format_report(report)
    output = "\n".join(lines)

    assert "memory" in output
    assert "prd" in output
    assert "0.900" in output
    assert "0.700" in output


# --- _write_pinned: fail loud on malformed config ---


def test_write_pinned_fails_loud_when_no_pinned_section(tmp_path):
    entry = _entry("solo-model", 8114)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[[embedding]]\n" f'id = "{entry.id}"\n' f'endpoint = "{entry.endpoint}"\n'
    )

    with pytest.raises(ValueError):
        _write_pinned(config_path, "winner-id")
