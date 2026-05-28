"""Learning Coach Mode with spaced repetition and quizzes."""

from __future__ import annotations

import datetime as dt
import difflib
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "learning_coach.sqlite3"
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
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                goal TEXT NOT NULL,
                level TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                prompt TEXT NOT NULL,
                answer TEXT NOT NULL,
                interval_days INTEGER NOT NULL,
                ease REAL NOT NULL,
                due_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                user_answer TEXT NOT NULL,
                correct INTEGER NOT NULL,
                notes TEXT NOT NULL
            )
            """
        )


def create_topic(name: str, *, goal: str = "", level: str = "beginner") -> dict[str, Any]:
    init_db()
    cleaned = _clean(name)
    if not cleaned:
        raise ValueError("topic name is required")
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO topics(name, goal, level, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET goal=excluded.goal, level=excluded.level, updated_at=excluded.updated_at
            """,
            (cleaned, _clean(goal), _clean(level) or "beginner", now, now),
        )
        row = conn.execute("SELECT * FROM topics WHERE name=?", (cleaned,)).fetchone()
    return _row(row)


def add_card(topic: str, prompt: str, answer: str) -> dict[str, Any]:
    prompt_clean = _clean(prompt)
    answer_clean = _clean(answer)
    if not prompt_clean:
        raise ValueError("prompt is required")
    if not answer_clean:
        raise ValueError("answer is required")
    topic_item = create_topic(topic)
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO cards(topic_id, prompt, answer, interval_days, ease, due_at, created_at, updated_at) VALUES (?, ?, ?, 1, 2.5, ?, ?, ?)",
            (int(topic_item["id"]), prompt_clean, answer_clean, now, now, now),
        )
        row = conn.execute("SELECT * FROM cards WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _card_row(row)


def due_cards(topic: str = "", limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    now = _now()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        if _clean(topic):
            rows = conn.execute(
                """
                SELECT cards.*, topics.name AS topic
                FROM cards JOIN topics ON topics.id=cards.topic_id
                WHERE cards.due_at <= ? AND topics.name LIKE ?
                ORDER BY cards.due_at ASC LIMIT ?
                """,
                (now, f"%{_clean(topic)}%", max(1, min(100, int(limit)))),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT cards.*, topics.name AS topic
                FROM cards JOIN topics ON topics.id=cards.topic_id
                WHERE cards.due_at <= ?
                ORDER BY cards.due_at ASC LIMIT ?
                """,
                (now, max(1, min(100, int(limit)))),
            ).fetchall()
    return [_card_row(row) for row in rows]


def quiz(topic: str = "", limit: int = 3) -> dict[str, Any]:
    cards = due_cards(topic=topic, limit=limit)
    return {"cards": cards, "summary": f"{len(cards)} review card(s) due." if cards else "No review cards due."}


def record_answer(card_id: int, user_answer: str, *, correct: bool | None = None, notes: str = "") -> dict[str, Any]:
    init_db()
    card = get_card(card_id)
    if not card:
        raise ValueError("card not found")
    grade = grade_answer(card_id, user_answer)
    if correct is None:
        correct = bool(grade["correct"])
    interval = int(card["interval_days"])
    ease = float(card["ease"])
    if correct:
        interval = max(1, int(round(interval * ease)))
        ease = min(3.0, ease + 0.12)
    else:
        interval = 1
        ease = max(1.3, ease - 0.25)
    due = (dt.datetime.now().astimezone() + dt.timedelta(days=interval)).isoformat(timespec="seconds")
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE cards SET interval_days=?, ease=?, due_at=?, updated_at=? WHERE id=?", (interval, ease, due, _now(), int(card_id)))
        conn.execute(
            "INSERT INTO attempts(card_id, timestamp, user_answer, correct, notes) VALUES (?, ?, ?, ?, ?)",
            (int(card_id), _now(), _clean(user_answer), 1 if correct else 0, _clean(notes)),
        )
        row = conn.execute("SELECT * FROM cards WHERE id=?", (int(card_id),)).fetchone()
    return _card_row(row) | {"grade": grade, "summary": f"Review saved. Next due in {interval} day(s)."}


def grade_answer(card_id: int, user_answer: str) -> dict[str, Any]:
    card = get_card(card_id)
    if not card:
        raise ValueError("card not found")
    expected_terms = _terms(str(card.get("answer") or ""))
    answer_terms = _terms(user_answer)
    overlap = len(expected_terms & answer_terms) / max(1, len(expected_terms))
    ratio = difflib.SequenceMatcher(a=_clean(user_answer).lower(), b=str(card.get("answer") or "").lower()).ratio()
    score = round(max(overlap, ratio), 3)
    return {
        "score": score,
        "correct": score >= 0.62 or (bool(expected_terms) and overlap >= 0.5),
        "expected_terms": sorted(expected_terms)[:12],
        "matched_terms": sorted(expected_terms & answer_terms)[:12],
    }


def get_card(card_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM cards WHERE id=?", (int(card_id),)).fetchone()
    return _card_row(row) if row else None


def progress() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        topic_count = int(conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0])
        card_count = int(conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0])
        attempt_count = int(conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0])
        correct = int(conn.execute("SELECT COUNT(*) FROM attempts WHERE correct=1").fetchone()[0])
    due = due_cards(limit=5)
    accuracy = round(correct / attempt_count, 3) if attempt_count else 0.0
    return {"topics": topic_count, "cards": card_count, "attempts": attempt_count, "accuracy": accuracy, "due": due, "summary": f"Learning coach: {card_count} cards, {len(due)} due, {accuracy:.0%} accuracy."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM attempts")
        conn.execute("DELETE FROM cards")
        conn.execute("DELETE FROM topics")


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _card_row(row: sqlite3.Row) -> dict[str, Any]:
    return _row(row)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _terms(value: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9_]+", str(value or "").lower()) if len(part) > 2}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
