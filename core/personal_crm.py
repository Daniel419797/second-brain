"""Personal CRM for people, promises, conversations, and follow-ups."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "personal_crm.sqlite3"
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
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                relationship TEXT NOT NULL,
                birthday TEXT NOT NULL,
                contact TEXT NOT NULL,
                notes TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                summary TEXT NOT NULL,
                sentiment TEXT NOT NULL,
                follow_up_at TEXT NOT NULL,
                promise TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_crm_interactions_person ON interactions(person_id, timestamp)")


def remember_person(name: str, *, relationship: str = "", birthday: str = "", contact: str = "", notes: str = "", tags: list[str] | None = None) -> dict[str, Any]:
    init_db()
    cleaned = _clean(name)
    if not cleaned:
        raise ValueError("name is required")
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO people(name, relationship, birthday, contact, notes, tags_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                relationship=excluded.relationship,
                birthday=COALESCE(NULLIF(excluded.birthday, ''), people.birthday),
                contact=COALESCE(NULLIF(excluded.contact, ''), people.contact),
                notes=TRIM(people.notes || char(10) || excluded.notes),
                tags_json=excluded.tags_json,
                updated_at=excluded.updated_at
            """,
            (cleaned, _clean(relationship), _clean(birthday), _clean(contact), _clean(notes), _json_dumps(sorted(set(tags or []))), now, now),
        )
        row = conn.execute("SELECT * FROM people WHERE name=?", (cleaned,)).fetchone()
    return _person_row(row)


def record_interaction(person_name: str, summary: str, *, sentiment: str = "", follow_up_at: str = "", promise: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    person = remember_person(person_name)
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO interactions(person_id, timestamp, summary, sentiment, follow_up_at, promise, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(person["id"]), _now(), _clean(summary), _clean(sentiment), _clean(follow_up_at), _clean(promise), _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM interactions WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _interaction_row(row)


def search_people(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    like = f"%{_clean(query)}%"
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        if _clean(query):
            rows = conn.execute(
                "SELECT * FROM people WHERE name LIKE ? OR relationship LIKE ? OR notes LIKE ? ORDER BY updated_at DESC LIMIT ?",
                (like, like, like, max(1, min(100, int(limit)))),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM people ORDER BY updated_at DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [_person_row(row) for row in rows]


def upcoming_followups(limit: int = 20, *, include_overdue: bool = True) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT interactions.*, people.name AS person_name
            FROM interactions JOIN people ON people.id=interactions.person_id
            WHERE follow_up_at != ''
            ORDER BY follow_up_at ASC LIMIT ?
            """,
            (max(1, min(200, int(limit) * 3)),),
        ).fetchall()
    items = [_with_followup_state(_interaction_row(row)) for row in rows]
    if not include_overdue:
        items = [item for item in items if item.get("follow_up_state") != "overdue"]
    items.sort(key=lambda item: (0 if item.get("follow_up_state") == "overdue" else 1, item.get("follow_up_at") or ""))
    return items[: max(1, min(100, int(limit)))]


def recent_interactions(person_name: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        if _clean(person_name):
            rows = conn.execute(
                """
                SELECT interactions.*, people.name AS person_name
                FROM interactions JOIN people ON people.id=interactions.person_id
                WHERE people.name LIKE ? ORDER BY interactions.id DESC LIMIT ?
                """,
                (f"%{_clean(person_name)}%", max(1, min(100, int(limit)))),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT interactions.*, people.name AS person_name
                FROM interactions JOIN people ON people.id=interactions.person_id
                ORDER BY interactions.id DESC LIMIT ?
                """,
                (max(1, min(100, int(limit))),),
            ).fetchall()
    return [_interaction_row(row) for row in rows]


def summary() -> dict[str, Any]:
    people = search_people(limit=5)
    followups = upcoming_followups(limit=5)
    overdue = [item for item in followups if item.get("follow_up_state") == "overdue"]
    return {
        "people_count": _count("people"),
        "interaction_count": _count("interactions"),
        "recent_people": people,
        "upcoming_followups": followups,
        "overdue_followups": overdue,
        "summary": f"CRM has {_count('people')} people, {len(overdue)} overdue follow-up(s), and {len(followups)} pending follow-up(s).",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM interactions")
        conn.execute("DELETE FROM people")


def _count(table: str) -> int:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _person_row(row: sqlite3.Row) -> dict[str, Any]:
    return {**{key: row[key] for key in row.keys() if key != "tags_json"}, "tags": _json_loads(row["tags_json"], [])}


def _interaction_row(row: sqlite3.Row) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys() if key != "metadata_json"}
    data["metadata"] = _json_loads(row["metadata_json"], {})
    return data


def _with_followup_state(item: dict[str, Any]) -> dict[str, Any]:
    due = _parse_time(item.get("follow_up_at"))
    if due is None:
        state = "undated"
    elif due < dt.datetime.now().astimezone():
        state = "overdue"
    else:
        state = "upcoming"
    return item | {"follow_up_state": state}


def _parse_time(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    except ValueError:
        return None


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
