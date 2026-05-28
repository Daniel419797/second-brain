"""Local document export helpers for Markdown, DOCX, and PDF outputs."""

from __future__ import annotations

import html
import re
import textwrap
import zipfile
from pathlib import Path
from typing import Any


def export_markdown(markdown: str, output_base: str | Path, *, formats: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    base = Path(output_base)
    base.parent.mkdir(parents=True, exist_ok=True)
    wanted = _formats(formats)
    paths: dict[str, str] = {}
    if "md" in wanted:
        md_path = base.with_suffix(".md")
        md_path.write_text(str(markdown or "").strip() + "\n", encoding="utf-8")
        paths["md"] = str(md_path)
    if "docx" in wanted:
        paths["docx"] = str(write_docx(markdown, base.with_suffix(".docx")))
    if "pdf" in wanted:
        paths["pdf"] = str(write_pdf(markdown, base.with_suffix(".pdf")))
    return {"paths": paths, "formats": sorted(paths), "summary": _summary(paths)}


def export_markdown_file(path: str | Path, *, formats: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    source = Path(path).expanduser()
    markdown = source.read_text(encoding="utf-8", errors="ignore")
    return export_markdown(markdown, source.with_suffix(""), formats=formats)


def write_docx(markdown: str, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    document_xml = _document_xml(_blocks(markdown))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        archive.writestr("word/styles.xml", _STYLES)
        archive.writestr("word/document.xml", document_xml)
    return output


def write_pdf(markdown: str, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    pages = _pdf_pages(markdown)
    output.write_bytes(_pdf_bytes(pages))
    return output


def _formats(formats: list[str] | tuple[str, ...] | None) -> set[str]:
    raw = formats or ["md", "docx", "pdf"]
    allowed = {"md", "docx", "pdf"}
    values = {str(item).strip().lower().lstrip(".") for item in raw if str(item).strip()}
    return values & allowed or {"md", "docx", "pdf"}


def _summary(paths: dict[str, str]) -> str:
    if not paths:
        return "No document exports were created."
    parts = [f"{fmt.upper()}: {path}" for fmt, path in paths.items()]
    return "Document exports created. " + " ".join(parts)


def _blocks(markdown: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for raw in str(markdown or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            blocks.append({"kind": "blank", "text": ""})
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            blocks.append({"kind": "heading", "level": len(heading.group(1)), "text": heading.group(2).strip()})
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet:
            blocks.append({"kind": "bullet", "text": bullet.group(1).strip()})
            continue
        numbered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if numbered:
            blocks.append({"kind": "numbered", "text": numbered.group(1).strip()})
            continue
        blocks.append({"kind": "paragraph", "text": stripped})
    return blocks


def _document_xml(blocks: list[dict[str, Any]]) -> str:
    body = []
    for block in blocks:
        kind = block["kind"]
        text = str(block.get("text") or "")
        if kind == "blank":
            body.append("<w:p/>")
        elif kind == "heading":
            style = f"Heading{min(3, int(block.get('level') or 1))}"
            body.append(_paragraph(text, style=style))
        elif kind == "bullet":
            body.append(_paragraph(f"- {text}"))
        elif kind == "numbered":
            body.append(_paragraph(text))
        else:
            body.append(_paragraph(text))
    body.append(
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        'xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:w10="urn:schemas-microsoft-com:office:word" '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
        'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
        'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" '
        'xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" '
        'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" mc:Ignorable="w14 wp14">'
        f"<w:body>{''.join(body)}</w:body></w:document>"
    )


def _paragraph(text: str, *, style: str = "") -> str:
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{props}<w:r><w:t xml:space=\"preserve\">{html.escape(_strip_markdown(text))}</w:t></w:r></w:p>"


def _pdf_pages(markdown: str) -> list[list[tuple[str, int]]]:
    pages: list[list[tuple[str, int]]] = [[]]
    line_count = 0
    for block in _blocks(markdown):
        kind = block["kind"]
        if kind == "blank":
            line_count = _append_pdf_line(pages, "", 12, line_count)
            continue
        text = _strip_markdown(str(block.get("text") or ""))
        if kind == "heading":
            size = 18 if int(block.get("level") or 1) == 1 else 15
            line_count = _append_pdf_line(pages, text, size, line_count)
        elif kind == "bullet":
            for wrapped in textwrap.wrap("- " + text, width=88) or ["- " + text]:
                line_count = _append_pdf_line(pages, wrapped, 11, line_count)
        else:
            for wrapped in textwrap.wrap(text, width=92) or [text]:
                line_count = _append_pdf_line(pages, wrapped, 11, line_count)
    return pages


def _append_pdf_line(pages: list[list[tuple[str, int]]], text: str, size: int, line_count: int) -> int:
    if line_count >= 48:
        pages.append([])
        line_count = 0
    pages[-1].append((text, size))
    return line_count + (2 if size >= 15 else 1)


def _pdf_bytes(pages: list[list[tuple[str, int]]]) -> bytes:
    objects: list[bytes] = []

    def add(obj: str | bytes) -> int:
        data = obj.encode("latin-1", errors="replace") if isinstance(obj, str) else obj
        objects.append(data)
        return len(objects)

    catalog_id = add("<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = add("placeholder")
    font_id = add("<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>")
    page_ids: list[int] = []
    for page in pages or [[]]:
        stream = _pdf_stream(page)
        content_id = add(f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream")
        page_id = add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>")
        page_ids.append(page_id)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{pid} 0 R' for pid in page_ids)}] /Count {len(page_ids)} >>".encode("latin-1")

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("latin-1"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1"))
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("latin-1"))
    return bytes(output)


def _pdf_stream(lines: list[tuple[str, int]]) -> bytes:
    y = 740
    chunks = []
    for text, size in lines:
        chunks.append(f"BT /F1 {size} Tf 72 {y} Td ({_pdf_escape(text)}) Tj ET")
        y -= 22 if size >= 15 else 15
    return "\n".join(chunks).encode("latin-1", errors="replace")


def _strip_markdown(text: str) -> str:
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", str(text or ""))
    cleaned = re.sub(r"\*(.*?)\*", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    return cleaned


def _pdf_escape(text: str) -> str:
    return _strip_markdown(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>"""

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="200" w:after="100"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="160" w:after="80"/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>
</w:styles>"""
