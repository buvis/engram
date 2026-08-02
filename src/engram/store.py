"""Chunk store: SQLite-backed FTS5 + sqlite-vec index over corpus chunks."""

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import sqlite_vec

from engram.client import Vector

DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "engram" / "engram.db"


@dataclass(frozen=True)
class Chunk:
    corpus: str
    repo: str
    doc_type: str
    path: str
    heading: str
    body: str
    line_start: int
    line_end: int
    content_hash: str
    chunk_ordinal: int


@dataclass(frozen=True)
class ChunkWithVector:
    chunk: Chunk
    vector: Vector


@dataclass(frozen=True)
class Scope:
    kind: Literal["repo", "portfolio"]
    repo: str | None

    def __post_init__(self) -> None:
        if self.kind == "repo" and self.repo is None:
            raise ValueError("Scope(kind='repo') requires repo to be set")


@dataclass(frozen=True)
class SearchHit:
    chunk_id: int
    score: float
    chunk: Chunk


@dataclass(frozen=True)
class CorpusStatus:
    row_count: int
    stale_files: list[str]
    dead_rows: int


@dataclass(frozen=True)
class StatusReport:
    per_corpus: dict[str, CorpusStatus]


class StoreModelMismatchError(RuntimeError):
    pass


def open_store(db_path: Path = DEFAULT_DB_PATH) -> "Store":
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    conn.execute(
        "CREATE TABLE IF NOT EXISTS chunks ("
        "id INTEGER PRIMARY KEY, corpus TEXT, repo TEXT, doc_type TEXT, path TEXT, "
        "heading TEXT, body TEXT, line_start INT, line_end INT, content_hash TEXT, "
        "chunk_ordinal INT, "
        "UNIQUE(repo, path, content_hash, chunk_ordinal))"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
        "heading, body, content='chunks', content_rowid='id')"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")

    return Store(conn)


class Store:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row is not None else None

    def _chunks_vec_exists(self) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chunks_vec'"
        ).fetchone()
        return row is not None

    def _scope_conditions(
        self, scope: Scope, corpus: str | None, alias: str
    ) -> tuple[str, list]:
        conditions = []
        params: list = []
        if scope.kind == "repo":
            conditions.append(f"{alias}.repo = ?")
            params.append(scope.repo)
        if corpus is not None:
            conditions.append(f"{alias}.corpus = ?")
            params.append(corpus)
        where = " AND ".join(conditions) if conditions else "1 = 1"
        return where, params

    def assert_configured_model(self, model_id: str) -> None:
        stored = self._get_meta("embedding_model_id")
        if stored is not None and stored != model_id:
            raise StoreModelMismatchError(
                f"configured embedding model {model_id!r} does not match "
                f"indexed model {stored!r}; run `engram index --rebuild`"
            )

    def _validate_vector(self, vector: Vector) -> None:
        stored_model_id = self._get_meta("embedding_model_id")
        if stored_model_id is None:
            return
        stored_dim = int(self._get_meta("embedding_dim"))
        if vector.model_id != stored_model_id or vector.dim != stored_dim:
            raise StoreModelMismatchError(
                f"vector model {vector.model_id!r}/{vector.dim} does not match "
                f"indexed model {stored_model_id!r}/{stored_dim}"
            )

    def _row_to_hit(self, row) -> SearchHit:
        (
            chunk_id,
            score,
            corpus,
            repo,
            doc_type,
            path,
            heading,
            body,
            line_start,
            line_end,
            content_hash,
            chunk_ordinal,
        ) = row
        chunk = Chunk(
            corpus=corpus,
            repo=repo,
            doc_type=doc_type,
            path=path,
            heading=heading,
            body=body,
            line_start=line_start,
            line_end=line_end,
            content_hash=content_hash,
            chunk_ordinal=chunk_ordinal,
        )
        return SearchHit(chunk_id=chunk_id, score=score, chunk=chunk)

    def _create_vec_schema(self, baseline_model_id: str, baseline_dim: int) -> None:
        conn = self.conn
        conn.execute(
            "CREATE VIRTUAL TABLE chunks_vec USING vec0("
            "chunk_id INTEGER PRIMARY KEY, "
            f"embedding FLOAT[{int(baseline_dim)}], "
            "repo TEXT PARTITION KEY, corpus TEXT PARTITION KEY)"
        )
        conn.execute(
            "CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN "
            "INSERT INTO chunks_fts(rowid, heading, body) "
            "VALUES (new.id, new.heading, new.body); "
            "END"
        )
        conn.execute(
            "CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN "
            "INSERT INTO chunks_fts(chunks_fts, rowid, heading, body) "
            "VALUES ('delete', old.id, old.heading, old.body); "
            "DELETE FROM chunks_vec WHERE chunk_id = old.id; "
            "END"
        )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('embedding_model_id', ?)",
            (baseline_model_id,),
        )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('embedding_dim', ?)",
            (str(baseline_dim),),
        )

    def _insert_chunk(self, item: ChunkWithVector) -> None:
        conn = self.conn
        chunk = item.chunk
        cursor = conn.execute(
            "INSERT INTO chunks (corpus, repo, doc_type, path, heading, body, "
            "line_start, line_end, content_hash, chunk_ordinal) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                chunk.corpus,
                chunk.repo,
                chunk.doc_type,
                chunk.path,
                chunk.heading,
                chunk.body,
                chunk.line_start,
                chunk.line_end,
                chunk.content_hash,
                chunk.chunk_ordinal,
            ),
        )
        chunk_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO chunks_vec (chunk_id, embedding, repo, corpus) "
            "VALUES (?, ?, ?, ?)",
            (
                chunk_id,
                sqlite_vec.serialize_float32(item.vector.values),
                chunk.repo,
                chunk.corpus,
            ),
        )

    def upsert_chunks(self, items: list[ChunkWithVector]) -> None:
        if not items:
            return

        conn = self.conn
        conn.execute("BEGIN")
        try:
            stored_model_id = self._get_meta("embedding_model_id")
            if stored_model_id is not None:
                baseline_model_id = stored_model_id
                baseline_dim = int(self._get_meta("embedding_dim"))
                first_write = False
            else:
                baseline_model_id = items[0].vector.model_id
                baseline_dim = items[0].vector.dim
                first_write = True

            for item in items:
                if (
                    item.vector.model_id != baseline_model_id
                    or item.vector.dim != baseline_dim
                ):
                    raise StoreModelMismatchError(
                        f"vector model {item.vector.model_id!r}/{item.vector.dim} "
                        f"does not match indexed model "
                        f"{baseline_model_id!r}/{baseline_dim}"
                    )

            if first_write:
                self._create_vec_schema(baseline_model_id, baseline_dim)

            for item in items:
                self._insert_chunk(item)
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()

    def known_sources(
        self, scope: Scope, corpus: str | None
    ) -> set[tuple[str, str, str]]:
        where, params = self._scope_conditions(scope, corpus, "chunks")
        rows = self.conn.execute(
            f"SELECT repo, path, content_hash FROM chunks WHERE {where}", params
        ).fetchall()
        return {(r[0], r[1], r[2]) for r in rows}

    def prune(
        self, scope: Scope, corpus: str | None, active_sources: set[tuple[str, str, str]]
    ) -> int:
        where, params = self._scope_conditions(scope, corpus, "chunks")
        rows = self.conn.execute(
            f"SELECT id, repo, path, content_hash FROM chunks WHERE {where}", params
        ).fetchall()
        to_delete = [
            row[0] for row in rows if (row[1], row[2], row[3]) not in active_sources
        ]
        if not to_delete:
            return 0

        placeholders = ",".join("?" * len(to_delete))
        self.conn.execute(
            f"DELETE FROM chunks WHERE id IN ({placeholders})", to_delete
        )
        return len(to_delete)

    def search_bm25(
        self, query: str, scope: Scope, corpus: str | None, k: int
    ) -> list[SearchHit]:
        where, params = self._scope_conditions(scope, corpus, "c")
        sql = (
            "SELECT c.id, bm25(chunks_fts) AS score, c.corpus, c.repo, c.doc_type, "
            "c.path, c.heading, c.body, c.line_start, c.line_end, c.content_hash, "
            "c.chunk_ordinal "
            "FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid "
            f"WHERE chunks_fts MATCH ? AND {where} "
            "ORDER BY score LIMIT ?"
        )
        tokens = query.split()
        if not tokens:
            return []
        match_query = " ".join('"' + token.replace('"', '""') + '"' for token in tokens)
        rows = self.conn.execute(sql, [match_query, *params, k]).fetchall()
        return [self._row_to_hit(row) for row in rows]

    def search_knn(
        self, vector: Vector, scope: Scope, corpus: str | None, k: int
    ) -> list[SearchHit]:
        self._validate_vector(vector)
        if not self._chunks_vec_exists():
            return []

        where, params = self._scope_conditions(scope, corpus, "cv")
        sql = (
            "SELECT c.id, cv.distance, c.corpus, c.repo, c.doc_type, c.path, "
            "c.heading, c.body, c.line_start, c.line_end, c.content_hash, "
            "c.chunk_ordinal "
            "FROM chunks_vec cv JOIN chunks c ON c.id = cv.chunk_id "
            f"WHERE cv.embedding MATCH ? AND cv.k = ? AND {where} "
            "ORDER BY cv.distance"
        )
        rows = self.conn.execute(
            sql, [sqlite_vec.serialize_float32(vector.values), k, *params]
        ).fetchall()
        return [self._row_to_hit(row) for row in rows]

    def status(self, scope: Scope) -> StatusReport:
        where, params = self._scope_conditions(scope, None, "chunks")
        corpora = [
            row[0]
            for row in self.conn.execute(
                f"SELECT DISTINCT corpus FROM chunks WHERE {where}", params
            ).fetchall()
        ]

        per_corpus = {}
        for corpus in corpora:
            rows = self.conn.execute(
                f"SELECT path, content_hash FROM chunks WHERE {where} AND corpus = ?",
                [*params, corpus],
            ).fetchall()
            stale: set[str] = set()
            dead = 0
            for path, content_hash in rows:
                file_path = Path(path)
                if not file_path.exists():
                    dead += 1
                    continue
                data = file_path.read_bytes()
                actual_hash = hashlib.sha1(
                    b"blob " + str(len(data)).encode() + b"\0" + data
                ).hexdigest()
                if actual_hash != content_hash:
                    stale.add(path)
            per_corpus[corpus] = CorpusStatus(
                row_count=len(rows), stale_files=sorted(stale), dead_rows=dead
            )

        return StatusReport(per_corpus=per_corpus)
