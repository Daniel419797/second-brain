"""Central inspect-build-run-see-fix-prove loop for Friday project builds."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Callable

from core import failure_autopsy_engine, friday_learning_loop, friday_trace, langgraph_backbone, product_studio, product_studio_gates, quality_taste_layer
from core.config import config_value, resolve_coding_root

FRIDAY_DIR = ".friday"
STUDIO_DIR = "product-studio"
LOOP_DIR = "implementation-loop"

GateRunner = Callable[..., dict[str, Any]]
Progress = Callable[[str], None]


def run_after_scaffold(
    root: str | Path,
    request: str,
    *,
    product_name: str,
    stack: dict[str, Any],
    initial_changed_files: list[str] | None = None,
    initial_tested: list[str] | None = None,
    run_live_design: bool = False,
    gate_runner: GateRunner | None = None,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Run Friday's full build loop after files exist on disk.

    This is deliberately evidence-first: if a required design handoff fails,
    executable gates are blocked. If visual quality fails and a deterministic
    low-risk fix exists, Friday applies it and reruns gates once.
    """

    project_root = resolve_coding_root(root)
    gate_runner = gate_runner or _default_gate_runner
    progress = progress or (lambda _message: None)
    trace_id = friday_trace.new_trace_id("product-build")
    friday_trace.start_trace(
        trace_id,
        kind="product_build_loop",
        title=product_name,
        root=project_root,
        metadata={"request": request, "stack": stack},
    )

    def tracked(name: str, handler: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def wrapped(current: dict[str, Any]) -> dict[str, Any]:
            friday_trace.record_event(trace_id, event_type="phase_start", title=name, summary=f"Product build phase {name} started.", status="running", metadata={"phase": name})
            try:
                result = handler(current) or {}
            except Exception as exc:
                friday_trace.record_event(trace_id, event_type="phase_error", title=name, summary=str(exc), status="failed", metadata={"phase": name})
                raise
            friday_trace.record_event(trace_id, event_type="phase_finish", title=name, summary=f"Product build phase {name} finished.", status="done", metadata={"phase": name, "delta_keys": sorted(result.keys())})
            return result

        return wrapped

    state = langgraph_backbone.run_phase_graph(
        [
            ("inspect", tracked("inspect", lambda current: _loop_inspect_phase(current))),
            ("plan", tracked("plan", lambda current: _loop_plan_phase(current))),
            (
                "design_handoff",
                tracked("design_handoff", lambda current: _loop_design_handoff_phase(
                    current,
                    project_root=project_root,
                    request=request,
                    product_name=product_name,
                    stack=stack,
                    run_live_design=run_live_design,
                )),
            ),
            (
                "taste_preflight",
                tracked("taste_preflight", lambda current: _loop_taste_preflight_phase(
                    current,
                    project_root=project_root,
                    request=request,
                    stack=stack,
                    run_live_design=run_live_design,
                )),
            ),
            (
                "verify_fix_retry",
                tracked("verify_fix_retry", lambda current: _loop_verify_fix_retry_phase(
                    current,
                    project_root=project_root,
                    request=request,
                    product_name=product_name,
                    stack=stack,
                    run_live_design=run_live_design,
                    gate_runner=gate_runner,
                    progress=progress,
                )),
            ),
            ("prove", tracked("prove", lambda current: _loop_prove_phase(current, project_root=project_root))),
        ],
        {
            "root": str(project_root),
            "request": request,
            "product_name": product_name,
            "stack": stack,
            "trace_id": trace_id,
            "changed_files": list(initial_changed_files or []),
            "tested": list(initial_tested or []),
            "phases": [],
            "artifacts": [],
            "quality_reviews": [],
            "fix_attempts": [],
            "failure_autopsies": [],
            "attempts": [],
            "design_handoff": {},
            "design_blockers": [],
            "gate_results": {},
        },
        thread_id=f"product-build-loop-{_clean(product_name).lower().replace(' ', '-') or 'project'}",
    )
    quality_reviews = state.get("quality_reviews") if isinstance(state.get("quality_reviews"), list) else []
    gate_results = state.get("gate_results") if isinstance(state.get("gate_results"), dict) else {}
    status = "blocked" if state.get("design_blockers") else "passed" if gate_results.get("technical_ready") and quality_reviews and quality_reviews[-1].get("ok") else "attention"
    summary = (
        "Blocked before executable gates because the required design-provider handoff did not succeed."
        if status == "blocked"
        else "Friday ran inspect-build-run-see-fix-proof loop."
    )
    return {
        "status": status,
        "summary": summary,
        "design_handoff": state.get("design_handoff") or {},
        "design_blockers": state.get("design_blockers") or [],
        "gate_results": gate_results,
        "quality_reviews": quality_reviews,
        "fix_attempts": state.get("fix_attempts") or [],
        "failure_autopsies": state.get("failure_autopsies") or [],
        "changed_files": _dedupe(list(state.get("changed_files") or [])),
        "tested": _dedupe(list(state.get("tested") or [])),
        "artifacts": _dedupe(list(state.get("artifacts") or [])),
        "phases": state.get("phases") or [],
        "attempts": state.get("attempts") or [],
        "workflow_backend": state.get("workflow_backend") or "native",
        "workflow_phases": state.get("workflow_phases") or [],
        "trace_id": trace_id,
        "learning": state.get("learning") or {},
    }


def _loop_inspect_phase(state: dict[str, Any]) -> dict[str, Any]:
    phases = list(state.get("phases") or [])
    _phase(phases, "inspect", "completed", "Project scaffold exists on disk before loop execution.")
    return {"phases": phases}


def _loop_plan_phase(state: dict[str, Any]) -> dict[str, Any]:
    phases = list(state.get("phases") or [])
    _phase(phases, "plan", "completed", "Friday selected stack, target files, proof artifacts, and gate contract.")
    return {"phases": phases}


def _loop_design_handoff_phase(
    state: dict[str, Any],
    *,
    project_root: Path,
    request: str,
    product_name: str,
    stack: dict[str, Any],
    run_live_design: bool,
) -> dict[str, Any]:
    phases = list(state.get("phases") or [])
    artifacts = list(state.get("artifacts") or [])
    changed_files = list(state.get("changed_files") or [])

    design_handoff = product_studio.prepare_design_handoff(
        project_root,
        request,
        product_name=product_name,
        stack=stack,
        run_live=run_live_design,
        apply_to_source=run_live_design,
    )
    artifacts.extend(str(item) for item in (design_handoff.get("artifacts") or []) if str(item).strip())
    changed_files.extend(artifacts)
    design_blockers = required_design_handoff_blockers(design_handoff, run_live=run_live_design)
    _phase(
        phases,
        "design_handoff",
        "blocked" if design_blockers else "completed",
        design_blockers[0] if design_blockers else "Design handoff accepted or not required for this stack.",
        evidence=design_handoff.get("artifacts") or [],
    )
    return {
        "phases": phases,
        "artifacts": _dedupe(artifacts),
        "changed_files": _dedupe(changed_files),
        "design_handoff": design_handoff,
        "design_blockers": design_blockers,
    }


def _loop_taste_preflight_phase(
    state: dict[str, Any],
    *,
    project_root: Path,
    request: str,
    stack: dict[str, Any],
    run_live_design: bool,
) -> dict[str, Any]:
    if state.get("design_blockers"):
        return {}
    phases = list(state.get("phases") or [])
    artifacts = list(state.get("artifacts") or [])
    changed_files = list(state.get("changed_files") or [])
    quality_reviews = list(state.get("quality_reviews") or [])
    fix_attempts = list(state.get("fix_attempts") or [])
    design_handoff = state.get("design_handoff") if isinstance(state.get("design_handoff"), dict) else {}
    required_handoff = design_handoff if run_live_design else {}
    pre_review = quality_taste_layer.review_project(project_root, request, stack=stack, design_handoff=required_handoff)
    quality_reviews.append(pre_review)
    artifacts.extend(pre_review.get("artifacts") or [])
    _phase(phases, "taste_preflight", "completed" if pre_review.get("ok") else "needs_revision", pre_review.get("summary") or "", evidence=pre_review.get("artifacts") or [])

    pre_fix = quality_taste_layer.apply_safe_fixes(project_root, pre_review)
    if pre_fix.get("ok"):
        fix_attempts.append(pre_fix)
        changed_files.extend(pre_fix.get("changed") or [])
        _phase(phases, "fix", "completed", pre_fix.get("summary") or "", evidence=pre_fix.get("changed") or [])
    return {
        "phases": phases,
        "artifacts": _dedupe(artifacts),
        "changed_files": _dedupe(changed_files),
        "quality_reviews": quality_reviews,
        "fix_attempts": fix_attempts,
    }


def _loop_verify_fix_retry_phase(
    state: dict[str, Any],
    *,
    project_root: Path,
    request: str,
    product_name: str,
    stack: dict[str, Any],
    run_live_design: bool,
    gate_runner: GateRunner,
    progress: Progress,
) -> dict[str, Any]:
    phases = list(state.get("phases") or [])
    artifacts = list(state.get("artifacts") or [])
    changed_files = list(state.get("changed_files") or [])
    tested = list(state.get("tested") or [])
    quality_reviews = list(state.get("quality_reviews") or [])
    fix_attempts = list(state.get("fix_attempts") or [])
    failure_autopsies = list(state.get("failure_autopsies") or [])
    attempts = list(state.get("attempts") or [])
    design_handoff = state.get("design_handoff") if isinstance(state.get("design_handoff"), dict) else {}
    design_blockers = list(state.get("design_blockers") or [])
    if design_blockers:
        gate_results = blocked_design_gate_results(project_root, stack=stack, blockers=design_blockers, artifacts=artifacts)
        artifacts.extend(gate_results.get("artifacts") or [])
        tested.extend(_gate_tested(gate_results))
        quality_review = quality_taste_layer.review_project(project_root, request, stack=stack, gate_results=gate_results, design_handoff=design_handoff)
        artifacts.extend(quality_review.get("artifacts") or [])
        _phase(phases, "verify", "blocked", "Executable gates skipped because required design handoff failed.", evidence=gate_results.get("artifacts") or [])
        return {
            "phases": phases,
            "artifacts": _dedupe(artifacts),
            "tested": _dedupe(tested),
            "quality_reviews": [quality_review],
            "gate_results": gate_results,
        }

    required_handoff = design_handoff if run_live_design else {}
    max_attempts = max(1, min(3, int(config_value("friday_product_loop_max_attempts", 2) or 2)))
    gate_results: dict[str, Any] = {}
    for attempt in range(1, max_attempts + 1):
        progress(f"Progress {70 + attempt}%: running executable gates, attempt {attempt}.")
        gate_results = gate_runner(project_root, stack=stack, install=True, request=request)
        tested.extend(_gate_tested(gate_results))
        artifacts.extend(gate_results.get("artifacts") or [])
        post_review = quality_taste_layer.review_project(project_root, request, stack=stack, gate_results=gate_results, design_handoff=required_handoff)
        quality_reviews.append(post_review)
        artifacts.extend(post_review.get("artifacts") or [])
        attempts.append({"attempt": attempt, "gate_status": gate_results.get("status"), "quality_status": post_review.get("status"), "technical_ready": gate_results.get("technical_ready")})
        _phase(phases, "verify", "completed" if gate_results.get("technical_ready") else "needs_revision", gate_results.get("summary") or "", evidence=gate_results.get("artifacts") or [])
        _phase(phases, "see", "completed" if post_review.get("ok") else "needs_revision", post_review.get("summary") or "", evidence=post_review.get("artifacts") or [])
        if gate_results.get("technical_ready") and post_review.get("ok"):
            break
        failure_autopsies.extend(_autopsy_failed_gates(project_root, gate_results, attempt=attempt))
        if attempt >= max_attempts:
            break
        if run_live_design and _design_revision_needed(post_review):
            revision = _revise_design_handoff(project_root, request, product_name=product_name, stack=stack, review=post_review)
            fix_attempts.append(revision)
            artifacts.extend(revision.get("artifacts") or [])
            changed_files.extend(revision.get("changed") or [])
            if revision.get("ok"):
                revised_handoff = revision.get("design_handoff") if isinstance(revision.get("design_handoff"), dict) else {}
                design_handoff = revised_handoff or design_handoff
                required_handoff = design_handoff
                _phase(phases, "fix", "completed", revision.get("summary") or "Regenerated design handoff from visual critique.", evidence=revision.get("artifacts") or [])
                continue
            _phase(phases, "fix", "blocked", revision.get("summary") or "Design revision did not produce an accepted handoff.", evidence=revision.get("artifacts") or [])
            break
        fix = quality_taste_layer.apply_safe_fixes(project_root, post_review)
        fix_attempts.append(fix)
        if not fix.get("ok"):
            _phase(phases, "fix", "blocked", fix.get("summary") or "No safe fix available.")
            break
        changed_files.extend(fix.get("changed") or [])
        _phase(phases, "fix", "completed", fix.get("summary") or "", evidence=fix.get("changed") or [])

    return {
        "phases": phases,
        "artifacts": _dedupe(artifacts),
        "changed_files": _dedupe(changed_files),
        "tested": _dedupe(tested),
        "quality_reviews": quality_reviews,
        "fix_attempts": fix_attempts,
        "failure_autopsies": failure_autopsies,
        "attempts": attempts,
        "gate_results": gate_results,
        "design_handoff": design_handoff,
    }


def _loop_prove_phase(state: dict[str, Any], *, project_root: Path) -> dict[str, Any]:
    phases = list(state.get("phases") or [])
    artifacts = list(state.get("artifacts") or [])
    design_handoff = state.get("design_handoff") if isinstance(state.get("design_handoff"), dict) else {}
    gate_results = state.get("gate_results") if isinstance(state.get("gate_results"), dict) else {}
    quality_reviews = state.get("quality_reviews") if isinstance(state.get("quality_reviews"), list) else []
    fix_attempts = state.get("fix_attempts") if isinstance(state.get("fix_attempts"), list) else []
    failure_autopsies = state.get("failure_autopsies") if isinstance(state.get("failure_autopsies"), list) else []
    attempts = state.get("attempts") if isinstance(state.get("attempts"), list) else []
    loop_report = _write_loop_report(project_root, phases, attempts, design_handoff, gate_results, quality_reviews, fix_attempts, failure_autopsies=failure_autopsies)
    artifacts.extend(loop_report)
    learning = friday_learning_loop.learn_from_run_outcome(
        str(state.get("request") or ""),
        root=project_root,
        design_handoff=design_handoff,
        gate_results=gate_results,
        quality_reviews=quality_reviews,
        fix_attempts=fix_attempts,
        failure_autopsies=failure_autopsies,
        source="product_build_loop",
    )
    artifacts.extend(learning.get("artifacts") or [])
    _phase(phases, "prove", "completed", "Implementation loop report written.", evidence=loop_report)
    return {
        "artifacts": _dedupe(artifacts),
        "phases": phases,
        "learning": learning,
    }


def required_design_handoff_blockers(design_handoff: dict[str, Any], *, run_live: bool) -> list[str]:
    if not run_live:
        return []
    if bool(design_handoff.get("ok")):
        return []
    blockers: list[str] = []
    summary = _clean(design_handoff.get("summary") or "")
    if summary:
        blockers.append(f"Design provider handoff blocked: {summary}")
    critique = design_handoff.get("design_critique") if isinstance(design_handoff.get("design_critique"), dict) else {}
    for page in critique.get("pages") or []:
        if not isinstance(page, dict) or page.get("frontend_handoff_allowed"):
            continue
        label = _clean(page.get("label") or page.get("id") or "page")
        status = _clean(page.get("status") or "blocked")
        page_summary = _clean(page.get("summary") or "")
        blockers.append(f"{label} design handoff {status}: {page_summary or 'no selected provider handoff'}")
    return _dedupe(blockers or ["Design provider handoff is required before executable gates and UI-ready claims."])


def blocked_design_gate_results(project_root: Path, *, stack: dict[str, Any], blockers: list[str], artifacts: list[str] | None = None) -> dict[str, Any]:
    gate_root = project_root / FRIDAY_DIR / STUDIO_DIR / "gates"
    gate_root.mkdir(parents=True, exist_ok=True)
    gate_path = gate_root / "gate-results.json"
    gate = {
        "id": "design_provider_handoff",
        "label": "Design provider handoff",
        "group": "design",
        "status": "blocked",
        "required": True,
        "summary": blockers[0] if blockers else "Configured design provider did not produce a selected handoff.",
    }
    result = {
        "attempted": True,
        "root": str(project_root),
        "status": "blocked",
        "summary": "Executable gates were skipped because the required design-provider handoff did not succeed.",
        "technical_ready": False,
        "market_ready": False,
        "preview_url": "",
        "approval_gates_cleared": False,
        "failed_required": blockers or [gate["summary"]],
        "gates": [gate],
        "required_gate_statuses": [gate],
        "artifacts": [str(gate_path), *[str(item) for item in (artifacts or []) if str(item).strip()]],
        "stack": stack,
    }
    gate_path.write_text(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return result


def _design_revision_needed(review: dict[str, Any]) -> bool:
    issue_ids = {
        str(item.get("id") or "")
        for item in (review.get("issues") if isinstance(review.get("issues"), list) else [])
        if isinstance(item, dict)
    }
    return bool(
        issue_ids
        & {
            "visual_incoherent_copy",
            "visual_wrong_hero_imagery",
            "visual_shallow_landing_page",
            "generic_scaffold_copy",
            "missing_domain_copy",
            "stitch_page_label_artifacts",
            "design_handoff_blocked",
        }
    )


def _revise_design_handoff(
    project_root: Path,
    request: str,
    *,
    product_name: str,
    stack: dict[str, Any],
    review: dict[str, Any],
) -> dict[str, Any]:
    issues = [
        _clean(item.get("summary") or item.get("id") or "")
        for item in (review.get("issues") if isinstance(review.get("issues"), list) else [])
        if isinstance(item, dict)
    ][:6]
    feedback = (
        "\n\nDesign revision required by Friday visual/taste review. "
        "Regenerate the design from scratch and do not reuse the rejected composition. "
        f"Rejected issues: {'; '.join(issues) if issues else 'visual/taste review failed'}. "
        "Non-negotiable: use coherent human-written headlines, product/code/docs/architecture proof for developer tools, "
        "full landing-page section depth, no stock/person portrait hero imagery, no placeholder copy, no page-label artifacts, "
        "and production web scale."
    )
    revised = product_studio.prepare_design_handoff(
        project_root,
        f"{request}{feedback}",
        product_name=product_name,
        stack=stack,
        run_live=True,
        apply_to_source=True,
    )
    applied = revised.get("applied_design") if isinstance(revised.get("applied_design"), dict) else {}
    changed = [str(item) for item in (applied.get("files") or []) if str(item).strip()]
    return {
        "ok": bool(revised.get("ok")),
        "status": "design_revision_applied" if revised.get("ok") else "design_revision_blocked",
        "summary": revised.get("summary") or "Design revision attempted from visual/taste critique.",
        "design_handoff": revised,
        "changed": changed,
        "artifacts": [str(item) for item in (revised.get("artifacts") or []) if str(item).strip()],
    }


def _default_gate_runner(project_root: Path, *, stack: dict[str, Any], install: bool, request: str) -> dict[str, Any]:
    return product_studio_gates.execute_gates(project_root, stack=stack, install=install, request=request)


def _write_loop_report(
    project_root: Path,
    phases: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    design_handoff: dict[str, Any],
    gate_results: dict[str, Any],
    quality_reviews: list[dict[str, Any]],
    fix_attempts: list[dict[str, Any]],
    *,
    failure_autopsies: list[dict[str, Any]] | None = None,
) -> list[str]:
    root = project_root / FRIDAY_DIR / STUDIO_DIR / LOOP_DIR
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "implementation-loop.json"
    md_path = root / "implementation-loop.md"
    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "phases": phases,
        "attempts": attempts,
        "design_handoff_status": design_handoff.get("status"),
        "gate_status": gate_results.get("status"),
        "technical_ready": bool(gate_results.get("technical_ready")),
        "quality_status": quality_reviews[-1].get("status") if quality_reviews else "",
        "quality_score": quality_reviews[-1].get("score") if quality_reviews else None,
        "fix_attempts": fix_attempts,
        "failure_autopsies": failure_autopsies or [],
        "summary": "Friday loop evidence for inspect -> plan -> implement -> run -> see -> fix -> prove.",
    }
    json_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    md_path.write_text(_loop_markdown(report), encoding="utf-8")
    return [str(json_path), str(md_path)]


def _loop_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Friday Implementation Loop",
        "",
        str(report.get("summary") or ""),
        "",
        f"Design handoff: {report.get('design_handoff_status')}",
        f"Gate status: {report.get('gate_status')}",
        f"Technical ready: {bool(report.get('technical_ready'))}",
        f"Quality: {report.get('quality_status')} ({report.get('quality_score')})",
        "",
        "## Phases",
    ]
    for phase in report.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        lines.append(f"- {phase.get('id')}: {phase.get('status')} - {phase.get('summary')}")
    autopsies = report.get("failure_autopsies") if isinstance(report.get("failure_autopsies"), list) else []
    if autopsies:
        lines.extend(["", "## Failure Hypotheses"])
        for item in autopsies[:8]:
            if not isinstance(item, dict):
                continue
            hypothesis = item.get("hypothesis") if isinstance(item.get("hypothesis"), dict) else {}
            lines.append(f"- {hypothesis.get('summary') or item.get('summary') or 'Failure autopsy recorded.'}")
    return "\n".join(lines) + "\n"


def _phase(phases: list[dict[str, Any]], phase_id: str, status: str, summary: str, *, evidence: list[Any] | None = None) -> None:
    phases.append({"id": phase_id, "status": status, "summary": _clean(summary), "evidence": [str(item) for item in (evidence or []) if _clean(item)]})


def _gate_tested(gate_results: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for gate in gate_results.get("gates") or []:
        if not isinstance(gate, dict):
            continue
        label = _clean(gate.get("label") or gate.get("id") or "gate")
        status = _clean(gate.get("status") or "unknown")
        summary = _clean(gate.get("summary") or "")
        items.append(f"{label}: {status}" + (f" - {summary}" if summary else ""))
    return items


def _autopsy_failed_gates(project_root: Path, gate_results: dict[str, Any], *, attempt: int) -> list[dict[str, Any]]:
    autopsies: list[dict[str, Any]] = []
    for gate in gate_results.get("gates") or []:
        if not isinstance(gate, dict) or not gate.get("required"):
            continue
        if str(gate.get("status") or "") == "passed":
            continue
        failure = {
            "gate_id": gate.get("id"),
            "label": gate.get("label"),
            "status": gate.get("status"),
            "summary": gate.get("summary"),
            "command": gate.get("command"),
            "output_tail": gate.get("output_tail"),
            "log_path": gate.get("log_path"),
            "attempt": attempt,
        }
        try:
            autopsies.append(failure_autopsy_engine.autopsy(failure, root=project_root, source="product_build_loop", remember=True))
        except Exception as exc:
            autopsies.append({"summary": f"Failure autopsy could not run: {exc}", "failure": failure})
    return autopsies


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        text = _clean(item)
        if text and text not in result:
            result.append(text)
    return result


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())
