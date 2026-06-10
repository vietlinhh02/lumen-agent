"""REST endpoint for knowledge graph visualization."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import Project, User
from app.db.session import get_db
from app.schemas.knowledge_graph import KnowledgeGraphResponse
from app.services.knowledge_graph import build_knowledge_graph

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge-graph"])


@router.get("/{project_id}/knowledge-graph", response_model=KnowledgeGraphResponse)
async def get_knowledge_graph(
    project_id: UUID,
    node_types: str | None = None,
    min_connections: int = 1,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeGraphResponse:
    """Build and return the knowledge graph for a project.

    Query params:
        node_types: comma-separated list of node types to include
                    (paper, method, dataset, limitation). Default: all.
        min_connections: hide nodes with fewer connections. Default: 1.
    """
    # Verify ownership
    stmt = select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Parse node_types filter
    allowed = None
    if node_types:
        allowed = [t.strip() for t in node_types.split(",") if t.strip()]

    result = await build_knowledge_graph(
        db,
        project_id,
        node_types=allowed,
        min_connections=min_connections,
    )

    return KnowledgeGraphResponse(**result)
