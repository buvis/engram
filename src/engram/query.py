"""Hybrid RRF retrieval over the chunk store."""

from dataclasses import dataclass

from engram.client import EngramConfig, Vector, embed, resolve_pinned_entry
from engram.store import Scope, SearchHit, Store

RRF_POOL = 20
RRF_K = 60


@dataclass(frozen=True)
class Pointer:
    rank: int
    score: float
    path: str
    line_start: int
    line_end: int
    heading: str
    corpus: str
    repo: str


def query(
    store: Store,
    config: EngramConfig,
    text: str,
    scope: Scope,
    corpus: str | None = None,
    k: int = 5,
) -> list[Pointer]:
    entry = resolve_pinned_entry(config)

    bm25_hits = store.search_bm25(text, scope, corpus, RRF_POOL)
    query_vector: Vector = embed([text], entry)[0]
    knn_hits = store.search_knn(query_vector, scope, corpus, RRF_POOL)

    # Build lookup: chunk_id -> SearchHit (prefer BM25 if present in both)
    hit_map: dict[int, SearchHit] = {}
    for hit in knn_hits:
        hit_map[hit.chunk_id] = hit
    for hit in bm25_hits:
        hit_map[hit.chunk_id] = hit

    # Reciprocal Rank Fusion
    fused: dict[int, float] = {}
    for i, hit in enumerate(bm25_hits):
        fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + 1.0 / (RRF_K + i + 1)
    for i, hit in enumerate(knn_hits):
        fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + 1.0 / (RRF_K + i + 1)

    sorted_ids = sorted(fused, key=lambda cid: fused[cid], reverse=True)[:k]

    return [
        Pointer(
            rank=i + 1,
            score=fused[cid],
            path=hit_map[cid].chunk.path,
            line_start=hit_map[cid].chunk.line_start,
            line_end=hit_map[cid].chunk.line_end,
            heading=hit_map[cid].chunk.heading,
            corpus=hit_map[cid].chunk.corpus,
            repo=hit_map[cid].chunk.repo,
        )
        for i, cid in enumerate(sorted_ids)
    ]
