import pytest
from _pack_helpers import (
    _chunk,
    _config,
    _small_budget,
    _vec,
)

from engram.indexer import IndexReport
from engram.pack import MAX_SYMBOLS_PER_PACK, RETRIEVAL_K, build
from engram.store import ChunkWithVector, open_store

# --- regression: a pack built in a worktree excludes spans indexed under main ---


def _write_files_diff(root, files):
    # Same def/blank/blank layout as _write_many_function_diff, over several
    # files: files maps rel_path -> function count, function i spans 1+4i..2+4i.
    diff_lines = []
    for rel, count in files.items():
        file_lines = []
        diff_lines += [
            f"diff --git a/{rel} b/{rel}",
            "index 1111111..2222222 100644",
            f"--- a/{rel}",
            f"+++ b/{rel}",
        ]
        for i in range(count):
            start = 1 + 4 * i
            file_lines += [f"def f{i}():", f"    return {i}", "", ""]
            diff_lines += [
                f"@@ -{start},2 +{start},2 @@",
                f" def f{i}():",
                "-    return -1",
                f"+    return {i}",
            ]
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("\n".join(file_lines) + "\n")
    diff_path = root / "changes.diff"
    diff_path.write_text("\n".join(diff_lines) + "\n")
    return diff_path


def _patch_worktree_embeds(monkeypatch, fake_embed):
    monkeypatch.setattr("engram.pack.index", lambda *a, **k: IndexReport(0, 0, 0, []))
    monkeypatch.setattr("engram.pack.embed", fake_embed)
    monkeypatch.setattr(
        "engram.query.embed",
        lambda texts, entry: [_vec([0, 0, 0, 1]) for _ in texts],
    )


def _seed_worktree_chunks(store, tmp_path, chunk_specs, query_vector):
    store.upsert_chunks(
        [
            ChunkWithVector(
                chunk=_chunk(
                    path=str(tmp_path / root / rel),
                    line_start=start,
                    line_end=end,
                    body=marker,
                    content_hash=marker,
                    chunk_ordinal=ordinal,
                ),
                vector=query_vector,
            )
            for ordinal, (root, rel, start, end, marker) in enumerate(chunk_specs)
        ],
    )


def _worktree_pack(tmp_path, monkeypatch, chunk_specs, files=None, **build_kwargs):
    # Pack built in tmp_path/wt for a diff of `files` (default: big.py with two
    # functions, spans 1-2 and 5-6).
    # chunk_specs: (root_dir, rel_path, start, end, marker); every chunk has the
    # query vector, so ranking cannot explain an absence from Similar code.
    # Every chunk ties on score, so more than RETRIEVAL_K could go unretrieved.
    assert len(chunk_specs) <= RETRIEVAL_K
    worktree = tmp_path / "wt"
    worktree.mkdir()
    diff_path = _write_files_diff(worktree, files or {"big.py": 2})
    store = open_store(tmp_path / "engram.db")
    query_vector = _vec([1.0, 0.0, 0.0, 0.0])
    embedded_texts = []

    def fake_embed(texts, entry):
        embedded_texts.extend(texts)
        return [query_vector for _ in texts]

    _patch_worktree_embeds(monkeypatch, fake_embed)
    _seed_worktree_chunks(store, tmp_path, chunk_specs, query_vector)
    report = build(
        store,
        _config(tmp_path, _small_budget()),
        "repoA",
        worktree,
        "wt",
        diff_path,
        out_dir=tmp_path / "out",
        **build_kwargs,
    )
    similar = next(s for s in report.sections if s.label == "Similar code")
    return similar.body, embedded_texts


def test_pack_in_worktree_excludes_changed_spans_indexed_under_main_checkout(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "main").mkdir()
    (tmp_path / "main" / "big.py").write_text("def f0():\n    return 'MAIN-TEXT'\n")
    similar, embedded_texts = _worktree_pack(
        tmp_path,
        monkeypatch,
        [
            ("main", "big.py", 1, 2, "MAIN-F0-SELF"),
            ("main", "big.py", 5, 6, "MAIN-F1-SELF"),
            ("wt", "big.py", 1, 2, "WT-F0-SELF"),
            # same file under main, lines between the two spans
            ("main", "big.py", 3, 4, "MAIN-GAP-KEEP"),
            # a sibling dir whose name only shares the main checkout's prefix
            ("mainx", "big.py", 1, 2, "MAINX-PREFIX-KEEP"),
        ],
        index_root=tmp_path / "main",
    )

    # every changed span is excluded under both checkouts
    for self_match in ("MAIN-F0-SELF", "MAIN-F1-SELF", "WT-F0-SELF"):
        assert self_match not in similar
    # the exclusion is exact, so near misses still reach Similar code
    assert "MAIN-GAP-KEEP" in similar
    assert "MAINX-PREFIX-KEEP" in similar
    # symbol text still comes from the worktree, not the main checkout
    assert any("return 0" in text for text in embedded_texts)
    assert any("return 1" in text for text in embedded_texts)
    assert not any("MAIN-TEXT" in text for text in embedded_texts)


_LAST_START = 1 + 4 * MAX_SYMBOLS_PER_PACK  # span of the first symbol past the cap


@pytest.mark.parametrize(
    ("files", "index_root", "chunk_specs", "excluded", "kept"),
    [
        pytest.param(
            {"pkg/big.py": 3, "other.py": 1},
            "main",
            [
                # third function of a file in a subdirectory
                ("main", "pkg/big.py", 9, 10, "MAIN-PKG-F2-SELF"),
                # overlaps only the last line of the 9-10 span
                ("main", "pkg/big.py", 10, 11, "MAIN-PKG-TAIL-SELF"),
                # the second changed file
                ("main", "other.py", 1, 2, "MAIN-OTHER-F0-SELF"),
                ("main", "pkg/big.py", 7, 8, "MAIN-PKG-GAP-KEEP"),
                # same basename at the top level is a different file
                ("main", "big.py", 9, 10, "MAIN-TOP-BASENAME-KEEP"),
            ],
            ["MAIN-PKG-F2-SELF", "MAIN-PKG-TAIL-SELF", "MAIN-OTHER-F0-SELF"],
            ["MAIN-PKG-GAP-KEEP", "MAIN-TOP-BASENAME-KEEP"],
            id="subdir-two-files-tail-overlap",
        ),
        pytest.param(
            {"big.py": MAX_SYMBOLS_PER_PACK + 1},
            "elsewhere/checkout",
            [
                # the symbol past the query cap is still a changed span
                ("elsewhere/checkout", "big.py", _LAST_START, _LAST_START + 1,
                 "ELSEWHERE-LAST-SELF"),
                ("elsewhere/checkout", "big.py", 1, 2, "ELSEWHERE-F0-SELF"),
                ("wt", "big.py", _LAST_START, _LAST_START + 1, "WT-LAST-SELF"),
                ("elsewhere/checkout", "big.py", _LAST_START + 2, _LAST_START + 3,
                 "ELSEWHERE-AFTER-KEEP"),
                # a sibling "main" dir is not the index root here
                ("main", "big.py", 1, 2, "MAIN-NOT-INDEX-ROOT-KEEP"),
            ],
            ["ELSEWHERE-LAST-SELF", "ELSEWHERE-F0-SELF", "WT-LAST-SELF"],
            ["ELSEWHERE-AFTER-KEEP", "MAIN-NOT-INDEX-ROOT-KEEP"],
            id="non-sibling-index-root-past-symbol-cap",
        ),
    ],
)
def test_pack_in_worktree_excludes_main_checkout_spans_of_every_changed_symbol(
    tmp_path,
    monkeypatch,
    files,
    index_root,
    chunk_specs,
    excluded,
    kept,
):
    (tmp_path / index_root).mkdir(parents=True)
    similar, _ = _worktree_pack(
        tmp_path,
        monkeypatch,
        chunk_specs,
        files=files,
        index_root=tmp_path / index_root,
    )

    for self_match in excluded:
        assert self_match not in similar
    for near_miss in kept:
        assert near_miss in similar


@pytest.mark.parametrize("index_root", ["omitted", "none", "repo_root"])
def test_pack_without_a_distinct_main_checkout_excludes_only_worktree_spans(
    tmp_path,
    monkeypatch,
    index_root,
):
    build_kwargs = {
        "omitted": {},
        "none": {"index_root": None},
        "repo_root": {"index_root": tmp_path / "wt"},
    }[index_root]
    similar, _ = _worktree_pack(
        tmp_path,
        monkeypatch,
        [
            ("wt", "big.py", 1, 2, "WT-F0-SELF"),
            ("wt", "big.py", 5, 6, "WT-F1-SELF"),
            ("wt", "big.py", 3, 4, "WT-GAP-KEEP"),
            ("main", "big.py", 1, 2, "MAIN-F0-KEEP"),
        ],
        **build_kwargs,
    )

    assert "WT-F0-SELF" not in similar
    assert "WT-F1-SELF" not in similar
    assert "WT-GAP-KEEP" in similar
    # no second span is added, so the main checkout's copy is not excluded
    assert "MAIN-F0-KEEP" in similar
