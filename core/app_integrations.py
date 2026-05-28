"""Free-first app integrations for local office data and workspace indexing."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "app_integrations.sqlite3"
OFFICE_DIR = DATA_DIR / "office_docs"

APP_LINKS = {
    "calendar": "https://calendar.google.com/calendar/u/0/r",
    "chatgpt": "https://chatgpt.com/",
    "chrome": "https://www.google.com/chrome/",
    "docs": "https://docs.google.com/document/u/0/",
    "doc": "https://docs.google.com/document/u/0/",
    "sheets": "https://docs.google.com/spreadsheets/u/0/",
    "sheet": "https://docs.google.com/spreadsheets/u/0/",
    "whatsapp": "https://web.whatsapp.com/",
    "discord": "https://discord.com/app",
    "github": "https://github.com/",
    "gmail": "https://mail.google.com/",
    "figma": "https://www.figma.com/files/",
    "linear": "https://linear.app/",
    "notion": "https://www.notion.so/",
    "postman": "https://web.postman.co/",
    "slack": "https://app.slack.com/client",
    "spotify": "https://open.spotify.com/",
    "vscode": "vscode://",
    "zoom": "https://app.zoom.us/wc",
}

DEFAULT_INDEX_EXTENSIONS = (
    ".py,.js,.jsx,.ts,.tsx,.json,.md,.txt,.css,.html,.yml,.yaml,.toml,.ini,"
    ".csv,.sql,.ps1,.bat,.sh,.env.example"
)
DEFAULT_SKIP_DIRS = ".git,.venv,node_modules,__pycache__,.next,dist,build,data/chroma_db,tools/whisper.cpp"


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
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(name)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                due_at TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                completed_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_status_due ON reminders(status, due_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS calendar_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                start_at TEXT NOT NULL DEFAULT '',
                end_at TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_calendar_start ON calendar_events(start_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS file_index (
                path TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                extension TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                summary TEXT NOT NULL,
                snippet TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_file_index_name ON file_index(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_file_index_extension ON file_index(extension)")


def app_link(name: str) -> str:
    return APP_LINKS.get(_clean_key(name), "")


def create_contact(name: str, *, email: str = "", phone: str = "", notes: str = "") -> dict[str, Any]:
    init_db()
    cleaned_name = _clean(name)
    if not cleaned_name:
        raise ValueError("Contact name is required.")
    now = _now()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO contacts(name, email, phone, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (cleaned_name, _clean(email), _clean(phone), _clean(notes), now, now),
        )
        contact_id = int(cursor.lastrowid)
    return get_contact(contact_id) or {"id": contact_id, "name": cleaned_name}


def search_contacts(query: str = "", *, limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    needle = f"%{_clean(query)}%"
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if query:
            rows = conn.execute(
                """
                SELECT * FROM contacts
                WHERE name LIKE ? OR email LIKE ? OR phone LIKE ? OR notes LIKE ?
                ORDER BY updated_at DESC, id DESC LIMIT ?
                """,
                (needle, needle, needle, needle, _bounded_limit(limit)),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM contacts ORDER BY updated_at DESC, id DESC LIMIT ?", (_bounded_limit(limit),)).fetchall()
    return [_row(row) for row in rows]


def get_contact(contact_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM contacts WHERE id=?", (int(contact_id),)).fetchone()
        return _row(row) if row else None


def create_reminder(title: str, *, due_at: str = "", notes: str = "") -> dict[str, Any]:
    init_db()
    cleaned_title = _clean(title)
    if not cleaned_title:
        raise ValueError("Reminder title is required.")
    now = _now()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO reminders(title, due_at, notes, status, created_at) VALUES (?, ?, ?, 'active', ?)",
            (cleaned_title, _normalize_when(due_at), _clean(notes), now),
        )
        reminder_id = int(cursor.lastrowid)
    return get_reminder(reminder_id) or {"id": reminder_id, "title": cleaned_title}


def list_reminders(*, include_done: bool = False, limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if include_done:
            rows = conn.execute("SELECT * FROM reminders ORDER BY status, due_at, id DESC LIMIT ?", (_bounded_limit(limit, 100),)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM reminders WHERE status='active' ORDER BY due_at='', due_at, id DESC LIMIT ?", (_bounded_limit(limit, 100),)).fetchall()
    return [_row(row) for row in rows]


def complete_reminder(reminder_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE reminders SET status='done', completed_at=? WHERE id=?", (_now(), int(reminder_id)))
    return get_reminder(reminder_id)


def get_reminder(reminder_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM reminders WHERE id=?", (int(reminder_id),)).fetchone()
        return _row(row) if row else None


def create_calendar_event(title: str, *, start_at: str = "", end_at: str = "", location: str = "", notes: str = "") -> dict[str, Any]:
    init_db()
    cleaned_title = _clean(title)
    if not cleaned_title:
        raise ValueError("Calendar event title is required.")
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO calendar_events(title, start_at, end_at, location, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (cleaned_title, _normalize_when(start_at), _normalize_when(end_at), _clean(location), _clean(notes), _now()),
        )
        event_id = int(cursor.lastrowid)
    return get_calendar_event(event_id) or {"id": event_id, "title": cleaned_title}


def list_calendar_events(*, limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM calendar_events ORDER BY start_at='', start_at, id DESC LIMIT ?", (_bounded_limit(limit, 100),)).fetchall()
    return [_row(row) for row in rows]


def get_calendar_event(event_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM calendar_events WHERE id=?", (int(event_id),)).fetchone()
        return _row(row) if row else None


def create_document(title: str, *, body: str = "") -> dict[str, Any]:
    root = _office_dir()
    path = _unique_path(root / f"{_slug(title or 'document')}.md")
    content = f"# {_clean(title) or 'Untitled'}\n\n{str(body or '').strip()}\n"
    path.write_text(content, encoding="utf-8")
    return {"path": str(path), "title": _clean(title) or path.stem, "kind": "document"}


def create_sheet(title: str, *, headers: list[str] | None = None) -> dict[str, Any]:
    root = _office_dir()
    path = _unique_path(root / f"{_slug(title or 'sheet')}.csv")
    columns = headers or ["Name", "Value", "Notes"]
    path.write_text(",".join(_csv_cell(item) for item in columns) + "\n", encoding="utf-8")
    return {"path": str(path), "title": _clean(title) or path.stem, "kind": "sheet"}


def index_workspace(root: str | Path = "", *, max_files: int | None = None) -> dict[str, Any]:
    init_db()
    root_path = _workspace_root(root)
    max_count = max_files or int(config_value("workspace_index_max_files", 2000))
    indexed = 0
    skipped = 0
    extensions: dict[str, int] = {}
    for path in _iter_workspace_files(root_path):
        if indexed >= max_count:
            break
        try:
            item = _file_index_item(path, root_path)
        except Exception:
            skipped += 1
            continue
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO file_index(path, name, extension, size, mtime, summary, snippet, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    name=excluded.name,
                    extension=excluded.extension,
                    size=excluded.size,
                    mtime=excluded.mtime,
                    summary=excluded.summary,
                    snippet=excluded.snippet,
                    updated_at=excluded.updated_at
                """,
                (
                    item["path"],
                    item["name"],
                    item["extension"],
                    item["size"],
                    item["mtime"],
                    item["summary"],
                    item["snippet"],
                    item["updated_at"],
                ),
            )
        indexed += 1
        extensions[item["extension"] or "(none)"] = extensions.get(item["extension"] or "(none)", 0) + 1
    return {"root": str(root_path), "indexed": indexed, "skipped": skipped, "extensions": extensions}


def search_workspace(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    if _file_index_count() == 0:
        index_workspace()
    terms = [term for term in re.split(r"\s+", _clean(query)) if term]
    if not terms:
        return []
    where = []
    params: list[Any] = []
    for term in terms[:6]:
        needle = f"%{term}%"
        where.append("(path LIKE ? OR name LIKE ? OR summary LIKE ? OR snippet LIKE ?)")
        params.extend([needle, needle, needle, needle])
    params.append(_bounded_limit(limit))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM file_index WHERE {' AND '.join(where)} ORDER BY mtime DESC LIMIT ?",
            params,
        ).fetchall()
    return [_row(row) for row in rows]


def workspace_overview(root: str | Path = "") -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        total = int(conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0])
        ext_rows = conn.execute(
            "SELECT extension, COUNT(*) AS count FROM file_index GROUP BY extension ORDER BY count DESC LIMIT 12"
        ).fetchall()
        recent = conn.execute("SELECT * FROM file_index ORDER BY mtime DESC LIMIT 8").fetchall()
    return {
        "root": str(_workspace_root(root)),
        "total_files": total,
        "extensions": {str(row["extension"] or "(none)"): int(row["count"]) for row in ext_rows},
        "recent_files": [_row(row) for row in recent],
    }


def _file_index_count() -> int:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT COUNT(*) FROM file_index").fetchone()
        return int(row[0]) if row else 0


def _iter_workspace_files(root: Path) -> list[Path]:
    allowed = {item.strip().lower() for item in str(config_value("workspace_index_extensions", DEFAULT_INDEX_EXTENSIONS)).split(",") if item.strip()}
    skip_parts = {item.strip().lower().replace("\\", "/") for item in str(config_value("workspace_index_skip_dirs", DEFAULT_SKIP_DIRS)).split(",") if item.strip()}
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        rel_parts = [part.lower() for part in rel.parts[:-1]]
        rel_text = "/".join(part.lower() for part in rel.parts)
        if any(part in skip_parts for part in rel_parts) or any(rel_text.startswith(skip + "/") for skip in skip_parts if "/" in skip):
            continue
        suffix = path.suffix.lower()
        if suffix not in allowed and path.name.lower() not in allowed:
            continue
        files.append(path)
    return sorted(files, key=lambda item: str(item).lower())


def _file_index_item(path: Path, root: Path) -> dict[str, Any]:
    stat = path.stat()
    text = path.read_text(encoding="utf-8", errors="ignore")[: int(config_value("workspace_index_snippet_chars", 4000))]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    summary = " ".join(lines[:3])[:500]
    rel = str(path.relative_to(root))
    return {
        "path": rel,
        "name": path.name,
        "extension": path.suffix.lower(),
        "size": int(stat.st_size),
        "mtime": float(stat.st_mtime),
        "summary": summary,
        "snippet": text[:1500],
        "updated_at": _now(),
    }


def _workspace_root(root: str | Path = "") -> Path:
    return resolve_coding_root(root)


def _office_dir() -> Path:
    configured = str(config_value("office_docs_dir", "") or "").strip()
    root = Path(configured).expanduser() if configured else OFFICE_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _unique_path(path: Path) -> Path:
    candidate = path
    index = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        index += 1
    return candidate


def _normalize_when(value: str) -> str:
    cleaned = _clean(value)
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    now = dt.datetime.now().astimezone()
    if lowered in {"today", "tonight"}:
        return now.replace(hour=20 if lowered == "tonight" else now.hour, minute=0, second=0, microsecond=0).isoformat(timespec="minutes")
    if lowered == "tomorrow":
        return (now + dt.timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat(timespec="minutes")
    try:
        return dt.datetime.fromisoformat(cleaned).astimezone().isoformat(timespec="minutes")
    except Exception:
        return cleaned


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug[:80] or "untitled"


def _csv_cell(value: Any) -> str:
    text = str(value or "")
    if any(char in text for char in [",", '"', "\n"]):
        text = '"' + text.replace('"', '""') + '"'
    return text


def _bounded_limit(limit: int, max_limit: int = 50) -> int:
    return max(1, min(max_limit, int(limit or 10)))


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _clean_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def to_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2)
