"""Ad campaign drafting and approval-gated posting."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import connector_runtime, notification_center, trust_proof
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "ad_campaigns.sqlite3"
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
            CREATE TABLE IF NOT EXISTS ad_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                product TEXT NOT NULL,
                audience TEXT NOT NULL,
                offer TEXT NOT NULL,
                objective TEXT NOT NULL,
                platform TEXT NOT NULL,
                tone TEXT NOT NULL,
                status TEXT NOT NULL,
                variants_json TEXT NOT NULL,
                outbox_id INTEGER,
                metadata_json TEXT NOT NULL
            )
            """
        )


def draft(
    product: str,
    *,
    audience: str = "",
    offer: str = "",
    objective: str = "conversions",
    platform: str = "social",
    tone: str = "direct",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    product_text = _clean(product) or "your offer"
    audience_text = _clean(audience) or "busy small-business operators"
    offer_text = _clean(offer) or f"save time with {product_text}"
    objective_text = _clean(objective) or "conversions"
    platform_text = _connector(platform) or "social"
    tone_text = _clean(tone) or "direct"
    variants = _variants(product_text, audience_text, offer_text, objective_text, platform_text, tone_text)
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO ad_campaigns(created_at, updated_at, product, audience, offer, objective, platform, tone, status, variants_json, outbox_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, NULL, ?)
            """,
            (now, now, product_text, audience_text, offer_text, objective_text, platform_text, tone_text, _json_dumps(variants), _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM ad_campaigns WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    notification_center.add(
        source="ad_campaigns",
        category="marketing",
        severity=2,
        title="Ad draft ready",
        message=item["summary"],
        metadata={"campaign_id": item["id"]},
    )
    return item


def queue_post(
    campaign_id: int = 0,
    *,
    connector: str = "",
    target: str = "",
    variant_index: int = 0,
    product: str = "",
    audience: str = "",
    offer: str = "",
    platform: str = "",
    tone: str = "direct",
) -> dict[str, Any]:
    init_db()
    campaign = get(campaign_id) if int(campaign_id or 0) > 0 else None
    if not campaign:
        campaign = draft(product or "your offer", audience=audience, offer=offer, platform=platform or connector or "social", tone=tone)
    key = _connector(connector or campaign.get("platform") or "manual")
    if key == "social":
        key = "manual"
    destination = _clean(target)
    if not destination:
        raise ValueError("target is required for ad posting.")
    variants = campaign.get("variants") or []
    variant = variants[max(0, min(len(variants) - 1, int(variant_index or 0)))] if variants else {}
    body = _format_post(variant, campaign)
    outbox = connector_runtime.queue_message(
        key,
        destination,
        body,
        subject=str(variant.get("headline") or f"Ad for {campaign['product']}"),
        action="ad_post",
        payload={"campaign_id": campaign["id"], "platform": campaign.get("platform"), "variant": variant},
        require_approval=True,
    )
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE ad_campaigns SET status='queued_for_approval', outbox_id=?, updated_at=? WHERE id=?", (int(outbox["id"]), _now(), int(campaign["id"])))
    proof = trust_proof.create_report(
        f"Ad campaign #{campaign['id']} queued",
        changed=[f"Queued ad post through {key} to {destination}"],
        tested=["Connector runtime accepted the outbound item into approval flow."],
        evidence=[outbox.get("summary", "")],
        risks=["The ad is not posted until the connector outbox is approved and dispatched.", "Platform ad policies and budget settings still need human review."],
        confidence=0.76,
        metadata={"source": "ad_campaigns", "campaign_id": campaign["id"], "outbox_id": outbox["id"]},
    )
    return get(int(campaign["id"])) | {"outbox": outbox, "proof": proof, "summary": f"Queued ad campaign #{campaign['id']} for approval via {key} outbox #{outbox['id']}."}


def get(campaign_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM ad_campaigns WHERE id=?", (int(campaign_id),)).fetchone()
    return _row(row) if row else None


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM ad_campaigns ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM ad_campaigns")


def _variants(product: str, audience: str, offer: str, objective: str, platform: str, tone: str) -> list[dict[str, Any]]:
    cta = "Start free" if objective in {"conversion", "conversions", "signup", "sales"} else "Learn more"
    punch = "Stop losing hours to repeat work."
    if tone.lower() in {"bold", "aggressive"}:
        punch = "Your workflow is leaking money."
    elif tone.lower() in {"warm", "friendly"}:
        punch = "Give your team a calmer way to work."
    return [
        {
            "headline": f"{product}: {offer.capitalize()}",
            "primary_text": f"{punch} {product} helps {audience} capture requests, decide faster, and move work forward without the usual back-and-forth.",
            "cta": cta,
            "hashtags": _hashtags(product, audience),
            "image_prompt": f"Clean product ad for {product}, showing {audience} saving time with an AI workflow dashboard.",
            "platform": platform,
        },
        {
            "headline": f"Built for {audience}",
            "primary_text": f"If your day is full of repeated status checks, scattered notes, and delayed decisions, {product} turns them into one clear action flow.",
            "cta": cta,
            "hashtags": _hashtags(product, "ai automation workflow"),
            "image_prompt": f"Modern ad creative for {product}, everyday AI assistant, organized tasks, confident team handoff.",
            "platform": platform,
        },
        {
            "headline": f"Ship daily work faster",
            "primary_text": f"{product} gives {audience} an AI-assisted command center for tasks, decisions, customer updates, and repeat workflows.",
            "cta": cta,
            "hashtags": _hashtags(product, "small business productivity"),
            "image_prompt": f"High-converting social ad for {product}, practical SMB workflow automation, bright professional UI.",
            "platform": platform,
        },
    ]


def _format_post(variant: dict[str, Any], campaign: dict[str, Any]) -> str:
    tags = " ".join(variant.get("hashtags") or [])
    return "\n\n".join(
        part
        for part in [
            str(variant.get("headline") or campaign.get("product") or "Ad"),
            str(variant.get("primary_text") or ""),
            f"CTA: {variant.get('cta')}" if variant.get("cta") else "",
            tags,
        ]
        if _clean(part)
    )


def _hashtags(*values: str) -> list[str]:
    words = []
    for value in values:
        words.extend(part for part in re.split(r"[^A-Za-z0-9]+", value) if len(part) > 3)
    tags = []
    for word in words:
        tag = "#" + word[:24].lower()
        if tag not in tags:
            tags.append(tag)
    return tags[:5] or ["#productivity", "#automation"]


def _row(row: sqlite3.Row) -> dict[str, Any]:
    variants = _json_loads(row["variants_json"], [])
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "product": str(row["product"]),
        "audience": str(row["audience"]),
        "offer": str(row["offer"]),
        "objective": str(row["objective"]),
        "platform": str(row["platform"]),
        "tone": str(row["tone"]),
        "status": str(row["status"]),
        "variants": variants,
        "outbox_id": int(row["outbox_id"] or 0),
        "metadata": _json_loads(row["metadata_json"], {}),
        "summary": f"Ad campaign #{row['id']} for {row['product']} is {row['status']} with {len(variants)} variant(s).",
    }


def _connector(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {"x": "twitter", "tweet": "twitter", "email": "gmail", "manual_post": "manual"}
    text = aliases.get(text, text)
    return "".join(ch for ch in text if ch.isalnum() or ch == "_").strip("_")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
