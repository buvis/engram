"""Score agent-session questions against a frozen copy of the production index.

PYTHONPATH=src:. .venv/bin/python -m eval.agent_session_eval freeze
PYTHONPATH=src:. .venv/bin/python -m eval.agent_session_eval run

Protocol: docs/dev/project-management/reviews/2026-11-10-agent-session-evaluation-protocol.md
Questions, labels and transcript excerpts stay private in PRIVATE; the public
summary holds counts and question ids only.
"""

import hashlib
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

from engram.client import load_config
from engram.query import query
from engram.store import Scope
from eval.probe_rerank_fixed import open_readonly

PRIVATE = Path.home() / ".cache" / "engram" / "compare" / "agent-sessions"
POOL = PRIVATE / "pool.db"
FREEZE = PRIVATE / "freeze.json"
QUESTION_FILES = ["questions_a.json", "questions_b.json"]
CONFIG = Path.home() / ".local" / "share" / "engram" / "config.toml"
PUBLIC = Path(__file__).resolve().parent / "results-agent-sessions.json"
DEPTH = 60  # fused chunks fetched per question, then deduplicated to files
PASS_RATE, PASS_LOWER = 0.60, 0.50  # threshold fixed by the user before scoring


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = hits / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    denom = 1 + z * z / n
    return (centre - spread) / denom, (centre + spread) / denom


def file_ranks(paths: list[str], labels: set[str], leaked: str) -> int | None:
    """1-based rank of the first label among unique files, leaked session excluded."""
    seen: list[str] = []
    for path in paths:
        if leaked in path or path in seen:
            continue
        seen.append(path)
        if path in labels:
            return len(seen)
    return None


def fingerprint() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    files = {name: sha256(PRIVATE / name) for name in QUESTION_FILES}
    return {
        **files,
        "pool.db": sha256(POOL),
        "config.toml": sha256(CONFIG),
        "script": sha256(Path(__file__)),
        "engram_head": head,
    }


def full_session_ids() -> dict[str, str]:
    ids: dict[str, str] = {}
    for line in (PRIVATE / "bursts.jsonl").open():
        session = json.loads(line)["session"]
        ids[session[:8]] = session
    return ids


def run() -> None:
    frozen = json.loads(FREEZE.read_text())
    if frozen != fingerprint():
        raise SystemExit("frozen inputs changed after freeze")
    questions = [q for name in QUESTION_FILES for q in json.loads((PRIVATE / name).read_text())]
    sessions = full_session_ids()
    config = load_config(CONFIG)
    rows = []
    with open_readonly(POOL) as store:
        for q in questions:
            pointers = query(store, config, q["question"], Scope("portfolio", None), k=DEPTH)
            paths = [p.path for p in pointers]
            leaked = sessions[q["session"]]
            labels = set(q["labels"])
            leak_in_top5 = any(leaked in p for p in dict.fromkeys(paths[:5]))
            rows.append(
                {
                    **{k: q[k] for k in ("q", "project", "class", "calls")},
                    "rank": file_ranks(paths, labels, leaked),
                    "rank_unfiltered": file_ranks(paths, labels, "\0"),
                    "leaked_transcript_in_top5": leak_in_top5,
                    "label_corpus": sorted({p.corpus for p in pointers if p.path in labels}),
                }
            )
            print(q["q"], rows[-1]["rank"], flush=True)
    n = len(rows)
    ranks = [r["rank"] for r in rows]
    top3 = sum(r is not None and r <= 3 for r in ranks)
    top5 = sum(r is not None and r <= 5 for r in ranks)
    low, _ = wilson(top3, n)

    def breakdown(key: str) -> dict[str, dict[str, int]]:
        out = {}
        for value in sorted({r[key] for r in rows}):
            sub = [r for r in rows if r[key] == value]
            out[value] = {"n": len(sub), "top3": sum(r["rank"] is not None and r["rank"] <= 3 for r in sub)}
        return out

    summary = {
        "n": n,
        "top3": top3,
        "top5": top5,
        "top3_rate": top3 / n,
        "top5_rate": top5 / n,
        "top3_wilson95": list(wilson(top3, n)),
        "top5_wilson95": list(wilson(top5, n)),
        "mrr": sum(1 / r for r in ranks if r) / n,
        "median_search_calls": statistics.median(r["calls"] for r in rows),
        "by_class": breakdown("class"),
        "by_project": breakdown("project"),
        "leaked_transcript_in_top5": sum(r["leaked_transcript_in_top5"] for r in rows),
        "misses_top3": [r["q"] for r in rows if not (r["rank"] and r["rank"] <= 3)],
        "pass": top3 / n >= PASS_RATE and low > PASS_LOWER,
        "freeze": frozen,
        "rows": rows,
    }
    PUBLIC.write_text(json.dumps(summary, indent=2) + "\n")
    print({k: v for k, v in summary.items() if k not in ("rows", "freeze")})


def main() -> None:
    action = sys.argv[1]
    if action == "freeze":
        with FREEZE.open("x") as stream:
            json.dump(fingerprint(), stream, indent=2)
    elif action == "run":
        run()
    else:
        raise SystemExit("usage: freeze | run")


if __name__ == "__main__":
    main()
