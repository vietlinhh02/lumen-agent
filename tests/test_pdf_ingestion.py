import subprocess
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import pdf_ingestion


class FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


@pytest.mark.asyncio
async def test_extract_text_prefers_poppler_when_output_is_usable(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF")
    poppler_text = "Title\n\nAbstract\n" + "Poppler keeps readable spacing. " * 4

    monkeypatch.setattr(pdf_ingestion.shutil, "which", lambda name: "/usr/bin/pdftotext")
    monkeypatch.setattr(
        pdf_ingestion.subprocess,
        "run",
        lambda *args, **kwargs: FakeCompletedProcess(poppler_text),
    )
    monkeypatch.setattr(pdf_ingestion, "_extract_text_pypdf", lambda path: "pypdf fallback text")

    text = await pdf_ingestion._extract_text(pdf_path)

    assert text == poppler_text.strip()


@pytest.mark.asyncio
async def test_extract_text_falls_back_to_pypdf_when_poppler_is_too_short(
    monkeypatch,
    tmp_path,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF")
    pypdf_text = "Title\n\nAbstract\n" + "pypdf fallback still has enough text. " * 4

    monkeypatch.setattr(pdf_ingestion.shutil, "which", lambda name: "/usr/bin/pdftotext")
    monkeypatch.setattr(
        pdf_ingestion.subprocess,
        "run",
        lambda *args, **kwargs: FakeCompletedProcess("short"),
    )
    monkeypatch.setattr(pdf_ingestion, "_extract_text_pypdf", lambda path: pypdf_text)

    text = await pdf_ingestion._extract_text(pdf_path)

    assert text == pypdf_text


@pytest.mark.asyncio
async def test_extract_text_uses_ocr_when_local_extractors_fail(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF")

    monkeypatch.setattr(pdf_ingestion.shutil, "which", lambda name: None)
    monkeypatch.setattr(pdf_ingestion, "_extract_text_pypdf", lambda path: None)

    async def fake_ocr(path):
        return "OCR text from scanned document."

    monkeypatch.setattr(pdf_ingestion, "_extract_text_ocr", fake_ocr)

    text = await pdf_ingestion._extract_text(pdf_path)

    assert text == "OCR text from scanned document."


def test_poppler_extractor_returns_none_when_command_fails(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF")

    monkeypatch.setattr(pdf_ingestion.shutil, "which", lambda name: "/usr/bin/pdftotext")

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="pdftotext", timeout=30)

    monkeypatch.setattr(pdf_ingestion.subprocess, "run", raise_timeout)

    assert pdf_ingestion._extract_text_poppler(pdf_path) is None


@pytest.mark.asyncio
async def test_store_chunks_persists_embedding_as_vector_list(monkeypatch) -> None:
    added = []

    class FakeDb:
        async def execute(self, stmt):
            return None

        def add(self, obj):
            added.append(obj)

        async def commit(self):
            return None

    monkeypatch.setattr(
        "app.core.embeddings.get_embedding_dimension",
        lambda: 2000,
    )
    monkeypatch.setattr(
        "app.core.embeddings.get_embedding_model_name",
        lambda: "test-embedding-model",
    )

    embedding = [0.1] * 2000
    chunk = pdf_ingestion.Chunk(
        text="A method chunk",
        section_label="Method",
        embedding=embedding,
    )

    await pdf_ingestion._store_chunks(cast(AsyncSession, FakeDb()), uuid4(), [chunk])

    assert added
    assert added[0].embedding is embedding
    assert not isinstance(added[0].embedding, str)
    assert added[0].embedding_dimension == 2000
