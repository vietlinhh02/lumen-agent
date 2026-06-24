"""Tests for T3 Phase 4 — report citation PDF path resolution."""

from __future__ import annotations

from types import SimpleNamespace

import app.core.config as config
from app.services import report_generation as rg
from app.services.pdf_downloader import _make_filename
from app.sources.base import RawPaper


def _paper():
    return SimpleNamespace(
        title="Retrieval-Augmented Generation for QA",
        abstract=None,
        year=2024,
        venue=None,
        doi="10.1234/ragqa",
        arxiv_id=None,
        semantic_scholar_id=None,
        url=None,
        citation_count=None,
        authors=[],
    )


def _expected_filename(paper) -> str:
    raw = RawPaper(
        title=paper.title,
        abstract=paper.abstract,
        year=paper.year,
        venue=paper.venue,
        doi=paper.doi,
        arxiv_id=paper.arxiv_id,
        semantic_scholar_id=paper.semantic_scholar_id,
        url=paper.url,
        citation_count=paper.citation_count,
        authors=paper.authors,
    )
    return _make_filename(raw)


def test_reference_pdf_path_returns_url_when_file_exists(tmp_path, monkeypatch):
    paper = _paper()
    filename = _expected_filename(paper)
    (tmp_path / filename).write_bytes(b"%PDF-1.4 fake pdf bytes")

    monkeypatch.setattr(
        config, "get_settings", lambda: SimpleNamespace(paper_pdf_dir=str(tmp_path))
    )

    assert rg._reference_pdf_path(paper) == f"/api/pdf-files/{filename}"


def test_reference_pdf_path_none_when_file_missing(tmp_path, monkeypatch):
    paper = _paper()
    # No file written to tmp_path → no served PDF.
    monkeypatch.setattr(
        config, "get_settings", lambda: SimpleNamespace(paper_pdf_dir=str(tmp_path))
    )

    assert rg._reference_pdf_path(paper) is None


def test_reference_pdf_path_none_when_file_empty(tmp_path, monkeypatch):
    paper = _paper()
    filename = _expected_filename(paper)
    (tmp_path / filename).write_bytes(b"")  # zero-byte → treated as absent

    monkeypatch.setattr(
        config, "get_settings", lambda: SimpleNamespace(paper_pdf_dir=str(tmp_path))
    )

    assert rg._reference_pdf_path(paper) is None
