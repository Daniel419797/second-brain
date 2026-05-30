from pathlib import Path

from core import document_intelligence


def test_document_intelligence_generates_and_reads_md_docx_pdf(tmp_path):
    markdown = "# Launch Plan\n\n- Build the product.\n- Verify the gates.\n"

    generated = document_intelligence.generate_document(
        "Launch Plan",
        markdown,
        root=tmp_path,
        filename="launch-plan",
        formats=["md", "docx", "pdf"],
    )

    assert set(generated["paths"]) == {"md", "docx", "pdf"}
    assert Path(generated["paths"]["md"]).exists()
    assert Path(generated["paths"]["docx"]).exists()
    assert Path(generated["paths"]["pdf"]).read_bytes().startswith(b"%PDF-1.4")

    md = document_intelligence.read_document(generated["paths"]["md"])
    docx = document_intelligence.read_document(generated["paths"]["docx"])
    pdf = document_intelligence.read_document(generated["paths"]["pdf"])

    assert md["ok"] is True
    assert "Launch Plan" in md["text"]
    assert docx["ok"] is True
    assert "Build the product" in docx["text"]
    assert pdf["kind"] == "pdf"
    assert pdf["path"].endswith(".pdf")


def test_document_intelligence_rejects_unsupported_file(tmp_path):
    path = tmp_path / "binary.exe"
    path.write_bytes(b"nope")

    result = document_intelligence.read_document(path)

    assert result["ok"] is False
    assert "Unsupported" in result["summary"]
