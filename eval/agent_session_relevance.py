"""Score the second agent-session set by judged relevance of the top 3.

PYTHONPATH=src:. .venv/bin/python -m eval.agent_session_relevance assemble
PYTHONPATH=src:. .venv/bin/python -m eval.agent_session_relevance hits
PYTHONPATH=src:. .venv/bin/python -m eval.agent_session_relevance score

Rules: docs/dev/project-management/reviews/2026-11-10-agent-session-evaluation-protocol.md,
section "Second set: relevance measure". `assemble` builds and freezes the
questions, `hits` writes each question's top 3 for the judge, `score` reads
the judge's verdicts. Question text, hits and verdicts stay private.
"""

import json
import random
import sys
from collections import Counter
from pathlib import Path

from engram.client import load_config
from engram.query import query
from engram.store import Scope
from eval.agent_session_eval import (
    CONFIG,
    DEPTH,
    PASS_LOWER,
    PASS_RATE,
    POOL,
    sha256,
    wilson,
)
from eval.probe_rerank_fixed import open_readonly

PRIVATE = Path.home() / ".cache" / "engram" / "compare" / "agent-sessions-v2"
BURSTS = PRIVATE / "bursts_october.jsonl"
QUESTIONS = PRIVATE / "questions.json"
FREEZE = PRIVATE / "freeze.json"
HITS = PRIVATE / "hits.json"
VERDICTS = PRIVATE / "verdicts.json"
PUBLIC = Path(__file__).resolve().parent / "results-agent-session-relevance.json"
SEED = 20261112
TOP = 3
TEXT = 6000  # characters of each hit shown to the judge


def assemble_questions() -> None:
    """Join the written questions to their bursts; cap each project at a third."""
    bursts = {b["id"]: b for b in map(json.loads, BURSTS.open())}
    pool = set((POOL.parent / "pool_paths.txt").read_text().splitlines())
    written = [
        row
        for part in sorted(PRIVATE.glob("questions_[0-9].json"))
        for row in json.loads(part.read_text())
    ]
    kept = sorted((r for r in written if r["burst"] is not None), key=str)
    random.Random(SEED).shuffle(kept)
    cap = len(kept) // 3
    while True:  # a smaller set lowers the cap, so repeat until it holds
        per_project: Counter[str] = Counter()
        chosen = []
        for row in kept:
            project = bursts[row["burst"]]["project"]
            if per_project[project] < cap:
                per_project[project] += 1
                chosen.append(row)
        if len(chosen) // 3 >= cap:
            break
        cap = len(chosen) // 3
    questions = []
    for n, row in enumerate(chosen, 1):
        burst = bursts[row["burst"]]
        if burst["session"] != row["session"]:
            raise SystemExit(f"burst {row['burst']} is not in session {row['session']}")
        questions.append(
            {
                "q": f"R{n}",
                "class": row["class"],
                "project": burst["project"],
                "session": burst["session"],
                "time": burst["time"],
                "calls": burst["search_calls"],
                "question": row["question"],
                "intent": burst["intent"],
                "labels": sorted({f for _, f in burst["next"] if f in pool}),
            },
        )
    with QUESTIONS.open("x") as stream:
        json.dump(questions, stream, indent=1)
    with FREEZE.open("x") as stream:
        json.dump(frozen_inputs(), stream, indent=2)
    print(
        {
            "sessions": len(written),
            "written": len(kept),
            "dropped_by_writer": len(written) - len(kept),
            "dropped_by_project_cap": len(kept) - len(chosen),
            "scored": len(questions),
            "by_class": Counter(q["class"] for q in questions),
            "by_project": Counter(q["project"][-24:] for q in questions),
        },
    )


def frozen_inputs() -> dict[str, str]:
    """Hashes of this set's questions and the pool and config it runs on."""
    return {
        "questions.json": sha256(QUESTIONS),
        "pool.db": sha256(POOL),
        "config.toml": sha256(CONFIG),
    }


def check_frozen() -> None:
    if json.loads(FREEZE.read_text()) != frozen_inputs():
        raise SystemExit("frozen questions, pool or config changed")


def transcript_start(path: str) -> str | None:
    """First timestamp in a transcript, or None when it cannot be read."""
    try:
        with Path(path).open() as stream:
            for line in stream:
                stamp = json.loads(line).get("timestamp")
                if stamp:
                    return stamp
    except (OSError, json.JSONDecodeError):
        return None
    return None


def keep_hit(
    path: str,
    corpus: str,
    session: str,
    asked: str,
    start: str | None,
) -> bool:
    """Time rule: no own transcript, no transcript begun after the question."""
    if session in path:
        return False
    if corpus != "transcripts":
        return True
    return start is not None and start < asked


def write_hits() -> None:
    check_frozen()
    config = load_config(CONFIG)
    out = []
    dropped = Counter()
    with open_readonly(POOL) as store:
        for q in json.loads(QUESTIONS.read_text()):
            pointers = query(
                store,
                config,
                q["question"],
                Scope("portfolio", None),
                k=DEPTH,
                include_body=True,
            )
            top: dict[str, dict] = {}
            for p in pointers:
                start = transcript_start(p.path) if p.corpus == "transcripts" else None
                if not keep_hit(p.path, p.corpus, q["session"], q["time"], start):
                    dropped[p.corpus] += 1
                    continue
                if p.path not in top and len(top) < TOP:
                    top[p.path] = {
                        "path": p.path,
                        "heading": p.heading,
                        "corpus": p.corpus,
                        "lines": [p.line_start, p.line_end],
                        "text": (p.body or "")[:TEXT],
                        "settled": p.path in q["labels"],
                    }
            keys = ("q", "question", "intent", "labels")
            out.append({**{k: q[k] for k in keys}, "hits": list(top.values())})
            print(q["q"], [h["corpus"] for h in top.values()], flush=True)
    with HITS.open("x") as stream:
        json.dump(out, stream, indent=1)
    print("hits dropped by the time rule, per corpus:", dict(dropped))


def score_verdicts() -> None:
    check_frozen()
    questions = {q["q"]: q for q in json.loads(QUESTIONS.read_text())}
    shown = {h["q"]: h["hits"] for h in json.loads(HITS.read_text())}
    verdicts = json.loads(VERDICTS.read_text())
    rows = []
    for name, q in questions.items():
        marks = verdicts[name]
        if len(marks) != len(shown[name]) or set(marks) - {"useful", "not"}:
            raise SystemExit(f"{name}: verdicts do not match the hits shown")
        useful = [m == "useful" or h["settled"] for m, h in zip(marks, shown[name])]
        rows.append(
            {
                "q": name,
                "class": q["class"],
                "calls": q["calls"],
                "hits_shown": len(marks),
                "useful": sum(useful),
                "settled_file_in_top3": any(h["settled"] for h in shown[name]),
                "useful_corpora": sorted(
                    {h["corpus"] for u, h in zip(useful, shown[name]) if u},
                ),
            },
        )
    n = len(rows)
    passed = sum(r["useful"] > 0 for r in rows)
    low, high = wilson(passed, n)
    by_class = {
        c: {
            "n": sum(r["class"] == c for r in rows),
            "passed": sum(r["class"] == c and r["useful"] > 0 for r in rows),
        }
        for c in sorted({r["class"] for r in rows})
    }
    summary = {
        "n": n,
        "passed": passed,
        "pass_rate": passed / n,
        "wilson95": [low, high],
        "pass": passed / n >= PASS_RATE and low > PASS_LOWER,
        "exact_settled_file_in_top3": sum(r["settled_file_in_top3"] for r in rows),
        "useful_hits_of_shown": [
            sum(r["useful"] for r in rows),
            sum(r["hits_shown"] for r in rows),
        ],
        "by_class": by_class,
        "failed": [r["q"] for r in rows if not r["useful"]],
        "freeze": json.loads(FREEZE.read_text()),
        "rows": rows,
    }
    PUBLIC.write_text(json.dumps(summary, indent=2) + "\n")
    print({k: v for k, v in summary.items() if k not in ("rows", "freeze")})


def write_spot_check() -> None:
    """Ten seeded questions with hits and the judge's reasons, for the human check."""
    check_frozen()
    shown = json.loads(HITS.read_text())
    judged = {}
    for part in sorted(PRIVATE.glob("verdicts_[0-9].json")):
        judged |= json.loads(part.read_text())
    lines = [
        "# Spot check: 10 judged questions",
        "",
        "For each question, decide: would at least one hit have helped the agent?",
        "Then compare with the judge's result. Count the questions where you differ.",
        "More than 2 differences voids the judged result.",
    ]
    for item in sorted(random.Random(SEED).sample(shown, 10), key=lambda i: i["q"]):
        verdict = judged[item["q"]]
        marks = [
            "useful" if h["settled"] else m
            for m, h in zip(verdict["marks"], item["hits"])
        ]
        result = "PASS" if "useful" in marks else "FAIL"
        lines += ["", f"## {item['q']}: judge says {result}", "", item["question"], ""]
        lines += ["The agent then read or edited:"]
        lines += [f"- `{label}`" for label in item["labels"]]
        for n, (hit, mark) in enumerate(zip(item["hits"], marks)):
            start, end = hit["lines"]
            lines += [
                "",
                f"### Hit {n + 1}: {mark}",
                "",
                f"`{hit['path']}:{start}-{end}` ({hit['corpus']}, {hit['heading']})",
                "",
                f"Judge: {verdict['reasons'][n]}",
                "",
                "```",
                hit["text"][:1500].replace("```", "'''"),
                "```",
            ]
    (PRIVATE / "spot-check.md").write_text("\n".join(lines) + "\n")
    print(PRIVATE / "spot-check.md")


def main() -> None:
    actions = {
        "assemble": assemble_questions,
        "hits": write_hits,
        "score": score_verdicts,
        "spot": write_spot_check,
    }
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        raise SystemExit("usage: assemble | hits | score | spot")
    actions[sys.argv[1]]()


if __name__ == "__main__":
    main()
