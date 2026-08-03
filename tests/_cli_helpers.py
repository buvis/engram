import subprocess
from pathlib import Path


def _refuse(*args, **kwargs):
    raise AssertionError("should not be called")


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
