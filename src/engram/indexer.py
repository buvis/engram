"""Incremental indexer: enumerate, diff, chunk, embed, upsert, prune."""

from dataclasses import dataclass, field

import engram.corpora as corpora
from engram import symbols, transcripts
from engram.chunker import chunk_markdown
from engram.client import EmbeddingEntry, EngramConfig, embed, resolve_pinned_entry
from engram.corpora import CorpusFile, enumerate_corpora, hash_source
from engram.store import Chunk, ChunkWithVector, Scope, Store


@dataclass(frozen=True)
class IndexReport:
    files_scanned: int
    chunks_added: int
    chunks_pruned: int
    corpora_missing: list[str]
    files_skipped: int = 0
    failed_sources: list[str] = field(default_factory=list)


def index(
    store: Store,
    config: EngramConfig,
    scope: Scope,
    corpus: str | None = None,
) -> IndexReport:
    # 1. Enumerate and filter
    files = list(enumerate_corpora())
    # Cellar is only required when the requested scope can include transcripts.
    if _needs_transcripts(scope, corpus):
        files += list(transcripts.enumerate())
    if corpus in (None, "code"):
        files += list(symbols.enumerate(exclude_globs=config.exclude_globs))
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
    # Only legacy anonymous headings need re-chunking when the source hash is
    # unchanged. Replace per source so interrupted migrations are safe to retry.
    legacy_code = store.legacy_code_sources(scope) if corpus in (None, "code") else set()
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
    failed_sources: list[str] = []

    for file in files:
        try:
            h = hash_source(file.path)
        except OSError:
            failed_sources.append(str(file.path))
            continue
        key = (file.repo, str(file.path), h)
        empty_key = (file.corpus, *key)

        migrate = file.corpus == "code" and str(file.path) in legacy_code
        if key in known and not migrate:
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
            failed_sources.append(str(file.path))
            continue
        if not chunks:
            if migrate:
                store.replace_chunks_for_source("code", str(file.path), [])
            store.mark_empty_source(*empty_key)
            active_empty.add(empty_key)
            continue

        texts = [c.text_for_embedding for c in chunks]
        vectors = embed(texts, entry)
        all_chunks = [
            ChunkWithVector(chunk=c, vector=v) for c, v in zip(chunks, vectors)
        ]
        if migrate:
            store.replace_chunks_for_source("code", str(file.path), all_chunks)
        else:
            store.upsert_chunks(all_chunks)
        active_sources.add(key)
        chunks_added += len(chunks)

    # A source that failed to read, hash, or parse keeps its previously indexed
    # rows (any hash) rather than being pruned as if it had vanished.
    failed = set(failed_sources)
    active_sources |= {key for key in known if key[1] in failed}
    active_empty |= {key for key in known_empty if key[2] in failed}

    # 3. Prune (only reached here if the loop completed without exception)
    chunks_pruned = store.prune(scope, corpus, active_sources)
    store.prune_empty_sources(scope, corpus, active_empty)

    return IndexReport(
        files_scanned=len(files),
        chunks_added=chunks_added,
        chunks_pruned=chunks_pruned,
        corpora_missing=corpora_missing,
        files_skipped=dispatch_skipped + (len(symbols.skipped_files) - skipped_before),
        failed_sources=failed_sources,
    )


def _needs_transcripts(scope: Scope, corpus: str | None) -> bool:
    if corpus is not None and corpus != "transcripts":
        return False
    return scope.kind == "portfolio" or scope.repo == "cellar"


def _chunk_file(file: CorpusFile, content_hash: str) -> list[Chunk]:
    if file.corpus == "transcripts":
        return transcripts.chunk(file.path, file.repo, content_hash)
    if file.corpus == "code":
        return symbols.chunk(file.path, file.repo, content_hash)
    return chunk_markdown(file.path, file.corpus, file.repo, content_hash)


@dataclass(frozen=True)
class BackfillReport:
    sources_rechunked: int
    chunks_embedded: int
    vectors_reused: int
    empty_cleared: int
    failed_sources: list[str]


def backfill_code(store: Store, config: EngramConfig, scope: Scope) -> BackfillReport:
    """Rechunk unchanged code sources whose stored chunks differ from the chunker's.

    Only sources indexed (or marked empty) under their current hash are touched;
    new and changed sources are left to index(). A stored vector is reused when
    its chunk's embedding text is unchanged, so only new chunks are embedded.
    """
    entry = resolve_pinned_entry(config)
    store.assert_configured_model(entry.id)

    files = list(symbols.enumerate(exclude_globs=config.exclude_globs))
    if scope.kind == "repo":
        files = [f for f in files if f.repo == scope.repo]
    known = store.known_sources(scope, "code")
    known_empty = store.known_empty_sources_by_corpus(scope, "code")

    rechunked = embedded = reused = cleared = 0
    failed_sources: list[str] = []
    for file in files:
        path = str(file.path)
        try:
            h = hash_source(file.path)
        except OSError:
            failed_sources.append(path)
            continue
        key = (file.repo, path, h)
        was_empty = ("code", *key) in known_empty
        if not was_empty and key not in known:
            continue
        try:
            chunks = symbols.chunk(file.path, file.repo, h)
        except Exception:
            # Existing rows and empty marks stay; the source is retried next run.
            failed_sources.append(path)
            continue
        counts = _rechunk_source(store, entry, key, chunks, was_empty=was_empty)
        if counts is None:
            continue
        rechunked += 1
        embedded += counts[0]
        reused += counts[1]
        cleared += int(was_empty)
    return BackfillReport(
        sources_rechunked=rechunked,
        chunks_embedded=embedded,
        vectors_reused=reused,
        empty_cleared=cleared,
        failed_sources=failed_sources,
    )


def _rechunk_source(
    store: Store,
    entry: EmbeddingEntry,
    source: tuple[str, str, str],
    chunks: list[Chunk],
    *,
    was_empty: bool,
) -> tuple[int, int] | None:
    """Store a (repo, path, hash) code source's chunks, reusing unchanged vectors.

    Returns (embedded, reused) counts, or None when the stored chunks already match.
    """
    repo, path, h = source
    stored = [] if was_empty else store.code_chunks_with_vectors(path)
    if [item.chunk for item in stored] == chunks:
        return None
    if not chunks:
        store.replace_chunks_for_source("code", path, [])
        store.mark_empty_source("code", repo, path, h)
        return 0, 0

    vectors = {item.chunk.text_for_embedding: item.vector for item in stored}
    missing = [c.text_for_embedding for c in chunks if c.text_for_embedding not in vectors]
    if missing:
        vectors = {**vectors, **dict(zip(missing, embed(missing, entry), strict=True))}
    items = [ChunkWithVector(chunk=c, vector=vectors[c.text_for_embedding]) for c in chunks]
    store.replace_chunks_for_source("code", path, items)
    if was_empty:
        store.unmark_empty_source("code", repo, path)
    return len(missing), len(chunks) - len(missing)


def reembed_code(store: Store, config: EngramConfig, batch_size: int = 64) -> int:
    """Regenerate the vector of every indexed code chunk from its current embedding text.

    Targeted migration for embedding-text changes (e.g. path enrichment): chunk rows
    and content hashes are kept, only vectors are replaced, one source at a time, so
    an interrupted run is safe to repeat. Returns the number of chunks re-embedded.
    """
    entry = resolve_pinned_entry(config)
    store.assert_configured_model(entry.id)

    by_path: dict[str, list[Chunk]] = {}
    for c in store.chunks_for_corpus("code"):
        by_path.setdefault(c.path, []).append(c)

    done = 0
    pending: list[tuple[str, list[Chunk]]] = []
    pending_count = 0

    def flush() -> None:
        nonlocal done, pending, pending_count
        if not pending:
            return
        texts = [c.text_for_embedding for _, cs in pending for c in cs]
        vectors = iter(embed(texts, entry))
        for path, cs in pending:
            items = [ChunkWithVector(chunk=c, vector=next(vectors)) for c in cs]
            store.replace_chunks_for_source("code", path, items)
            done += len(cs)
        pending, pending_count = [], 0

    for path, cs in by_path.items():
        pending.append((path, cs))
        pending_count += len(cs)
        if pending_count >= batch_size:
            flush()
    flush()
    return done
