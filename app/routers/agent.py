"""REST endpoints for the LangGraph agent workflow."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import run_research_workflow, stream_research_workflow
from app.core.security import get_current_user
from app.db.models import Project, User
from app.db.session import get_db
from app.schemas.agent import StartWorkflowRequest, WorkflowStatusResponse
import json
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])

@router.post("/stream")
async def stream_workflow(
    body: StartWorkflowRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run the full research workflow and stream progress via SSE."""
    import uuid

    # Verify project ownership
    project_result = await db.execute(
        select(Project).where(Project.id == uuid.UUID(body.project_id), Project.owner_id == user.id)
    )
    project = project_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # If project has no topic yet, update it
    if not project.topic or project.topic.strip() == "":
        project.topic = body.topic
    if body.research_question:
        project.research_question = body.research_question
    await db.commit()

    async def event_generator():
        try:
            async for output in stream_research_workflow(
                project_id=str(project.id),
                user_id=str(user.id),
                topic=body.topic,
                research_question=body.research_question,
            ):
                # Clean up state to only include lightweight status fields for the UI
                state = output.get("state", {})
                safe_state = {
                    "current_node": state.get("current_node"),
                    "completed": state.get("completed", False),
                    "papers_found": len(state.get("raw_papers", [])),
                    "matrix_rows": len(state.get("matrix_rows", [])),
                    "gaps_count": len(state.get("gaps", [])),
                    "report_sections": len(state.get("report_sections", [])),
                }
                yield {
                    "event": "update",
                    "data": json.dumps({"node": output.get("node"), "state": safe_state})
                }
            yield {
                "event": "complete",
                "data": json.dumps({"status": "done"})
            }
        except Exception as exc:
            logger.exception("Streaming workflow failed for project %s", body.project_id)
            yield {
                "event": "error",
                "data": json.dumps({"detail": str(exc)})
            }

    return EventSourceResponse(event_generator())

@router.post("/run", response_model=WorkflowStatusResponse)
async def start_workflow(
    body: StartWorkflowRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WorkflowStatusResponse:
    """Run the full research workflow for a project.

    Executes: query_planner → search → save_screened → matrix_extraction
    → gap_analysis → review_writer → citation_validator.
    """
    # Verify project ownership
    import uuid

    project_result = await db.execute(
        select(Project).where(Project.id == uuid.UUID(body.project_id), Project.owner_id == user.id)
    )
    project = project_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # If project has no topic yet, update it
    if not project.topic or project.topic.strip() == "":
        project.topic = body.topic
    if body.research_question:
        project.research_question = body.research_question
    await db.commit()

    # Run the workflow
    try:
        state = await run_research_workflow(
            project_id=str(project.id),
            user_id=str(user.id),
            topic=body.topic,
            research_question=body.research_question,
        )
    except Exception as exc:
        logger.exception("Workflow failed for project %s", body.project_id)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow failed: {exc}",
        ) from exc

    # Build response
    return WorkflowStatusResponse(
        project_id=str(state.project_id),
        current_node=state.current_node,
        completed=state.completed,
        papers_found=len(state.raw_papers),
        source_diagnostics=state.source_diagnostics,
        matrix_rows=len(state.matrix_rows),
        matrix_status=state.matrix_status,
        gaps_count=len(state.gaps),
        gap_status=state.gap_status,
        report_sections=state.report_sections,
        report_status=state.report_status,
        citation_valid=state.citation_validation.get("valid"),
        invalid_citation_ids=state.citation_validation.get("invalid_ids", []),
        errors=state.errors,
    )
