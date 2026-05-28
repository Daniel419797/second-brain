"""Protected private vault for sensitive references and memories."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "privacy_vault.sqlite3"
_LOCK = threading.Lock()


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
            CREATE TABLE IF NOT EXISTS privacy_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                sensitivity TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_privacy_items_kind ON privacy_items(kind, sensitivity)")


def store_item(
    kind: str,
    title: str,
    content: str = "",
    *,
    sensitivity: str = "private",
    tags: list[str] | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    now = _now()
    clean_content = str(content or "")
    stored_content = clean_content if bool(config_value("privacy_vault_store_plaintext", False)) else ""
    content_hash = hashlib.sha256(clean_content.encode("utf-8")).hexdigest() if clean_content else ""
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO privacy_items(created_at, updated_at, kind, title, content, content_hash, sensitivity, tags_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                now,
                _clean(kind) or "private",
                _clean(title)[:300] or "Private item",
                stored_content,
                content_hash,
                _sensitivity(sensitivity),
                _json_dumps(_tags(tags)),
                _json_dumps(metadata or {}),
            ),
        )
        row = conn.execute("SELECT * FROM privacy_items WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row, reveal=False)


def list_items(kind: str = "", *, limit: int = 50, redacted: bool = True) -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if kind:
        where = "WHERE kind=?"
        params.append(_clean(kind))
    params.append(max(1, min(500, int(limit or 50))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM privacy_items {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_row(row, reveal=not redacted) for row in rows]


def get_item(item_id: int, *, reveal: bool = False) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM privacy_items WHERE id=?", (int(item_id),)).fetchone()
    return _row(row, reveal=reveal) if row else None


def search(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    terms = _terms(query)
    if not terms:
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in list_items(limit=500, redacted=True):
        haystack = " ".join([item.get("title", ""), item.get("kind", ""), " ".join(item.get("tags") or [])]).lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], -int(pair[1]["id"])))
    return [item for _score, item in scored[: max(1, min(100, int(limit or 20)))]]


def summary() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        counts = conn.execute("SELECT sensitivity, COUNT(*) FROM privacy_items GROUP BY sensitivity").fetchall()
        kinds = conn.execute("SELECT kind, COUNT(*) FROM privacy_items GROUP BY kind").fetchall()
    by_sensitivity = {str(key): int(count) for key, count in counts}
    by_kind = {str(key): int(count) for key, count in kinds}
    total = sum(by_sensitivity.values())
    return {
        "count": total,
        "by_sensitivity": by_sensitivity,
        "by_kind": by_kind,
        "plaintext_storage": bool(config_value("privacy_vault_store_plaintext", False)),
        "summary": f"{total} privacy vault item(s). Plaintext storage is {'enabled' if bool(config_value('privacy_vault_store_plaintext', False)) else 'disabled'} by default.",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM privacy_items")


def _row(row: sqlite3.Row, *, reveal: bool) -> dict[str, Any]:
    content = str(row["content"] or "")
    has_content = bool(content)
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "kind": str(row["kind"]),
        "title": str(row["title"]),
        "content": content if reveal else ("[stored]" if has_content else "[not stored; hash only]"),
        "has_plaintext": has_content,
        "content_hash": str(row["content_hash"]),
        "sensitivity": str(row["sensitivity"]),
        "tags": _json_loads(row["tags_json"], []),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _sensitivity(value: str) -> str:
    lowered = _clean(value).lower()
    return lowered if lowered in {"private", "sensitive", "secret"} else "private"


def _tags(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.split(",")
    else:
        raw = value
    return sorted({_clean(item).lower() for item in raw if _clean(item)})


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
