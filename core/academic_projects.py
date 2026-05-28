"""Source-backed academic project and paper drafting workflow."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from core import document_exports, llm, research
from core.config import DATA_DIR, ROOT_DIR, config_value

DEFAULT_DIR = DATA_DIR / "academic_projects"


def create_project(
    topic: str,
    *,
    kind: str = "final_year_project",
    citation_style: str = "APA",
    formats: list[str] | tuple[str, ...] | str | None = None,
    max_sources: int | None = None,
    extra_requirements: str = "",
) -> dict[str, Any]:
    clean_topic = _clean(topic)
    if not clean_topic:
        raise ValueError("topic is required")
    project_kind = _kind(kind)
    source_limit = max_sources if max_sources is not None else int(config_value("academic_project_max_sources", 5))
    source_report = research.research_topic(clean_topic, limit=max(1, int(source_limit)))
    sources = _sources(source_report)
    notes_md = _research_notes(clean_topic, project_kind, citation_style, sources, str(source_report.get("notes") or ""))
    draft_md = _draft(clean_topic, project_kind, citation_style, sources, notes_md, extra_requirements=extra_requirements)
    root = _project_dir(clean_topic, project_kind)
    root.mkdir(parents=True, exist_ok=True)
    notes_path = root / "source-notes.md"
    draft_path = root / "draft.md"
    notes_path.write_text(notes_md, encoding="utf-8")
    draft_path.write_text(draft_md, encoding="utf-8")
    export = document_exports.export_markdown(draft_md, root / "project", formats=_formats(formats))
    manifest = {
        "topic": clean_topic,
        "kind": project_kind,
        "citation_style": citation_style,
        "created_at": _now(),
        "source_count": len(sources),
        "source_notes": str(notes_path),
        "draft": str(draft_path),
        "exports": export.get("paths", {}),
        "integrity_note": "Draft uses the gathered source register only; verify citations and institutional formatting before submission.",
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
    manifest["manifest"] = str(manifest_path)
    manifest["summary"] = _summary(manifest)
    return manifest


def export_project(markdown_path: str | Path, *, formats: list[str] | tuple[str, ...] | str | None = None) -> dict[str, Any]:
    export = document_exports.export_markdown_file(markdown_path, formats=_formats(formats))
    return export | {"summary": export.get("summary", "Document exported.")}


def _draft(
    topic: str,
    kind: str,
    citation_style: str,
    sources: list[dict[str, str]],
    notes_md: str,
    *,
    extra_requirements: str = "",
) -> str:
    if bool(config_value("academic_project_llm_enabled", True)):
        prompt = _draft_prompt(topic, kind, citation_style, sources, notes_md, extra_requirements)
        providers = str(config_value("academic_project_provider_chain", "nvidia>ollama"))
        try:
            generated = llm.ask_simple_with_provider_chain(prompt, providers, retries=1) or ""
        except Exception:
            generated = ""
        cleaned = _clean_markdown(generated)
        if cleaned:
            return cleaned
    return _fallback_draft(topic, kind, citation_style, sources, extra_requirements=extra_requirements)


def _draft_prompt(topic: str, kind: str, citation_style: str, sources: list[dict[str, str]], notes_md: str, extra_requirements: str) -> str:
    source_lines = "\n".join(
        f"[S{index}] {source['title']} - {source['url']}\nSnippet: {source['snippet'][:700]}"
        for index, source in enumerate(sources, start=1)
    ) or "No live sources were found."
    return (
        "Write an academic draft in Markdown for the user. Return only Markdown.\n"
        "Rules: use only the provided source register for citations; do not fabricate authors, years, page numbers, URLs, or references. "
        "When evidence is missing, write a Source gap note. Keep wording original and suitable for the user to revise.\n"
        f"Document type: {kind.replace('_', ' ')}\n"
        f"Topic: {topic}\n"
        f"Citation style: {citation_style}\n"
        f"Extra requirements: {_clean(extra_requirements) or 'none'}\n\n"
        f"Source register:\n{source_lines}\n\n"
        f"Research notes:\n{notes_md[:6000]}"
    )


def _fallback_draft(topic: str, kind: str, citation_style: str, sources: list[dict[str, str]], *, extra_requirements: str = "") -> str:
    refs = _reference_section(sources, citation_style)
    source_note = _source_note(sources)
    if kind == "research_paper":
        return f"""# {topic}

## Abstract
This draft examines {topic}. It is structured as a source-backed starting point and should be expanded with verified institutional requirements, primary data, and supervisor feedback.

## Keywords
{_keywords(topic)}

## Introduction
{topic} is an important research area because it connects practical implementation with measurable academic inquiry. {source_note}

## Related Work
The gathered sources provide initial context for the topic. Use this section to compare methods, findings, limitations, and unresolved questions from the source register.

## Methodology
This study can use a mixed workflow: source review, requirements analysis, prototype or model design where relevant, and evaluation against clear criteria.

## Discussion
The discussion should connect evidence from the source register with the proposed research questions. Any unsupported claim should be marked as a source gap until verified.

## Conclusion
This paper draft provides a defensible structure for {topic}, but final submission should include verified citations, stronger evidence, and institution-specific formatting.

{refs}
"""
    if kind == "proposal":
        return f"""# Project Proposal: {topic}

## Background
{topic} is proposed as an academic project with practical and research value. {source_note}

## Problem Statement
There is a need to define the problem clearly, identify affected users or stakeholders, and justify why the proposed work matters.

## Aim
To design and document a source-backed project on {topic}.

## Objectives
- Review relevant literature and existing solutions.
- Define system or research requirements.
- Design a feasible methodology.
- Produce implementation, evaluation, and documentation plans.

## Methodology
The project will combine literature review, requirements analysis, design, implementation or analytical work, testing, and final evaluation.

## Expected Outcome
The expected outcome is a completed academic project package with documentation, evidence, and deliverables suitable for supervisor review.

{refs}
"""
    return f"""# Final Year Project: {topic}

## Abstract
This final year project draft presents {topic} as a structured academic and practical work. It includes a source-backed foundation, a proposed methodology, and a project structure that should be revised with supervisor feedback.

## Chapter One: Introduction
### Background of the Study
{topic} sits at the intersection of academic inquiry and practical problem solving. {source_note}

### Statement of the Problem
The problem should be framed around a clear gap, pain point, or inefficiency that the project can investigate or solve.

### Aim and Objectives
The aim is to design, develop, or investigate {topic}.

Objectives:
- Review relevant literature and existing systems.
- Identify requirements and constraints.
- Design a suitable solution or research method.
- Implement or analyze the proposed approach.
- Evaluate results and document limitations.

### Scope of the Study
This project should define what is included, what is excluded, and the assumptions used during development or research.

### Significance of the Study
The project can help students, researchers, developers, or organizations understand and apply the topic in a structured way.

## Chapter Two: Literature Review
Use the source register below as the starting point. Compare each source by purpose, method, findings, and limitations. Do not add unsupported citations.

## Chapter Three: Methodology
The methodology should describe research design, tools, data sources, system architecture where relevant, implementation steps, and evaluation metrics.

## Chapter Four: Implementation and Results
Document the implemented system or analysis, screenshots or tables where applicable, test cases, and results.

## Chapter Five: Summary, Conclusion, and Recommendations
Summarize the work, explain limitations, and recommend future improvements.

{refs}
"""


def _research_notes(topic: str, kind: str, citation_style: str, sources: list[dict[str, str]], notes: str) -> str:
    lines = [
        f"# Source Notes: {topic}",
        "",
        f"- Document type: {kind.replace('_', ' ')}",
        f"- Citation style: {citation_style}",
        "- Integrity rule: use only verified sources; mark missing evidence as a source gap.",
        "",
        "## Fresh Research Notes",
        notes.strip() or "No fresh research notes were returned.",
        "",
        "## Source Register",
    ]
    if not sources:
        lines.append("- No live sources found. Add verified academic or official sources before final submission.")
    for index, source in enumerate(sources, start=1):
        lines.append(f"- [S{index}] {source['title']} - {source['url']}")
        if source.get("snippet"):
            lines.append(f"  - Snippet: {source['snippet'][:500]}")
    return "\n".join(lines).strip() + "\n"


def _reference_section(sources: list[dict[str, str]], citation_style: str) -> str:
    lines = [f"## References ({citation_style})"]
    if not sources:
        lines.append("- Source gap: add verified academic or official sources.")
    for index, source in enumerate(sources, start=1):
        title = source.get("title") or f"Source {index}"
        url = source.get("url") or "URL unavailable"
        lines.append(f"- [S{index}] {title}. {url}")
    return "\n".join(lines)


def _sources(report: dict[str, Any]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for source in report.get("sources") or []:
        title = _clean(source.get("title") or "Untitled source")
        url = _clean(source.get("url") or "")
        snippet = _clean(source.get("text") or source.get("snippet") or "")
        if title or url or snippet:
            output.append({"title": title or "Untitled source", "url": url, "snippet": snippet})
    return output


def _project_dir(topic: str, kind: str) -> Path:
    root = _root_dir()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return root / f"{_slug(kind)}-{_slug(topic)[:60]}-{stamp}"


def _root_dir() -> Path:
    raw = str(config_value("academic_projects_dir", "") or "").strip()
    if not raw:
        return DEFAULT_DIR
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _formats(value: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(";", ",").split(",")
    elif value is None:
        raw = str(config_value("academic_project_formats", "md,docx,pdf")).split(",")
    else:
        raw = list(value)
    formats = [str(item).strip().lower().lstrip(".") for item in raw if str(item).strip()]
    return formats or ["md", "docx", "pdf"]


def _kind(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    aliases = {
        "fyp": "final_year_project",
        "final_project": "final_year_project",
        "final_year": "final_year_project",
        "final_year_project": "final_year_project",
        "research": "research_paper",
        "paper": "research_paper",
        "research_paper": "research_paper",
        "proposal": "proposal",
        "project_proposal": "proposal",
        "literature_review": "research_paper",
        "thesis": "final_year_project",
    }
    return aliases.get(lowered, lowered or "final_year_project")


def _source_note(sources: list[dict[str, str]]) -> str:
    if not sources:
        return "Current source gap: no live sources were found, so claims need verification before submission."
    refs = ", ".join(f"[S{index}]" for index in range(1, min(4, len(sources)) + 1))
    return f"Initial evidence is available in the source register ({refs})."


def _keywords(topic: str) -> str:
    words = [word.lower() for word in re.findall(r"[A-Za-z0-9]+", topic) if len(word) > 2]
    unique = []
    for word in words:
        if word not in unique:
            unique.append(word)
    return ", ".join(unique[:6]) or "research, project"


def _summary(manifest: dict[str, Any]) -> str:
    exports = manifest.get("exports") or {}
    docx = exports.get("docx", "")
    pdf = exports.get("pdf", "")
    return (
        f"Academic {manifest['kind'].replace('_', ' ')} draft ready with {manifest['source_count']} source(s). "
        f"DOCX: {docx or 'not requested'}. PDF: {pdf or 'not requested'}."
    )


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_markdown(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown|md)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug[:90] or "untitled"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
