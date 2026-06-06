from pathlib import Path

from core import document_intelligence, document_knowledge


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


def test_document_intelligence_indexes_documents_with_native_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(document_knowledge, "_load_llama_index", lambda: {"available": False, "error": "missing"})
    path = tmp_path / "requirements.md"
    path.write_text("# Requirements\n\nFriday must verify gates and attach proof before claiming done.", encoding="utf-8")

    result = document_intelligence.index_documents([str(path)], root=tmp_path, query="verify proof gates")

    assert result["ok"] is True
    assert result["backend"] == "native"
    assert result["chunks"] >= 1
    assert result["top_chunks"]
    assert Path(result["artifact"]).exists()
    assert "proof" in result["top_chunks"][0]["text"].lower()


def test_document_knowledge_uses_llama_index_when_available(monkeypatch, tmp_path):
    class FakeDocument:
        def __init__(self, text, metadata):
            self.text = text
            self.metadata = metadata

    class FakeNode:
        def __init__(self, text, metadata):
            self._text = text
            self.metadata = metadata

        def get_content(self):
            return self._text

    class FakeSentenceSplitter:
        def __init__(self, chunk_size, chunk_overlap):
            self.chunk_size = chunk_size
            self.chunk_overlap = chunk_overlap

        def get_nodes_from_documents(self, docs):
            return [FakeNode(f"llama chunk: {doc.text}", doc.metadata) for doc in docs]

    monkeypatch.setattr(
        document_knowledge,
        "_load_llama_index",
        lambda: {
            "available": True,
            "Document": FakeDocument,
            "SentenceSplitter": FakeSentenceSplitter,
            "error": "",
        },
    )
    monkeypatch.setattr(document_knowledge, "config_value", lambda key, default=None: "auto" if key == "document_knowledge_backend" else default)

    result = document_knowledge.index_texts(
        [{"path": str(tmp_path / "brief.md"), "name": "brief.md", "kind": "markdown", "text": "Design proof and verification rules."}],
        root=tmp_path,
        query="verification",
    )

    assert result["backend"] == "llama_index"
    assert result["llama_index_available"] is True
    assert result["top_chunks"][0]["text"].startswith("llama chunk")
