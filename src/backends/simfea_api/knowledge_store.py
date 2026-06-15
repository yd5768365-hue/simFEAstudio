import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from ..simfea_api.logger import create_logger
except ImportError:
    from simfea_api.logger import create_logger

log = create_logger("knowledge_store")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    original_path TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
"""


def _db_path(db_dir: str | Path | None = None) -> Path:
    if db_dir:
        root = Path(db_dir)
    else:
        from .config import PROJECT_ROOT
        root = PROJECT_ROOT / ".simfea" / "knowledge"
    root.mkdir(parents=True, exist_ok=True)
    return root / "knowledge.db"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_conn(db_dir: str | Path | None = None) -> sqlite3.Connection:
    db_path = _db_path(db_dir)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn


def insert_document(
    name: str,
    chunks: list[str],
    embeddings: list[list[float]],
    original_path: str = "",
    db_dir: str | Path | None = None,
) -> str:
    """Insert a document and its chunks into the knowledge store.

    Returns the new doc_id.
    """
    conn = _get_conn(db_dir)
    doc_id = uuid.uuid4().hex[:12]

    try:
        conn.execute(
            "INSERT INTO documents (id, name, original_path, created_at) VALUES (?, ?, ?, ?)",
            (doc_id, name, original_path, _now_utc()),
        )
        for i, (text, embedding) in enumerate(zip(chunks, embeddings)):
            conn.execute(
                "INSERT INTO chunks (doc_id, chunk_index, text, embedding_json) VALUES (?, ?, ?, ?)",
                (doc_id, i, text, json.dumps(embedding, ensure_ascii=False)),
            )
        conn.commit()
        log.info(f"Inserted document '{name}' ({doc_id}) with {len(chunks)} chunks")
    finally:
        conn.close()

    return doc_id


def list_documents(db_dir: str | Path | None = None) -> list[dict]:
    """Return all documents with chunk counts."""
    conn = _get_conn(db_dir)
    try:
        rows = conn.execute(
            """
            SELECT d.id, d.name, d.original_path, d.created_at, COUNT(c.id) AS chunk_count
            FROM documents d
            LEFT JOIN chunks c ON c.doc_id = d.id
            GROUP BY d.id
            ORDER BY d.created_at DESC
            """
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "id": row[0],
            "name": row[1],
            "original_path": row[2],
            "created_at": row[3],
            "chunk_count": row[4],
        }
        for row in rows
    ]


def delete_document(doc_id: str, db_dir: str | Path | None = None) -> bool:
    """Delete a document and its chunks. Returns True if deleted."""
    conn = _get_conn(db_dir)
    try:
        cursor = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        if deleted:
            log.info(f"Deleted document {doc_id}")
    finally:
        conn.close()
    return deleted


def get_all_chunks_with_embeddings(
    db_dir: str | Path | None = None,
    doc_ids: list[str] | None = None,
) -> list[dict]:
    """Return all chunks with their parsed embeddings and document names.

    If *doc_ids* is provided, only return chunks from those documents.
    Used for brute-force cosine similarity search.
    """
    conn = _get_conn(db_dir)
    try:
        if doc_ids:
            placeholders = ",".join("?" for _ in doc_ids)
            rows = conn.execute(
                f"""
                SELECT c.text, c.embedding_json, d.name AS doc_name
                FROM chunks c
                JOIN documents d ON d.id = c.doc_id
                WHERE d.id IN ({placeholders})
                """,
                doc_ids,
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT c.text, c.embedding_json, d.name AS doc_name
                FROM chunks c
                JOIN documents d ON d.id = c.doc_id
                """
            ).fetchall()
    finally:
        conn.close()

    results: list[dict] = []
    for text, embedding_json, doc_name in rows:
        try:
            embedding = json.loads(embedding_json)
        except (json.JSONDecodeError, TypeError):
            continue
        results.append({
            "text": text,
            "embedding": embedding,
            "doc_name": doc_name,
        })
    return results
