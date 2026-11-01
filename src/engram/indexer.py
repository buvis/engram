"""Incremental indexer: enumerate, diff, chunk, embed, upsert, prune."""

from dataclasses import dataclass

import engram.corpora as corpora
from engram import symbols, transcripts
from engram.chunker import chunk_markdown
from engram.client import EngramConfig, embed, resolve_pinned_entry
from engram.corpora import CorpusFile, enumerate_corpora, hash_source
from engram.store import Chunk, ChunkWithVector, Scope, Store


@dataclass(frozen=True)
class IndexReport:
    files_scanned: int
    chunks_added: int
    chunks_pruned: int
    corpora_missing: list[str]
    files_skipped: int = 0


def index(
    store: Store,
    config: EngramConfig,
    scope: Scope,
    corpus: str | None = None,
) -> IndexReport:
    # 1. Enumerate and filter
    files = list(enumerate_corpora()) + list(transcripts.enumerate()) + list(symbols.enumerate())
    if scope.kind == "repo":
        files = [f for f in files if f.repo == scope.repo]
    if corpus is not None:
        files = [f for f in files if f.corpus == corpus]

    corpora_missing = list(corpora.missing_dirs)

    entry = resolve_pinned_entry(config)

    store.assert_configured_model(entry.id)

    # 2. Diff, chunk, embed, and upsert per-file (commit as we go)
    known = store.known_sources(scope, corpus)
    known_empty = store.known_empty_sources_by_corpus(scope, corpus)
    chunks_added = 0

    # Repos whose `code:` enumeration failed this run enumerated no files;
    # carry their already-known code chunks forward so prune() doesn't treat
    # them as vanished. Scoped to the code corpus specifically so a code
    # enumeration failure doesn't also exempt the repo's other corpora.
    failed_code_repos = {
        name.split(":", 1)[1] for name in corpora_missing if name.startswith("code:")
    }
    known_code = store.known_sources(scope, "code")
    active_sources: set[tuple[str, str, str]] = {
        key for key in known_code if key[0] in failed_code_repos
    }
    active_empty: set[tuple[str, str, str, str]] = {
        key for key in known_empty if key[0] == "code" and key[1] in failed_code_repos
    }

    skipped_before = len(symbols.skipped_files)
    dispatch_skipped = 0

    for file in files:
        h = hash_source(file.path)
        key = (file.repo, str(file.path), h)
        empty_key = (file.corpus, *key)

        if key in known:
            active_sources.add(key)
            continue
        if empty_key in known_empty:
            active_empty.add(empty_key)
            continue

        try:
            chunks = _chunk_file(file, h)
        except Exception:
            # Not recorded as empty: a chunker failure is retried next run.
            dispatch_skipped += 1
            continue
        if not chunks:
            store.mark_empty_source(*empty_key)
            active_empty.add(empty_key)
            continue

        texts = [c.text_for_embedding for c in chunks]
        vectors = embed(texts, entry)
        all_chunks = [ChunkWithVector(chunk=c, vector=v) for c, v in zip(chunks, vectors)]
        store.upsert_chunks(all_chunks)
        active_sources.add(key)
        chunks_added += len(chunks)

    # 3. Prune (only reached here if the loop completed without exception)
    chunks_pruned = store.prune(scope, corpus, active_sources)
    store.prune_empty_sources(scope, corpus, active_empty)

    return IndexReport(
        files_scanned=len(files),
        chunks_added=chunks_added,
        chunks_pruned=chunks_pruned,
        corpora_missing=corpora_missing,
        files_skipped=dispatch_skipped + (len(symbols.skipped_files) - skipped_before),
    )


def _chunk_file(file: CorpusFile, content_hash: str) -> list[Chunk]:
    if file.corpus == "transcripts":
        return transcripts.chunk(file.path, file.repo, content_hash)
    if file.corpus == "code":
        return symbols.chunk(file.path, file.repo, content_hash)
    return chunk_markdown(file.path, file.corpus, file.repo, content_hash)
