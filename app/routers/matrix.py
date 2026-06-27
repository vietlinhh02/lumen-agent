"""REST endpoints for literature matrix CRUD."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import status as http_status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user
from app.db.models import LiteratureMatrixRow, Project, ProjectPaper, User
from app.db.session import async_session_factory, get_db
from app.schemas.evidence import EvidenceChunkResponse
from app.schemas.matrix import (
    MatrixAggregateBucket,
    MatrixAggregateResponse,
    MatrixEvidenceResponse,
    MatrixFilterRequest,
    MatrixFilterResponse,
    MatrixGenerateRequest,
    MatrixListResponse,
    MatrixRowResponse,
    MatrixRowUpdate,
)
from app.services.extraction_schema import get_effective_schema
from app.services.hybrid_retrieval import retrieve_paper_evidence
from app.services.literature_matrix import (
    aggregate_by_field,
    bulk_delete_by_confidence,
    count_by_confidence,
    delete_row,
    filter_rows,
    get_by_project,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["matrix"])
_PROGRESS_TITLE_LIMIT = 50


async def _verify_project_owner(
    db: AsyncSession,
    user: User,
    project_id: UUID,
) -> Project:
    """Load project and verify ownership. Raises 404 if not found or not owned."""
    stmt = select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


# ── List Matrix Rows ─────────────────────────────────────────────────────


@router.get("/{project_id}/matrix", response_model=MatrixListResponse)
async def list_matrix_rows(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MatrixListResponse:
    await _verify_project_owner(db, user, project_id)
    rows = await get_by_project(db, project_id)
    # T4: include the effective schema so the frontend can render
    # column-typed cells without a second round-trip.
    schema = await get_effective_schema(db, project_id)

    items = []
    for row in rows:
        # Load paper title from relationship
        paper_title = None
        if row.project_paper and row.project_paper.paper:
            paper_title = row.project_paper.paper.title
        items.append(
            MatrixRowResponse(
                id=row.id,
                project_id=row.project_id,
                project_paper_id=row.project_paper_id,
                paper_title=paper_title,
                research_problem=row.research_problem,
                method=row.method,
                dataset_or_context=row.dataset_or_context,
                key_result=row.key_result,
                limitation=row.limitation,
                contribution=row.contribution,
                relevance=row.relevance,
                custom_fields=row.custom_fields or {},
                extraction_confidence=row.extraction_confidence,
                created_by=row.created_by,
                updated_at=row.updated_at,
            )
        )

    return MatrixListResponse(items=items, extraction_schema=schema)


# ── T4: filter & aggregate over typed fields ─────────────────────────────


@router.post("/{project_id}/matrix:filter", response_model=MatrixFilterResponse)
async def filter_matrix_rows(
    project_id: UUID,
    body: MatrixFilterRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MatrixFilterResponse:
    """Return row IDs that match the given predicate."""
    await _verify_project_owner(db, user, project_id)
    try:
        row_ids = await filter_rows(db, project_id, body.field, body.op, body.value)
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return MatrixFilterResponse(row_ids=row_ids, total=len(row_ids))


@router.get(
    "/{project_id}/matrix:aggregate",
    response_model=MatrixAggregateResponse,
)
async def aggregate_matrix(
    project_id: UUID,
    field: str,
    group_by: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MatrixAggregateResponse:
    """Bucket matrix rows by ``field`` value (optionally cross-tabulated by
    ``group_by``). Counts are computed in Python to support both reserved
    and custom fields uniformly."""
    await _verify_project_owner(db, user, project_id)
    try:
        raw_buckets, total = await aggregate_by_field(db, project_id, field, group_by)
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    buckets = [
        MatrixAggregateBucket(key=key, count=count)
        for key, count in sorted(raw_buckets.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return MatrixAggregateResponse(
        field=field,
        group_by=group_by,
        buckets=buckets,
        total=total,
    )


# ── Markdown / CSV export (T4: schema-aware) ───────────────────────────────


@router.get("/{project_id}/matrix:export.md")
async def export_matrix_markdown(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Download every matrix row as a Markdown table keyed by the
    project's effective extraction schema."""
    from fastapi.responses import PlainTextResponse

    await _verify_project_owner(db, user, project_id)
    rows = await get_by_project(db, project_id)
    schema = await get_effective_schema(db, project_id)

    headers = [f.label for f in schema.fields]
    keys = [f.key for f in schema.fields]
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    body_lines: list[str] = []

    from app.services.literature_matrix import (
        RESERVED_FIELD_KEYS as _RESERVED,
    )

    for row in rows:
        paper_title = ""
        if row.project_paper and row.project_paper.paper:
            paper_title = row.project_paper.paper.title
        values: list[str] = []
        for k in keys:
            if k == "paper_title":
                values.append(paper_title)
            elif k in _RESERVED:
                values.append(str(getattr(row, k, "") or ""))
            else:
                v = (row.custom_fields or {}).get(k)
                if isinstance(v, list):
                    values.append(", ".join(str(x) for x in v))
                elif v is None:
                    values.append("")
                else:
                    values.append(str(v))
        body_lines.append("| " + " | ".join(values) + " |")

    md = (
        f"# Literature matrix — {len(rows)} row(s)\n\n"
        + header_line
        + "\n"
        + sep_line
        + "\n"
        + ("\n".join(body_lines) if body_lines else "")
        + "\n"
    )
    return PlainTextResponse(
        content=md,
        media_type="text/markdown",
        headers={
            "Content-Disposition": 'attachment; filename="matrix.md"',
        },
    )


@router.get("/{project_id}/matrix:export.csv")
async def export_matrix_csv(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Download every matrix row as CSV keyed by the project's effective
    extraction schema. Values are JSON-encoded for list / number /
    boolean cells to keep the CSV well-formed."""
    from fastapi.responses import PlainTextResponse

    await _verify_project_owner(db, user, project_id)
    rows = await get_by_project(db, project_id)
    schema = await get_effective_schema(db, project_id)

    import csv
    import io
    import json

    from app.services.literature_matrix import (
        RESERVED_FIELD_KEYS as _RESERVED,
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([f.key for f in schema.fields])
    for row in rows:
        paper_title = ""
        if row.project_paper and row.project_paper.paper:
            paper_title = row.project_paper.paper.title
        cells: list[str] = []
        for f in schema.fields:
            k = f.key
            if k == "paper_title":
                cells.append(paper_title)
            elif k in _RESERVED:
                cells.append(str(getattr(row, k, "") or ""))
            else:
                v = (row.custom_fields or {}).get(k)
                if isinstance(v, (list, dict, bool, int, float)):
                    cells.append(json.dumps(v, ensure_ascii=False))
                else:
                    cells.append("" if v is None else str(v))
        writer.writerow(cells)

    return PlainTextResponse(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="matrix.csv"',
        },
    )


# ── Update Matrix Row ────────────────────────────────────────────────────


@router.patch("/{project_id}/matrix/{row_id}", response_model=MatrixRowResponse)
async def update_matrix_row(
    project_id: UUID,
    row_id: UUID,
    body: MatrixRowUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MatrixRowResponse:
    await _verify_project_owner(db, user, project_id)

    stmt = select(LiteratureMatrixRow).where(
        LiteratureMatrixRow.id == row_id,
        LiteratureMatrixRow.project_id == project_id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Matrix row not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(row, field, value)
    row.created_by = "user"
    row.updated_by = user.id

    await db.commit()
    await db.refresh(row)

    paper_title = None
    if row.project_paper and row.project_paper.paper:
        paper_title = row.project_paper.paper.title

    return MatrixRowResponse(
        id=row.id,
        project_id=row.project_id,
        project_paper_id=row.project_paper_id,
        paper_title=paper_title,
        research_problem=row.research_problem,
        method=row.method,
        dataset_or_context=row.dataset_or_context,
        key_result=row.key_result,
        limitation=row.limitation,
        contribution=row.contribution,
        relevance=row.relevance,
        custom_fields=row.custom_fields or {},
        extraction_confidence=row.extraction_confidence,
        created_by=row.created_by,
        updated_at=row.updated_at,
    )


# ── Delete Matrix Row ────────────────────────────────────────────────────


@router.delete("/{project_id}/matrix/{row_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_matrix_row(
    project_id: UUID,
    row_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    await _verify_project_owner(db, user, project_id)
    deleted = await delete_row(db, project_id, row_id)
    if not deleted:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Matrix row not found",
        )


# ── Evidence for a matrix row (T3 evidence viewer) ───────────────────────


def _evidence_query(row: LiteratureMatrixRow, paper_title: str | None) -> str:
    """Build a retrieval query from the row's claim-bearing fields.

    Falls back to the paper title when every field is empty so the drawer
    still surfaces representative chunks instead of returning nothing.
    """
    parts = [row.research_problem, row.method, row.key_result, row.limitation]
    query = " ".join(p.strip() for p in parts if p and p.strip())
    return query or (paper_title or "")


@router.get("/{project_id}/matrix/{row_id}/evidence", response_model=MatrixEvidenceResponse)
async def get_matrix_row_evidence(
    project_id: UUID,
    row_id: UUID,
    limit: int = 5,
    content_types: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MatrixEvidenceResponse:
    """Return the top supporting chunks for a matrix row.

    Wraps ``retrieve_paper_evidence`` with a query derived from the row's
    fields. Read-only: no DB writes, no migration. ``content_types`` is an
    optional CSV (e.g. ``method,results``) to filter the chunk pool.
    """
    await _verify_project_owner(db, user, project_id)

    stmt = (
        select(LiteratureMatrixRow)
        .options(selectinload(LiteratureMatrixRow.project_paper).selectinload(ProjectPaper.paper))
        .where(
            LiteratureMatrixRow.id == row_id,
            LiteratureMatrixRow.project_id == project_id,
        )
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Matrix row not found",
        )

    paper_title = None
    if row.project_paper and row.project_paper.paper:
        paper_title = row.project_paper.paper.title

    types_list = (
        [t.strip() for t in content_types.split(",") if t.strip()] if content_types else None
    )
    chunks = await retrieve_paper_evidence(
        db,
        row.project_paper_id,
        _evidence_query(row, paper_title),
        limit=max(1, min(limit, 20)),
        content_types=types_list,
    )

    items = [
        EvidenceChunkResponse(
            chunk_id=c.chunk_id,
            project_paper_id=c.project_paper_id,
            chunk_text=c.chunk_text,
            section_label=c.section_label,
            content_type=c.content_type,
            page_start=c.page_start,
            page_end=c.page_end,
            score=c.score,
        )
        for c in chunks
    ]
    return MatrixEvidenceResponse(
        project_paper_id=row.project_paper_id,
        paper_title=paper_title,
        items=items,
    )


# ── Bulk operations ─────────────────────────────────────────────────────


@router.get("/{project_id}/matrix:low-count")
async def low_confidence_count(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Return how many matrix rows have ``extraction_confidence = 'low'``.

    Used by the matrix page to decide whether to show the "Remove Low" button.
    """
    await _verify_project_owner(db, user, project_id)
    count = await count_by_confidence(db, project_id, "low")
    return {"count": count}


@router.post("/{project_id}/matrix:bulk-delete-low")
async def bulk_delete_low_confidence(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Delete every matrix row in this project whose extraction_confidence is 'low'.

    Only deletes the matrix row — the underlying saved paper remains so the
    user can re-generate the matrix later (which will produce a fresh row
    with potentially higher confidence after better extraction).
    """
    await _verify_project_owner(db, user, project_id)
    deleted = await bulk_delete_by_confidence(db, project_id, "low")
    logger.info(
        "User %s bulk-deleted %d low-confidence matrix rows in project %s",
        user.id,
        deleted,
        project_id,
    )
    return {"deleted_count": deleted}


# ── Generate Matrix Rows (trigger AI extraction) ─────────────────────────


@router.post("/{project_id}/matrix:generate")
async def generate_matrix(
    project_id: UUID,
    body: MatrixGenerateRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Start matrix generation as a background job. Returns job info immediately."""
    import asyncio

    from app.db.models import BackgroundJob

    project = await _verify_project_owner(db, user, project_id)

    # Load saved papers count
    count_stmt = select(ProjectPaper).where(
        ProjectPaper.project_id == project_id, ProjectPaper.status == "saved"
    )
    saved_papers = (await db.execute(count_stmt)).scalars().all()
    if not saved_papers:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="No saved papers to generate matrix from",
        )

    # Create a background job record
    job = BackgroundJob(
        job_type="matrix_generate",
        project_id=project_id,
        user_id=user.id,
        status="pending",
        total=len(saved_papers),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Launch background task
    asyncio.ensure_future(_run_matrix_job(job.id, project_id, user.id, project.topic))

    return {"job_id": str(job.id), "status": "running", "total": len(saved_papers)}


async def _run_matrix_job(
    job_id: UUID,
    project_id: UUID,
    user_id: UUID,
    topic: str,
) -> None:
    """Background worker: run matrix extraction."""
    async with async_session_factory() as bg_db:
        job = None
        try:
            from app.db.models import BackgroundJob

            job_result = await bg_db.execute(
                select(BackgroundJob).where(BackgroundJob.id == job_id)
            )
            job = job_result.scalar_one_or_none()
            if not job:
                return

            job.status = "running"
            job.progress = 0
            job.progress_json = {"processed": 0, "total": job.total, "current": ""}
            await bg_db.commit()

            from app.agents.nodes import matrix_extraction_node
            from app.agents.state import ResearchState

            # Hydrate protocol from the project so matrix rows can be grounded
            # in inclusion/exclusion + population + outcome criteria.
            proj_reload = await bg_db.execute(select(Project).where(Project.id == project_id))
            proj_row = proj_reload.scalar_one_or_none()
            protocol = (proj_row.review_protocol if proj_row else None) or None

            # T4: snapshot the schema version at the start of the run so
            # we can warn the user if the schema is edited mid-flight.
            from app.services.extraction_schema import get_effective_schema

            initial_schema = await get_effective_schema(bg_db, project_id)
            schema_version_at_start = initial_schema.version
            schema_is_default_at_start = initial_schema.is_default

            state = ResearchState(
                project_id=project_id,
                user_id=user_id,
                user_topic=topic,
                review_protocol=protocol,
            )

            async def _update_progress(processed: int, total: int, current_paper: str) -> None:
                progress_payload = {
                    "processed": processed,
                    "total": total,
                    "current": current_paper[:_PROGRESS_TITLE_LIMIT],
                }
                async with async_session_factory() as progress_db:
                    await progress_db.execute(
                        update(BackgroundJob)
                        .where(BackgroundJob.id == job_id)
                        .values(progress=processed, progress_json=progress_payload)
                    )
                    await progress_db.commit()

            result = await matrix_extraction_node(state, bg_db, progress_callback=_update_progress)

            # T4: detect schema drift — if the schema was edited during
            # the run, future matrix extractions will use a different
            # shape than the rows we just produced. We surface this in
            # the job result so the UI can warn the user.
            final_schema = await get_effective_schema(bg_db, project_id)
            schema_drifted = (
                final_schema.version != schema_version_at_start
                or final_schema.is_default != schema_is_default_at_start
            )

            created = len(result.get("matrix_rows", []))
            job.status = result.get("matrix_status", "failed")
            job.progress = job.total
            job.progress_json = {
                "processed": job.total,
                "total": job.total,
                "current": "Completed",
            }
            job.result = {
                "created_count": created,
                "skipped_count": job.total - created,
                "schema_version": final_schema.version,
                "schema_drifted": schema_drifted,
                "schema_is_default": final_schema.is_default,
            }
            from datetime import UTC, datetime

            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            await bg_db.commit()

        except Exception as exc:
            logger.exception("Background matrix job failed: %s", exc)
            try:
                if job is not None:
                    job.status = "failed"
                    job.error_message = str(exc)[:500]
                    job.progress_json = {
                        "processed": job.progress,
                        "total": job.total,
                        "current": "Failed",
                    }
                    from datetime import UTC, datetime

                    job.completed_at = datetime.now(UTC).replace(tzinfo=None)
                    await bg_db.commit()
            except Exception:
                pass
