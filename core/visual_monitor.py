"""Continuous screen/camera visual monitor with low-CPU change detection."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Generator

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

try:
    from PIL import Image, ImageGrab
except Exception:  # pragma: no cover - Pillow is provided by PyAutoGUI in normal installs
    Image = None
    ImageGrab = None

DB_PATH = DATA_DIR / "visual_monitor.sqlite3"
FRAME_ROOT = DATA_DIR / "visual_frames"

_LOCK = threading.Lock()
_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_STATE: dict[str, Any] = {"running": False, "source": "", "started_at": "", "last_error": "", "realtime": False}
_LATEST_FRAME_BYTES: dict[str, bytes] = {}
_LATEST_FRAME_META: dict[str, Any] = {}


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
            CREATE TABLE IF NOT EXISTS visual_monitor_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                frame_path TEXT NOT NULL,
                signature TEXT NOT NULL,
                change_score REAL NOT NULL,
                details_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_visual_events_source_time ON visual_monitor_events(source, timestamp)")


def start_monitor(source: str = "screen", *, realtime: bool = False) -> dict[str, Any]:
    """Start a daemon visual monitor for screen, camera, or both."""
    global _THREAD
    normalized = _normalize_source(source)
    with _LOCK:
        running = bool(_THREAD and _THREAD.is_alive())
        current_source = str(_STATE.get("source") or "")
        current_realtime = bool(_STATE.get("realtime", False))
    if running:
        if current_source == normalized and current_realtime == bool(realtime):
            return status()
        stop_monitor()
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return status()
        _STOP.clear()
        _STATE.update({"running": True, "source": normalized, "started_at": _now(), "last_error": "", "realtime": bool(realtime)})
        _THREAD = threading.Thread(target=_monitor_loop, args=(normalized, bool(realtime)), name="FridayVisualMonitor", daemon=True)
        _THREAD.start()
    return status()


def stop_monitor(timeout: float = 2.0) -> dict[str, Any]:
    _STOP.set()
    thread = _THREAD
    if thread and thread.is_alive():
        thread.join(timeout=timeout)
    with _LOCK:
        _STATE["running"] = bool(_THREAD and _THREAD.is_alive())
    return status()


def status() -> dict[str, Any]:
    init_db()
    with _LOCK:
        running = bool(_THREAD and _THREAD.is_alive())
        _STATE["running"] = running
        payload = dict(_STATE)
    payload["latest_event"] = latest_event()
    payload["event_count"] = _event_count()
    payload["interval_seconds"] = float(config_value("visual_monitor_interval_seconds", 2.0))
    payload["realtime_fps"] = float(config_value("visual_monitor_realtime_fps", 4.0))
    payload["latest_frames"] = latest_frames()
    return payload


def capture_once(source: str = "screen", *, analyze: bool | None = None) -> list[dict[str, Any]]:
    normalized = _normalize_source(source)
    events: list[dict[str, Any]] = []
    for item in _source_items(normalized):
        events.append(_capture_and_record(item, analyze=analyze))
    return events


def recent_events(limit: int = 20, *, source: str = "") -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if source:
            rows = conn.execute(
                "SELECT * FROM visual_monitor_events WHERE source=? ORDER BY id DESC LIMIT ?",
                (source, max(1, min(200, int(limit)))),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM visual_monitor_events ORDER BY id DESC LIMIT ?",
                (max(1, min(200, int(limit))),),
            ).fetchall()
        return [_event_from_row(row) for row in rows]


def latest_event(source: str = "") -> dict[str, Any] | None:
    events = recent_events(1, source=source)
    return events[0] if events else None


def planner_context(limit: int = 6) -> dict[str, Any]:
    events = recent_events(limit)
    return {
        "running": bool(_THREAD and _THREAD.is_alive()),
        "source": str(_STATE.get("source") or ""),
        "realtime": bool(_STATE.get("realtime", False)),
        "latest_frames": latest_frames(),
        "recent_events": [
            {
                "timestamp": event["timestamp"],
                "source": event["source"],
                "event_type": event["event_type"],
                "summary": event["summary"][:300],
                "change_score": event["change_score"],
            }
            for event in events
        ],
    }


def frame_root() -> Path:
    return FRAME_ROOT


def live_frame(source: str = "screen") -> tuple[bytes, str]:
    normalized = _normalize_live_source(source)
    existing = _LATEST_FRAME_BYTES.get(normalized)
    meta = _LATEST_FRAME_META.get(normalized) or {}
    if existing and time.time() - float(meta.get("captured_monotonic") or 0.0) <= 2.0:
        return existing, str(meta.get("content_type") or "image/jpeg")
    data, content_type = _capture_frame_bytes(normalized)
    _remember_latest_frame(normalized, data, content_type)
    return data, content_type


def latest_frames() -> dict[str, Any]:
    with _LOCK:
        return {source: {key: value for key, value in meta.items() if key != "captured_monotonic"} for source, meta in _LATEST_FRAME_META.items()}


def mjpeg_stream(source: str = "screen") -> Generator[bytes, None, None]:
    normalized = _normalize_live_source(source)
    interval = 1.0 / max(0.5, min(30.0, float(config_value("visual_monitor_realtime_fps", 4.0))))
    while True:
        try:
            data, content_type = live_frame(normalized)
            yield (
                b"--frame\r\n"
                + f"Content-Type: {content_type}\r\nCache-Control: no-cache\r\n\r\n".encode("ascii")
                + data
                + b"\r\n"
            )
        except GeneratorExit:
            return
        except Exception as exc:
            _STATE["last_error"] = str(exc)
            time.sleep(interval)
            continue
        time.sleep(interval)


def _monitor_loop(source: str, realtime: bool) -> None:
    _record_event(source, "started", "Realtime visual monitor started." if realtime else "Visual monitor started.", "", "", 0.0, {"realtime": realtime})
    try:
        while not _STOP.is_set():
            for item in _source_items(source):
                if _STOP.is_set():
                    break
                try:
                    _capture_and_record(item)
                except Exception as exc:
                    _STATE["last_error"] = str(exc)
                    _record_event(item, "error", f"Visual monitor error: {exc}", "", "", 0.0, {"error": str(exc)})
            _STOP.wait(_monitor_interval(realtime))
    finally:
        _STATE["running"] = False
        _record_event(source, "stopped", "Visual monitor stopped.", "", "", 0.0, {})


def _capture_and_record(source: str, *, analyze: bool | None = None) -> dict[str, Any]:
    path, message = _capture_frame(source)
    if not path:
        return _record_event(source, "error", message, "", "", 0.0, {"message": message})
    _remember_latest_frame_from_path(source, path)
    signature = _frame_signature(path)
    previous = _latest_signature(source)
    change_score = _signature_change(previous, signature)
    threshold = float(config_value("visual_monitor_change_threshold", 0.08))
    changed = not previous or change_score >= threshold
    event_type = "change" if changed else "frame"
    summary = message
    do_analyze = bool(config_value("visual_monitor_analysis_enabled", False)) if analyze is None else bool(analyze)
    if changed and do_analyze and _analysis_due(source):
        summary = _analyze_frame(path, source)
        event_type = "summary"
    elif changed:
        summary = f"{source.title()} changed; score={change_score:.2f}."
    return _record_event(
        source,
        event_type,
        summary,
        str(path),
        signature,
        change_score,
        {"changed": changed, "capture_message": message},
    )


def _capture_frame(source: str) -> tuple[Path | None, str]:
    if source == "screen":
        return _capture_screen()
    if source == "camera":
        return _capture_camera()
    return None, f"Unknown visual source: {source}"


def _capture_screen() -> tuple[Path | None, str]:
    if str(config_value("visual_monitor_screen_capture_backend", "imagegrab")).lower() != "pc_control":
        image = _grab_screen_image()
        if image is not None:
            target = _new_frame_path("screen", ".jpg")
            image.convert("RGB").save(str(target), format="JPEG", quality=82)
            return target, "Screen frame captured."
    from tools import pc_control

    target = _new_frame_path("screen", ".png")
    result = pc_control.execute({"action": "screenshot", "target": str(target)})
    prefix = "Screenshot saved to "
    if not str(result).startswith(prefix):
        return None, str(result)
    return target, "Screen frame captured."


def _capture_camera() -> tuple[Path | None, str]:
    try:
        import cv2  # type: ignore
    except Exception:
        return None, "Camera monitoring requires optional opencv-python. Install it only if you want live camera frames."
    index = int(config_value("visual_monitor_camera_index", 0))
    capture = cv2.VideoCapture(index)
    try:
        if not capture.isOpened():
            return None, f"Camera {index} is unavailable."
        ok, frame = capture.read()
        if not ok or frame is None:
            return None, f"Camera {index} did not return a frame."
        target = _new_frame_path("camera", ".jpg")
        cv2.imwrite(str(target), frame)
        return target, "Camera frame captured."
    finally:
        capture.release()


def _capture_frame_bytes(source: str) -> tuple[bytes, str]:
    if source == "screen":
        image = _grab_screen_image()
        if image is not None:
            buffer = BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=78)
            return buffer.getvalue(), "image/jpeg"
        path, message = _capture_screen()
        if not path:
            raise RuntimeError(message)
        return path.read_bytes(), _content_type(path)
    if source == "camera":
        try:
            import cv2  # type: ignore
        except Exception as exc:
            raise RuntimeError("Camera streaming requires optional opencv-python.") from exc
        index = int(config_value("visual_monitor_camera_index", 0))
        capture = cv2.VideoCapture(index)
        try:
            if not capture.isOpened():
                raise RuntimeError(f"Camera {index} is unavailable.")
            ok, frame = capture.read()
            if not ok or frame is None:
                raise RuntimeError(f"Camera {index} did not return a frame.")
            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                raise RuntimeError("Camera frame encoding failed.")
            return encoded.tobytes(), "image/jpeg"
        finally:
            capture.release()
    raise RuntimeError(f"Unknown live visual source: {source}")


def _grab_screen_image() -> Any:
    if ImageGrab is None:
        return None
    try:
        return ImageGrab.grab(all_screens=True)
    except Exception:
        return None


def _analyze_frame(path: Path, source: str) -> str:
    try:
        from core import desktop_vision

        instruction = f"Describe the important visual change in this {source} frame. Be concise."
        return desktop_vision.analyze_screenshot(path, instruction=instruction)
    except Exception as exc:
        return f"{source.title()} changed, but analysis failed: {exc}"


def _analysis_due(source: str) -> bool:
    last = _latest_event_type(source, "summary")
    if not last:
        return True
    try:
        previous = dt.datetime.fromisoformat(last["timestamp"])
    except Exception:
        return True
    gap = dt.datetime.now(dt.timezone.utc).astimezone() - previous
    return gap.total_seconds() >= float(config_value("visual_monitor_analysis_interval_seconds", 20.0))


def _record_event(
    source: str,
    event_type: str,
    summary: str,
    frame_path: str,
    signature: str,
    change_score: float,
    details: dict[str, Any],
) -> dict[str, Any]:
    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO visual_monitor_events (
                timestamp, source, event_type, summary, frame_path, signature, change_score, details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                source,
                event_type,
                _clean(summary),
                frame_path,
                signature,
                float(change_score),
                json.dumps(details, ensure_ascii=True, sort_keys=True),
            ),
        )
        event_id = int(cursor.lastrowid)
    return latest_event_by_id(event_id) or {
        "id": event_id,
        "timestamp": now,
        "source": source,
        "event_type": event_type,
        "summary": _clean(summary),
        "frame_path": frame_path,
        "signature": signature,
        "change_score": float(change_score),
        "details": details,
    }


def latest_event_by_id(event_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM visual_monitor_events WHERE id=?", (int(event_id),)).fetchone()
        return _event_from_row(row) if row else None


def _latest_signature(source: str) -> str:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT signature FROM visual_monitor_events WHERE source=? AND signature<>'' ORDER BY id DESC LIMIT 1",
            (source,),
        ).fetchone()
        return str(row[0]) if row else ""


def _latest_event_type(source: str, event_type: str) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM visual_monitor_events WHERE source=? AND event_type=? ORDER BY id DESC LIMIT 1",
            (source, event_type),
        ).fetchone()
        return _event_from_row(row) if row else None


def _event_count() -> int:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT COUNT(*) FROM visual_monitor_events").fetchone()
        return int(row[0]) if row else 0


def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": row["timestamp"],
        "source": row["source"],
        "event_type": row["event_type"],
        "summary": row["summary"],
        "frame_path": row["frame_path"],
        "frame_name": Path(row["frame_path"]).name if row["frame_path"] else "",
        "signature": row["signature"],
        "change_score": float(row["change_score"]),
        "details": _json_loads(row["details_json"]),
    }


def _new_frame_path(source: str, suffix: str) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    root = FRAME_ROOT / source
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{source}_{stamp}{suffix}"


def _remember_latest_frame_from_path(source: str, path: Path) -> None:
    try:
        _remember_latest_frame(source, path.read_bytes(), _content_type(path), frame_name=path.name)
    except OSError:
        return


def _remember_latest_frame(source: str, data: bytes, content_type: str, *, frame_name: str = "") -> None:
    with _LOCK:
        _LATEST_FRAME_BYTES[source] = data
        _LATEST_FRAME_META[source] = {
            "timestamp": _now(),
            "content_type": content_type,
            "bytes": len(data),
            "frame_name": frame_name,
            "captured_monotonic": time.time(),
        }


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    return "application/octet-stream"


def _frame_signature(path: Path) -> str:
    if Image is None:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        with Image.open(path) as image:
            small = image.convert("L").resize((8, 8))
            pixels = list(small.getdata())
    except Exception:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    average = sum(pixels) / max(1, len(pixels))
    return "".join("1" if pixel >= average else "0" for pixel in pixels)


def _signature_change(previous: str, current: str) -> float:
    if not previous or not current:
        return 1.0
    if len(previous) != len(current):
        return 1.0
    diff = sum(1 for left, right in zip(previous, current) if left != right)
    return diff / max(1, len(current))


def _source_items(source: str) -> list[str]:
    if source == "both":
        return ["screen", "camera"]
    return [source]


def _normalize_source(source: str) -> str:
    lowered = str(source or "screen").strip().lower()
    if lowered in {"screen", "camera", "both"}:
        return lowered
    return "screen"


def _normalize_live_source(source: str) -> str:
    normalized = _normalize_source(source)
    return "screen" if normalized == "both" else normalized


def _monitor_interval(realtime: bool) -> float:
    if realtime:
        return 1.0 / max(0.5, min(30.0, float(config_value("visual_monitor_realtime_fps", 4.0))))
    return max(0.5, min(30.0, float(config_value("visual_monitor_interval_seconds", 2.0))))


def _json_loads(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
