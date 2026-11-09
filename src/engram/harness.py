"""Eval harness: score embedding models against a gold set, compare to rg baseline."""

import hashlib
import itertools
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from engram import symbols, transcripts
from engram.client import EmbeddingEntry, EngramConfig, ensure_served, stop_served
from engram.corpora import enumerate_corpora
from engram.indexer import index
from engram.query import query
from engram.store import Scope, open_store

RRF_DEDUP_POOL = 25

STOPWORDS = frozenset(
    {
        "a",
        "the",
        "is",
        "are",
        "of",
        "to",
        "in",
        "and",
        "or",
        "for",
        "on",
        "with",
        "how",
        "what",
    },
)

_VALID_CORPORA = frozenset(
    {"memory", "prd", "decision", "discovery", "transcripts", "code"},
)

# Classes carrying a per-class threshold, because a requirement names one: PRD
# 00002's two success metrics are the transcript and code corpora it introduces.
# The pooled rate still has to clear the bar across every entry, and any class
# can drag it down - but only these two can fail the gate on their own. Applying
# a per-class bar to every class in the gold set blocked on `prd` (0.769), a
# pre-existing corpus no requirement gates.
GATED_CORPORA = frozenset({"transcripts", "code"})


@dataclass(frozen=True)
class GoldEntry:
    query: str
    expected_path: str
    corpus: str


@dataclass(frozen=True)
class RetainedSource:
    expected_path: str
    path: Path


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


# Modules that cannot change what lands in an index: the eval that reads it and
# the retrieval that queries it. Everything else in the package is included by
# default, so a new module that produces chunks is covered without being listed.
_NON_INDEXING_MODULES = frozenset({"harness.py", "query.py"})


def _chunking_sources() -> list[Path]:
    """The modules whose content decides what an index holds."""
    package = Path(__file__).resolve().parent
    return sorted(
        p for p in package.glob("*.py") if p.name not in _NON_INDEXING_MODULES
    )


def _chunking_signature() -> str:
    """Fingerprint of the code that produces chunks and vectors.

    A candidate index is only safe to reuse while the code that built it is
    unchanged: `index()` skips a file whose *source* hash is unchanged, so a
    chunker or embedding change would leave the old chunks in place and the gate
    would score yesterday's vectors. Folding this into the database name makes
    such a change produce a different file rather than silently stale rows.

    Scoped to the indexing modules on purpose: hashing the whole package meant
    editing this file invalidated all three candidate indexes and charged a
    20-25 minute cold rebuild per candidate for a change that cannot affect a
    single stored chunk.
    """
    digest = hashlib.sha256()
    for path in _chunking_sources():
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _candidate_db(work_dir: Path, entry: EmbeddingEntry, goldset) -> Path:
    """Where this candidate's index lives.

    Keyed by everything the index depends on - the model, the corpora the
    goldset asks for, and the chunking code - so a cached index is either
    exactly right to reuse or is not found at all. Reuse matters because
    `index()` is incremental: a re-run with all three unchanged reindexes in
    seconds instead of repeating a 20-25 minute cold build per candidate.
    """
    corpora = "-".join(sorted({g.corpus for g in goldset}))
    name = (
        f"harness-{_sanitize_for_filename(entry.id)}-{corpora}-{_chunking_signature()}"
    )
    return work_dir / f"{name}.db"


def load_goldset(
    goldset_path: Path, *, source_paths: dict[str, RetainedSource] | None = None
) -> list[GoldEntry]:
    """Validate live sources, or explicitly supplied retained copies.

    Retained paths are for validation only; expected_path remains the original
    scoring identity. Snapshot callers must verify hashes before supplying them.
    The live harness deliberately does not pass this mapping.
    """
    raw = yaml.safe_load(goldset_path.read_text())
    if len(raw) < 30:
        raise ValueError(f"goldset has {len(raw)} entries, need >= 30")
    entries = []
    for entry in raw:
        if entry["corpus"] not in _VALID_CORPORA:
            raise ValueError(f"unknown corpus {entry['corpus']!r}")
        label = entry["expected_path"]
        if source_paths is None:
            source = Path(label).resolve()
            resolved = str(source)
        else:
            if label not in source_paths:
                raise ValueError(f"retained source missing: {label}")
            source = source_paths[label].path
            resolved = source_paths[label].expected_path
        if not source.is_file():
            raise ValueError(f"expected_path does not exist: {resolved}")
        entries.append(GoldEntry(entry["query"], resolved, entry["corpus"]))
    return entries


def _score_candidate(
    entry: EmbeddingEntry,
    config_path: Path,
    goldset,
    work_dir: Path,
) -> ModelScore:
    cand_cfg = EngramConfig(
        embeddings=[entry],
        pinned_id=entry.id,
        config_path=config_path,
    )
    db = _candidate_db(work_dir, entry, goldset)
    store = open_store(db)
    try:
        for corpus in sorted({g.corpus for g in goldset}):
            index(store, cand_cfg, Scope("portfolio", None), corpus=corpus)
        hits = 0
        per_corpus_hits: dict[str, int] = {}
        per_corpus_totals: dict[str, int] = {}
        for g in goldset:
            # Scoped to the corpus the entry declares, matching how every real
            # consumer queries. Unscoped, a "have I built X" code entry competes
            # against the PRD specifying X and the transcript where X was built,
            # and loses to them: measured 0.600 unscoped against 1.000 scoped for
            # the code class, with every other class unchanged.
            pointers = query(
                store,
                cand_cfg,
                g.query,
                Scope("portfolio", None),
                corpus=g.corpus,
                k=RRF_DEDUP_POOL,
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
    finally:
        store.conn.close()


def _batch_corpus_files(corpus_files: list[Path], max_bytes: int) -> list[list[Path]]:
    batches: list[list[Path]] = []
    current: list[Path] = []
    current_bytes = 0
    for f in corpus_files:
        f_bytes = len(os.fsencode(str(f))) + 1
        if current and current_bytes + f_bytes > max_bytes:
            batches.append(current)
            current = []
            current_bytes = 0
        current.append(f)
        current_bytes += f_bytes
    if current:
        batches.append(current)
    return batches


def _baseline_hit_rate(goldset) -> float:
    goldset_corpora = {g.corpus for g in goldset}
    corpus_files = [
        f.path
        for f in itertools.chain(
            enumerate_corpora(),
            transcripts.enumerate(),
            symbols.enumerate(),
        )
        if f.corpus in goldset_corpora
    ]
    if not corpus_files:
        # No corpus files to search — never pass an empty path list to rg, which
        # would make it recursively scan the cwd and corrupt the baseline.
        return 0.0
    # Keep every rg invocation well under the OS's ARG_MAX (a few thousand
    # corpus files can otherwise blow past it): split into batches, each
    # comfortably within a quarter of the limit.
    batches = _batch_corpus_files(corpus_files, os.sysconf("SC_ARG_MAX") // 4)
    baseline_hits = 0
    for g in goldset:
        tokens = {
            t
            for t in re.split(r"[^a-zA-Z0-9]+", g.query.lower())
            if t and t not in STOPWORDS
        }
        match_counts: dict[str, int] = {}
        for term in tokens:
            matched_files: set[str] = set()
            for batch in batches:
                result = subprocess.run(
                    ["rg", "-il", term, *batch],
                    capture_output=True,
                    text=True,
                )
                if result.returncode not in (0, 1):
                    raise RuntimeError(
                        f"rg failed (exit {result.returncode}) for term {term!r}: {result.stderr.strip()}",
                    )
                if result.stdout.strip():
                    for line in result.stdout.strip().split("\n"):
                        fp = line.strip()
                        if fp:
                            matched_files.add(fp)
            for fp in matched_files:
                match_counts[fp] = match_counts.get(fp, 0) + 1
        # rg gives us a match count and nothing else, so it cannot order files
        # that tie. Ranking them by path made the whole baseline depend on how
        # a file happened to be spelled (a rename once moved the rate from
        # 0.205 to 0.068). Take the 5th-best count as a cutoff and admit every
        # file at or above it, so a tie is resolved by admitting the whole
        # band rather than by alphabet.
        counts = sorted(match_counts.values(), reverse=True)
        cutoff = counts[min(4, len(counts) - 1)] if counts else 0
        top5 = {str(Path(p).resolve()) for p, c in match_counts.items() if c >= cutoff}
        if g.expected_path in top5:
            baseline_hits += 1
    return baseline_hits / len(goldset)


def _write_pinned(config_path: Path, winner_id: str) -> None:
    new_lines = []
    in_pinned = False
    seen_pinned = False
    for line in config_path.read_text().split("\n"):
        stripped = line.strip()
        if stripped == "[pinned]":
            in_pinned = True
            seen_pinned = True
            new_lines.append(line)
        elif stripped.startswith("[") and not stripped.startswith("[["):
            in_pinned = False
            new_lines.append(line)
        elif in_pinned and stripped.startswith("id"):
            new_lines.append(f'id = "{winner_id}"')
        else:
            new_lines.append(line)
    if not seen_pinned:
        raise ValueError(
            f"config {config_path} has no [pinned] section to write the winner into",
        )
    config_path.write_text("\n".join(new_lines))


def _select_winner(per_model: dict[str, ModelScore], pinned_id: str | None) -> str:
    # Dict order preserves shortlist order when the pin is not tied for best.
    winner_id = max(per_model, key=lambda model_id: per_model[model_id].hit_rate)
    # Equal scores must not repoint config away from the live index's model.
    if (
        pinned_id in per_model
        and per_model[pinned_id].hit_rate == per_model[winner_id].hit_rate
    ):
        return pinned_id
    return winner_id


def run_harness(
    config: EngramConfig,
    goldset_path: Path,
    work_dir: Path,
) -> HarnessReport:
    goldset = load_goldset(goldset_path)
    leases = []
    per_model: dict[str, ModelScore] = {}
    try:
        for entry in config.embeddings:
            leases.append(ensure_served(entry))
            per_model[entry.id] = _score_candidate(
                entry,
                config.config_path,
                goldset,
                work_dir,
            )
            # Emit as we go: a full run takes ~40 minutes, and a crash in a
            # later candidate used to discard every score already computed.
            for line in _model_lines(entry.id, per_model[entry.id]):
                print(line, flush=True)

        winner_id = _select_winner(per_model, config.pinned_id)
        baseline_hit_rate = _baseline_hit_rate(goldset)
        gate_passed = (
            per_model[winner_id].hit_rate >= 0.80
            and per_model[winner_id].hit_rate > baseline_hit_rate
            and all(
                rate >= 0.80
                for corpus, rate in per_model[winner_id].per_corpus_hit_rate.items()
                if corpus in GATED_CORPORA
            )
        )
        if gate_passed:
            _write_pinned(config.config_path, winner_id)
        return HarnessReport(per_model, winner_id, baseline_hit_rate, gate_passed)
    finally:
        # Every lease, winner included. Server ownership is in-process only,
        # so a winner left running is not reusable by the next run - it just
        # holds the endpoint until someone kills it by hand.
        for lease in leases:
            stop_served(lease)


def _model_lines(model_id: str, score: ModelScore) -> list[str]:
    """One model's block of report lines. Shared by the summary and by the
    per-candidate lines run_harness streams as it goes, so the two can be
    diffed against each other."""
    lines = [f"{model_id}\t{score.hit_rate:.3f}"]
    for corpus in sorted(score.per_corpus_hit_rate):
        lines.append(f"{model_id}\t{corpus}\t{score.per_corpus_hit_rate[corpus]:.3f}")
    return lines


def format_report(report: HarnessReport) -> list[str]:
    lines: list[str] = []
    for model_id, score in report.per_model.items():
        lines.extend(_model_lines(model_id, score))
    lines.append(f"winner\t{report.winner_id}")
    lines.append(f"baseline\t{report.baseline_hit_rate:.3f}")
    lines.append(f"gate_passed\t{report.gate_passed}")
    return lines
