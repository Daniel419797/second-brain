"""Per-repository memory for architecture, commands, env names, and fixes."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import workspace_brain
from core.config import DATA_DIR, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "project_memory.sqlite3"
REFERENCE_IMAGE_DIR = DATA_DIR / "project_reference_images"
MAX_REFERENCE_IMAGE_BYTES = 12 * 1024 * 1024
VALID_REFERENCE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
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
            CREATE TABLE IF NOT EXISTS project_profiles (
                root_hash TEXT PRIMARY KEY,
                root TEXT NOT NULL,
                name TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                architecture_json TEXT NOT NULL,
                commands_json TEXT NOT NULL,
                env_names_json TEXT NOT NULL,
                deploy_steps_json TEXT NOT NULL,
                common_bugs_json TEXT NOT NULL,
                preferred_style_json TEXT NOT NULL,
                past_fixes_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root_hash TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_notes_root ON project_notes(root_hash, kind, timestamp)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_reference_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root_hash TEXT NOT NULL,
                root TEXT NOT NULL,
                project_name TEXT NOT NULL,
                title TEXT NOT NULL,
                note TEXT NOT NULL,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                content_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                width INTEGER NOT NULL DEFAULT 0,
                height INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_reference_images_root ON project_reference_images(root_hash, timestamp)")


def profile(root: str | Path = "", *, refresh: bool = False) -> dict[str, Any]:
    init_db()
    project_root = _safe_root(root)
    root_hash = _hash(project_root)
    if not refresh:
        existing = get_profile(project_root)
        if existing:
            return existing
    discovered = _discover(project_root)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO project_profiles(root_hash, root, name, updated_at, architecture_json, commands_json, env_names_json, deploy_steps_json, common_bugs_json, preferred_style_json, past_fixes_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(root_hash) DO UPDATE SET
                root=excluded.root,
                name=excluded.name,
                updated_at=excluded.updated_at,
                architecture_json=excluded.architecture_json,
                commands_json=excluded.commands_json,
                env_names_json=excluded.env_names_json,
                deploy_steps_json=excluded.deploy_steps_json,
                common_bugs_json=excluded.common_bugs_json,
                preferred_style_json=excluded.preferred_style_json,
                past_fixes_json=excluded.past_fixes_json,
                metadata_json=excluded.metadata_json
            """,
            (
                root_hash,
                str(project_root),
                project_root.name,
                _now(),
                _json_dumps(discovered["architecture"]),
                _json_dumps(discovered["commands"]),
                _json_dumps(discovered["env_names"]),
                _json_dumps(discovered["deploy_steps"]),
                _json_dumps(discovered["common_bugs"]),
                _json_dumps(discovered["preferred_style"]),
                _json_dumps(discovered["past_fixes"]),
                _json_dumps(discovered["metadata"]),
            ),
        )
        row = conn.execute("SELECT * FROM project_profiles WHERE root_hash=?", (root_hash,)).fetchone()
    return _attach_reference_images(_profile_row(row), project_root)


def get_profile(root: str | Path) -> dict[str, Any] | None:
    init_db()
    project_root = _safe_root(root)
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM project_profiles WHERE root_hash=?", (_hash(project_root),)).fetchone()
    if not row:
        return None
    return _attach_reference_images(_profile_row(row), project_root)


def remember(root: str | Path, kind: str, title: str, content: str, *, confidence: float = 0.75, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    project_root = _safe_root(root)
    _ensure_profile_shell(project_root)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO project_notes(timestamp, root_hash, kind, title, content, confidence, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), _hash(project_root), _clean(kind).lower()[:80] or "note", _clean(title)[:300], _clean(content)[:4000], _confidence(confidence), _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM project_notes WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _note_row(row)


def search(query: str, *, root: str | Path = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    project_root = _safe_root(root) if root else None
    where: list[str] = []
    params: list[Any] = []
    if project_root:
        where.append("root_hash=?")
        params.append(_hash(project_root))
    if query:
        like = f"%{_clean(query)}%"
        where.append("(kind LIKE ? OR title LIKE ? OR content LIKE ?)")
        params.extend([like, like, like])
    params.append(max(1, min(200, int(limit or 20))))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM project_notes {clause} ORDER BY confidence DESC, id DESC LIMIT ?", params).fetchall()
    return [_note_row(row) for row in rows]


def add_reference_image(
    root: str | Path = "",
    *,
    title: str = "",
    note: str = "",
    filename: str = "",
    content: bytes = b"",
    content_type: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    project_root = _safe_root(root)
    if not content:
        raise ValueError("Reference image is empty.")
    if len(content) > MAX_REFERENCE_IMAGE_BYTES:
        raise ValueError(f"Reference image is too large. Max size is {MAX_REFERENCE_IMAGE_BYTES // (1024 * 1024)}MB.")
    suffix = _reference_suffix(filename, content_type)
    safe_title = _clean(title)[:300] or _clean(Path(filename or "reference").stem)[:300] or "Reference image"
    safe_note = _clean(note)[:2000]
    profile(project_root)
    root_hash = _hash(project_root)
    timestamp = _now()
    stamp = dt.datetime.now(dt.timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S_%f")
    stored_filename = f"{stamp}_{_slug(safe_title) or 'reference'}{suffix}"
    image_dir = REFERENCE_IMAGE_DIR / root_hash
    image_dir.mkdir(parents=True, exist_ok=True)
    path = image_dir / stored_filename
    path.write_bytes(content)
    width, height = _image_dimensions(path)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO project_reference_images(
                timestamp, root_hash, root, project_name, title, note, filename, path,
                content_type, size_bytes, width, height, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                root_hash,
                str(project_root),
                project_root.name,
                safe_title,
                safe_note,
                stored_filename,
                str(path),
                _clean(content_type)[:120],
                len(content),
                width,
                height,
                _json_dumps(metadata or {}),
            ),
        )
        row = conn.execute("SELECT * FROM project_reference_images WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _reference_image_row(row)


def list_reference_images(root: str | Path = "", *, limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    params: list[Any] = []
    where = ""
    if root:
        project_root = _safe_root(root)
        where = "WHERE root_hash=?"
        params.append(_hash(project_root))
    params.append(max(1, min(200, int(limit or 50))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM project_reference_images {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_reference_image_row(row) for row in rows]


def reference_image_path(root_hash: str, filename: str) -> Path:
    safe_hash = _clean(root_hash).lower()
    if not re.fullmatch(r"[a-f0-9]{24}", safe_hash):
        raise ValueError("Invalid project reference image root.")
    safe_name = Path(str(filename or "")).name
    if not safe_name or safe_name != str(filename or ""):
        raise ValueError("Invalid project reference image filename.")
    base = (REFERENCE_IMAGE_DIR / safe_hash).resolve()
    path = (base / safe_name).resolve()
    if path.parent != base:
        raise ValueError("Invalid project reference image path.")
    return path


def status(limit: int = 8) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        profiles = conn.execute("SELECT * FROM project_profiles ORDER BY updated_at DESC LIMIT ?", (max(1, min(50, int(limit or 8))),)).fetchall()
        note_count = conn.execute("SELECT COUNT(*) FROM project_notes").fetchone()[0]
        reference_image_count = conn.execute("SELECT COUNT(*) FROM project_reference_images").fetchone()[0]
    rows = [_profile_row(row) for row in profiles]
    return {
        "projects": rows,
        "note_count": int(note_count or 0),
        "reference_image_count": int(reference_image_count or 0),
        "summary": f"{len(rows)} project profile(s), {int(note_count or 0)} project memory note(s), {int(reference_image_count or 0)} reference image(s).",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM project_notes")
        conn.execute("DELETE FROM project_profiles")


def _discover(root: Path) -> dict[str, Any]:
    package = _read_json(root / "package.json")
    pyproject = _read_text(root / "pyproject.toml")
    readme = _read_text(root / "README.md")
    env_names = _env_names(root)
    scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
    commands = [f"npm run {name}" for name in scripts.keys()]
    if (root / "pytest.ini").exists() or (root / "tests").exists():
        commands.append("python -m pytest")
    if pyproject and "pytest" in pyproject:
        commands.append("python -m pytest")
    architecture = _safe(lambda: workspace_brain.analyze_project(str(root)), {})
    deploy_steps = [cmd for cmd in commands if any(term in cmd.lower() for term in ("deploy", "build", "start"))]
    return {
        "architecture": architecture or {"summary": _first_heading(readme) or f"{root.name} project"},
        "commands": sorted(set(commands)),
        "env_names": env_names,
        "deploy_steps": deploy_steps,
        "common_bugs": [],
        "preferred_style": {"readability": True, "security": True, "performance": True, "maintainability": True},
        "past_fixes": [],
        "metadata": {"has_package_json": bool(package), "has_pyproject": bool(pyproject), "has_tests": (root / "tests").exists()},
    }


def _ensure_profile_shell(project_root: Path) -> None:
    if get_profile(project_root):
        return
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO project_profiles(
                root_hash, root, name, updated_at, architecture_json, commands_json, env_names_json,
                deploy_steps_json, common_bugs_json, preferred_style_json, past_fixes_json, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _hash(project_root),
                str(project_root),
                project_root.name,
                _now(),
                _json_dumps({"summary": f"{project_root.name} project", "reference_image_ready": True}),
                _json_dumps([]),
                _json_dumps([]),
                _json_dumps([]),
                _json_dumps([]),
                _json_dumps({"readability": True, "security": True, "visual_reference_images": True}),
                _json_dumps([]),
                _json_dumps({"created_from_reference_image": True}),
            ),
        )


def _env_names(root: Path) -> list[str]:
    names: set[str] = set()
    for filename in (".env.example", ".env.sample", "README.md"):
        text = _read_text(root / filename)
        for match in re.finditer(r"(?m)^\s*([A-Z][A-Z0-9_]{2,})\s*=", text):
            names.add(match.group(1))
        for match in re.finditer(r"\b([A-Z][A-Z0-9_]{2,})\b", text):
            if any(term in match.group(1) for term in ("KEY", "TOKEN", "SECRET", "URL", "PASSWORD")):
                names.add(match.group(1))
    env_file = root / ".env"
    if env_file.exists():
        for line in _read_text(env_file).splitlines():
            match = re.match(r"\s*([A-Z][A-Z0-9_]{2,})\s*=", line)
            if match:
                names.add(match.group(1))
    return sorted(names)[:80]


def _profile_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "root_hash": str(row["root_hash"]),
        "root": str(row["root"]),
        "name": str(row["name"]),
        "updated_at": str(row["updated_at"]),
        "architecture": _json_loads(row["architecture_json"], {}),
        "commands": _json_loads(row["commands_json"], []),
        "env_names": _json_loads(row["env_names_json"], []),
        "deploy_steps": _json_loads(row["deploy_steps_json"], []),
        "common_bugs": _json_loads(row["common_bugs_json"], []),
        "preferred_style": _json_loads(row["preferred_style_json"], {}),
        "past_fixes": _json_loads(row["past_fixes_json"], []),
        "metadata": _json_loads(row["metadata_json"], {}),
        "summary": f"{row['name']}: {len(_json_loads(row['commands_json'], []))} command(s), {len(_json_loads(row['env_names_json'], []))} env name(s).",
    }


def _note_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root_hash": str(row["root_hash"]),
        "kind": str(row["kind"]),
        "title": str(row["title"]),
        "content": str(row["content"]),
        "confidence": float(row["confidence"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _reference_image_row(row: sqlite3.Row) -> dict[str, Any]:
    root_hash = str(row["root_hash"])
    filename = str(row["filename"])
    url = f"/project-memory/reference-images/{root_hash}/{filename}"
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root_hash": root_hash,
        "root": str(row["root"]),
        "project_name": str(row["project_name"]),
        "title": str(row["title"]),
        "note": str(row["note"]),
        "filename": filename,
        "content_type": str(row["content_type"]),
        "size_bytes": int(row["size_bytes"] or 0),
        "width": int(row["width"] or 0),
        "height": int(row["height"] or 0),
        "metadata": _json_loads(row["metadata_json"], {}),
        "url": url,
        "image_url": url,
        "summary": f"{row['title']} reference for {row['project_name']}",
    }


def _attach_reference_images(profile_data: dict[str, Any], project_root: Path, *, limit: int = 12) -> dict[str, Any]:
    references = list_reference_images(project_root, limit=limit)
    profile_data["reference_images"] = references
    if references:
        profile_data["summary"] = f"{profile_data.get('summary', project_root.name)} {len(references)} reference image(s) attached."
    return profile_data


def _safe_root(value: str | Path) -> Path:
    try:
        return resolve_coding_root(value)
    except Exception:
        return resolve_coding_root()


def _hash(root: Path) -> str:
    return hashlib.sha256(str(root.resolve()).lower().encode("utf-8")).hexdigest()[:24]


def _reference_suffix(filename: str, content_type: str = "") -> str:
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix in VALID_REFERENCE_SUFFIXES:
        return ".jpg" if suffix == ".jpeg" else suffix
    lowered = _clean(content_type).lower()
    by_type = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if lowered in by_type:
        return by_type[lowered]
    raise ValueError("Unsupported reference image type. Use PNG, JPG, WebP, or GIF.")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", _clean(value).lower()).strip("_")
    return slug[:80]


def _image_dimensions(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return int(image.width or 0), int(image.height or 0)
    except Exception:
        return 0, 0


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.strip().startswith("#"):
            return line.strip("# ").strip()
    return ""


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.6


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
