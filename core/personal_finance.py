"""Free/local personal finance helper for budgeting and organization."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "personal_finance.sqlite3"
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
            CREATE TABLE IF NOT EXISTS finance_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                category TEXT NOT NULL,
                merchant TEXT NOT NULL,
                notes TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS finance_budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL UNIQUE,
                period TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                notes TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS finance_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                cadence TEXT NOT NULL,
                next_due_at TEXT NOT NULL,
                notes TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def add_expense(amount: float, *, category: str = "general", merchant: str = "", notes: str = "", currency: str = "NGN", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO finance_expenses(timestamp, amount, currency, category, merchant, notes, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), float(amount), _clean(currency).upper() or "NGN", _clean(category) or "general", _clean(merchant), _clean(notes)[:2000], _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM finance_expenses WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _expense_row(row)


def list_expenses(category: str = "", limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    params: list[Any] = []
    where = ""
    if category:
        where = "WHERE category=?"
        params.append(_clean(category))
    params.append(max(1, min(500, int(limit or 50))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM finance_expenses {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_expense_row(row) for row in rows]


def set_budget(category: str, amount: float, *, period: str = "monthly", currency: str = "NGN", notes: str = "") -> dict[str, Any]:
    init_db()
    cleaned = _clean(category) or "general"
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO finance_budgets(category, period, amount, currency, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(category) DO UPDATE SET period=excluded.period, amount=excluded.amount, currency=excluded.currency, notes=excluded.notes, updated_at=excluded.updated_at
            """,
            (cleaned, _clean(period) or "monthly", float(amount), _clean(currency).upper() or "NGN", _clean(notes), _now()),
        )
        row = conn.execute("SELECT * FROM finance_budgets WHERE category=?", (cleaned,)).fetchone()
    return _budget_row(row)


def list_budgets() -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM finance_budgets ORDER BY category").fetchall()
    return [_budget_row(row) for row in rows]


def add_subscription(name: str, amount: float, *, cadence: str = "monthly", next_due_at: str = "", currency: str = "NGN", notes: str = "") -> dict[str, Any]:
    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO finance_subscriptions(name, amount, currency, cadence, next_due_at, notes, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (_clean(name) or "Subscription", float(amount), _clean(currency).upper() or "NGN", _clean(cadence) or "monthly", _clean(next_due_at), _clean(notes), now, now),
        )
        row = conn.execute("SELECT * FROM finance_subscriptions WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _subscription_row(row)


def list_subscriptions(active: bool | None = True) -> list[dict[str, Any]]:
    init_db()
    where = "" if active is None else "WHERE active=?"
    params = [] if active is None else [1 if active else 0]
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM finance_subscriptions {where} ORDER BY active DESC, name", params).fetchall()
    return [_subscription_row(row) for row in rows]


def can_i_afford(amount: float, *, category: str = "general", currency: str = "NGN") -> dict[str, Any]:
    budgets = list_budgets()
    budget = next((item for item in budgets if item["category"].lower() == _clean(category).lower()), None)
    spent = _category_spend(category)
    if not budget:
        return {"ok": True, "confidence": 0.35, "summary": "No budget exists for that category, so I cannot judge affordability strongly.", "spent": spent}
    remaining = float(budget["amount"]) - spent
    ok = float(amount) <= remaining
    return {
        "ok": ok,
        "confidence": 0.75,
        "category": category,
        "amount": float(amount),
        "currency": currency,
        "budget": budget,
        "spent": spent,
        "remaining": remaining,
        "summary": f"{'Yes' if ok else 'Not safely'} based on your {budget['period']} {category} budget. Remaining: {remaining:.2f} {budget['currency']}.",
    }


def scan_receipts_folder(path: str = "") -> dict[str, Any]:
    root = Path(path or (DATA_DIR / "receipts")).expanduser()
    if not root.exists():
        return {"count": 0, "summary": f"Receipt folder not found: {root}", "items": []}
    items = []
    pattern = re.compile(r"(?P<currency>NGN|USD|GBP|EUR|\$|₦)?\s*(?P<amount>\d+(?:,\d{3})*(?:\.\d{1,2})?)", re.IGNORECASE)
    for file_path in root.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in {".txt", ".md", ".csv"}:
            continue
        text = file_path.read_text(encoding="utf-8", errors="ignore")[:8000]
        match = pattern.search(text)
        if match:
            amount = float(match.group("amount").replace(",", ""))
            currency = (match.group("currency") or "NGN").replace("₦", "NGN").replace("$", "USD").upper()
            items.append(add_expense(amount, category="receipts", merchant=file_path.stem, notes=f"Imported from {file_path}", currency=currency, metadata={"source_file": str(file_path)}))
    return {"count": len(items), "items": items, "summary": f"Imported {len(items)} receipt-like expense(s)."}


def summary() -> dict[str, Any]:
    expenses = list_expenses(limit=100)
    budgets = list_budgets()
    subs = list_subscriptions(active=True)
    total = sum(float(item["amount"]) for item in expenses)
    by_category: dict[str, float] = {}
    for item in expenses:
        by_category[item["category"]] = by_category.get(item["category"], 0.0) + float(item["amount"])
    return {
        "expense_count": len(expenses),
        "recent_expenses": expenses[:10],
        "budgets": budgets,
        "subscriptions": subs,
        "total_recent": round(total, 2),
        "by_category": {key: round(value, 2) for key, value in sorted(by_category.items())},
        "summary": f"{len(expenses)} recent expense(s), {len(budgets)} budget(s), {len(subs)} active subscription(s).",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM finance_expenses")
        conn.execute("DELETE FROM finance_budgets")
        conn.execute("DELETE FROM finance_subscriptions")


def _category_spend(category: str) -> float:
    return sum(float(item["amount"]) for item in list_expenses(category=category, limit=500))


def _expense_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "amount": float(row["amount"]),
        "currency": str(row["currency"]),
        "category": str(row["category"]),
        "merchant": str(row["merchant"]),
        "notes": str(row["notes"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _budget_row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "category": str(row["category"]), "period": str(row["period"]), "amount": float(row["amount"]), "currency": str(row["currency"]), "notes": str(row["notes"]), "updated_at": str(row["updated_at"])}


def _subscription_row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "name": str(row["name"]), "amount": float(row["amount"]), "currency": str(row["currency"]), "cadence": str(row["cadence"]), "next_due_at": str(row["next_due_at"]), "notes": str(row["notes"]), "active": bool(row["active"]), "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"])}


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
