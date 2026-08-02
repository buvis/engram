import pytest

from engram.cli import main


def test_cli_with_no_subcommand_exits_nonzero():
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0
