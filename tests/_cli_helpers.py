import subprocess
from pathlib import Path

import pytest


def _refuse(*args, **kwargs):
    raise AssertionError("should not be called")


@pytest.fixture(autouse=True)
def _stub_symbols_count_skipped(monkeypatch):
    # _run_status now prints a "code\tskipped=N" line driven by
    # symbols.count_skipped(); default it to 0 (no line printed) so existing
    # tests (written before this producer existed) are unaffected.
    monkeypatch.setattr(
        "engram.cli.symbols.count_skipped",
        lambda *a, **k: 0,
        raising=False,
    )


def _init_git_repo(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip())
