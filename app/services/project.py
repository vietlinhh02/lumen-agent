"""Project CRUD and paper management business logic."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Paper, Project, ProjectPaper, User
from app.schemas.project import (
    ProjectCreate,
    ProjectPaperResponse,
    ProjectResponse,
    ProjectUpdate,
    ReviewProtocol,
    SavePaperRequest,
    SavePaperResponse,
    UpdatePaperRequest,
)
from app.services.pdf_downloader import PDFDownloader

if TYPE_CHECKING:
    from app.sources.base import RawPaper

logger = logging.getLogger(__name__)

VALID_PROJECT_PAPER_STATUSES = {"saved", "rejected", "uncertain"}
VALID_EXCLUSION_REASONS = {
    "wrong_population",
    "wrong_intervention_or_topic",
    "wrong_outcome",
    "wrong_study_type",
    "not_peer_reviewed",
    "outside_date_range",
    "duplicate",
    "no_full_text",
    "insufficient_relevance",
    "other",
}


# ── Project CRUD ───────────────────────────────────────────────────────────


async def create_project(db: AsyncSession, user: User, data: ProjectCreate) -> ProjectResponse:
    project = Project(
        owner_id=user.id,
        title=data.title,
        topic=data.topic,
        research_question=data.research_question,
        review_protocol=data.review_protocol.model_dump(),
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return _to_project_response(project, paper_count=0)


async def list_projects(db: AsyncSession, user: User) -> list[ProjectResponse]:
    result = await db.execute(
        select(Project).where(Project.owner_id == user.id).order_by(Project.updated_at.desc())
    )
    projects = result.scalars().all()

    # Batch load paper counts
    project_ids = [p.id for p in projects]
    if project_ids:
        counts_result = await db.execute(
            select(ProjectPaper.project_id, func.count(ProjectPaper.id))
            .where(
                ProjectPaper.project_id.in_(project_ids),
                ProjectPaper.status == "saved",
            )
            .group_by(ProjectPaper.project_id)
        )
        counts = dict(counts_result.all())
    else:
        counts = {}

    return [_to_project_response(p, paper_count=counts.get(p.id, 0)) for p in projects]


async def get_project(db: AsyncSession, user: User, project_id: UUID) -> ProjectResponse | None:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        return None

    paper_count_result = await db.execute(
        select(func.count(ProjectPaper.id)).where(
            ProjectPaper.project_id == project_id,
            ProjectPaper.status == "saved",
        )
    )
    paper_count = paper_count_result.scalar() or 0
    return _to_project_response(project, paper_count=paper_count)


async def update_project(
    db: AsyncSession, user: User, project_id: UUID, data: ProjectUpdate
) -> ProjectResponse | None:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        return None

    for field in ("title", "topic", "research_question", "status"):
        value = getattr(data, field, None)
        if value is not None:
            setattr(project, field, value)
    if data.review_protocol is not None:
        project.review_protocol = data.review_protocol.model_dump()

    await db.commit()
    await db.refresh(project)

    paper_count_result = await db.execute(
        select(func.count(ProjectPaper.id)).where(
            ProjectPaper.project_id == project_id,
            ProjectPaper.status == "saved",
        )
    )
    paper_count = paper_count_result.scalar() or 0
    return _to_project_response(project, paper_count=paper_count)


async def delete_project(db: AsyncSession, user: User, project_id: UUID) -> bool:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        return False
    await db.delete(project)
    await db.commit()
    return True


# ── Paper Management ───────────────────────────────────────────────────────


async def save_paper_to_project(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    data: SavePaperRequest,
) -> SavePaperResponse | None:
    # Verify project ownership
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    project = project_result.scalar_one_or_none()
    if project is None:
        return None

    # Upsert canonical paper (deduplicate by DOI > arXiv ID > Semantic Scholar ID)
    paper = await _upsert_paper(db, data)

    # Link to project (no duplicates)
    target_status = data.status or "saved"
    _validate_project_paper_update(target_status, data.exclusion_reason)
    existing = await db.execute(
        select(ProjectPaper).where(
            ProjectPaper.project_id == project_id,
            ProjectPaper.paper_id == paper.id,
        )
    )
    pp = existing.scalar_one_or_none()
    if pp is not None:
        # Already saved — update fields if provided
        if data.relevance_label is not None:
            pp.relevance_label = data.relevance_label
        if data.user_note is not None:
            pp.user_note = data.user_note
        pp.status = target_status
        pp.exclusion_reason = data.exclusion_reason if target_status == "rejected" else None
        await db.commit()
        await db.refresh(pp)
    else:
        pp = ProjectPaper(
            project_id=project_id,
            paper_id=paper.id,
            status=target_status,
            relevance_label=data.relevance_label,
            exclusion_reason=data.exclusion_reason if target_status == "rejected" else None,
            user_note=data.user_note,
        )
        db.add(pp)
        await db.commit()
        await db.refresh(pp)

    # Persist open access url in PaperEnrichment if provided in source_specific
    oa_url = data.source_specific.get("pdf_url")
    if oa_url:
        from sqlalchemy import delete

        from app.db.models import PaperEnrichment

        await db.execute(delete(PaperEnrichment).where(PaperEnrichment.project_paper_id == pp.id))
        enrichment = PaperEnrichment(
            project_paper_id=pp.id, open_access_url=oa_url, enrichment_status="completed"
        )
        db.add(enrichment)
        await db.commit()
        await db.refresh(pp)

    # Optional PDF handling — pushed to background so the request returns instantly.
    # The paper record is already committed; the background task handles
    # download + text extraction asynchronously.
    pdf_path: str | None = None
    full_text_status: str | None = None
    if data.download_pdf:
        full_text_status = "pending"
        from app.sources.base import RawPaper

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
            source_name="semantic_scholar",
            source_specific=data.source_specific or {},
        )

        # If the caller already has the PDF on disk (e.g. search_papers
        # downloaded it in parallel), skip the redundant network fetch.
        prefetched: str | None = data.prefetched_pdf_path
        if prefetched:
            pdf_path = prefetched
            full_text_status = "ingesting"

        import asyncio

        asyncio.ensure_future(_download_and_ingest_bg(pp.id, raw, pdf_path=prefetched))

    return SavePaperResponse(
        project_paper_id=pp.id,
        paper_id=paper.id,
        title=paper.title,
        status=pp.status,
        pdf_path=pdf_path,
        full_text_status=full_text_status,
    )


async def list_project_papers(
    db: AsyncSession,
    user: User,
    project_id: UUID,
) -> list[ProjectPaperResponse] | None:
    # Verify ownership
    proj_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    if proj_result.scalar_one_or_none() is None:
        return None

    result = await db.execute(
        select(ProjectPaper, Paper)
        .join(Paper, ProjectPaper.paper_id == Paper.id)
        .where(ProjectPaper.project_id == project_id, ProjectPaper.status == "saved")
        .order_by(ProjectPaper.saved_at.desc())
    )
    rows = result.all()

    from app.db.models import LiteratureMatrixRow, PaperEnrichment

    pp_ids = [pp.id for pp, _ in rows]

    matrix_ids: set[UUID] = set()
    enrichment_ids: set[UUID] = set()
    if pp_ids:
        matrix_result = await db.execute(
            select(LiteratureMatrixRow.project_paper_id).where(
                LiteratureMatrixRow.project_paper_id.in_(pp_ids)
            )
        )
        matrix_ids = set(matrix_result.scalars().all())

        enrichment_result = await db.execute(
            select(PaperEnrichment.project_paper_id).where(
                PaperEnrichment.project_paper_id.in_(pp_ids),
                PaperEnrichment.enrichment_status == "completed",
            )
        )
        enrichment_ids = set(enrichment_result.scalars().all())

    import asyncio

    return await asyncio.gather(
        *[
            _to_project_paper_response(
                pp,
                paper,
                project_id,
                has_matrix=pp.id in matrix_ids,
                has_enrichment=pp.id in enrichment_ids,
            )
            for pp, paper in rows
        ]
    )


async def update_project_paper(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    project_paper_id: UUID,
    data: UpdatePaperRequest,
) -> ProjectPaperResponse | None:
    # Verify ownership
    proj_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    if proj_result.scalar_one_or_none() is None:
        return None

    result = await db.execute(
        select(ProjectPaper, Paper)
        .join(Paper, ProjectPaper.paper_id == Paper.id)
        .where(
            ProjectPaper.id == project_paper_id,
            ProjectPaper.project_id == project_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        return None

    pp, paper = row
    if data.relevance_label is not None:
        pp.relevance_label = data.relevance_label
    if data.user_note is not None:
        pp.user_note = data.user_note
    if data.status is not None:
        _validate_project_paper_update(data.status, data.exclusion_reason)
        pp.status = data.status
        if data.status != "rejected":
            pp.exclusion_reason = None
    if data.exclusion_reason is not None:
        _validate_project_paper_update(data.status or pp.status, data.exclusion_reason)
        pp.exclusion_reason = data.exclusion_reason

    await db.commit()
    await db.refresh(pp)

    from app.db.models import LiteratureMatrixRow, PaperEnrichment

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


async def remove_project_paper(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    project_paper_id: UUID,
) -> bool:
    proj_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    if proj_result.scalar_one_or_none() is None:
        return False

    result = await db.execute(
        select(ProjectPaper).where(
            ProjectPaper.id == project_paper_id,
            ProjectPaper.project_id == project_id,
        )
    )
    pp = result.scalar_one_or_none()
    if pp is None:
        return False

    await db.delete(pp)
    await db.commit()
    return True


# ── Helpers ────────────────────────────────────────────────────────────────


async def _download_and_ingest_bg(
    project_paper_id: UUID, raw: RawPaper, *, pdf_path: str | Path | None = None
) -> None:
    """Background task: download PDF for *raw* paper and extract text.

    Opens its own DB session so the caller's session can return immediately.
    If *pdf_path* is provided (pre-downloaded), skips download + Firecrawl.
    Never raises — failures are logged, not propagated.
    """

    from app.db.session import async_session_factory
    from app.services.pdf_fulltext import process_pdf
    from app.sources.firecrawl import crawl_pdf_links

    try:
        pdf_result: Path | None = Path(pdf_path) if pdf_path else None

        if pdf_result is None:
            # Enrich with PDF links via Firecrawl if none available yet
            if not raw.arxiv_id and not raw.source_specific.get("pdf_url"):
                try:
                    await crawl_pdf_links([raw])
                except Exception as exc:
                    logger.debug("Firecrawl enrichment skipped: %s", exc)

            settings = get_settings()
            downloader = PDFDownloader(output_dir=Path(settings.paper_pdf_dir), timeout=60)
            pdf_result = await downloader.download(raw)

        if pdf_result is None or not pdf_result.exists():
            async with async_session_factory() as bg_db:
                await _update_paper_status(bg_db, project_paper_id, "failed")
            return

        # Single-pass: extract -> chunk -> embed -> store. No batch trigger.
        async with async_session_factory() as bg_db:
            result = await process_pdf(bg_db, project_paper_id, pdf_result)
            logger.info(
                "Background fulltext done for %s: %s (status=%s, chunks=%d, chars=%d)",
                project_paper_id,
                pdf_result.name,
                result.status,
                result.chunk_count,
                result.char_count,
            )
    except Exception as exc:
        logger.exception("Background download+ingest failed for %s: %s", project_paper_id, exc)


async def _update_paper_status(db, project_paper_id: UUID, status: str) -> None:
    """Update the full_text_status on the ProjectPaper row."""
    from sqlalchemy import select

    from app.db.models import ProjectPaper

    result = await db.execute(select(ProjectPaper).where(ProjectPaper.id == project_paper_id))
    pp = result.scalar_one_or_none()
    if pp is not None:
        pp.full_text_status = status
        await db.commit()


async def _upsert_paper(db: AsyncSession, data: SavePaperRequest) -> Paper:
    """Find existing paper or create a new one. Deduplicates by strongest ID.

    Identifier lookups run sequentially because SQLAlchemy AsyncSession is not
    safe for concurrent operations.
    """
    paper: Paper | None = None

    # Priority: semantic_scholar > arxiv > doi
    if data.paper_semantic_scholar_id:
        result = await db.execute(
            select(Paper).where(Paper.semantic_scholar_id == data.paper_semantic_scholar_id)
        )
        paper = result.scalar_one_or_none()

    if paper is None and data.paper_arxiv_id:
        result = await db.execute(select(Paper).where(Paper.arxiv_id == data.paper_arxiv_id))
        paper = result.scalar_one_or_none()

    if paper is None and data.paper_doi:
        result = await db.execute(select(Paper).where(Paper.doi == data.paper_doi))
        paper = result.scalar_one_or_none()

    if paper is not None:
        # Merge missing fields
        merged = False
        for field in (
            "abstract",
            "year",
            "venue",
            "doi",
            "arxiv_id",
            "semantic_scholar_id",
            "url",
            "citation_count",
        ):
            existing_val = getattr(paper, field, None)
            new_val = getattr(data, f"paper_{field}", None)
            if existing_val is None and new_val is not None:
                setattr(paper, field, new_val)
                merged = True
        if isinstance(paper.authors, list) and data.paper_authors and not paper.authors:
            paper.authors = data.paper_authors
            merged = True
        if data.paper_source_names:
            existing_sources = set(paper.source_names or [])
            for src in data.paper_source_names:
                if src not in existing_sources:
                    paper.source_names = list(existing_sources) + [src]
                    merged = True
        if merged:
            await db.commit()
            await db.refresh(paper)
        return paper

    # Create new canonical paper
    paper = Paper(
        title=data.paper_title,
        abstract=data.paper_abstract,
        year=data.paper_year,
        venue=data.paper_venue,
        doi=data.paper_doi,
        arxiv_id=data.paper_arxiv_id,
        semantic_scholar_id=data.paper_semantic_scholar_id,
        url=data.paper_url,
        citation_count=data.paper_citation_count,
        authors=data.paper_authors,
        source_names=data.paper_source_names,
    )
    db.add(paper)
    await db.commit()
    await db.refresh(paper)
    return paper


def _to_project_response(p: Project, paper_count: int) -> ProjectResponse:
    return ProjectResponse(
        id=p.id,
        owner_id=p.owner_id,
        title=p.title,
        topic=p.topic,
        research_question=p.research_question,
        review_protocol=ReviewProtocol.model_validate(p.review_protocol or {}),
        status=p.status,
        created_at=p.created_at,
        updated_at=p.updated_at,
        paper_count=paper_count,
    )


async def _to_project_paper_response(
    pp: ProjectPaper,
    paper: Paper,
    project_id: UUID,
    *,
    has_matrix: bool = False,
    has_enrichment: bool = False,
) -> ProjectPaperResponse:
    # Check if a PDF file exists for this paper locally (async to not block event loop)
    import asyncio

    from app.core.config import get_settings
    from app.services.pdf_downloader import _make_filename
    from app.sources.base import RawPaper

    settings = get_settings()
    pdf_dir = Path(settings.paper_pdf_dir)

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
    )
    filename = _make_filename(raw)
    dest = pdf_dir / filename

    loop = asyncio.get_running_loop()
    pdf_exists = await loop.run_in_executor(None, lambda: dest.exists() and dest.stat().st_size > 0)
    pdf_path = f"/api/pdf-files/{filename}" if pdf_exists else None

    return ProjectPaperResponse(
        id=pp.id,
        project_id=project_id,
        paper_id=paper.id,
        status=pp.status,
        relevance_label=pp.relevance_label,
        exclusion_reason=pp.exclusion_reason,
        user_note=pp.user_note,
        full_text_status=pp.full_text_status,
        saved_at=pp.saved_at,
        title=paper.title,
        abstract=paper.abstract,
        year=paper.year,
        venue=paper.venue,
        doi=paper.doi,
        arxiv_id=paper.arxiv_id,
        authors=paper.authors if isinstance(paper.authors, list) else [],
        citation_count=paper.citation_count,
        pdf_path=pdf_path,
        has_matrix=has_matrix,
        has_enrichment=has_enrichment,
    )


def _validate_project_paper_update(status: str, exclusion_reason: str | None) -> None:
    if status not in VALID_PROJECT_PAPER_STATUSES:
        raise ValueError(f"Invalid project paper status: {status}")
    if exclusion_reason is not None and exclusion_reason not in VALID_EXCLUSION_REASONS:
        raise ValueError(f"Invalid exclusion reason: {exclusion_reason}")
    if status == "rejected" and not exclusion_reason:
        raise ValueError("Rejected papers require an exclusion reason")
