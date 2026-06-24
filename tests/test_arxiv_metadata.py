"""Tests for the arXiv metadata enrichment service."""

from __future__ import annotations

import pytest

from app.services.arxiv_metadata import (
    _parse_authors_from_html,
    enrich_papers_concurrently,
    fetch_arxiv_authors,
)


# ── _parse_authors_from_html ────────────────────────────────────────────────


def test_parse_authors_from_meta_tags():
    """The canonical form: <meta name="citation_author" content="...">."""
    html = """
    <html>
      <head>
        <meta name="citation_author" content="Yin, Zhuowen" />
        <meta name="citation_author" content="Gao, Cuifeng" />
        <meta name="citation_author" content="Xue, Yinxing" />
      </head>
      <body>...</body>
    </html>
    """
    authors = _parse_authors_from_html(html)
    assert [a["name"] for a in authors] == [
        "Yin, Zhuowen",
        "Gao, Cuifeng",
        "Xue, Yinxing",
    ]
    assert all(a["author_id"] == "" for a in authors)


def test_parse_authors_handles_html_entities():
    """Common HTML entities in author names are unescaped."""
    html = (
        '<meta name="citation_author" content="Andr&#233; Martins" />'
        '<meta name="citation_author" content="Jane &amp; John Doe" />'
    )
    authors = _parse_authors_from_html(html)
    assert [a["name"] for a in authors] == ["André Martins", "Jane & John Doe"]


def test_parse_authors_falls_back_to_authors_div():
    """When the meta tags are absent, scrape the authors <div>."""
    html = """
    <div class="authors">
        <a href="/a/1">Zhuowen Yin</a>
        <a href="/a/2">Cuifeng Gao</a>
    </div>
    """
    authors = _parse_authors_from_html(html)
    assert [a["name"] for a in authors] == ["Zhuowen Yin", "Cuifeng Gao"]


def test_parse_authors_returns_empty_on_no_match():
    """A page without any author markers returns an empty list."""
    html = "<html><body>Some page without author metadata.</body></html>"
    assert _parse_authors_from_html(html) == []


# ── fetch_arxiv_authors ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_arxiv_authors_returns_empty_for_empty_id():
    """An empty / missing arxiv id never raises and returns []."""
    assert await fetch_arxiv_authors("") == []
    assert await fetch_arxiv_authors("   ") == []


@pytest.mark.asyncio
async def test_fetch_arxiv_authors_strips_version_suffix():
    """The ``v1`` suffix is removed before issuing the request."""
    # We just verify the function does not raise; the actual HTTP call is
    # not exercised in unit tests (see integration test below).
    import httpx

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            class _Resp:
                status_code = 200
                text = '<meta name="citation_author" content="Test Author" />'

            # Make sure the version suffix was stripped.
            assert "v1" not in url
            return _Resp()

    httpx.AsyncClient = _FakeClient
    authors = await fetch_arxiv_authors("2511.00872v1")
    assert [a["name"] for a in authors] == ["Test Author"]


# ── enrich_papers_concurrently ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enrich_papers_concurrently_dedupes_input():
    """Duplicate arxiv_ids are de-duplicated before the network calls."""
    import httpx

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            class _Resp:
                status_code = 200
                text = '<meta name="citation_author" content="Only Author" />'

            return _Resp()

    httpx.AsyncClient = _FakeClient
    result = await enrich_papers_concurrently(["2511.00872", "2511.00872", "2511.00873"])
    assert set(result.keys()) == {"2511.00872", "2511.00873"}
    assert all(len(authors) == 1 for authors in result.values())


@pytest.mark.asyncio
async def test_enrich_papers_concurrently_empty_input():
    """Empty / falsy input skips the network entirely."""
    result = await enrich_papers_concurrently([])
    assert result == {}
    result = await enrich_papers_concurrently(["", None])  # type: ignore[list-item]
    assert result == {}
