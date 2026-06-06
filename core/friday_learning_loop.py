"""Evidence-backed learning loop for Friday.

This module turns corrections, failed gates, and successful proof into durable
non-secret lessons that future runs can consume.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from core import failure_autopsy_engine, friday_memory, project_memory, taste_memory

FRIDAY_DIR = ".friday"
STUDIO_DIR = "product-studio"
LEARNING_DIR = "learning"


def learn_from_user_feedback(
    feedback: str,
    *,
    root: str | Path = "",
    domain: str = "product",
    evidence: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Store a user correction as an actionable Friday lesson."""

    text = _clean(feedback)
    if not text:
        return {"ok": False, "status": "empty", "summary": "No feedback was provided.", "lessons": []}
    domain_id = _domain(domain, text)
    lesson = _feedback_lesson(text, domain_id)
    evidence_items = [str(item) for item in (evidence or []) if _clean(item)]
    memory = friday_memory.remember(
        lesson["memory_type"],
        lesson["title"],
        lesson["content"],
        root=root,
        tags=_dedupe(["learning", "user_feedback", domain_id, *lesson["tags"]]),
        confidence=lesson["confidence"],
        metadata={
            "source": "user_feedback",
            "domain": domain_id,
            "evidence": evidence_items,
            **(metadata or {}),
        },
    )
    taste: dict[str, Any] = {}
    if domain_id in {"design", "coding", "frontend", "product", "copy"}:
        try:
            taste = taste_memory.learn(text, domain=domain_id, root=root, evidence=evidence_items or ["friday_learning_loop"])
        except Exception as exc:  # pragma: no cover - defensive bridge
            taste = {"ok": False, "summary": f"Taste memory bridge failed: {exc}"}
    project_note: dict[str, Any] = {}
    if _clean(root):
        try:
            project_note = project_memory.remember(
                root,
                "learned_rule",
                lesson["title"],
                lesson["content"],
                confidence=lesson["confidence"],
                metadata={"source": "friday_learning_loop", "domain": domain_id, "memory_id": memory.get("id")},
            )
        except Exception as exc:  # pragma: no cover - project memory is optional
            project_note = {"ok": False, "summary": f"Project memory bridge failed: {exc}"}
    return {
        "ok": True,
        "status": "learned",
        "summary": f"Friday learned a {lesson['memory_type'].replace('_', ' ')} for {domain_id}.",
        "lessons": [lesson],
        "memory": memory,
        "taste": taste,
        "project_memory": project_note,
    }


def learn_from_run_outcome(
    request: str,
    *,
    root: str | Path = "",
    design_handoff: dict[str, Any] | None = None,
    gate_results: dict[str, Any] | None = None,
    quality_reviews: list[dict[str, Any]] | None = None,
    fix_attempts: list[dict[str, Any]] | None = None,
    failure_autopsies: list[dict[str, Any]] | None = None,
    final_report: dict[str, Any] | None = None,
    source: str = "friday_run",
    write_artifacts: bool = True,
) -> dict[str, Any]:
    """Learn from objective run evidence and optionally write a proof artifact."""

    root_path = Path(root).expanduser().resolve() if _clean(root) else Path()
    request_text = _clean(request)
    gates = gate_results if isinstance(gate_results, dict) else {}
    reviews = quality_reviews if isinstance(quality_reviews, list) else []
    fixes = fix_attempts if isinstance(fix_attempts, list) else []
    handoff = design_handoff if isinstance(design_handoff, dict) else {}
    final = final_report if isinstance(final_report, dict) else {}
    stored: list[dict[str, Any]] = []
    lessons: list[dict[str, Any]] = []

    for lesson in _gate_lessons(gates):
        lessons.append(lesson)
        stored.append(_remember_lesson(lesson, root=root_path, source=source, request=request_text))

    for lesson in _quality_lessons(reviews):
        lessons.append(lesson)
        stored.append(_remember_lesson(lesson, root=root_path, source=source, request=request_text))

    for lesson in _fix_lessons(fixes):
        lessons.append(lesson)
        stored.append(_remember_lesson(lesson, root=root_path, source=source, request=request_text))

    success_lesson = _success_lesson(request_text, handoff, gates, reviews, final)
    if success_lesson:
        lessons.append(success_lesson)
        stored.append(_remember_lesson(success_lesson, root=root_path, source=source, request=request_text))

    # Keep failure autopsy memory alive even when the caller already generated
    # hypotheses but did not persist them.
    for autopsy in failure_autopsies or []:
        if not isinstance(autopsy, dict):
            continue
        failure = autopsy.get("failure") if isinstance(autopsy.get("failure"), dict) else {}
        if not failure:
            continue
        try:
            failure_autopsy_engine.autopsy(failure, root=root_path, source=f"{source}:learning", remember=True)
        except Exception:
            pass

    artifacts: list[str] = []
    if write_artifacts and _clean(root):
        artifacts = _write_learning_report(
            root_path,
            {
                "generated_at": _now(),
                "source": source,
                "request": request_text,
                "lesson_count": len(lessons),
                "lessons": lessons,
                "stored_memory_ids": [item.get("id") for item in stored if isinstance(item, dict) and item.get("id")],
                "summary": _learning_summary(lessons),
            },
        )
    return {
        "ok": True,
        "status": "learned" if lessons else "no_new_lessons",
        "summary": _learning_summary(lessons),
        "lesson_count": len(lessons),
        "lessons": lessons,
        "memories": stored,
        "artifacts": artifacts,
    }


def learning_context_for_request(
    request: str,
    *,
    root: str | Path = "",
    domain: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    """Return compact learned rules that should influence a future run."""

    request_text = _clean(request)
    domain_id = _domain(domain, request_text)
    root_text = str(root or "")
    candidates: list[dict[str, Any]] = []
    queries = _dedupe([request_text, domain_id, "never again", "design", "quality", "style", "generic", "scaffold"])
    for query in queries:
        if not query:
            continue
        try:
            candidates.extend(friday_memory.search(query, limit=max(8, limit * 2)))
        except Exception:
            continue
    try:
        candidates.extend(friday_memory.recent(limit=max(20, limit * 3)))
    except Exception:
        pass
    if root_text:
        try:
            for item in project_memory.search(request_text or domain_id, root=root_text, limit=max(8, limit)):
                candidates.append(
                    {
                        "id": f"project:{item.get('id')}",
                        "memory_type": item.get("kind") or "project_convention",
                        "title": item.get("title") or "Project lesson",
                        "content": item.get("content") or "",
                        "root": root_text,
                        "confidence": item.get("confidence") or 0.7,
                        "tags": ["project_memory", domain_id],
                        "metadata": item.get("metadata") or {},
                    }
                )
        except Exception:
            pass

    ranked = _rank_memories(candidates, request_text, domain_id, root_text)
    selected = ranked[: max(1, min(20, int(limit or 10)))]
    prompt_lines = [_memory_prompt_line(item) for item in selected]
    return {
        "available": bool(selected),
        "domain": domain_id,
        "request": request_text,
        "rules": selected,
        "prompt_lines": prompt_lines,
        "summary": f"{len(selected)} learned rule(s) selected for this request." if selected else "No learned rules matched this request yet.",
    }


def status(limit: int = 20) -> dict[str, Any]:
    payload = friday_memory.status(limit=limit)
    learning_items = [
        item
        for item in payload.get("recent") or []
        if "learning" in (item.get("tags") or [])
        or str(item.get("memory_type") or "") in {"never_again_rule", "design_preference", "design_failure", "quality_rule", "successful_pattern"}
    ]
    return {
        "summary": f"{len(learning_items)} recent Friday learning item(s); {payload.get('summary')}",
        "counts": payload.get("counts") or {},
        "recent": learning_items[: max(1, min(100, int(limit or 20)))],
    }


def _feedback_lesson(text: str, domain: str) -> dict[str, Any]:
    lowered = text.lower()
    tags = [domain]
    memory_type = "user_preference"
    title = f"{domain.title()} preference"
    confidence = 0.82
    if any(term in lowered for term in ("never", "don't", "do not", "stop", "hate", "trash", "rubbish", "shit", "bad")):
        memory_type = "never_again_rule"
        title = f"Never again: {_short_title(text)}"
        confidence = 0.9
        tags.append("never_again")
    if any(term in lowered for term in ("design", "ui", "hero", "layout", "stitch", "visual", "copy", "typography", "animation", "3d", "parallax")):
        tags.extend(["design", "taste"])
        if memory_type == "user_preference":
            memory_type = "design_preference"
            title = f"Design preference: {_short_title(text)}"
    if any(term in lowered for term in ("generic", "scaffold", "placeholder", "home 1", "home1", "service 1", "split hero")):
        memory_type = "design_failure"
        title = f"Rejected design pattern: {_short_title(text)}"
        confidence = max(confidence, 0.92)
        tags.extend(["quality_gate", "rejected_pattern"])
    if any(term in lowered for term in ("next.js", "nextjs", "route", "component", "folder", "src/app", "tests", "clean code")):
        tags.extend(["coding", "project_convention"])
        if memory_type == "user_preference":
            memory_type = "coding_preference"
            title = f"Coding preference: {_short_title(text)}"
    return {
        "memory_type": memory_type,
        "title": title,
        "content": _actionable_rule(text, domain),
        "tags": _dedupe(tags),
        "confidence": confidence,
    }


def _gate_lessons(gate_results: dict[str, Any]) -> list[dict[str, Any]]:
    lessons: list[dict[str, Any]] = []
    failed = [str(item) for item in (gate_results.get("failed_required") or []) if _clean(item)]
    for item in failed[:8]:
        lessons.append(
            {
                "memory_type": "failure_pattern",
                "title": f"Required gate failure: {_short_title(item)}",
                "content": f"When this kind of project is run, do not claim readiness until this required gate is fixed: {item}",
                "tags": ["learning", "gate", "failure", "readiness"],
                "confidence": 0.82,
            }
        )
    for gate in gate_results.get("gates") or []:
        if not isinstance(gate, dict) or not gate.get("required"):
            continue
        if str(gate.get("status") or "").lower() == "passed":
            continue
        summary = _clean(gate.get("summary") or gate.get("label") or gate.get("id") or "required gate failed")
        lessons.append(
            {
                "memory_type": "failure_pattern",
                "title": f"{_clean(gate.get('label') or gate.get('id') or 'Gate')} failed",
                "content": f"Gate {gate.get('id') or gate.get('label')} blocked readiness: {summary}",
                "tags": ["learning", "gate", "failure", str(gate.get("group") or "")],
                "confidence": 0.78,
            }
        )
    return _dedupe_lessons(lessons)


def _quality_lessons(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lessons: list[dict[str, Any]] = []
    for review in reviews[-3:]:
        if not isinstance(review, dict):
            continue
        issues = review.get("issues") if isinstance(review.get("issues"), list) else []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            severity = int(issue.get("severity") or 0)
            if severity < 4:
                continue
            issue_id = _clean(issue.get("id") or "quality_issue")
            summary = _clean(issue.get("summary") or issue.get("message") or issue_id)
            is_design = any(term in f"{issue_id} {summary}".lower() for term in ("visual", "design", "copy", "hero", "layout", "stitch", "button"))
            lessons.append(
                {
                    "memory_type": "design_failure" if is_design else "quality_rule",
                    "title": f"Quality failure: {_short_title(summary)}",
                    "content": f"Reject or fix this pattern before handoff: {summary}",
                    "tags": ["learning", "quality", "design" if is_design else "engineering", issue_id],
                    "confidence": 0.84,
                }
            )
    return _dedupe_lessons(lessons)


def _fix_lessons(fixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lessons: list[dict[str, Any]] = []
    for fix in fixes[-5:]:
        if not isinstance(fix, dict) or not fix.get("ok"):
            continue
        summary = _clean(fix.get("summary") or fix.get("status") or "")
        if not summary:
            continue
        lessons.append(
            {
                "memory_type": "successful_fix",
                "title": f"Successful fix: {_short_title(summary)}",
                "content": f"This fix path worked and can be considered for similar evidence: {summary}",
                "tags": ["learning", "fix", str(fix.get("status") or "")],
                "confidence": 0.76,
            }
        )
    return _dedupe_lessons(lessons)


def _success_lesson(
    request: str,
    design_handoff: dict[str, Any],
    gate_results: dict[str, Any],
    reviews: list[dict[str, Any]],
    final_report: dict[str, Any],
) -> dict[str, Any] | None:
    latest_review = reviews[-1] if reviews and isinstance(reviews[-1], dict) else {}
    technical_ready = bool(gate_results.get("technical_ready") or final_report.get("technical_ready"))
    quality_ok = bool(latest_review.get("ok")) if latest_review else True
    if not technical_ready or not quality_ok:
        return None
    design_plan = design_handoff.get("design_plan") if isinstance(design_handoff.get("design_plan"), dict) else {}
    context = design_plan.get("design_context") if isinstance(design_plan.get("design_context"), dict) else {}
    composition = context.get("composition_spec") if isinstance(context.get("composition_spec"), dict) else {}
    experience = context.get("experience_mode") if isinstance(context.get("experience_mode"), dict) else {}
    details = [
        f"Request: {request}",
        f"Gate status: {gate_results.get('status') or 'passed'}",
        f"Composition: {composition.get('archetype_name') or composition.get('archetype') or 'not recorded'}",
        f"Experience: {experience.get('mode_name') or experience.get('mode') or 'not recorded'}",
    ]
    return {
        "memory_type": "successful_pattern",
        "title": "Verified project pattern",
        "content": " | ".join(item for item in details if _clean(item)),
        "tags": ["learning", "success", "verified", "design", "gates"],
        "confidence": 0.8,
    }


def _remember_lesson(lesson: dict[str, Any], *, root: Path, source: str, request: str) -> dict[str, Any]:
    return friday_memory.remember(
        lesson.get("memory_type") or "learning",
        lesson.get("title") or "Friday lesson",
        lesson.get("content") or "",
        root=root if str(root) != "." else "",
        tags=_dedupe(["learning", *(lesson.get("tags") or [])]),
        confidence=float(lesson.get("confidence") or 0.75),
        metadata={"source": source, "request": request},
    )


def _rank_memories(candidates: list[dict[str, Any]], request: str, domain: str, root: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    tokens = set(_keywords(request))
    ranked: list[tuple[float, dict[str, Any]]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id") or "") or f"{item.get('memory_type')}:{item.get('title')}:{item.get('content')}"
        if key in seen:
            continue
        seen.add(key)
        content = f"{item.get('memory_type')} {item.get('title')} {item.get('content')} {' '.join(item.get('tags') or [])}".lower()
        score = float(item.get("confidence") or 0.5)
        if root and str(item.get("root") or "") == root:
            score += 0.35
        if domain and domain in content:
            score += 0.25
        if any(term in content for term in ("never_again", "never again", "design_failure", "quality_rule")):
            score += 0.25
        if tokens:
            score += min(0.35, len(tokens & set(_keywords(content))) * 0.05)
        if _memory_applies(item, domain):
            ranked.append((score, _public_memory(item, score)))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in ranked]


def _memory_applies(item: dict[str, Any], domain: str) -> bool:
    tags = {str(tag).lower() for tag in (item.get("tags") or [])}
    memory_type = str(item.get("memory_type") or "").lower()
    if domain in tags or domain in memory_type:
        return True
    if memory_type in {"never_again_rule", "design_failure", "design_preference", "quality_rule", "successful_pattern", "user_preference"}:
        return True
    return "learning" in tags


def _public_memory(item: dict[str, Any], score: float) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "memory_type": item.get("memory_type"),
        "title": item.get("title"),
        "content": item.get("content"),
        "root": item.get("root") or "",
        "confidence": item.get("confidence") or 0.0,
        "relevance": round(score, 3),
        "tags": item.get("tags") or [],
        "created_at": item.get("created_at") or "",
    }


def _memory_prompt_line(item: dict[str, Any]) -> str:
    marker = "NEVER" if str(item.get("memory_type") or "") in {"never_again_rule", "design_failure"} else "Apply"
    return f"{marker}: {_clean(item.get('title'))} - {_clean(item.get('content'))}"


def _write_learning_report(root: Path, report: dict[str, Any]) -> list[str]:
    out_dir = root / FRIDAY_DIR / STUDIO_DIR / LEARNING_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "learning-report.json"
    md_path = out_dir / "learning-report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    md_path.write_text(_learning_markdown(report), encoding="utf-8")
    return [str(json_path), str(md_path)]


def _learning_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Friday Learning Report",
        "",
        str(report.get("summary") or ""),
        "",
        f"Source: {report.get('source') or ''}",
        f"Request: {report.get('request') or ''}",
        "",
        "## Lessons",
    ]
    for lesson in report.get("lessons") or []:
        if isinstance(lesson, dict):
            lines.append(f"- {lesson.get('memory_type')}: {lesson.get('title')} - {lesson.get('content')}")
    return "\n".join(lines) + "\n"


def _learning_summary(lessons: list[dict[str, Any]]) -> str:
    if not lessons:
        return "No new evidence-backed lessons were extracted from this run."
    counts: dict[str, int] = {}
    for lesson in lessons:
        counts[str(lesson.get("memory_type") or "learning")] = counts.get(str(lesson.get("memory_type") or "learning"), 0) + 1
    return "Friday learned from this run: " + ", ".join(f"{count} {kind.replace('_', ' ')}" for kind, count in sorted(counts.items())) + "."


def _actionable_rule(text: str, domain: str) -> str:
    lowered = text.lower()
    if "split hero" in lowered or ("text left" in lowered and "image right" in lowered):
        return f"For {domain} work, do not default to generic left-text/right-card or left-text/right-image split heroes. Choose composition from product intent and verify screenshots."
    if "home 1" in lowered or "service 1" in lowered or "home1" in lowered:
        return "Reject generated page-label artifacts like Home 1, Home 2, Service 1, or Service 2 before frontend handoff."
    if "scaffold" in lowered or "generic" in lowered:
        return f"For {domain} work, treat generic scaffold output as a failure unless domain-specific copy, structure, evidence, and browser proof are attached. Feedback: {text}"
    return text


def _domain(domain: str, text: str) -> str:
    raw = _clean(domain).lower().replace(" ", "_")
    if raw and raw not in {"auto", "general"}:
        return raw[:80]
    lowered = text.lower()
    if any(term in lowered for term in ("design", "ui", "hero", "layout", "stitch", "visual", "animation", "3d", "parallax")):
        return "design"
    if any(term in lowered for term in ("copy", "headline", "wording", "message")):
        return "copy"
    if any(term in lowered for term in ("code", "nextjs", "backend", "api", "test", "component")):
        return "coding"
    return "product"


def _dedupe_lessons(lessons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for lesson in lessons:
        key = f"{lesson.get('memory_type')}:{lesson.get('title')}:{lesson.get('content')}"
        if key in seen:
            continue
        seen.add(key)
        result.append(lesson)
    return result


def _dedupe(items: list[Any]) -> list[str]:
    result: list[str] = []
    for item in items:
        text = _clean(item).lower()
        if text and text not in result:
            result.append(text)
    return result


def _short_title(value: str) -> str:
    text = _clean(value)
    text = re.sub(r"[^A-Za-z0-9 +#._/-]+", "", text)
    return text[:80].strip() or "lesson"


def _keywords(value: str) -> list[str]:
    return [item for item in re.findall(r"[a-zA-Z0-9_+#-]{3,}", str(value or "").lower()) if item not in {"the", "and", "for", "with", "that", "this", "from"}]


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
