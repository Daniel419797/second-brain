"""Unified private lexical search across safe local Friday sources."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ROOT_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "semantic_search.sqlite3"
_LOCK = threading.Lock()
TEXT_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".txt", ".css", ".html", ".yml", ".yaml", ".toml", ".ini", ".csv", ".sql", ".ps1", ".bat", ".sh", ".env.example"}
SENSITIVE_NAMES = {".env", ".env.local", ".env.production", "secrets.json", "credentials.json"}
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".next", "dist", "build", "data/chroma_db", "tools/whisper.cpp"}
SECRET_LINE_RE = re.compile(r"(?i)\b(api[_-]?key|token|secret|password|credential|private[_-]?key)\b")


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
            CREATE TABLE IF NOT EXISTS semantic_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS semantic_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                text TEXT NOT NULL,
                kind TEXT NOT NULL,
                sensitivity TEXT NOT NULL,
                tags TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_chunks_kind ON semantic_chunks(kind, sensitivity)")


def index_path(path: str | Path = "", *, include_private: bool = False, limit: int = 500) -> dict[str, Any]:
    init_db()
    root = _safe_root(path)
    max_files = max(1, min(5000, int(limit or 500)))
    max_bytes = int(config_value("semantic_search_max_file_bytes", 800000))
    indexed = 0
    skipped_sensitive = 0
    errors: list[str] = []
    candidates = [root] if root.is_file() else _walk(root, max_files=max_files)
    for file_path in candidates:
        if indexed >= max_files:
            break
        if not file_path.is_file():
            continue
        if _is_sensitive_path(file_path) and not include_private:
            _index_env_names(file_path)
            skipped_sensitive += 1
            continue
        if file_path.suffix.lower() not in TEXT_EXTENSIONS and not _is_sensitive_path(file_path):
            continue
        try:
            if file_path.stat().st_size > max_bytes:
                continue
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            if not text.strip():
                continue
            sensitivity = "private" if _is_sensitive_path(file_path) or SECRET_LINE_RE.search(text) else "normal"
            safe_text = _redact_sensitive_text(text) if sensitivity != "normal" else text
            _store_source(str(file_path), "file", safe_text[: int(config_value("semantic_search_chunk_chars", 4000))], title=file_path.name, sensitivity=sensitivity, metadata={"path": str(file_path)})
            indexed += 1
        except Exception as exc:
            errors.append(f"{file_path}: {exc}")
    return {"root": str(root), "indexed": indexed, "skipped_sensitive": skipped_sensitive, "errors": errors[:10], "summary": f"Indexed {indexed} safe chunk(s)."}


def index_text(title: str, text: str, *, source: str = "manual", kind: str = "note", sensitive: bool = False, tags: str = "") -> dict[str, Any]:
    init_db()
    return _store_source(source, kind, _redact_sensitive_text(text) if sensitive else text, title=title, sensitivity="private" if sensitive else "normal", tags=tags)


def search(query: str, *, limit: int = 10, include_sensitive: bool = False) -> list[dict[str, Any]]:
    init_db()
    terms = _terms(query)
    if not terms:
        return []
    params: list[Any] = []
    where = ""
    if not include_sensitive:
        where = "WHERE sensitivity='normal'"
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT c.*, s.source, s.updated_at
            FROM semantic_chunks c JOIN semantic_sources s ON s.id=c.source_id
            {where}
            ORDER BY c.id DESC LIMIT 2000
            """,
            params,
        ).fetchall()
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        haystack = f"{row['title']} {row['text']} {row['tags']}".lower()
        score = sum(haystack.count(term) for term in terms)
        if score:
            item = _chunk_row(row)
            item["score"] = score
            item["snippet"] = _snippet(str(row["text"]), terms)
            scored.append((score, item))
    scored.sort(key=lambda item: (item[0], item[1]["id"]), reverse=True)
    return [item for _score, item in scored[: max(1, min(50, int(limit or 10)))]]


def status() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        sources = conn.execute("SELECT COUNT(*) FROM semantic_sources").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM semantic_chunks").fetchone()[0]
        private = conn.execute("SELECT COUNT(*) FROM semantic_chunks WHERE sensitivity!='normal'").fetchone()[0]
    return {"sources": int(sources), "chunks": int(chunks), "private_chunks": int(private), "summary": f"{chunks} searchable chunk(s) across {sources} source(s)."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM semantic_chunks")
        conn.execute("DELETE FROM semantic_sources")


def _store_source(source: str, kind: str, text: str, *, title: str, sensitivity: str = "normal", tags: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO semantic_sources(source, kind, updated_at, metadata_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET kind=excluded.kind, updated_at=excluded.updated_at, metadata_json=excluded.metadata_json
            """,
            (_clean(source), _clean(kind), now, _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT id FROM semantic_sources WHERE source=?", (_clean(source),)).fetchone()
        source_id = int(row["id"] if row else cursor.lastrowid)
        conn.execute("DELETE FROM semantic_chunks WHERE source_id=?", (source_id,))
        conn.execute(
            """
            INSERT INTO semantic_chunks(source_id, title, text, kind, sensitivity, tags, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (source_id, _clean(title)[:300], _clean(text)[:12000], _clean(kind), sensitivity, _clean(tags), _json_dumps(metadata or {})),
        )
    return {"source": source, "kind": kind, "title": title, "sensitivity": sensitivity}


def _walk(root: Path, max_files: int) -> list[Path]:
    results: list[Path] = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.is_file():
            results.append(path)
        if len(results) >= max_files:
            break
    return results


def _is_sensitive_path(path: Path) -> bool:
    return path.name.lower() in SENSITIVE_NAMES or path.name.lower().startswith(".env")


def _index_env_names(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    try:
        names = []
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = re.match(r"\s*([A-Z0-9_]{2,})\s*=", line)
            if match:
                names.append(match.group(1))
        if names:
            _store_source(str(path), "env_names", "Environment variables present: " + ", ".join(sorted(set(names))), title=path.name, sensitivity="private", metadata={"path": str(path), "values_indexed": False})
    except Exception:
        pass


def _redact_sensitive_text(text: str) -> str:
    lines = []
    for line in str(text or "").splitlines():
        if SECRET_LINE_RE.search(line) and "=" in line:
            key = line.split("=", 1)[0].strip()
            lines.append(f"{key}=[redacted]")
        else:
            lines.append(line)
    return "\n".join(lines)


def _terms(query: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9_]{2,}", str(query or "").lower()) if term not in {"the", "and", "for", "with"}]


def _snippet(text: str, terms: list[str]) -> str:
    lowered = text.lower()
    first = min((lowered.find(term) for term in terms if term in lowered), default=0)
    start = max(0, first - 100)
    return text[start : start + 500].replace("\n", " ").strip()


def _chunk_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "source_id": int(row["source_id"]),
        "source": str(row["source"]),
        "title": str(row["title"]),
        "kind": str(row["kind"]),
        "sensitivity": str(row["sensitivity"]),
        "tags": str(row["tags"]),
        "metadata": _json_loads(row["metadata_json"], {}),
        "updated_at": str(row["updated_at"]),
    }


def _safe_root(value: str | Path) -> Path:
    text = _clean(str(value or ""))
    if not text:
        return ROOT_DIR
    try:
        return Path(text).expanduser().resolve()
    except Exception:
        return ROOT_DIR


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return default
