"""REST endpoints for the PRISMA-style project audit (T2).

Read-only aggregate views over existing tables — search runs, project
papers, matrix rows, review citations. Three surfaces:

- GET  /{project_id}/audit               — JSON payload
- GET  /{project_id}/audit/export        — Markdown file (default)
- GET  /{project_id}/audit/export?fmt=csv — CSV file
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.audit import PrismaAuditResponse
from app.services.audit import (
    build_project_audit,
    render_audit_csv,
    render_audit_markdown,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])


@router.get("/{project_id}/audit", response_model=PrismaAuditResponse)
async def get_project_audit(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PrismaAuditResponse:
    """Return the PRISMA-style audit summary for a project.

    Counts are derived from existing data — no new state is written.
    """
    audit = await build_project_audit(db, user, project_id)
    if audit is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return audit


@router.get("/{project_id}/audit/export")
async def export_project_audit(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    fmt: str = Query("markdown", pattern="^(markdown|csv)$"),
) -> PlainTextResponse:
    """Export the audit as Markdown (default) or CSV."""
    audit = await build_project_audit(db, user, project_id)
    if audit is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    if fmt == "csv":
        content = render_audit_csv(audit)
        media_type = "text/csv"
        suffix = "csv"
    else:
        content = render_audit_markdown(audit)
        media_type = "text/markdown"
        suffix = "md"

    safe_title = "".join(c if c.isalnum() else "_" for c in audit.project_title).strip("_")[:40]
    filename = f"prisma_audit_{safe_title or 'project'}.{suffix}"
    return PlainTextResponse(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
