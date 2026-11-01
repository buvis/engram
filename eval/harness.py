"""Runnable eval entry: score the configured embedding models against the gold
set, pin the winner into config.toml, and exit nonzero when the gate fails
(top-5 hit rate < 0.80, or engram does not beat the rg baseline). The scoring
logic lives in ``engram.harness``; this is the thin command-line entry the PRD's
eval gate runs."""

import shutil
import sys
from pathlib import Path

from engram.client import DEFAULT_CONFIG_PATH, load_config
from engram.harness import format_report, run_harness

GOLDSET_PATH = Path(__file__).resolve().parent / "goldset.yaml"

# Persistent, not a TemporaryDirectory: each candidate's index costs a 20-25
# minute cold build, and `index()` is incremental, so throwing the directory
# away made every re-run of the gate pay full price again. The database names
# carry the model, the goldset's corpora and a chunking-code fingerprint, so a
# cached index is either exactly right to reuse or is never found - delete this
# directory freely, it only ever costs time.
WORK_DIR = Path.home() / ".cache" / "engram" / "harness"


def isolated_config_path(work_dir: Path = WORK_DIR, source: Path = DEFAULT_CONFIG_PATH) -> Path:
    """Fresh copy of the production config inside work_dir.

    The harness writes the winning model into the config it was given when the
    gate passes; running on a copy means an eval can never repoint production.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    load_config(source)  # materialize the default config if missing
    copy = work_dir / "eval-config.toml"
    shutil.copyfile(source, copy)
    return copy


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(isolated_config_path())
    report = run_harness(config, GOLDSET_PATH, WORK_DIR)
    for line in format_report(report):
        print(line)
    return 0 if report.gate_passed else 1


if __name__ == "__main__":
    sys.exit(main())
