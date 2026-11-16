import subprocess
from pathlib import Path


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


def _write_repos_csv(csv_path, entries):
    lines = [f"{repo_path},{name}" for repo_path, name in entries]
    csv_path.write_text("\n".join(lines) + "\n")
