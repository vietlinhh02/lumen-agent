"""Download papers from arXiv, Semantic Scholar, and OpenAlex for a given topic.

Usage:
    python scripts/download_papers.py "RAG medical" --max 100 --pdf
    python scripts/download_papers.py "deep learning" --max 500 --sources arxiv --pdf --delay 2.0

Output per paper saved as data/{source}_{paper_id}.json:
    { id, title, authors, year, abstract, source, url, citations, pdf_path, source_path }
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ARXIV_API = "https://export.arxiv.org/api/query"
S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_API_KEY = os.environ.get("S2_API_KEY", "")
OPENALEX_API = "https://api.openalex.org/works"


def eprint(*args, **kwargs):
    kwargs.setdefault("file", sys.stderr)
    print(*args, **kwargs)


# ── arXiv ────────────────────────────────────────────────────────────
def _parse_arxiv_entry(entry: ET.Element) -> dict:
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }

    def _el(tag: str) -> str:
        e = entry.find(f"atom:{tag}", ns)
        return e.text.strip() if e is not None and e.text else ""

    arxiv_id = _el("id")
    # arxiv_id looks like http://arxiv.org/abs/2301.12345v1
    arxiv_id = arxiv_id.split("/abs/")[-1] if "/abs/" in arxiv_id else arxiv_id

    authors_list: list[str] = []
    for author_el in entry.findall("atom:author", ns):
        name_el = author_el.find("atom:name", ns)
        if name_el is not None and name_el.text:
            authors_list.append(name_el.text.strip())

    return {
        "id": arxiv_id,
        "source": "arxiv",
        "title": " ".join(_el("title").split()),
        "authors": authors_list,
        "year": int(_el("published")[:4]) if _el("published") else None,
        "abstract": " ".join(_el("summary").split()),
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "categories": [
            c.get("term", "") for c in entry.findall("atom:category", ns)
        ],
        "citations": None,
        "full_text_path": None,
    }


def search_arxiv(query: str, max_results: int = 100, start: int = 0) -> list[dict]:
    params = {
        "search_query": f'all:{query}',
        "start": start,
        "max_results": min(max_results, 100),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"

    eprint(f"[arxiv] fetching {url}")
    data = _fetch_with_retry(url)
    root = ET.fromstring(data)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)
    papers = [_parse_arxiv_entry(e) for e in entries]
    eprint(f"[arxiv] got {len(papers)} papers (start={start})")
    return papers


def _arxiv_id_strip(arxiv_id: str) -> str:
    """Remove version suffix: 2308.16118v2 -> 2308.16118"""
    return arxiv_id.rsplit("v", 1)[0] if arxiv_id and "v" in arxiv_id.split("/")[-1] else arxiv_id


def download_arxiv_pdf(arxiv_id: str, out_dir: Path) -> str | None:
    """Download arXiv PDF. Returns path or None."""
    base_id = _arxiv_id_strip(arxiv_id)
    url = f"https://arxiv.org/pdf/{base_id}.pdf"
    filepath = out_dir / f"{base_id}.pdf"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LitReviewBot/0.1"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read()
        if content[:4] == b"%PDF":
            filepath.write_bytes(content)
            eprint(f"[arxiv] pdf downloaded: {base_id}.pdf")
            return str(filepath)
        return None
    except Exception as exc:
        eprint(f"[arxiv] pdf download failed for {arxiv_id}: {exc}")
        return None


def download_arxiv_source(arxiv_id: str, out_dir: Path) -> str | None:
    """Download arXiv LaTeX source tarball. Returns path or None."""
    url = f"https://arxiv.org/e-print/{arxiv_id}"
    filepath = out_dir / f"{arxiv_id}.tar.gz"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LitReviewBot/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
        # Only save if it's an actual tarball (not HTML error page)
        if content[:2] == b"\x1f\x8b":
            filepath.write_bytes(content)
            return str(filepath)
        return None
    except Exception as exc:
        eprint(f"[arxiv] source download failed for {arxiv_id}: {exc}")
        return None


# ── Semantic Scholar ─────────────────────────────────────────────────
def search_semantic_scholar(
    query: str, max_results: int = 100, offset: int = 0
) -> list[dict]:
    params = {
        "query": query,
        "limit": min(max_results, 100),
        "offset": offset,
        "fields": "title,authors,year,abstract,externalIds,url,citationCount,publicationTypes,venue",
    }
    url = f"{S2_API}?{urllib.parse.urlencode(params)}"

    eprint(f"[semantic_scholar] fetching {url}")
    headers = {}
    if S2_API_KEY:
        headers["x-api-key"] = S2_API_KEY
    data = _fetch_json(url, headers)

    papers = []
    for d in data.get("data", []):
        authors = [a.get("name", "") for a in d.get("authors", [])]
        ext_ids = d.get("externalIds", {}) or {}
        arxiv_id = ext_ids.get("ArXiv", "")

        papers.append({
            "id": d.get("paperId", ""),
            "source": "semantic_scholar",
            "title": d.get("title", ""),
            "authors": authors,
            "year": d.get("year"),
            "abstract": d.get("abstract", ""),
            "url": d.get("url", ""),
            "arxiv_id": arxiv_id,
            "citations": d.get("citationCount"),
            "full_text_path": None,
        })

    eprint(f"[semantic_scholar] got {len(papers)} papers (offset={offset})")
    return papers


# ── OpenAlex ─────────────────────────────────────────────────────────
def search_openalex(
    query: str, max_results: int = 200, page: int = 1
) -> list[dict]:
    params = {
        "search": query,
        "per_page": min(max_results, 200),
        "page": page,
        "filter": "type:article",
        "sort": "relevance_score:desc",
    }
    url = f"{OPENALEX_API}?{urllib.parse.urlencode(params)}"

    eprint(f"[openalex] fetching {url}")
    data = _fetch_json(url)

    papers = []
    for d in data.get("results", []):
        authorships = d.get("authorships", [])
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in authorships
        ]

        papers.append({
            "id": d.get("id", "").split("/")[-1] if d.get("id") else "",
            "source": "openalex",
            "title": d.get("title", ""),
            "authors": authors,
            "year": d.get("publication_year"),
            "abstract": _clean_inverted_abstract(d.get("abstract_inverted_index")),
            "url": "",  # OpenAlex doesn't always have direct URL
            "doi": d.get("doi", ""),
            "citations": d.get("cited_by_count"),
            "full_text_path": None,
        })

    eprint(f"[openalex] got {len(papers)} papers (page={page})")
    return papers


def _clean_inverted_abstract(inverted: dict | None) -> str:
    """OpenAlex returns abstracts as inverted index. Reconstruct."""
    if not inverted:
        return ""
    max_pos = max(max(positions) for positions in inverted.values())
    words = [""] * (max_pos + 1)
    for word, positions in inverted.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words)


# ── HTTP helpers ─────────────────────────────────────────────────────
def _fetch_with_retry(
    url: str, extra_headers: dict[str, str] | None = None, max_retries: int = 5
) -> str:
    """GET url returning response body as string, with retry on 429/503."""
    base_headers = {"User-Agent": "LitReviewBot/0.1"}
    if extra_headers:
        base_headers.update(extra_headers)

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=base_headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < max_retries - 1:
                wait = 3 ** (attempt + 1)  # 3, 9, 27, 81s
                eprint(f"[http] {exc.code}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(3)
            else:
                raise
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts")


def _fetch_json(url: str, extra_headers: dict[str, str] | None = None) -> dict:
    body = _fetch_with_retry(url, extra_headers)
    return json.loads(body)


# ── Save + merge ─────────────────────────────────────────────────────
def save_papers(
    papers: list[dict], out_dir: Path, download_pdf: bool, download_source: bool
):
    out_dir.mkdir(parents=True, exist_ok=True)

    for paper in papers:
        source = paper["source"]
        pid = paper["id"].replace("/", "_")
        fpath = out_dir / f"{source}_{pid}.json"

        if fpath.exists():
            continue

        arxiv_id = paper.get("arxiv_id") or (paper["id"] if source == "arxiv" else None)

        if arxiv_id:
            if download_pdf:
                pdf = download_arxiv_pdf(arxiv_id, out_dir)
                if pdf:
                    paper["pdf_path"] = pdf
            if download_source:
                src = download_arxiv_source(arxiv_id, out_dir)
                if src:
                    paper["source_path"] = src

        fpath.write_text(json.dumps(paper, ensure_ascii=False, indent=2))
        time.sleep(0.05)

    eprint(f"\n[save] wrote {len(papers)} papers to {out_dir}")


def deduplicate(papers: list[dict]) -> list[dict]:
    """Deduplicate by title similarity (case-insensitive, first 100 chars)."""
    seen: set[str] = set()
    uniq = []
    for p in papers:
        key = p["title"].lower()[:100].strip()
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


# ── Main ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Download CS papers from academic sources")
    parser.add_argument("query", help="Search query (e.g. 'retrieval augmented generation')")
    parser.add_argument("--max", type=int, default=100, help="Total papers to collect (default 100)")
    parser.add_argument("--out", default="data/papers", help="Output directory (default data/papers)")
    parser.add_argument(
        "--sources", default="arxiv,s2,openalex",
        help="Comma-separated: arxiv,s2,openalex (default all three)"
    )
    parser.add_argument(
        "--pdf", action="store_true",
        help="Download PDF from arXiv (works for any paper with arxiv_id)"
    )
    parser.add_argument(
        "--source", "--full-text", dest="download_source", action="store_true",
        help="Download arXiv LaTeX source tarballs"
    )
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between API calls in seconds")

    args = parser.parse_args()
    sources_list = [s.strip() for s in args.sources.split(",")]
    out_dir = Path(args.out)

    per_source = args.max // len(sources_list)
    remaining = args.max
    all_papers: list[dict] = []

    for idx, source in enumerate(sources_list):
        target = per_source if idx < len(sources_list) - 1 else remaining

        collected = 0
        if source == "arxiv":
            for start in range(0, 9999, 100):
                if collected >= target:
                    break
                batch = search_arxiv(args.query, max_results=min(100, target - collected), start=start)
                all_papers.extend(batch)
                collected += len(batch)
                time.sleep(args.delay)
                if len(batch) < 100:
                    break

        elif source == "s2":
            for offset in range(0, 9999, 100):
                if collected >= target:
                    break
                batch = search_semantic_scholar(args.query, max_results=min(100, target - collected), offset=offset)
                all_papers.extend(batch)
                collected += len(batch)
                time.sleep(args.delay)
                if len(batch) < 100:
                    break

        elif source == "openalex":
            for page in range(1, 9999):
                if collected >= target:
                    break
                batch = search_openalex(args.query, max_results=min(200, target - collected), page=page)
                all_papers.extend(batch)
                collected += len(batch)
                time.sleep(args.delay)
                if len(batch) < min(200, target - collected):
                    break
        else:
            eprint(f"Unknown source: {source}")
            collected = 0

        remaining -= collected

    before = len(all_papers)
    all_papers = deduplicate(all_papers)
    eprint(f"\n[dedup] {before} -> {len(all_papers)} unique papers")

    save_papers(all_papers, out_dir, download_pdf=args.pdf, download_source=args.download_source)
    eprint(f"\nDone. {len(all_papers)} papers saved to {out_dir.resolve()}/")


if __name__ == "__main__":
    main()
