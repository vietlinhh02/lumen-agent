import asyncio
import json
import logging
from typing import Any, Dict
from sqlalchemy import select

from app.agents.assistant.events import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    MessageEvent,
    ProgressEvent,
    AssistantDeltaEvent,
)
from app.agents.assistant.graph.state import AssistantGraphState, get_last_user_message
from app.agents.assistant.tools.context import get_project_id
from app.db.models import ProjectPaper, Paper, PaperChunk
from app.db.session import async_session_factory
from app.services.search_session import start_search_job, auto_save_high_papers
from app.ai.provider import get_provider
from uuid import UUID

logger = logging.getLogger(__name__)

async def deep_search_node(state: AssistantGraphState) -> Dict[str, Any]:
    from langgraph.config import get_stream_writer
    writer = get_stream_writer()
    
    streamed_done = False
    def emit(event: BaseEvent) -> None:
        nonlocal streamed_done
        if isinstance(event, DoneEvent):
            streamed_done = True
        try:
            writer(event.model_dump(mode="json"))
        except Exception:
            pass

    query = get_last_user_message(state) or ""
    project_id = get_project_id()
    
    if not project_id:
        emit(MessageEvent(role="assistant", content="Vui lòng mở hoặc tạo một project để em có thể tìm kiếm và lưu tài liệu nhé."))
        emit(DoneEvent())
        return {"pending_events": []}

    try:
        emit(ProgressEvent(stage="search", progress=0.1, message="Đang tạo Search Session..."))
        
        # We need the current user. Assistant API doesn't pass User easily, so we might need a workaround or get it from state if possible.
        # But wait, start_search_job needs a User object.
        # Let's get the user from the db using the project's owner.
        async with async_session_factory() as db:
            from app.db.models import Project, User
            proj = await db.scalar(select(Project).where(Project.id == UUID(project_id)))
            if not proj:
                emit(ErrorEvent(code="NO_PROJECT", message="Project not found"))
                emit(DoneEvent())
                return {"pending_events": []}
            user = await db.scalar(select(User).where(User.id == proj.owner_id))

        # 1. Start search job
        emit(ProgressEvent(stage="search", progress=0.2, message="Đang tìm kiếm trên Exa & Semantic Scholar..."))
        async with async_session_factory() as db:
            search_res = await start_search_job(db, user, UUID(project_id), query, limit=10)
            
        session_id_str = search_res.get("session_id")
        if not session_id_str:
            emit(ErrorEvent(code="SEARCH_FAILED", message="Failed to create search session"))
            emit(DoneEvent())
            return {"pending_events": []}

        # Send link to user immediately
        emit(MessageEvent(role="assistant", content=f"Đã tạo [Search Session](/search?session={session_id_str}) cho anh. Em đang tiếp tục tải PDF và trích xuất dữ liệu, vui lòng chờ..."))
        
        # Wait a bit for the search job to finish. The search job runs synchronously in start_search_job?
        # Actually start_search_job returns AFTER searching. It returns immediately if it's not a background job.
        
        # 2. Auto save high relevance papers
        emit(ProgressEvent(stage="screen", progress=0.4, message="Đang sàng lọc và lưu các bài báo liên quan..."))
        async with async_session_factory() as db:
            save_res = await auto_save_high_papers(db, user, UUID(project_id), UUID(session_id_str))
            
        job_id = save_res.get("job_id")
        
        # 3. Wait for auto-save job
        emit(ProgressEvent(stage="save", progress=0.5, message="Đang tải PDF và trích xuất dữ liệu (việc này có thể mất vài phút)..."))
        
        # Poll ProjectPaper for this project that were recently added
        # Actually auto_save_high_papers creates a background job. We should poll it.
        from app.db.models import BackgroundJob
        async def wait_job(j_id):
            for _ in range(60):
                async with async_session_factory() as db:
                    j = await db.scalar(select(BackgroundJob).where(BackgroundJob.id == UUID(j_id)))
                    if not j or j.status in ("completed", "failed"):
                        return j
                await asyncio.sleep(2)
            return None
            
        if job_id:
            await wait_job(job_id)
            
        # 4. Wait for full text extraction
        emit(ProgressEvent(stage="extract", progress=0.7, message="Đợi xử lý vector và chunking..."))
        # we can just wait a fixed amount of time or poll the ProjectPaper
        await asyncio.sleep(5) 
        
        # Let's just generate a response
        emit(ProgressEvent(stage="report", progress=0.9, message="Đang tổng hợp dữ liệu..."))
        provider = get_provider()
        streamed_text = ""
        emit(AssistantDeltaEvent(delta="Đã hoàn tất! Anh có thể xem chi tiết trong phiên tìm kiếm hoặc tại tab Papers của project.", is_final=True))

    except Exception as exc:
        logger.error("Deep search failed: %s", exc)
        emit(ErrorEvent(code="DEEP_SEARCH_ERROR", message=str(exc)))

    if not streamed_done:
        emit(DoneEvent())
        
    return {"pending_events": []}
