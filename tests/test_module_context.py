from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest

from engram import corpora, store, symbols
from engram.client import EmbeddingEntry, EngramConfig, Vector
from engram.corpora import CorpusFile
from engram.indexer import index
from engram.store import Chunk, ChunkWithVector, Scope, open_store


def _ctx(path, body, line_start, line_end, ordinal, repo="widget", content_hash="h1"):
    return Chunk(
        corpus="code",
        repo=repo,
        doc_type="module_context",
        path=str(path),
        heading="Module context",
        body=body,
        line_start=line_start,
        line_end=line_end,
        content_hash=content_hash,
        chunk_ordinal=ordinal,
    )


def _sym(
    path,
    doc_type,
    heading,
    body,
    line_start,
    line_end,
    ordinal,
    repo,
    content_hash,
):
    return Chunk(
        corpus="code",
        repo=repo,
        doc_type=doc_type,
        path=str(path),
        heading=heading,
        body=body,
        line_start=line_start,
        line_end=line_end,
        content_hash=content_hash,
        chunk_ordinal=ordinal,
    )


TWO_FUNCTIONS = (
    "import os\n"  # 1
    "\n"  # 2
    "LIMIT = 10\n"  # 3
    "\n"  # 4
    "\n"  # 5
    "def alpha():\n"  # 6
    "    return LIMIT\n"  # 7
    "\n"  # 8
    'BETA_NAME = "beta"\n'  # 9
    "\n"  # 10
    "def beta():\n"  # 11
    "    return os.sep\n"  # 12
    "\n"  # 13
    "print(alpha())\n"  # 14
)


# --- chunk(): preamble, interstitial and tail context after the symbols ---


def test_chunk_emits_preamble_interstitial_and_tail_context_after_symbols(tmp_path):
    symbols.skipped_files.clear()
    path = tmp_path / "service.py"
    path.write_text(TWO_FUNCTIONS)

    chunks = symbols.chunk(path, "widget", "h1")

    assert [c.doc_type for c in chunks] == [
        "function",
        "function",
        "module_context",
        "module_context",
        "module_context",
    ]
    assert chunks[2:] == [
        _ctx(path, "import os\n\nLIMIT = 10", 1, 3, 3),
        _ctx(path, 'BETA_NAME = "beta"', 9, 9, 4),
        _ctx(path, "print(alpha())", 14, 14, 5),
    ]
    assert str(path) not in symbols.skipped_files


def test_chunk_keeps_symbol_chunks_identical_alongside_context(tmp_path):
    path = tmp_path / "service.py"
    path.write_text(TWO_FUNCTIONS)

    chunks = symbols.chunk(path, "gadget", "h2")

    symbol_chunks = [c for c in chunks if c.doc_type != "module_context"]
    assert symbol_chunks == [
        _sym(
            path,
            "function",
            "Function alpha",
            "def alpha():\n    return LIMIT",
            6,
            7,
            1,
            "gadget",
            "h2",
        ),
        _sym(
            path,
            "function",
            "Function beta",
            "def beta():\n    return os.sep",
            11,
            12,
            2,
            "gadget",
            "h2",
        ),
    ]
    assert chunks[:2] == symbol_chunks
    assert len(chunks) == 5
    assert all(c.repo == "gadget" and c.content_hash == "h2" for c in chunks)


# --- chunk(): symbol-less files gain context only in allowlisted languages ---


def test_chunk_gives_symbolless_python_file_one_context_chunk(tmp_path):
    symbols.skipped_files.clear()
    path = tmp_path / "consts.py"
    path.write_text("\nimport os\nimport sys\n\nNAME = 'x'\n\n")

    chunks = symbols.chunk(path, "gadget", "h2")

    assert chunks == [
        _ctx(path, "import os\nimport sys\n\nNAME = 'x'", 2, 5, 1, "gadget", "h2"),
    ]
    assert str(path) not in symbols.skipped_files
    assert store.MODULE_CONTEXT_DOC_TYPE == "module_context"
    assert symbols.MODULE_CONTEXT_HEADING == "Module context"
    assert (
        frozenset(
            {
                "python",
                "javascript",
                "typescript",
                "tsx",
                "rust",
                "go",
                "c",
                "cpp",
                "arduino",
                "swift",
                "kotlin",
                "lua",
                "bash",
                "batch",
            },
        )
        == symbols.CONTEXT_LANGUAGES
    )


@pytest.mark.parametrize(
    ("filename", "source", "body", "line_end"),
    [
        (
            "consts.js",
            "import fs from 'fs';\n\nconst LIMIT = 10;\n",
            "import fs from 'fs';\n\nconst LIMIT = 10;",
            3,
        ),
        (
            "consts.rs",
            "use std::io;\n\nconst LIMIT: u32 = 10;\n",
            "use std::io;\n\nconst LIMIT: u32 = 10;",
            3,
        ),
        (
            "consts.go",
            'package main\n\nimport "os"\n\nvar Limit = 10\n',
            'package main\n\nimport "os"\n\nvar Limit = 10',
            5,
        ),
        (
            "script.sh",
            "set -e\n\nexport NAME=x\necho hi\n",
            "set -e\n\nexport NAME=x\necho hi",
            4,
        ),
    ],
    ids=["javascript", "rust", "go", "bash"],
)
def test_chunk_gives_symbolless_allowlisted_file_one_context_chunk(
    tmp_path,
    filename,
    source,
    body,
    line_end,
):
    symbols.skipped_files.clear()
    path = tmp_path / filename
    path.write_text(source)

    chunks = symbols.chunk(path, "widget", "h1")

    assert chunks == [_ctx(path, body, 1, line_end, 1)]
    assert str(path) not in symbols.skipped_files


def test_chunk_gives_context_to_symbol_file_in_non_context_language(tmp_path):
    symbols.skipped_files.clear()
    path = tmp_path / "tool.rb"
    path.write_text("require 'json'\n\ndef size\n  1\nend\n\nputs size\n")

    chunks = symbols.chunk(path, "widget", "h1")

    assert chunks == [
        _sym(
            path,
            "method",
            "Method size",
            "def size\n  1\nend",
            3,
            5,
            1,
            "widget",
            "h1",
        ),
        _ctx(path, "require 'json'", 1, 1, 2),
        _ctx(path, "puts size", 7, 7, 3),
    ]
    assert str(path) not in symbols.skipped_files


@pytest.mark.parametrize(
    ("filename", "source"),
    [
        ("consts.py.json", "[1, 2, 3]\n"),
        ("README.md", "Just some prose.\n\nMore prose here.\n"),
        ("config.yaml", "name: x\nlimit: 10\n"),
        ("config.toml", 'name = "x"\nlimit = 10\n'),
        ("page.html", "<html><body><p>hi</p></body></html>\n"),
    ],
)
def test_chunk_returns_nothing_for_symbolless_non_context_language(
    tmp_path,
    filename,
    source,
):
    symbols.skipped_files.clear()
    path = tmp_path / filename
    path.write_text(source)

    chunks = symbols.chunk(path, "widget", "h1")

    assert chunks == []
    assert str(path) not in symbols.skipped_files


# --- chunk(): nested spans never leak lines into context ---


def test_chunk_does_not_duplicate_nested_class_lines_into_context(tmp_path):
    path = tmp_path / "shapes.py"
    path.write_text(
        "# Shapes.\n"  # 1
        "\n"  # 2
        "class Shape:\n"  # 3
        '    """A shape."""\n'  # 4
        "\n"  # 5
        "    def area(self):\n"  # 6
        "        return 0\n"  # 7
        "\n"  # 8
        "SHAPES = [Shape]\n",  # 9
    )

    chunks = symbols.chunk(path, "widget", "h1")

    assert [
        (c.doc_type, c.line_start, c.line_end, c.chunk_ordinal) for c in chunks[:2]
    ] == [
        ("class", 3, 7, 1),
        ("function", 6, 7, 2),
    ]
    assert chunks[2:] == [
        _ctx(path, "# Shapes.", 1, 1, 3),
        _ctx(path, "SHAPES = [Shape]", 9, 9, 4),
    ]


# --- _context_chunks(): union of crossing and overhanging spans ---


@pytest.mark.parametrize("order", [(0, 1, 2, 3), (2, 1, 0, 3)])
def test_context_chunks_emits_only_slices_outside_crossing_and_overhanging_spans(
    order,
):
    lines = [f"x{n} = {n}" for n in range(1, 15)]
    path = Path("pkg/mod.py")
    by_line = [
        _sym(path, "function", "Function a", "", 2, 5, 3, "gizmo", "h9"),
        _sym(path, "function", "Function b", "", 4, 7, 5, "gizmo", "h9"),  # crosses a
        _sym(path, "class", "Class C", "", 10, 12, 7, "gizmo", "h9"),
        _sym(path, "function", "Function d", "", 11, 13, 9, "gizmo", "h9"),  # past C
    ]
    # The highest-ordinal span stays last in both orders.
    spans = [by_line[i] for i in order]
    original = list(spans)

    context = symbols._context_chunks(lines, spans, path, "gizmo", "h9")

    assert context == [
        _ctx("pkg/mod.py", "x1 = 1", 1, 1, 10, "gizmo", "h9"),
        _ctx("pkg/mod.py", "x8 = 8\nx9 = 9", 8, 9, 11, "gizmo", "h9"),
        _ctx("pkg/mod.py", "x14 = 14", 14, 14, 12, "gizmo", "h9"),
    ]
    assert spans == original


def test_context_chunks_without_spans_starts_ordinals_at_one():
    path = Path("pkg/other.py")

    assert symbols._context_chunks([], [], path, "gizmo", "h9") == []
    assert symbols._context_chunks(["a = 1", "", "b = 2"], [], path, "gizmo", "h9") == [
        _ctx("pkg/other.py", "a = 1\n\nb = 2", 1, 3, 1, "gizmo", "h9"),
    ]


def test_context_chunks_ignores_span_lines_past_end_of_file():
    lines = ["a = 1", "def f():", "    pass"]
    path = Path("m.py")
    spans = [_sym(path, "function", "Function f", "", 2, 9, 1, "w", "h")]

    assert symbols._context_chunks(lines, spans, path, "w", "h") == [
        _ctx("m.py", "a = 1", 1, 1, 2, "w", "h"),
    ]


# --- chunk(): blank-line trimming ---


def test_chunk_trims_blank_run_edges_keeps_interior_and_drops_blank_gaps(tmp_path):
    path = tmp_path / "blanks.py"
    path.write_text(
        "\n"  # 1
        "   \t\n"  # 2
        "import os\n"  # 3
        "  \n"  # 4 interior whitespace-only line
        "\n"  # 5 second interior blank line in a row
        "import sys\n"  # 6
        "    \n"  # 7
        "\n"  # 8
        "def f():\n"  # 9
        "    return 1\n"  # 10
        "\n"  # 11
        "   \t\n"  # 12
        "\n"  # 13
        "def g():\n"  # 14
        "    return 2\n"  # 15
        "\n"  # 16
        "\t\n",  # 17
    )

    chunks = symbols.chunk(path, "widget", "h1")

    assert [(c.doc_type, c.line_start, c.line_end) for c in chunks[:2]] == [
        ("function", 9, 10),
        ("function", 14, 15),
    ]
    assert chunks[2:] == [_ctx(path, "import os\n  \n\nimport sys", 3, 6, 3)]


# --- chunk(): non-ASCII text keeps line numbers and exact bodies ---


def test_chunk_keeps_line_numbers_and_bodies_for_non_ascii_lines(tmp_path):
    path = tmp_path / "zdravi.py"
    path.write_text(
        "# Příliš žluťoučký kůň úpěl ďábelské ódy\n"  # 1
        'NAME = "東京タワー"\n'  # 2
        "\n"  # 3
        "def pozdrav():\n"  # 4
        '    return "こんにちは"\n'  # 5
        "\n"  # 6
        'ČAS = "時間"\n',  # 7
        encoding="utf-8",
    )

    chunks = symbols.chunk(path, "widget", "h1")

    assert chunks == [
        _sym(
            path,
            "function",
            "Function pozdrav",
            'def pozdrav():\n    return "こんにちは"',
            4,
            5,
            1,
            "widget",
            "h1",
        ),
        _ctx(
            path,
            '# Příliš žluťoučký kůň úpěl ďábelské ódy\nNAME = "東京タワー"',
            1,
            2,
            2,
        ),
        _ctx(path, 'ČAS = "時間"', 7, 7, 3),
    ]


def test_chunk_counts_lines_at_newline_only_despite_form_feed(tmp_path):
    path = tmp_path / "paged.py"
    path.write_text("import os\n\x0c\nX = 1\n\ndef f():\n    return 2\n\nTAIL = 3\n")

    chunks = symbols.chunk(path, "widget", "h1")

    assert chunks == [
        _sym(
            path,
            "function",
            "Function f",
            "def f():\n    return 2",
            5,
            6,
            1,
            "widget",
            "h1",
        ),
        _ctx(path, "import os\n\x0c\nX = 1", 1, 3, 2),
        _ctx(path, "TAIL = 3", 8, 8, 3),
    ]


# --- chunk(): every uncovered nonblank line lands in exactly one context chunk ---

INVENTORY = '''"""Inventory tools."""
import json
from pathlib import Path

DEFAULT = {"a": 1}


class Store:
    """Holds items."""

    kind = "store"

    def load(self, path):
        return json.loads(Path(path).read_text())

    def save(self, path, data):
        Path(path).write_text(json.dumps(data))


TIMEOUT = 5


def build():
    return Store()


RETRIES = 3


def helper():
    return RETRIES


if __name__ == "__main__":
    build()
'''


def test_chunk_context_covers_each_uncovered_nonblank_line_exactly_once(tmp_path):
    path = tmp_path / "inventory.py"
    path.write_text(INVENTORY)
    lines = INVENTORY.splitlines()

    chunks = symbols.chunk(path, "widget", "h1")

    syms = [c for c in chunks if c.doc_type != "module_context"]
    context = [c for c in chunks if c.doc_type == "module_context"]
    assert chunks == syms + context
    assert syms and context
    covered = {n for c in syms for n in range(c.line_start, c.line_end + 1)}
    uncovered = {
        n for n in range(1, len(lines) + 1) if n not in covered and lines[n - 1].strip()
    }
    assert {2, 3, 5, 20, 27, 34, 35} <= uncovered
    assert len(context) == 4  # top, TIMEOUT, RETRIES, __main__ block
    for n in uncovered:
        hits = [c for c in context if c.line_start <= n <= c.line_end]
        assert len(hits) == 1, n
    for c in context:
        span = set(range(c.line_start, c.line_end + 1))
        assert not span & covered
        assert c.body == "\n".join(lines[c.line_start - 1 : c.line_end])
        assert lines[c.line_start - 1].strip() and lines[c.line_end - 1].strip()
    last = max(c.chunk_ordinal for c in syms)
    assert [c.chunk_ordinal for c in context] == list(
        range(last + 1, last + 1 + len(context)),
    )


# --- chunk(): unchanged boundaries ---


@pytest.mark.parametrize(
    ("filename", "source", "skipped"),
    [
        ("empty.py", "   \n\t\n\n", False),
        ("blank.py", "", False),
        ("data.bin", "x = 1\n", True),
        ("Makefile", "all:\n\techo hi\n", True),
    ],
)
def test_chunk_returns_nothing_for_blank_or_unsupported_files(
    tmp_path,
    filename,
    source,
    skipped,
):
    symbols.skipped_files.clear()
    path = tmp_path / filename
    path.write_text(source)

    chunks = symbols.chunk(path, "widget", "h1")

    assert chunks == []
    assert (str(path) in symbols.skipped_files) is skipped


@pytest.mark.parametrize("source", ["def f():\n    pass\n", "import os\nLIMIT = 1\n"])
def test_chunk_propagates_parser_failure_without_context(tmp_path, monkeypatch, source):
    symbols.skipped_files.clear()
    path = tmp_path / "pathological.py"
    path.write_text(source)

    def raising_process(source, process_config):
        raise RuntimeError("tree-sitter blew up")

    monkeypatch.setattr(symbols, "process", raising_process)

    with pytest.raises(RuntimeError, match="tree-sitter blew up"):
        symbols.chunk(path, "widget", "h1")
    assert str(path) not in symbols.skipped_files


# --- Store: name lookup skips context rows, path lookup and search keep them ---

PORTFOLIO = Scope("portfolio", None)


@pytest.fixture
def db(tmp_path):
    opened = open_store(tmp_path / "db")
    yield opened
    opened.conn.close()


def _put(
    db,
    path,
    doc_type,
    heading,
    body,
    ordinal,
    repo="a",
    content_hash="h1",
    corpus="code",
):
    row = Chunk(
        corpus=corpus,
        repo=repo,
        doc_type=doc_type,
        path=path,
        heading=heading,
        body=body,
        line_start=ordinal,
        line_end=ordinal,
        content_hash=content_hash,
        chunk_ordinal=ordinal,
    )
    db.upsert_chunks([ChunkWithVector(row, Vector([1.0, 0.0], "test", 2))])
    return row


def _context(db, path, body, ordinal, repo="a"):
    return _put(db, path, "module_context", "Module context", body, ordinal, repo)


def test_lookup_by_name_never_returns_context_rows(db):
    _context(db, "a.py", "import os", 3)
    _context(db, "b.py", "LIMIT = 10", 2, repo="b")
    _context(db, "c.py", "print(context)", 2)
    _put(db, "d.py", "function", "Function Context", "def Context(): ...", 1)

    assert db.lookup_by_name("context", PORTFOLIO) == []
    assert db.lookup_by_name("cont", PORTFOLIO, prefix=True) == []
    assert db.lookup_by_name("cont", PORTFOLIO) == []
    assert db.lookup_by_name("Module context", PORTFOLIO) == []
    assert db.lookup_by_name("context", Scope("repo", "a")) == []

    contour = _put(db, "c.py", "function", "Function contour", "def contour(): ...", 1)
    assert db.lookup_by_name("cont", PORTFOLIO) == [contour]
    assert db.lookup_by_name("cont", PORTFOLIO, prefix=True) == [contour]
    assert db.lookup_by_name("context", PORTFOLIO) == []

    cont = _put(db, "b.py", "function", "Function cont", "def cont(): ...", 1)
    assert db.lookup_by_name("cont", PORTFOLIO) == [cont]
    assert db.lookup_by_name("cont", PORTFOLIO, prefix=True) == [cont, contour]


def test_lookup_by_name_falls_back_past_context_rows_to_prefix_symbols(db):
    _context(db, "a.py", "print(os.sep)", 2)
    contexts = _put(db, "d.py", "class", "Class contexts", "class contexts: n = 1", 4)

    assert db.lookup_by_name("context", PORTFOLIO) == [contexts]
    assert db.lookup_by_name("context", PORTFOLIO, prefix=True) == [contexts]


def test_lookup_by_name_keeps_function_and_module_symbols_named_context(db):
    _context(db, "b.py", "print(context)", 3)
    late = _put(db, "a.py", "function", "Function context", "import os\nx = 1", 5)
    func = _put(db, "b.py", "function", "Function context", "def context(): x = 1", 1)
    _context(db, "a.py", "import os", 2)
    module = _put(db, "a.py", "module", "Module context", "mod context {}", 1)
    klass = _put(db, "c.py", "class", "Class context", "class context: ...", 1)
    _put(db, "a.py", "function", "Function Context", "def Context(): ...", 3)
    _put(db, "context.md", "prd", "Function context", "notes", 1, corpus="prd")

    expected = [module, late, func, klass]
    assert db.lookup_by_name("context", PORTFOLIO) == expected
    assert db.lookup_by_name("cont", PORTFOLIO, prefix=True) == expected
    assert db.lookup_by_name("cont", PORTFOLIO) == expected
    assert all(row.doc_type != "module_context" for row in expected)


def test_lookup_by_path_returns_context_rows_with_file_symbols(db):
    ctx_tail = _context(db, "svc.py", "print(beta())", 5)
    beta = _put(db, "svc.py", "function", "Function beta", "def beta(): ...", 4)
    ctx_mid = _context(db, "svc.py", "LIMIT = 10", 3)
    alpha = _put(db, "svc.py", "function", "Function alpha", "def alpha(): ...", 2)
    ctx_head = _context(db, "svc.py", "import os", 1)
    _put(db, "svc.py", "prd", "Section svc", "svc notes", 6, corpus="prd")
    _context(db, "svc.py.bak", "import sys", 1)
    _context(db, "pkg/svc.py", "import re", 2)

    expected = [ctx_head, alpha, ctx_mid, beta, ctx_tail]
    assert db.lookup_by_path("svc.py") == expected
    assert db.lookup_by_path("pkg/svc.py")[0].doc_type == "module_context"
    assert db.lookup_by_path("missing.py") == []


def test_lookup_leaves_context_row_body_searchable_by_bm25(db):
    alpha = _put(db, "svc.py", "function", "Function alpha", "def alpha(): 1", 1)
    zanzibar = _context(db, "svc.py", "import zanzibar", 2)
    quokka = _context(db, "util.py", "RETRIES = quokka", 1)

    assert [hit.chunk for hit in db.search_bm25("alpha", PORTFOLIO, "code", 5)] == [
        alpha,
    ]
    assert [hit.chunk for hit in db.search_bm25("zanzibar", PORTFOLIO, "code", 5)] == [
        zanzibar,
    ]
    assert [hit.chunk for hit in db.search_bm25("quokka", PORTFOLIO, "code", 5)] == [
        quokka,
    ]
    assert db.search_bm25("pangolin", PORTFOLIO, "code", 5) == []


def test_lookup_respects_repository_scope_for_symbols_and_context(db):
    a_build = _put(db, "a/app.py", "function", "Function build", "def build(): 1", 1)
    b_build = _put(
        db,
        "b/app.py",
        "function",
        "Function build",
        "def build(): 2",
        1,
        repo="b",
    )
    a_ctx = _context(db, "a/app.py", "wombat.run()", 2)
    b_ctx = _context(db, "b/app.py", "wombat.run()", 2, repo="b")
    repo_a, repo_b = Scope("repo", "a"), Scope("repo", "b")

    assert db.lookup_by_name("bui", repo_a, prefix=True) == [a_build]
    assert db.lookup_by_name("bui", repo_b, prefix=True) == [b_build]
    assert db.lookup_by_name("bui", repo_a) == [a_build]
    assert db.lookup_by_name("build", repo_a) == [a_build]
    assert db.lookup_by_name("build", repo_b) == [b_build]
    assert db.lookup_by_name("build", PORTFOLIO) == [a_build, b_build]
    assert db.lookup_by_name("build", Scope("repo", "c")) == []
    for scope in (repo_a, repo_b, PORTFOLIO):
        assert db.lookup_by_name("context", scope) == []
        assert db.lookup_by_name("cont", scope, prefix=True) == []

    assert [h.chunk for h in db.search_bm25("build", repo_a, "code", 10)] == [a_build]
    assert [h.chunk for h in db.search_bm25("wombat", repo_a, "code", 10)] == [a_ctx]
    assert [h.chunk for h in db.search_bm25("wombat", repo_b, "code", 10)] == [b_ctx]
    both = db.search_bm25("wombat", PORTFOLIO, "code", 10)
    assert sorted(h.chunk.repo for h in both) == ["a", "b"]


# --- index(): incremental runs add, keep, replace and prune context rows ---


def _service(path, word):
    body = "def run():\n    return os.sep"
    path.write_text(f'import os\n\nMODE = "{word}"\n\n\n{body}\n')
    h = corpora.hash_source(path)
    return [
        _sym(path, "function", "Function run", body, 6, 7, 1, "repo", h),
        _ctx(path, f'import os\n\nMODE = "{word}"', 1, 3, 2, "repo", h),
    ]


def _hits(db, word):
    return [hit.chunk for hit in db.search_bm25(word, PORTFOLIO, "code", 5)]


@pytest.fixture
def idx(db, tmp_path, monkeypatch):
    files, calls = [CorpusFile("code", "repo", tmp_path / "service.py")], []
    entry = EmbeddingEntry(id="test", endpoint="http://127.0.0.1:8081/v1")
    config = EngramConfig([entry], None, tmp_path / "config.toml")
    monkeypatch.setattr(corpora, "missing_dirs", [])
    monkeypatch.setattr("engram.indexer.enumerate_corpora", lambda: iter(()))
    monkeypatch.setattr("engram.indexer.transcripts.enumerate", lambda: iter(()))
    monkeypatch.setattr(symbols, "enumerate", lambda **kwargs: iter(files))

    def fake_embed(texts, entry):
        calls.append(list(texts))
        return [Vector([1.0, 0.0], entry.id, 2) for _ in texts]

    monkeypatch.setattr("engram.indexer.embed", fake_embed)
    run = partial(index, db, config, PORTFOLIO)
    return SimpleNamespace(path=files[0].path, files=files, calls=calls, run=run)


def test_index_adds_searchable_context_rows_for_new_file(db, idx):
    rows = _service(idx.path, "marmot")
    report = idx.run()
    assert db.lookup_by_path(str(idx.path)) == rows
    assert _hits(db, "marmot") == [rows[1]]
    assert (report.chunks_added, len(idx.calls)) == (2, 1)


def test_index_keeps_unchanged_file_rows_without_embedding(db, idx):
    rows = _service(idx.path, "marmot")
    idx.run()
    report = idx.run()
    assert (report.chunks_added, report.chunks_pruned, len(idx.calls)) == (0, 0, 1)
    assert db.lookup_by_path(str(idx.path)) == rows


def test_index_skips_cached_empty_file_until_its_content_changes(db, idx, monkeypatch):
    idx.path.write_text("import os\nimport sys\n")
    empty = ("code", "repo", str(idx.path), corpora.hash_source(idx.path))
    db.mark_empty_source(*empty)
    with monkeypatch.context() as m:
        m.setattr(symbols, "process", None)  # any parse attempt raises TypeError
        report = idx.run()
    assert (report.chunks_added, report.failed_sources, idx.calls) == (0, [], [])
    assert db.lookup_by_path(str(idx.path)) == []
    assert db.known_empty_sources_by_corpus(PORTFOLIO, "code") == {empty}
    idx.path.write_text("import json\nRETRY = 'badger'\n")
    h = corpora.hash_source(idx.path)
    report = idx.run()
    ctx = _ctx(idx.path, "import json\nRETRY = 'badger'", 1, 2, 1, "repo", h)
    assert db.lookup_by_path(str(idx.path)) == [ctx]
    assert db.known_empty_sources_by_corpus(PORTFOLIO, "code") == set()
    assert (report.chunks_added, len(idx.calls)) == (1, 1)


def test_index_replaces_rows_of_changed_file_and_prunes_old_hash(db, idx):
    _service(idx.path, "marmot")
    idx.run()
    rows = _service(idx.path, "ocelot")
    report = idx.run()
    assert db.lookup_by_path(str(idx.path)) == rows
    assert (report.chunks_added, report.chunks_pruned) == (2, 2)
    assert (_hits(db, "marmot"), _hits(db, "ocelot")) == ([], [rows[1]])


def test_index_prunes_all_rows_of_deleted_file(db, idx):
    _service(idx.path, "marmot")
    idx.run()
    idx.files.clear()
    idx.path.unlink()
    report = idx.run()
    assert (db.lookup_by_path(str(idx.path)), _hits(db, "marmot")) == ([], [])
    assert (report.chunks_pruned, report.chunks_added) == (2, 0)


def test_index_retains_rows_when_changed_file_fails_then_retries(db, idx, monkeypatch):
    old = _service(idx.path, "marmot")
    idx.run()
    new = _service(idx.path, "ocelot")
    with monkeypatch.context() as m:
        m.setattr(symbols, "process", None)  # the parser raises TypeError
        failed = idx.run()
    assert (failed.failed_sources, failed.chunks_pruned) == ([str(idx.path)], 0)
    assert db.lookup_by_path(str(idx.path)) == old
    assert db.known_empty_sources_by_corpus(PORTFOLIO, "code") == set()
    retried = idx.run()
    assert db.lookup_by_path(str(idx.path)) == new
    assert (retried.chunks_added, retried.chunks_pruned, len(idx.calls)) == (2, 2, 2)
