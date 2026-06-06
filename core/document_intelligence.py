"""Friday document reading and generation for MD, DOCX, and PDF files."""

from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path
from typing import Any

from core import document_exports, document_knowledge
from core.config import resolve_coding_root

READABLE_EXTENSIONS = {".md", ".markdown", ".txt", ".pdf", ".docx"}
GENERATABLE_FORMATS = {"md", "docx", "pdf"}


def capabilities() -> dict[str, Any]:
    return {
        "read": sorted(READABLE_EXTENSIONS),
        "generate": sorted(GENERATABLE_FORMATS),
        "knowledge": document_knowledge.capabilities(),
        "summary": "Friday can read Markdown/text, DOCX, and PDF documents, and generate Markdown, DOCX, and PDF from Markdown content.",
    }


def read_document(path: str | Path, *, max_chars: int = 12000) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    if not target.exists() or not target.is_file():
        return {"ok": False, "path": str(target), "text": "", "summary": "Document not found."}
    suffix = target.suffix.lower()
    if suffix not in READABLE_EXTENSIONS:
        return {"ok": False, "path": str(target), "text": "", "summary": f"Unsupported document type: {suffix}."}
    if suffix in {".md", ".markdown", ".txt"}:
        text = _read_text(target, max_chars=max_chars)
        kind = "markdown" if suffix in {".md", ".markdown"} else "text"
    elif suffix == ".docx":
        text = _read_docx(target, max_chars=max_chars)
        kind = "docx"
    else:
        text = _read_pdf(target, max_chars=max_chars)
        kind = "pdf"
    return {
        "ok": bool(text),
        "path": str(target),
        "name": target.name,
        "kind": kind,
        "extension": suffix,
        "text": text,
        "characters": len(text),
        "summary": _summary(target.name, kind, text),
    }


def generate_document(
    title: str,
    markdown: str,
    *,
    root: str | Path = "",
    filename: str = "",
    formats: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    base = resolve_coding_root(root) / ".friday" / "documents"
    safe_name = _slug(filename or title or "friday-document")
    output_base = base / safe_name
    export = document_exports.export_markdown(_with_title(title, markdown), output_base, formats=_formats(formats))
    return {
        "ok": bool(export.get("paths")),
        "title": title,
        "root": str(base),
        "paths": export.get("paths") or {},
        "formats": export.get("formats") or [],
        "summary": export.get("summary") or "Document generation complete.",
    }


def index_documents(
    paths: list[str] | tuple[str, ...],
    *,
    root: str | Path = "",
    query: str = "",
    max_chars: int = 60000,
) -> dict[str, Any]:
    documents = []
    failures = []
    for item in paths:
        result = read_document(item, max_chars=max_chars)
        if result.get("ok"):
            documents.append(result)
        else:
            failures.append({"path": str(item), "summary": result.get("summary") or "Document could not be read."})
    indexed = document_knowledge.index_texts(documents, root=root, query=query)
    indexed["failures"] = failures
    indexed["paths"] = [str(item) for item in paths]
    if failures:
        indexed["summary"] = f"{indexed['summary']} {len(failures)} document(s) could not be indexed."
    return indexed


def _read_text(path: Path, *, max_chars: int) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""


def _read_docx(path: Path, *, max_chars: int) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    except Exception:
        return ""
    paragraphs = re.findall(r"<w:p\b.*?</w:p>", xml, flags=re.DOTALL)
    lines: list[str] = []
    for paragraph in paragraphs:
        texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", paragraph, flags=re.DOTALL)
        line = html.unescape("".join(texts))
        if line.strip():
            lines.append(line.strip())
    return "\n".join(lines)[:max_chars]


def _read_pdf(path: Path, *, max_chars: int) -> str:
    try:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(str(path))
        return _clean(" ".join((page.extract_text() or "") for page in reader.pages))[:max_chars]
    except Exception:
        try:
            import PyPDF2  # type: ignore

            reader = PyPDF2.PdfReader(str(path))
            return _clean(" ".join((page.extract_text() or "") for page in reader.pages))[:max_chars]
        except Exception:
            return ""


def _with_title(title: str, markdown: str) -> str:
    text = str(markdown or "").strip()
    if text.startswith("#"):
        return text + "\n"
    clean_title = _clean(title) or "Friday Document"
    return f"# {clean_title}\n\n{text}\n"


def _formats(formats: list[str] | tuple[str, ...] | None) -> list[str]:
    values = [str(item or "").strip().lower().lstrip(".") for item in (formats or ["md", "docx", "pdf"])]
    selected = [item for item in values if item in GENERATABLE_FORMATS]
    return selected or ["md", "docx", "pdf"]


def _summary(name: str, kind: str, text: str) -> str:
    if not text:
        return f"{kind.upper()} document {name} could not be read."
    excerpt = _clean(text)[:220]
    return f"Read {kind.upper()} document {name}: {excerpt}"


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _clean(value).lower()).strip("-") or "friday-document"


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()
