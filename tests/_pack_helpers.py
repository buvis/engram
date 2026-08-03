from engram.client import EmbeddingEntry, EngramConfig, PackBudget, Vector
from engram.store import Chunk

MODEL_ID = "test-model"
DIM = 4


def _entry():
    return EmbeddingEntry(id=MODEL_ID, endpoint="http://127.0.0.1:8081/v1")


def _config(tmp_path, pack_budget):
    return EngramConfig(
        embeddings=[_entry()],
        pinned_id=None,
        config_path=tmp_path / "config.toml",
        pack_budget=pack_budget,
    )


def _small_budget():
    return PackBudget(
        hard_cap_tokens=2000,
        similar_cap_tokens=300,
        reuse_cap_tokens=300,
        findings_cap_tokens=300,
        prose_cap_tokens=200,
    )


def _vec(values):
    return Vector(values, MODEL_ID, DIM)


def _chunk(**kw):
    defaults = dict(
        corpus="code",
        repo="repoA",
        doc_type="function",
        path="unrelated.py",
        heading="H",
        body="body",
        line_start=1,
        line_end=1,
        content_hash="hash",
        chunk_ordinal=0,
    )
    defaults.update(kw)
    return Chunk(**defaults)


def _write_single_function_diff(tmp_path):
    file_path = tmp_path / "mod.py"
    file_path.write_text("def foo():\n    return 1\n")
    diff_path = tmp_path / "changes.diff"
    diff_path.write_text(
        "\n".join(
            [
                "diff --git a/mod.py b/mod.py",
                "index 1111111..2222222 100644",
                "--- a/mod.py",
                "+++ b/mod.py",
                "@@ -1,2 +1,2 @@",
                " def foo():",
                "-    return 0",
                "+    return 1",
            ],
        )
        + "\n",
    )
    return file_path, diff_path


def _write_many_function_diff(tmp_path, count):
    # Reproduces the def/blank/blank block layout established in
    # tests/test_diffmap.py (foo() at lines 1-2, bar() at lines 5-6, ...), just
    # repeated `count` times, so each function's line span is 1+4*i .. 2+4*i and
    # each hunk's "-" line is a placebo (changed_symbols only needs the '+' line's
    # post-image line number, not a faithful pre-image).
    file_lines = []
    diff_lines = [
        "diff --git a/big.py b/big.py",
        "index 1111111..2222222 100644",
        "--- a/big.py",
        "+++ b/big.py",
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
    file_path = tmp_path / "big.py"
    file_path.write_text("\n".join(file_lines) + "\n")
    diff_path = tmp_path / "changes.diff"
    diff_path.write_text("\n".join(diff_lines) + "\n")
    return file_path, diff_path
