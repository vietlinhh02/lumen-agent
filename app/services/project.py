"""Project CRUD and paper management business logic."""

from __future__ import annotations

import logging
from pathlib import Path
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
    SavePaperRequest,
    SavePaperResponse,
    UpdatePaperRequest,
)
from app.services.pdf_downloader import PDFDownloader

logger = logging.getLogger(__name__)


# ── Project CRUD ───────────────────────────────────────────────────────────


async def create_project(db: AsyncSession, user: User, data: ProjectCreate) -> ProjectResponse:
    project = Project(
        owner_id=user.id,
        title=data.title,
        topic=data.topic,
        research_question=data.research_question,
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
            .where(ProjectPaper.project_id.in_(project_ids))
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
        select(func.count(ProjectPaper.id)).where(ProjectPaper.project_id == project_id)
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

    await db.commit()
    await db.refresh(project)

    paper_count_result = await db.execute(
        select(func.count(ProjectPaper.id)).where(ProjectPaper.project_id == project_id)
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
        await db.commit()
        await db.refresh(pp)
    else:
        pp = ProjectPaper(
            project_id=project_id,
            paper_id=paper.id,
            relevance_label=data.relevance_label,
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

    # Optional PDF download
    pdf_path: str | None = None
    full_text_status: str | None = None
    if data.download_pdf:
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
        settings = get_settings()
        downloader = PDFDownloader(output_dir=Path(settings.paper_pdf_dir), timeout=60)
        pdf_result = await downloader.download(raw)
        if pdf_result is not None:
            pdf_path = str(pdf_result)
            # Run PDF ingestion pipeline
            from app.services.pdf_ingestion import ingest_pdf

            full_text_status = await ingest_pdf(db, pp.id, pdf_result)

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
        .where(ProjectPaper.project_id == project_id)
        .order_by(ProjectPaper.saved_at.desc())
    )
    rows = result.all()
    return [_to_project_paper_response(pp, paper, project_id) for pp, paper in rows]


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
        pp.status = data.status

    await db.commit()
    await db.refresh(pp)
    return _to_project_paper_response(pp, paper, project_id)


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


async def _upsert_paper(db: AsyncSession, data: SavePaperRequest) -> Paper:
    """Find existing paper or create a new one. Deduplicates by strongest ID."""
    paper: Paper | None = None

    # Try by strongest identifier first
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
        status=p.status,
        created_at=p.created_at,
        updated_at=p.updated_at,
        paper_count=paper_count,
    )


def _to_project_paper_response(
    pp: ProjectPaper,
    paper: Paper,
    project_id: UUID,
) -> ProjectPaperResponse:
    has_matrix = False
    has_enrichment = False

    # Check if a PDF file exists for this paper locally
    from pathlib import Path

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
    pdf_path = f"/api/pdf-files/{filename}" if dest.exists() and dest.stat().st_size > 0 else None

    return ProjectPaperResponse(
        id=pp.id,
        project_id=project_id,
        paper_id=paper.id,
        status=pp.status,
        relevance_label=pp.relevance_label,
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
