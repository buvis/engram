"""Eval harness: score embedding models against a gold set, compare to rg baseline."""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from engram.client import EmbeddingEntry, EngramConfig, ensure_served, stop_served
from engram.corpora import enumerate_corpora
from engram.indexer import index
from engram.query import query
from engram.store import Scope, open_store

RRF_DEDUP_POOL = 25

STOPWORDS = frozenset(
    {"a", "the", "is", "are", "of", "to", "in", "and", "or", "for", "on", "with", "how", "what"}
)

_VALID_CORPORA = frozenset({"memory", "prd", "decision", "discovery"})


@dataclass(frozen=True)
class GoldEntry:
    query: str
    expected_path: str
    corpus: str


@dataclass(frozen=True)
class ModelScore:
    hit_rate: float
    per_corpus_hit_rate: dict[str, float]


@dataclass(frozen=True)
class HarnessReport:
    per_model: dict[str, ModelScore]
    winner_id: str
    baseline_hit_rate: float
    gate_passed: bool


def _sanitize_for_filename(model_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", model_id)


def load_goldset(goldset_path: Path) -> list[GoldEntry]:
    raw = yaml.safe_load(goldset_path.read_text())
    if len(raw) < 30:
        raise ValueError(f"goldset has {len(raw)} entries, need >= 30")
    for entry in raw:
        if entry["corpus"] not in _VALID_CORPORA:
            raise ValueError(f"unknown corpus {entry['corpus']!r}")
        resolved = str(Path(entry["expected_path"]).resolve())
        if not Path(resolved).exists():
            raise ValueError(f"expected_path does not exist: {resolved}")
    return [
        GoldEntry(
            query=e["query"],
            expected_path=str(Path(e["expected_path"]).resolve()),
            corpus=e["corpus"],
        )
        for e in raw
    ]


def _score_candidate(entry: EmbeddingEntry, config_path: Path, goldset, work_dir: Path) -> ModelScore:
    cand_cfg = EngramConfig(
        embeddings=[entry], pinned_id=entry.id, config_path=config_path
    )
    db = work_dir / f"harness-{_sanitize_for_filename(entry.id)}.db"
    if db.exists():
        db.unlink()
    store = open_store(db)
    for corpus in sorted({g.corpus for g in goldset}):
        index(store, cand_cfg, Scope("portfolio", None), corpus=corpus)
    hits = 0
    per_corpus_hits: dict[str, int] = {}
    per_corpus_totals: dict[str, int] = {}
    for g in goldset:
        pointers = query(
            store, cand_cfg, g.query, Scope("portfolio", None), k=RRF_DEDUP_POOL
        )
        seen: list[str] = []
        for p in pointers:
            if p.path not in seen:
                seen.append(p.path)
            if len(seen) == 5:
                break
        hit = 1 if g.expected_path in seen else 0
        hits += hit
        per_corpus_hits[g.corpus] = per_corpus_hits.get(g.corpus, 0) + hit
        per_corpus_totals[g.corpus] = per_corpus_totals.get(g.corpus, 0) + 1
    hit_rate = hits / len(goldset)
    per_corpus_hit_rate = {
        c: per_corpus_hits[c] / per_corpus_totals[c] for c in per_corpus_totals
    }
    return ModelScore(hit_rate, per_corpus_hit_rate)


def _baseline_hit_rate(goldset) -> float:
    goldset_corpora = {g.corpus for g in goldset}
    corpus_files = [f.path for f in enumerate_corpora() if f.corpus in goldset_corpora]
    if not corpus_files:
        # No corpus files to search — never pass an empty path list to rg, which
        # would make it recursively scan the cwd and corrupt the baseline.
        return 0.0
    baseline_hits = 0
    for g in goldset:
        tokens = {
            t
            for t in re.split(r"[^a-zA-Z0-9]+", g.query.lower())
            if t and t not in STOPWORDS
        }
        if not tokens:
            continue
        match_counts: dict[str, int] = {}
        for term in tokens:
            result = subprocess.run(
                ["rg", "-il", term, *corpus_files], capture_output=True, text=True
            )
            if result.returncode in (0, 1) and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    fp = line.strip()
                    if fp:
                        match_counts[fp] = match_counts.get(fp, 0) + 1
        ranked = sorted(match_counts.items(), key=lambda x: (-x[1], x[0]))
        top5 = {str(Path(p).resolve()) for p, _ in ranked[:5]}
        if g.expected_path in top5:
            baseline_hits += 1
    return baseline_hits / len(goldset)


def _write_pinned(config_path: Path, winner_id: str) -> None:
    new_lines = []
    in_pinned = False
    for line in config_path.read_text().split("\n"):
        stripped = line.strip()
        if stripped == "[pinned]":
            in_pinned = True
            new_lines.append(line)
        elif stripped.startswith("[") and not stripped.startswith("[["):
            in_pinned = False
            new_lines.append(line)
        elif in_pinned and stripped.startswith("id"):
            new_lines.append(f'id = "{winner_id}"')
        else:
            new_lines.append(line)
    config_path.write_text("\n".join(new_lines))


def run_harness(config: EngramConfig, goldset_path: Path, work_dir: Path) -> HarnessReport:
    goldset = load_goldset(goldset_path)
    leases = []
    per_model: dict[str, ModelScore] = {}
    winner_id: str | None = None
    try:
        for entry in config.embeddings:
            leases.append(ensure_served(entry))
            per_model[entry.id] = _score_candidate(entry, config.config_path, goldset, work_dir)

        best_rate = -1.0
        for entry in config.embeddings:
            rate = per_model[entry.id].hit_rate
            if rate > best_rate:
                best_rate = rate
                winner_id = entry.id

        baseline_hit_rate = _baseline_hit_rate(goldset)
        gate_passed = (
            per_model[winner_id].hit_rate >= 0.80
            and per_model[winner_id].hit_rate > baseline_hit_rate
        )
        _write_pinned(config.config_path, winner_id)
        return HarnessReport(per_model, winner_id, baseline_hit_rate, gate_passed)
    finally:
        for lease in leases:
            if lease.entry.id != winner_id:
                stop_served(lease)
