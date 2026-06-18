import logging
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

async def fetch_arxiv_html(arxiv_id: str) -> str | None:
    """
    Fetches the HTML version of an arXiv paper and extracts its text.
    Removes <figure> and <math> tags.
    """
    url = f"https://arxiv.org/html/{arxiv_id}"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                logger.warning(f"arXiv HTML not found or error for {arxiv_id}: {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Remove complex/unwanted tags
            for tag in soup.find_all(['figure', 'math', 'script', 'style']):
                tag.decompose()
            
            # The main content in arXiv HTML is usually in <div class="ltx_page_main">
            from markdownify import markdownify as md
            
            main_div = soup.find('div', class_='ltx_page_main')
            if main_div:
                return md(str(main_div), heading_style="ATX").strip()
                
            body = soup.find('body')
            if not body:
                return None
                
            return md(str(body), heading_style="ATX").strip()
    except Exception as e:
        logger.error(f"Error fetching arXiv HTML for {arxiv_id}: {e}")
        return None

async def fetch_europepmc_xml(pmc_id: str) -> str | None:
    """
    Fetches the full text XML from Europe PMC and extracts its text.
    Filters content from <body> tag, maintaining headings and paragraphs.
    """
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc_id}/fullTextXML"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                logger.warning(f"Europe PMC XML not found or error for {pmc_id}: {response.status_code}")
                return None
            
            # Parse XML
            soup = BeautifulSoup(response.content, "xml")
            
            body = soup.find('body')
            if not body:
                logger.warning(f"No <body> found in Europe PMC XML for {pmc_id}")
                return None
            
            # Convert XML body to markdown
            from markdownify import markdownify as md
            return md(str(body), heading_style="ATX").strip()
            
    except Exception as e:
        logger.error(f"Error fetching Europe PMC XML for {pmc_id}: {e}")
        return None
