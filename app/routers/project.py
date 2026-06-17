"""REST endpoints for project CRUD and paper management."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.project import (
    EvidenceChunkResponse,
    FullTextResponse,
    NormalizeResponse,
    ProjectCreate,
    ProjectListResponse,
    ProjectPaperResponse,
    ProjectResponse,
    ProjectUpdate,
    RetrieveEvidenceRequest,
    RetrieveEvidenceResponse,
    SavePaperRequest,
    SavePaperResponse,
    UpdatePaperRequest,
)
from app.services.project import (
    create_project,
    delete_project,
    get_project,
    list_project_papers,
    list_projects,
    remove_project_paper,
    save_paper_to_project,
    update_project,
    update_project_paper,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["projects"])


# ── Project CRUD ─────────────────────────────────────────────────────────


@router.post("", response_model=ProjectResponse, status_code=http_status.HTTP_201_CREATED)
async def create_project_endpoint(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    return await create_project(db, user, body)


@router.get("", response_model=ProjectListResponse)
async def list_projects_endpoint(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectListResponse:
    projects = await list_projects(db, user)
    return ProjectListResponse(projects=projects)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project_endpoint(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    project = await get_project(db, user, project_id)
    if project is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project_endpoint(
    project_id: UUID,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    project = await update_project(db, user, project_id, body)
    if project is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_project_endpoint(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    deleted = await delete_project(db, user, project_id)
    if not deleted:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")


# ── Paper Management ───────────────────────────────────────────────────


@router.post(
    "/{project_id}/papers",
    response_model=SavePaperResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def save_paper_endpoint(
    project_id: UUID,
    body: SavePaperRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SavePaperResponse:
    result = await save_paper_to_project(db, user, project_id, body)
    if result is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")
    return result


@router.post("/{project_id}/papers:normalize", response_model=NormalizeResponse)
async def normalize_papers_endpoint(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NormalizeResponse:
    """Batch-normalise all papers with raw_extracted status via LLM.

    Runs in a background task to avoid socket timeout on long LLM calls.
    Returns immediately with the number of papers queued.
    """

    from sqlalchemy import select

    from app.db.models import Project
    from app.services.pdf_normalizer import count_raw_papers

    proj = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    if proj.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")

    raw_count = await count_raw_papers(db, project_id)
    if raw_count == 0:
        return NormalizeResponse(processed=0, skipped=0, failed=0)

    from app.db.session import async_session_factory

    async def _bg_normalize():
        try:
            async with async_session_factory() as bg_db:
                from app.services.pdf_normalizer import normalize_project_papers

                result = await normalize_project_papers(bg_db, project_id)
                logger.info("Normalization done for project %s: %s", project_id, result)
        except Exception as exc:
            logger.exception("Background normalization crashed for project %s: %s", project_id, exc)

    asyncio.ensure_future(_bg_normalize())
    logger.info(
        "Background normalization started for project %s (%d papers)", project_id, raw_count
    )

    return NormalizeResponse(processed=0, skipped=raw_count, failed=0)


@router.post("/{project_id}/evidence:retrieve", response_model=RetrieveEvidenceResponse)
async def retrieve_evidence_endpoint(
    project_id: UUID,
    body: RetrieveEvidenceRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RetrieveEvidenceResponse:
    """Retrieve citation-ready evidence chunks for a project."""
    from sqlalchemy import select

    from app.db.models import Project
    from app.services.hybrid_retrieval import retrieve_project_evidence

    proj = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    if proj.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")

    chunks = await retrieve_project_evidence(
        db,
        project_id,
        body.query,
        limit=body.limit,
        content_types=body.content_types,
    )
    return RetrieveEvidenceResponse(
        query=body.query,
        total=len(chunks),
        chunks=[
            EvidenceChunkResponse(
                project_paper_id=chunk.project_paper_id,
                paper_id=chunk.paper_id,
                chunk_id=chunk.chunk_id,
                title=chunk.title,
                section_label=chunk.section_label,
                section_path=chunk.section_path,
                chunk_index=chunk.chunk_index,
                content_type=chunk.content_type,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                content_hash=chunk.content_hash,
                score=chunk.score,
                keyword_score=chunk.keyword_score,
                vector_score=chunk.vector_score,
                chunk_text=chunk.chunk_text,
            )
            for chunk in chunks
        ],
    )


@router.get("/{project_id}/papers", response_model=list[ProjectPaperResponse])
async def list_papers_endpoint(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ProjectPaperResponse]:
    papers = await list_project_papers(db, user, project_id)
    if papers is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")
    return papers


@router.patch("/{project_id}/papers/{project_paper_id}", response_model=ProjectPaperResponse)
async def update_paper_endpoint(
    project_id: UUID,
    project_paper_id: UUID,
    body: UpdatePaperRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectPaperResponse:
    result = await update_project_paper(db, user, project_id, project_paper_id, body)
    if result is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Paper not found in project"
        )
    return result


@router.delete(
    "/{project_id}/papers/{project_paper_id}", status_code=http_status.HTTP_204_NO_CONTENT
)
async def remove_paper_endpoint(
    project_id: UUID,
    project_paper_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    removed = await remove_project_paper(db, user, project_id, project_paper_id)
    if not removed:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Paper not found in project"
        )


@router.post(
    "/{project_id}/papers/{project_paper_id}/download-pdf", response_model=ProjectPaperResponse
)
async def download_paper_pdf_endpoint(
    project_id: UUID,
    project_paper_id: UUID,
    pdf_url: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectPaperResponse:
    """Trigger a PDF download for a saved paper that only has metadata."""

    # Verify ownership
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.core.config import get_settings
    from app.db.models import Paper, Project, ProjectPaper
    from app.sources.base import RawPaper

    settings = get_settings()

    proj_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    if proj_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(ProjectPaper)
        .options(selectinload(ProjectPaper.enrichments))
        .where(
            ProjectPaper.id == project_paper_id,
            ProjectPaper.project_id == project_id,
        )
    )
    pp = result.scalar_one_or_none()
    if pp is None:
        raise HTTPException(status_code=404, detail="Paper not found in project")

    # Fetch corresponding Paper separately or from relation
    paper_result = await db.execute(select(Paper).where(Paper.id == pp.paper_id))
    paper = paper_result.scalar_one_or_none()
    if paper is None:
        raise HTTPException(status_code=404, detail="Canonical paper not found")

    # Try to find a PDF URL from PaperEnrichment if it exists
    open_access_url = pdf_url

    if open_access_url:
        # Save custom URL to DB
        from sqlalchemy import delete

        from app.db.models import PaperEnrichment

        await db.execute(delete(PaperEnrichment).where(PaperEnrichment.project_paper_id == pp.id))
        enrichment = PaperEnrichment(
            project_paper_id=pp.id, open_access_url=open_access_url, enrichment_status="completed"
        )
        db.add(enrichment)
        await db.commit()
    elif pp.enrichments:
        open_access_url = pp.enrichments[0].open_access_url

    # Fallback: query Semantic Scholar API directly for openAccessPdf URL if not cached
    if not open_access_url and paper.semantic_scholar_id:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                headers = {}
                if settings.semantic_scholar_api_key:
                    headers["x-api-key"] = settings.semantic_scholar_api_key
                resp = await client.get(
                    f"https://api.semanticscholar.org/graph/v1/paper/{paper.semantic_scholar_id}",
                    params={"fields": "openAccessPdf"},
                    headers=headers,
                )
                if resp.status_code == 200:
                    oa_data = resp.json().get("openAccessPdf") or {}
                    open_access_url = oa_data.get("url")
                    if open_access_url:
                        # Cache it back in DB for next time
                        from sqlalchemy import delete

                        from app.db.models import PaperEnrichment

                        await db.execute(
                            delete(PaperEnrichment).where(PaperEnrichment.project_paper_id == pp.id)
                        )
                        enrichment = PaperEnrichment(
                            project_paper_id=pp.id,
                            open_access_url=open_access_url,
                            enrichment_status="completed",
                        )
                        db.add(enrichment)
                        await db.commit()
        except Exception as e:
            logger.warning("Failed to fetch OA url from Semantic Scholar fallback: %s", e)

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
        authors=paper.authors if isinstance(paper.authors, list) else [],
        source_specific={"pdf_url": open_access_url} if open_access_url else {},
    )

    # Kick off download + ingest in background — API returns immediately

    from app.services.project import _download_and_ingest_bg

    asyncio.ensure_future(_download_and_ingest_bg(pp.id, raw))
    pp.full_text_status = "pending"
    await db.commit()
    await db.refresh(pp)

    # Return updated paper status
    from app.db.models import LiteratureMatrixRow, PaperEnrichment
    from app.services.project import _to_project_paper_response

    has_matrix = (
        await db.execute(
            select(LiteratureMatrixRow.id).where(LiteratureMatrixRow.project_paper_id == pp.id)
        )
    ).first() is not None
    has_enrichment = (
        await db.execute(
            select(PaperEnrichment.id).where(
                PaperEnrichment.project_paper_id == pp.id,
                PaperEnrichment.enrichment_status == "completed",
            )
        )
    ).first() is not None

    return await _to_project_paper_response(
        pp, paper, project_id, has_matrix=has_matrix, has_enrichment=has_enrichment
    )


@router.get(
    "/{project_id}/papers/{project_paper_id}/full-text",
    response_model=FullTextResponse,
)
async def get_paper_full_text(
    project_id: UUID,
    project_paper_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FullTextResponse:
    """Return extracted full-text chunks for a saved paper."""
    from sqlalchemy import select

    from app.db.models import Paper, PaperChunk, PaperEnrichment, Project, ProjectPaper

    proj = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    if proj.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")

    row = await db.execute(
        select(ProjectPaper, Paper)
        .join(Paper, ProjectPaper.paper_id == Paper.id)
        .where(
            ProjectPaper.id == project_paper_id,
            ProjectPaper.project_id == project_id,
        )
    )
    row_data = row.one_or_none()
    if row_data is None:
        raise HTTPException(status_code=404, detail="Paper not found in project")
    pp, paper = row_data

    chunk_rows = await db.execute(
        select(PaperChunk)
        .where(
            PaperChunk.project_paper_id == project_paper_id,
            PaperChunk.chunk_type == "full_text",
        )
        .order_by(PaperChunk.chunk_index, PaperChunk.created_at)
    )
    chunks = chunk_rows.scalars().all()

    from app.schemas.project import FullTextChunk

    items: list[FullTextChunk] = []
    total_chars = 0

    if chunks:
        for c in chunks:
            items.append(
                FullTextChunk(
                    section_label=c.section_label or "Full Text",
                    section_path=c.section_path,
                    chunk_index=c.chunk_index,
                    page_start=c.page_start,
                    page_end=c.page_end,
                    content_type=c.content_type,
                    pipeline_version=c.pipeline_version,
                    content_hash=c.content_hash,
                    chunk_text=c.chunk_text,
                    char_count=len(c.chunk_text),
                )
            )
            total_chars += len(c.chunk_text)
    else:
        # Fall back to raw text from enrichment
        enrich_result = await db.execute(
            select(PaperEnrichment).where(
                PaperEnrichment.project_paper_id == project_paper_id,
            )
        )
        enrichment = enrich_result.scalar_one_or_none()
        if enrichment and enrichment.raw_text:
            raw = enrichment.raw_text
            items.append(
                FullTextChunk(
                    section_label="Raw Extracted Text",
                    chunk_text=raw,
                    char_count=len(raw),
                )
            )
            total_chars = len(raw)

    # Fetch crawled_markdown if available (LLM-normalized clean markdown)
    crawled_md = None
    if pp.full_text_status == "completed":
        enrich_result = await db.execute(
            select(PaperEnrichment).where(
                PaperEnrichment.project_paper_id == project_paper_id,
            )
        )
        enrichment = enrich_result.scalar_one_or_none()
        if enrichment and enrichment.crawled_markdown:
            crawled_md = enrichment.crawled_markdown

    return FullTextResponse(
        project_paper_id=pp.id,
        title=paper.title,
        full_text_status=pp.full_text_status,
        total_chars=total_chars,
        total_chunks=len(items),
        chunks=items,
        crawled_markdown=crawled_md,
    )
