import os
from pathlib import Path

import pytest

from engram import cli, findings, symbols
from engram.client import Vector, load_config
from engram.store import Chunk, ChunkWithVector, Scope, open_store


def add_chunk(
    store, path, *, corpus="code", repo="a", heading="Function exact", ordinal=1
) -> Chunk:
    chunk = Chunk(
        corpus,
        repo,
        "function",
        str(path),
        heading,
        "body",
        ordinal,
        ordinal + 1,
        "old-hash",
        ordinal,
    )
    store.upsert_chunks([ChunkWithVector(chunk, Vector([1.0, 0.0], "test", 2))])
    return chunk


@pytest.mark.parametrize("value", ['"bad"', "[1]", "true"])
def test_invalid_exclude_config(tmp_path, value) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[[embedding]]\nid="test"\nendpoint="http://localhost:8081/v1"\n'
        f"[code]\nexclude_globs={value}\n"
    )
    with pytest.raises(ValueError, match="exclude_globs"):
        load_config(path)


def test_exclude_config_defaults_and_extension(tmp_path) -> None:
    path = tmp_path / "config.toml"
    assert load_config(path).exclude_globs == ()
    with path.open("a") as f:
        f.write('\n[code]\nexclude_globs=["generated/*"]\n')
    assert load_config(path).exclude_globs == ("generated/*",)


@pytest.mark.parametrize(
    "relative,body,expected",
    [
        ("node_modules/x.js", "x", True),
        ("vendor/x.py", "x", True),
        ("a.min.js", "x", True),
        ("bundle.js", "x" * 1001, True),
        ("normal.py", "x" * 1000, False),
        ("generated/x.py", "x", True),
    ],
)
def test_code_exclusions(tmp_path, relative, body, expected) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    assert symbols.is_excluded(path, ("*/generated/*",)) is expected


def test_anonymous_callbacks_stay_in_parent(tmp_path) -> None:
    path = tmp_path / "callbacks.js"
    path.write_text(
        "function parent() { [1].map(() => 1); [2].map(() => 2); }\n"
        "export default () => 42;\n"
    )
    chunks = symbols.chunk(path, "a", "hash")
    assert [c.heading for c in chunks] == ["Function parent", "Function (anonymous)"]
    assert "() => 2" in chunks[0].body


def test_lookup_scope_exact_prefix_literal_and_file_order(tmp_path) -> None:
    store = open_store(tmp_path / "db")
    exact = add_chunk(store, "a.py", ordinal=2)
    prefix = add_chunk(store, "a.py", heading="Function exact_more", ordinal=1)
    other = add_chunk(store, "b.py", repo="b")
    add_chunk(store, "note.md", corpus="notes")
    add_chunk(store, "percent.py", heading="Function exact%")
    assert store.lookup_by_name("exact", Scope("portfolio", None)) == [exact, other]
    assert store.lookup_by_name("exact", Scope("repo", "a")) == [exact]
    assert store.lookup_by_name("exact_m", Scope("portfolio", None)) == [prefix]
    assert (
        len(store.lookup_by_name("exact%", Scope("portfolio", None), prefix=True)) == 1
    )
    assert store.lookup_by_path("a.py") == [prefix, exact]


def test_lookup_cli_without_config_or_embedding(tmp_path, monkeypatch, capsys) -> None:
    store = open_store(tmp_path / "db")
    path = tmp_path / "source.py"
    add_chunk(store, path)
    monkeypatch.setattr(cli, "open_store", lambda: store)

    def refuse() -> None:
        pytest.fail("lookup loaded embedding configuration")

    monkeypatch.setattr(cli, "load_config", refuse)
    assert cli.main(["lookup", "--name", "exact", "--scope", "portfolio"]) == 0
    assert capsys.readouterr().out == f"{path}:1-2\tFunction exact\n"
    monkeypatch.setattr(cli, "_resolve_pack_repo", lambda: ("a", tmp_path))
    assert cli.main(["lookup", "--file", "source.py"]) == 0
    assert capsys.readouterr().out == f"{path}:1-2\tFunction exact\n"
    assert cli.main(["lookup", "--name", "exact"]) == 1
    assert "scope" in capsys.readouterr().err
    assert cli.main(["lookup", "--name", "missing", "--scope", "portfolio"]) == 1
    assert "no symbol matched" in capsys.readouterr().err
    with pytest.raises(SystemExit) as error:
        cli.main(["lookup", "--name", "exact", "--file", "source.py"])
    assert error.value.code == 2


AUDIT = """# Decision Audit Log: example

PRD: `example.md`
Autonomous: 2 | Deferred: 1 | Doubts: 0

### [autonomous] 2026-08-06T12:00:00Z

**Decision**: Choose an oracle.
**Rationale**: Keep the leaf module as the existence oracle.

### [deferred] 2026-08-06T12:01:00Z

**Decision**: Defer migration.
**Rationale**: Preserve old callers.

### [autonomous] 2026-08-06T12:02:00Z

**Decision**: Retain the boundary.
**Rationale**: Last line without newline."""


def test_audit_records_preserve_text_and_line_spans(tmp_path) -> None:
    path = tmp_path / "not-named-audit.md"
    path.write_text(AUDIT)
    assert findings._detect_genre(AUDIT) == "audit"
    records = findings.parse(path)
    assert len(records) == 4
    assert "Autonomous: 2" in records[0].body
    assert records[1].heading == "[autonomous] 2026-08-06T12:00:00Z"
    assert records[-1].body.endswith("Last line without newline.")
    for record in records:
        assert record.body == "\n".join(
            AUDIT.splitlines()[record.line_start - 1 : record.line_end]
        )


def test_audit_empty_is_error_and_review_takes_precedence(tmp_path) -> None:
    path = tmp_path / "empty.md"
    path.write_text("# Decision Audit Log: empty\n")
    with pytest.raises(ValueError, match="decision"):
        findings.parse(path)
    assert findings._detect_genre("nothing") == "unrecognised"
    review = "---\nreviewers: bob\n---\nVerdict: pass\nTests: pass\n" + AUDIT
    assert findings._detect_genre(review) == "review"


def test_real_audit_fixture_preserves_decisions() -> None:
    # Header and three blocks from ddb's 00176 audit (2026-10-18), including
    # a deferred decision; the older 00164 source no longer exists.
    records = findings.parse(Path(__file__).parent / "fixtures/decision-audit.md")
    assert len(records) == 4
    assert "00176-route-search-through-contract-v1.md" in records[0].body
    assert "Routed SearchCommand+PageRequest" in records[1].body
    assert records[-1].heading.startswith("[deferred]")


def test_audit_section_without_header_has_valid_pointer(tmp_path) -> None:
    path = tmp_path / "audit.md"
    path.write_text("### [doubt] 2026-11-09\n**Rationale**: Verify this.\n")
    records = findings.parse(path)
    assert len(records) == 1
    assert records[0].line_start == 1
    assert records[0].line_end == 2


@pytest.mark.parametrize(
    "corpus,age,in_flight",
    [
        ("transcripts", 1, True),
        ("transcripts", 601, False),
        ("transcripts", -10, True),
        ("code", 1, False),
    ],
)
def test_staleness_classification(
    tmp_path, monkeypatch, corpus, age, in_flight
) -> None:
    store = open_store(tmp_path / "db")
    path = tmp_path / "source"
    path.write_text("changed")
    os.utime(path, (10000 - age, 10000 - age))
    add_chunk(store, path, corpus=corpus)
    monkeypatch.setattr("engram.store.time.time", lambda: 10000)
    report = store.status(Scope("portfolio", None), in_flight_seconds=600).per_corpus[
        corpus
    ]
    assert report.in_flight_files == ([str(path)] if in_flight else [])
    assert report.stale_files == ([] if in_flight else [str(path)])
    path.unlink()
    report = store.status(Scope("portfolio", None), in_flight_seconds=600).per_corpus[
        corpus
    ]
    assert report.dead_rows == 1
    assert report.in_flight_files == []


def test_reindex_migrates_unchanged_anonymous_and_prunes_vendor(
    tmp_path, monkeypatch
) -> None:
    from engram import corpora, indexer

    store = open_store(tmp_path / "db")
    path = tmp_path / "source.js"
    path.write_text("function parent() { [1].map(() => 1); }\n")
    old = Chunk(
        "code",
        "a",
        "function",
        str(path),
        "Function None",
        "old",
        1,
        1,
        corpora.hash_source(path),
        1,
    )
    store.upsert_chunks([ChunkWithVector(old, Vector([1.0, 0.0], "test", 2))])
    add_chunk(store, tmp_path / "bundle.min.js")
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[[embedding]]\nid="test"\nendpoint="http://localhost:8081/v1"\n'
    )
    monkeypatch.setattr(indexer, "enumerate_corpora", lambda: iter(()))
    monkeypatch.setattr(
        symbols, "enumerate", lambda **kw: iter([corpora.CorpusFile("code", "a", path)])
    )
    monkeypatch.setattr(
        indexer,
        "embed",
        lambda texts, entry: [Vector([1.0, 0.0], "test", 2) for _ in texts],
    )
    report = indexer.index(
        store, load_config(config_path), Scope("portfolio", None), "code"
    )
    assert report.chunks_pruned == 1
    assert [c.heading for c in store.chunks_for_corpus("code")] == ["Function parent"]

    def refuse(*args) -> None:
        pytest.fail("unchanged migration embedded twice")

    monkeypatch.setattr(indexer, "embed", refuse)
    assert (
        indexer.index(
            store, load_config(config_path), Scope("portfolio", None), "code"
        ).chunks_added
        == 0
    )


@pytest.mark.parametrize("value", ["0", "-1", "true", '"10"'])
def test_invalid_transcript_window(tmp_path, value) -> None:
    from engram.client import load_corpus_settings

    path = tmp_path / "config.toml"
    path.write_text(f"[transcripts]\nin_flight_seconds={value}\n")
    with pytest.raises(ValueError, match="in_flight_seconds"):
        load_corpus_settings(path)


def test_transcript_window_config_used_by_status(tmp_path, monkeypatch) -> None:
    from engram.client import load_corpus_settings

    config = tmp_path / "config.toml"
    config.write_text("[transcripts]\nin_flight_seconds=120\n")
    monkeypatch.setattr(
        "engram.store.load_corpus_settings", lambda: load_corpus_settings(config)
    )
    store = open_store(tmp_path / "db")
    path = tmp_path / "transcript"
    path.write_text("changed")
    os.utime(path, (9800, 9800))
    add_chunk(store, path, corpus="transcripts")
    monkeypatch.setattr("engram.store.time.time", lambda: 10000)
    assert store.status(Scope("portfolio", None)).per_corpus[
        "transcripts"
    ].stale_files == [str(path)]


@pytest.mark.parametrize(
    "stale,dead,expected", [([], 0, 0), (["old"], 0, 1), ([], 1, 1)]
)
def test_status_cli_churn_exit_contract(
    tmp_path, monkeypatch, capsys, stale, dead, expected
) -> None:
    from engram import corpora
    from engram.store import CorpusStatus, StatusReport

    report = StatusReport({"transcripts": CorpusStatus(3, stale, dead, ["active"])})

    class StatusStore:
        def status(self, scope) -> StatusReport:
            return report

    monkeypatch.setattr(cli, "open_store", StatusStore)
    monkeypatch.setattr(cli, "enumerate_corpora", lambda: iter(()))
    monkeypatch.setattr(cli.transcripts, "enumerate", lambda: iter(()))
    monkeypatch.setattr(symbols, "count_skipped", lambda: 0)
    monkeypatch.setattr(symbols, "count_excluded", lambda: 2)
    monkeypatch.setattr(corpora, "missing_dirs", [])
    assert cli.main(["status", "--scope", "portfolio"]) == expected
    output = capsys.readouterr().out
    assert "in-flight=1" in output
    assert "excluded=2" in output


def test_enumeration_excludes_configured_relative_paths(tmp_path, monkeypatch) -> None:
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "generated").mkdir()
    (repo / "generated/a.py").write_text("def generated(): pass\n")
    (repo / "source.py").write_text("def kept(): pass\n")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, capture_output=True
    )
    registry = tmp_path / "repos.csv"
    registry.write_text(f"{repo},a\n")
    files = list(symbols.enumerate(registry, exclude_globs=("generated/*",)))
    assert [f.path.name for f in files] == ["source.py"]
    assert symbols.count_excluded() == 1


def test_lookup_file_rejects_scope_flags(capsys) -> None:
    assert cli.main(["lookup", "--file", "x.py", "--repo", "other"]) == 1
    assert "does not accept" in capsys.readouterr().err


def test_status_unavailable_code_source_fails(monkeypatch) -> None:
    from engram import corpora
    from engram.store import StatusReport

    class StatusStore:
        def status(self, scope) -> StatusReport:
            return StatusReport({})

    monkeypatch.setattr(cli, "open_store", StatusStore)
    monkeypatch.setattr(cli, "enumerate_corpora", lambda: iter(()))
    monkeypatch.setattr(cli.transcripts, "enumerate", lambda: iter(()))
    monkeypatch.setattr(symbols, "count_skipped", lambda: 0)
    monkeypatch.setattr(symbols, "count_excluded", lambda: 0)
    monkeypatch.setattr(corpora, "missing_dirs", ["code:missing"])
    assert cli.main(["status", "--scope", "portfolio"]) == 1


def test_ten_status_runs_during_transcript_writes_stay_healthy(
    tmp_path, monkeypatch, capsys
) -> None:
    from engram import corpora

    store = open_store(tmp_path / "db")
    path = tmp_path / "session.jsonl"
    path.write_text('{"message":"active"}\n')
    add_chunk(store, path, corpus="transcripts")
    monkeypatch.setattr(cli, "open_store", lambda: store)
    monkeypatch.setattr(cli, "enumerate_corpora", lambda: iter(()))
    monkeypatch.setattr(cli.transcripts, "enumerate", lambda: iter(()))
    monkeypatch.setattr(symbols, "count_skipped", lambda: 0)
    monkeypatch.setattr(symbols, "count_excluded", lambda: 0)
    monkeypatch.setattr(corpora, "missing_dirs", [])
    exits = []
    for _ in range(10):
        with path.open("a") as stream:
            stream.write('{"message":"still active"}\n')
        exits.append(cli.main(["status", "--scope", "portfolio"]))
    assert exits == [0] * 10
    assert capsys.readouterr().out.count("in-flight=1") == 10
