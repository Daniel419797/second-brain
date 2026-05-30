"""Integration capability registry for Friday OS.

This registry stores only capability metadata and connection state. Secrets and
tokens must stay in provider-specific env vars or external secret stores.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "integration_registry.sqlite3"
_LOCK = threading.Lock()

DEFAULT_INTEGRATIONS = [
    {"id": "github", "label": "GitHub", "category": "code", "capabilities": ["create_branch", "commit", "open_pr", "inspect_ci"], "required_env": ["GITHUB_TOKEN"], "approval_required": ["push", "open_pr"]},
    {"id": "vercel", "label": "Vercel", "category": "preview_deploy", "capabilities": ["preview_deploy", "promote", "rollback"], "required_env": ["VERCEL_TOKEN"], "approval_required": ["deploy_preview", "deploy_production"]},
    {"id": "render", "label": "Render", "category": "preview_deploy", "capabilities": ["preview_deploy", "logs"], "required_env": ["RENDER_API_KEY"], "approval_required": ["deploy_preview", "deploy_production"]},
    {"id": "fly", "label": "Fly.io", "category": "preview_deploy", "capabilities": ["deploy", "logs"], "required_env": ["FLY_API_TOKEN"], "approval_required": ["deploy_preview", "deploy_production"]},
    {"id": "railway", "label": "Railway", "category": "preview_deploy", "capabilities": ["deploy", "logs"], "required_env": ["RAILWAY_TOKEN"], "approval_required": ["deploy_preview", "deploy_production"]},
    {"id": "neon", "label": "Neon Postgres", "category": "database", "capabilities": ["provision_database", "migrations"], "required_env": ["NEON_API_KEY"], "approval_required": ["customer_data_access"]},
    {"id": "supabase", "label": "Supabase", "category": "database", "capabilities": ["provision_database", "auth", "storage"], "required_env": ["SUPABASE_ACCESS_TOKEN"], "approval_required": ["customer_data_access"]},
    {"id": "clerk", "label": "Clerk", "category": "auth", "capabilities": ["managed_auth"], "required_env": ["CLERK_SECRET_KEY"], "approval_required": ["customer_data_access"]},
    {"id": "auth0", "label": "Auth0", "category": "auth", "capabilities": ["managed_auth"], "required_env": ["AUTH0_CLIENT_SECRET"], "approval_required": ["customer_data_access"]},
    {"id": "stripe", "label": "Stripe", "category": "billing", "capabilities": ["billing", "checkout", "webhooks"], "required_env": ["STRIPE_SECRET_KEY"], "approval_required": ["enable_billing"]},
    {"id": "paystack", "label": "Paystack", "category": "billing", "capabilities": ["billing", "checkout", "webhooks"], "required_env": ["PAYSTACK_SECRET_KEY"], "approval_required": ["enable_billing"]},
    {"id": "google_ads", "label": "Google Ads", "category": "ads", "capabilities": ["draft_ads", "post_ads"], "required_env": ["GOOGLE_ADS_TOKEN"], "approval_required": ["post_ads", "paid_api_spend"]},
    {"id": "meta_ads", "label": "Meta Ads", "category": "ads", "capabilities": ["draft_ads", "post_ads"], "required_env": ["META_ADS_TOKEN"], "approval_required": ["post_ads", "paid_api_spend"]},
    {"id": "slack", "label": "Slack", "category": "outbound", "capabilities": ["send_message", "webhooks"], "required_env": ["SLACK_BOT_TOKEN"], "approval_required": ["send_outreach"]},
    {"id": "gmail", "label": "Gmail", "category": "outbound", "capabilities": ["send_email", "draft_email"], "required_env": ["GOOGLE_CLIENT_SECRET"], "approval_required": ["send_outreach"]},
    {"id": "sentry", "label": "Sentry", "category": "observability", "capabilities": ["errors", "performance"], "required_env": ["SENTRY_AUTH_TOKEN"], "approval_required": []},
    {"id": "playwright", "label": "Playwright", "category": "verification", "capabilities": ["browser_screenshot", "e2e", "dead_button_check"], "required_env": [], "approval_required": []},
]


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
            CREATE TABLE IF NOT EXISTS integration_state (
                id TEXT PRIMARY KEY,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def list_integrations() -> list[dict[str, Any]]:
    init_db()
    state = _state_map()
    rows = []
    for item in DEFAULT_INTEGRATIONS:
        configured = all(os.getenv(name) for name in item.get("required_env", []))
        saved = state.get(item["id"], {})
        status = saved.get("status") or ("configured" if configured else "missing_env")
        rows.append(
            {
                **item,
                "configured": configured,
                "status": status,
                "notes": saved.get("notes", ""),
                "metadata": saved.get("metadata", {}),
                "secret_storage": "external_env_only",
            }
        )
    return rows


def status() -> dict[str, Any]:
    rows = list_integrations()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {"integrations": rows, "counts": counts, "summary": f"{len(rows)} integration capability record(s); secrets are not stored in Friday memory."}


def update_state(integration_id: str, status_value: str, *, notes: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            INSERT INTO integration_state(id, updated_at, status, notes, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, status=excluded.status, notes=excluded.notes, metadata_json=excluded.metadata_json
            """,
            (integration_id, now, status_value, notes, json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True, default=str)),
        )
    return {"id": integration_id, "updated_at": now, "status": status_value, "notes": notes, "metadata": metadata or {}}


def _state_map() -> dict[str, dict[str, Any]]:
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM integration_state").fetchall()
    result = {}
    for row in rows:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except Exception:
            metadata = {}
        result[str(row["id"])] = {"status": str(row["status"]), "notes": str(row["notes"]), "metadata": metadata}
    return result
