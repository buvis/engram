"""Incremental indexer: enumerate, diff, chunk, embed, upsert, prune."""

from dataclasses import dataclass

import engram.corpora as corpora
from engram.chunker import chunk_markdown
from engram.client import EmbeddingEntry, EngramConfig, embed
from engram.corpora import enumerate_corpora, hash_source
from engram.store import ChunkWithVector, Scope, Store


@dataclass(frozen=True)
class IndexReport:
    files_scanned: int
    chunks_added: int
    chunks_updated: int
    chunks_pruned: int
    corpora_missing: list[str]


def index(
    store: Store,
    config: EngramConfig,
    scope: Scope,
    corpus: str | None = None,
) -> IndexReport:
    # 1. Enumerate and filter
    files = list(enumerate_corpora())
    if scope.kind == "repo":
        files = [f for f in files if f.repo == scope.repo]
    if corpus is not None:
        files = [f for f in files if f.corpus == corpus]

    corpora_missing = list(corpora.missing_dirs)

    # 2. Diff against known sources
    known = store.known_sources(scope, corpus)

    chunks_added = 0
    all_chunks: list[ChunkWithVector] = []
    active_sources: set[tuple[str, str, str]] = set()

    for file in files:
        h = hash_source(file.path)
        key = (file.repo, str(file.path), h)
        active_sources.add(key)

        if key in known:
            continue

        chunks = chunk_markdown(file.path, file.corpus, file.repo, h)
        if not chunks:
            continue

        entry: EmbeddingEntry
        if config.pinned_id is not None:
            entry = next(e for e in config.embeddings if e.id == config.pinned_id)
        else:
            entry = config.embeddings[0]

        vectors = embed([c.body for c in chunks], entry)
        all_chunks.extend(
            ChunkWithVector(chunk=c, vector=v) for c, v in zip(chunks, vectors)
        )
        chunks_added += len(chunks)

    # 3. Upsert
    if all_chunks:
        store.upsert_chunks(all_chunks)

    # 4. Prune
    chunks_pruned = store.prune(scope, corpus, active_sources)

    return IndexReport(
        files_scanned=len(files),
        chunks_added=chunks_added,
        chunks_updated=0,
        chunks_pruned=chunks_pruned,
        corpora_missing=corpora_missing,
    )
