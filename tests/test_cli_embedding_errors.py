from unittest.mock import Mock

import pytest

from engram import cli
from engram.client import EmbeddingPreflightError, EmbeddingServerError
from engram.store import Scope


@pytest.mark.parametrize("command", ["query", "index"])
@pytest.mark.parametrize("error_type", [EmbeddingServerError, EmbeddingPreflightError])
def test_embedding_failures_print_actionable_error_without_traceback(
    monkeypatch, capsys, command, error_type
) -> None:
    monkeypatch.setattr(cli, "_resolve_scope", lambda kind: Scope("portfolio", None))
    monkeypatch.setattr(cli, "load_config", lambda: object())
    monkeypatch.setattr(cli, "open_store", lambda: object())
    monkeypatch.setattr(cli, command, Mock(side_effect=error_type("embedding unavailable")))
    argv = [command, "--scope", "portfolio"]
    if command == "query":
        argv.append("a query")

    assert cli.main(argv) == 1
    captured = capsys.readouterr()
    assert captured.err == "embedding unavailable\n"
    assert captured.out == ""
