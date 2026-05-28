"""Private local search memory with optional embedding support."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib
import json
import math
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "private_embedding_memory.sqlite3"
_LOCK = threading.Lock()
_EMBEDDER: Any = None
_EMBEDDER_FAILED = False


def init_db(path: Path | None = None) -> None:
    ensure_runtime_dirs()
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS private_memory_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                text_hash TEXT NOT NULL,
                sensitive INTEGER NOT NULL DEFAULT 0,
                embedding_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_private_memory_source ON private_memory_chunks(source, title)")


def index_text(title: str, text: str, *, source: str = "manual", metadata: dict[str, Any] | None = None, sensitive: bool = False) -> dict[str, Any]:
    init_db()
    chunks = _chunks(text)
    now = _now()
    ids = []
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        for index, chunk in enumerate(chunks):
            embedding = _embedding(chunk)
            digest = hashlib.sha256(f"{source}:{title}:{index}:{chunk}".encode("utf-8")).hexdigest()
            cursor = conn.execute(
                """
                INSERT INTO private_memory_chunks(created_at, updated_at, source, title, chunk_index, text, text_hash, sensitive, embedding_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now, now, _clean(source)[:300], _clean(title)[:300], index, chunk, digest, 1 if sensitive else 0, _json_dumps(embedding), _json_dumps(metadata or {})),
            )
            ids.append(int(cursor.lastrowid))
    return {"ids": ids, "count": len(ids), "summary": f"Indexed {len(ids)} private memory chunk(s)."}


def index_file(path: str, *, sensitive: bool = False) -> dict[str, Any]:
    target = Path(path).expanduser()
    if not target.exists() or not target.is_file():
        return {"count": 0, "summary": "File not found.", "path": str(target)}
    max_bytes = int(config_value("private_embedding_max_file_bytes", 2_000_000))
    if target.stat().st_size > max_bytes:
        return {"count": 0, "summary": "File is too large for private memory indexing.", "path": str(target)}
    text = target.read_text(encoding="utf-8", errors="ignore")
    result = index_text(target.name, text, source=str(target), metadata={"path": str(target)}, sensitive=sensitive)
    return result | {"path": str(target)}


def search(query: str, *, limit: int = 10, include_sensitive: bool = False) -> list[dict[str, Any]]:
    init_db()
    q_embedding = _embedding(query)
    terms = _terms(query)
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM private_memory_chunks ORDER BY id DESC LIMIT 2000").fetchall()
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        item = _row(row)
        if item["sensitive"] and not include_sensitive:
            continue
        text_terms = _terms(item["text"])
        lexical = len(terms & text_terms) * 3.0 + (2.0 if str(query or "").lower() in item["text"].lower() else 0.0)
        vector = _cosine(q_embedding, item.get("embedding") or [])
        score = lexical + vector
        if score > 0:
            item["score"] = round(score, 4)
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], -int(pair[1]["id"])))
    return [item for _score, item in scored[: max(1, min(100, int(limit or 10)))]]


def summary() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        count = int(conn.execute("SELECT COUNT(*) FROM private_memory_chunks").fetchone()[0])
        sensitive = int(conn.execute("SELECT COUNT(*) FROM private_memory_chunks WHERE sensitive=1").fetchone()[0])
        sources = int(conn.execute("SELECT COUNT(DISTINCT source) FROM private_memory_chunks").fetchone()[0])
    return {
        "count": count,
        "sensitive_count": sensitive,
        "source_count": sources,
        "embedding_backend": "sentence-transformers" if _embedder_available() else "lexical-hash-local",
        "summary": f"{count} private memory chunk(s) from {sources} source(s).",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM private_memory_chunks")


def _chunks(text: str) -> list[str]:
    clean = "\n".join(line.strip() for line in str(text or "").splitlines() if line.strip())
    if not clean:
        return []
    size = max(300, int(config_value("private_embedding_chunk_chars", 1200)))
    return [clean[index : index + size].strip() for index in range(0, len(clean), size) if clean[index : index + size].strip()]


def _embedding(text: str) -> list[float]:
    embedder = _embedder()
    if embedder is not None:
        try:
            values = embedder.encode(text)
            return [float(value) for value in values.tolist()]
        except Exception:
            pass
    return _hash_embedding(text)


def _embedder() -> Any:
    global _EMBEDDER, _EMBEDDER_FAILED
    if not bool(config_value("private_embedding_use_sentence_transformers", False)):
        return None
    if _EMBEDDER is not None:
        return _EMBEDDER
    if _EMBEDDER_FAILED:
        return None
    try:
        sentence_transformers = importlib.import_module("sentence_transformers")
        _EMBEDDER = sentence_transformers.SentenceTransformer(str(config_value("memory_embedding_model", "all-MiniLM-L6-v2")))
        return _EMBEDDER
    except Exception:
        _EMBEDDER_FAILED = True
        return None


def _embedder_available() -> bool:
    return _embedder() is not None


def _hash_embedding(text: str, dims: int = 64) -> list[float]:
    vector = [0.0] * dims
    for term in _terms(text):
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        idx = digest[0] % dims
        sign = 1.0 if digest[1] % 2 == 0 else -1.0
        vector[idx] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "source": str(row["source"]),
        "title": str(row["title"]),
        "chunk_index": int(row["chunk_index"]),
        "text": str(row["text"]),
        "text_hash": str(row["text_hash"]),
        "sensitive": bool(row["sensitive"]),
        "embedding": _json_loads(row["embedding_json"], []),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _terms(text: str) -> set[str]:
    return {part for part in "".join(ch if ch.isalnum() else " " for ch in str(text or "").lower()).split() if len(part) > 1}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
