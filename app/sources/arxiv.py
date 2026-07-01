"""ArXiv source adapter."""

from __future__ import annotations

import logging
import urllib.parse
import xml.etree.ElementTree as ET

import httpx

from app.sources.base import PaperSource, RawPaper

logger = logging.getLogger(__name__)


class ArxivSource(PaperSource):
    """Search papers through the ArXiv API."""

    name = "arxiv"

    async def search(
        self,
        query: str,
        limit: int = 25,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[RawPaper]:
        """Fetch papers from ArXiv API."""
        base_url = "https://export.arxiv.org/api/query"
        
        # We pass the query directly to let ArXiv advanced syntax work.
        params = {
            "search_query": query,
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        logger.info("Searching ArXiv: %s", url)

        async with httpx.AsyncClient(follow_redirects=True) as client:
            try:
                response = await client.get(url, timeout=15.0)
                response.raise_for_status()
                xml_data = response.text
            except Exception as e:
                logger.warning("ArXiv search failed: %s", e)
                return []

        return self._parse_atom_feed(xml_data)

    def _parse_atom_feed(self, xml_data: str) -> list[RawPaper]:
        papers = []
        try:
            root = ET.fromstring(xml_data)
            ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
            
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                title_text = title.text.strip().replace("\n", " ") if title is not None and title.text else ""
                
                summary = entry.find("atom:summary", ns)
                abstract = summary.text.strip().replace("\n", " ") if summary is not None and summary.text else ""
                
                published = entry.find("atom:published", ns)
                year = None
                if published is not None and published.text:
                    year = int(published.text[:4])
                
                authors = []
                for author in entry.findall("atom:author", ns):
                    name = author.find("atom:name", ns)
                    if name is not None and name.text:
                        authors.append({"name": name.text.strip(), "author_id": ""})
                
                id_elem = entry.find("atom:id", ns)
                arxiv_id = None
                if id_elem is not None and id_elem.text:
                    arxiv_id = id_elem.text.split("/abs/")[-1].split("v")[0]
                
                doi = None
                doi_elem = entry.find("arxiv:doi", ns)
                if doi_elem is not None and doi_elem.text:
                    doi = doi_elem.text.strip()
                
                pdf_url = None
                for link in entry.findall("atom:link", ns):
                    if link.attrib.get("title") == "pdf":
                        pdf_url = link.attrib.get("href")
                        break
                
                if not pdf_url and arxiv_id:
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                
                paper = RawPaper(
                    title=title_text,
                    abstract=abstract,
                    year=year,
                    arxiv_id=arxiv_id,
                    doi=doi,
                    authors=authors,
                    source_name=self.name,
                    url=id_elem.text if id_elem is not None else None,
                    source_specific={
                        "pdf_url": pdf_url
                    }
                )
                papers.append(paper)
        except Exception as e:
            logger.error("Failed to parse ArXiv XML: %s", e)
            
        return papers
