"""Local file intelligence for common user folders, PDFs, and image metadata."""

from __future__ import annotations

import datetime as dt
import json
import mimetypes
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ROOT_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "local_file_intelligence.sqlite3"
_LOCK = threading.Lock()

TEXT_EXTENSIONS = {".txt", ".md", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".csv", ".yml", ".yaml", ".html", ".css", ".ini", ".toml", ".ps1", ".bat", ".sh", ".sql"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".next", "dist", "build", "AppData"}


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
            CREATE TABLE IF NOT EXISTS local_files (
                path TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                parent TEXT NOT NULL,
                extension TEXT NOT NULL,
                mime TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                kind TEXT NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_local_files_name ON local_files(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_local_files_kind ON local_files(kind, updated_at)")


def index_locations(paths: list[str] | None = None, *, max_files: int | None = None) -> dict[str, Any]:
    init_db()
    roots = [_safe_path(path) for path in (paths or _default_roots())]
    roots = [path for path in roots if path.exists()]
    max_count = int(max_files or config_value("local_file_intelligence_max_files", 2500))
    indexed = 0
    skipped = 0
    kinds: dict[str, int] = {}
    for root in roots:
        for path in _iter_files(root):
            if indexed >= max_count:
                break
            try:
                item = _file_item(path)
            except Exception:
                skipped += 1
                continue
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                conn.execute(
                    """
                    INSERT INTO local_files(path, name, parent, extension, mime, size, mtime, kind, summary, metadata_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        name=excluded.name,
                        parent=excluded.parent,
                        extension=excluded.extension,
                        mime=excluded.mime,
                        size=excluded.size,
                        mtime=excluded.mtime,
                        kind=excluded.kind,
                        summary=excluded.summary,
                        metadata_json=excluded.metadata_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        item["path"],
                        item["name"],
                        item["parent"],
                        item["extension"],
                        item["mime"],
                        item["size"],
                        item["mtime"],
                        item["kind"],
                        item["summary"],
                        _json_dumps(item["metadata"]),
                        item["updated_at"],
                    ),
                )
            indexed += 1
            kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
        if indexed >= max_count:
            break
    return {"roots": [str(path) for path in roots], "indexed": indexed, "skipped": skipped, "kinds": kinds, "summary": f"Indexed {indexed} local file(s)."}


def search(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    if _count() == 0:
        index_locations(max_files=500)
    terms = [term for term in re.split(r"\s+", str(query or "").lower()) if term][:8]
    if not terms:
        return []
    where = []
    params: list[Any] = []
    for term in terms:
        needle = f"%{term}%"
        where.append("(lower(path) LIKE ? OR lower(name) LIKE ? OR lower(parent) LIKE ? OR lower(summary) LIKE ?)")
        params.extend([needle, needle, needle, needle])
    params.append(max(1, min(100, int(limit or 20))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM local_files WHERE {' AND '.join(where)} ORDER BY mtime DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def summarize_folder(path: str | Path) -> dict[str, Any]:
    root = _safe_path(path)
    if not root.exists() or not root.is_dir():
        return {"ok": False, "summary": f"Folder not found: {root}", "path": str(root)}
    index_locations([str(root)], max_files=int(config_value("local_file_intelligence_folder_max_files", 800)))
    prefix = str(root).lower()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM local_files WHERE lower(path) LIKE ? ORDER BY mtime DESC LIMIT 100", (prefix + "%",)).fetchall()
    files = [_row(row) for row in rows]
    kinds: dict[str, int] = {}
    for item in files:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    return {
        "ok": True,
        "path": str(root),
        "file_count_sample": len(files),
        "kinds": kinds,
        "recent": files[:12],
        "summary": f"{root.name} contains {len(files)} indexed file(s) in the recent sample.",
    }


def answer(query: str) -> dict[str, Any]:
    results = search(query, limit=12)
    if not results:
        return {"answer": "I did not find matching local files yet. Try indexing the folder first.", "results": []}
    top = results[0]
    return {
        "answer": f"Best match: {top['name']} in {top['parent']}. {top['summary']}",
        "results": results,
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM local_files")


def _file_item(path: Path) -> dict[str, Any]:
    stat = path.stat()
    suffix = path.suffix.lower()
    mime = mimetypes.guess_type(str(path))[0] or ""
    kind = "other"
    metadata: dict[str, Any] = {}
    summary = ""
    if suffix in TEXT_EXTENSIONS:
        kind = "text"
        summary = _text_summary(path)
    elif suffix in PDF_EXTENSIONS:
        kind = "pdf"
        summary = _pdf_summary(path)
    elif suffix in IMAGE_EXTENSIONS:
        kind = "image"
        metadata = _image_metadata(path)
        summary = _image_summary(path, metadata)
    else:
        summary = f"{path.name} ({round(stat.st_size / 1024, 1)} KB)."
    return {
        "path": str(path),
        "name": path.name,
        "parent": str(path.parent),
        "extension": suffix,
        "mime": mime,
        "size": int(stat.st_size),
        "mtime": float(stat.st_mtime),
        "kind": kind,
        "summary": summary[:1000],
        "metadata": metadata,
        "updated_at": _now(),
    }


def _text_summary(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[: int(config_value("local_file_intelligence_text_chars", 3000))]
    except Exception:
        return f"Text file: {path.name}."
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines[:4])[:800] or f"Text file: {path.name}."


def _pdf_summary(path: Path) -> str:
    try:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(str(path))
        text = " ".join((page.extract_text() or "") for page in reader.pages[:3])
        return " ".join(text.split())[:800] or f"PDF with {len(reader.pages)} page(s)."
    except Exception:
        try:
            import PyPDF2  # type: ignore

            reader = PyPDF2.PdfReader(str(path))
            text = " ".join((page.extract_text() or "") for page in reader.pages[:3])
            return " ".join(text.split())[:800] or f"PDF with {len(reader.pages)} page(s)."
        except Exception:
            return f"PDF file: {path.name}."


def _image_metadata(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as image:
            return {"width": image.width, "height": image.height, "mode": image.mode, "format": image.format}
    except Exception:
        return {}


def _image_summary(path: Path, metadata: dict[str, Any]) -> str:
    if metadata.get("width") and metadata.get("height"):
        return f"Image {path.name}, {metadata['width']}x{metadata['height']}."
    return f"Image file: {path.name}."


def _iter_files(root: Path):
    max_size = int(config_value("local_file_intelligence_max_file_bytes", 8_000_000))
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = {part for part in path.relative_to(root).parts[:-1]}
        if parts & SKIP_DIRS:
            continue
        try:
            if path.stat().st_size > max_size:
                continue
        except OSError:
            continue
        suffix = path.suffix.lower()
        if suffix in TEXT_EXTENSIONS | PDF_EXTENSIONS | IMAGE_EXTENSIONS:
            yield path


def _default_roots() -> list[str]:
    raw = str(config_value("local_file_intelligence_roots", "Desktop,Documents,Downloads"))
    home = Path.home()
    roots = []
    for item in raw.split(","):
        text = item.strip()
        if not text:
            continue
        path = Path(text).expanduser()
        if not path.is_absolute():
            path = home / text
        roots.append(str(path))
    roots.append(str(ROOT_DIR))
    return list(dict.fromkeys(roots))


def _safe_path(path: str | Path) -> Path:
    raw = str(path or "").strip()
    return Path(raw).expanduser().resolve() if raw else ROOT_DIR.resolve()


def _count() -> int:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        row = conn.execute("SELECT COUNT(*) FROM local_files").fetchone()
    return int(row[0]) if row else 0


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "path": str(row["path"]),
        "name": str(row["name"]),
        "parent": str(row["parent"]),
        "extension": str(row["extension"]),
        "mime": str(row["mime"]),
        "size": int(row["size"]),
        "mtime": float(row["mtime"]),
        "kind": str(row["kind"]),
        "summary": str(row["summary"]),
        "metadata": _json_loads(row["metadata_json"]),
        "updated_at": str(row["updated_at"]),
    }


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str) -> Any:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
