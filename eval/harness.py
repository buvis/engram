"""Runnable eval entry: score the configured embedding models against the gold
set, pin the winner into config.toml, and exit nonzero when the gate fails
(top-5 hit rate < 0.80, or engram does not beat the rg baseline). The scoring
logic lives in ``engram.harness``; this is the thin command-line entry the PRD's
eval gate runs."""

import sys
import tempfile
from pathlib import Path

from engram.client import load_config
from engram.harness import run_harness

GOLDSET_PATH = Path(__file__).resolve().parent / "goldset.yaml"


def main() -> int:
    config = load_config()
    with tempfile.TemporaryDirectory() as work_dir:
        report = run_harness(config, GOLDSET_PATH, Path(work_dir))
    for model_id, score in report.per_model.items():
        print(f"{model_id}\t{score.hit_rate:.3f}")
    print(f"winner\t{report.winner_id}")
    print(f"baseline\t{report.baseline_hit_rate:.3f}")
    print(f"gate_passed\t{report.gate_passed}")
    return 0 if report.gate_passed else 1


if __name__ == "__main__":
    sys.exit(main())
