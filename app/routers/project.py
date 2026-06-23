"""REST endpoints for project CRUD and paper management."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.paper import AutoSearchRequest
from app.schemas.project import (
    ConfirmUploadsRequest,
    DiscardUploadsRequest,
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
    ReviewProtocol,
    SavePaperRequest,
    SavePaperResponse,
    UpdatePaperRequest,
    UploadResponse,
    UploadStatusItem,
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


# ── AI Project Metadata Generation ─────────────────────────────────────


from pydantic import BaseModel, Field


class GenerateMetadataRequest(BaseModel):
    idea: str = Field(..., min_length=1, max_length=2000)


class GenerateMetadataResponse(BaseModel):
    title: str
    topic: str
    research_question: str | None = None


@router.post("/generate-metadata", response_model=GenerateMetadataResponse)
async def generate_project_metadata(
    body: GenerateMetadataRequest,
    user: User = Depends(get_current_user),
) -> GenerateMetadataResponse:
    """Use AI to generate a proper project title, topic, and research question
    from a free-form idea description."""
    from app.ai.provider import get_provider

    class _ProjectMeta(BaseModel):
        title: str = Field(
            description="Short, descriptive project title (max 60 chars). "
            "Academic style, no quotes. NOT the raw user message.",
        )
        topic: str = Field(
            description="Refined research topic (1-2 sentences).",
        )
        research_question: str | None = Field(
            default=None,
            description="A concrete research question if one can be inferred, else null.",
        )

    system = (
        "You are a research project metadata extractor. Given a user's "
        "idea or description, produce a concise project title, a refined "
        "research topic, and an optional research question.\n\n"
        "Rules:\n"
        "- Title: max 60 characters, academic style, no quotes.\n"
        "- Topic: 1-2 clear sentences describing the research area.\n"
        "- Research question: a focused, answerable question if possible, "
        "otherwise null.\n"
        "- ALL output MUST be in English. If the user's input is in another "
        "language (e.g. Vietnamese), translate and normalize it to English "
        "to optimize for paper searching.\n"
        "- Do NOT copy the raw user message verbatim."
    )

    provider = get_provider()
    try:
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": body.idea.strip()}],
            schema=_ProjectMeta.model_json_schema(),
            tool_name="extract_project_metadata",
            system=system,
            max_tokens=300,
        )
        meta = _ProjectMeta.model_validate(result)
        return GenerateMetadataResponse(
            title=(meta.title.strip()[:60] or "Untitled Research").rstrip(),
            topic=(meta.topic.strip() or body.idea.strip())[:512],
            research_question=meta.research_question,
        )
    except Exception as exc:
        logger.warning("AI metadata generation failed: %s", exc)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate project metadata. Please fill in manually.",
        ) from exc


@router.post("/{project_id}/protocol:suggest", response_model=ReviewProtocol)
async def suggest_review_protocol(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReviewProtocol:
    """Generate an editable protocol draft from the current project metadata."""
    from app.ai.provider import get_provider

    project = await get_project(db, user, project_id)
    if project is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    system = (
        "You are a systematic literature review protocol assistant. "
        "Draft a practical, editable review protocol from the project metadata. "
        "Return only structured data that matches the requested schema.\n\n"
        "Rules:\n"
        "- Keep criteria concrete enough for title/abstract screening.\n"
        "- Use controlled, researcher-friendly wording.\n"
        "- Include 3-6 inclusion criteria and 3-6 exclusion criteria.\n"
        "- Prefer academic sources that this app can search.\n"
        "- Use English.\n"
        "- Fill population, intervention_or_topic, comparison, outcome, and "
        "date_range when the project metadata supports a reasonable broad draft.\n"
        "- If there is no direct comparator, set comparison to a useful baseline "
        "such as 'alternative methods', 'standard practice', or 'not applicable'.\n"
        "- Only use null when even a broad, editable draft would be misleading."
    )
    user_msg = (
        f"Project title: {project.title}\n"
        f"Topic: {project.topic}\n"
        f"Research question: {project.research_question or 'Not specified'}\n"
        f"Existing protocol draft: {project.review_protocol.model_dump()}"
    )

    provider = get_provider()
    try:
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            schema=ReviewProtocol.model_json_schema(),
            tool_name="draft_review_protocol",
            system=system,
            max_tokens=900,
        )
        return ReviewProtocol.model_validate(result)
    except Exception as exc:
        logger.warning("AI protocol generation failed for project %s: %s", project_id, exc)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate review protocol. Please fill in manually.",
        ) from exc


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
    try:
        result = await save_paper_to_project(db, user, project_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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


# ── Upload Papers (PDF / Markdown) ─────────────────────────────────────────


@router.post("/{project_id}/papers:upload", response_model=UploadResponse)
async def upload_papers_endpoint(
    project_id: UUID,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UploadResponse:
    """Upload up to 5 PDF/Markdown files; ingestion runs in the background."""
    from app.services.paper_upload import handle_uploads

    try:
        drafts = await handle_uploads(db, user, project_id, files)
    except ValueError as exc:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if drafts is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")
    return UploadResponse(drafts=drafts)


@router.get("/{project_id}/papers:upload-status", response_model=list[UploadStatusItem])
async def upload_status_endpoint(
    project_id: UUID,
    ids: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[UploadStatusItem]:
    """Poll ingest status + extracted metadata for draft uploads (comma-separated ids)."""
    from app.services.paper_upload import get_upload_status

    try:
        id_list = [UUID(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail="Invalid ids"
        ) from exc

    items = await get_upload_status(db, user, project_id, id_list)
    if items is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")
    return items


@router.post("/{project_id}/papers:confirm-uploads")
async def confirm_uploads_endpoint(
    project_id: UUID,
    body: ConfirmUploadsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Apply confirmed metadata, promote drafts to saved, trigger matrix."""
    from app.services.paper_upload import confirm_uploads

    ok = await confirm_uploads(db, user, project_id, body.items)
    if ok is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")
    return {"status": "ok"}


@router.post("/{project_id}/papers:discard-uploads", status_code=http_status.HTTP_204_NO_CONTENT)
async def discard_uploads_endpoint(
    project_id: UUID,
    body: DiscardUploadsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Cancel pending uploads: delete draft papers + files."""
    from app.services.paper_upload import discard_uploads

    ok = await discard_uploads(db, user, project_id, body.project_paper_ids)
    if ok is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")


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
    try:
        result = await update_project_paper(db, user, project_id, project_paper_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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


# ── Auto search & save ──────────────────────────────────────────────────


@router.post(
    "/{project_id}/search/auto",
    status_code=http_status.HTTP_202_ACCEPTED,
)
async def auto_search_project(
    project_id: UUID,
    body: AutoSearchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Start an auto-search-and-save background job.

    Fetches up to ~200 papers from each of 4 sources (S2, arXiv, OpenAlex, Exa),
    LLM-scores all candidates, picks the top N (target_count) most relevant,
    and auto-saves them into the project.

    Returns ``{job_id, session_id, target_count, status: "running"}`` immediately.
    The frontend polls ``GET /api/papers/search/jobs/{job_id}`` for progress.
    """
    from app.services.search_session import auto_search_and_save

    try:
        result = await auto_search_and_save(
            db, user, project_id, body.query, body.target_count,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if result.get("error") == "Project not found":
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    if result.get("status_code") == 429:
        raise HTTPException(
            status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
            detail=result["error"],
        )
    return result
