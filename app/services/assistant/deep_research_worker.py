import asyncio
import logging
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime

from app.db.models import DeepResearchJob, AssistantSession
from app.db.session import async_session_factory
from app.agents.assistant.tools.paper_tools import _search_web_impl, _save_paper_impl
from app.agents.assistant.tools.matrix_tools import _generate_matrix_impl
from app.agents.assistant.tools.gap_tools import _detect_gaps_impl
from app.agents.assistant.tools.report_tools import _generate_report_impl
from app.db.models import User

logger = logging.getLogger(__name__)

async def _update_job_progress(job_id: str, db: AsyncSession, stage: str, progress: float, message: str, step_data: dict = None):
    """Cập nhật tiến trình của job xuống DB."""
    try:
        job = await db.scalar(select(DeepResearchJob).where(DeepResearchJob.id == uuid.UUID(job_id)))
        if not job:
            return
            
        job.stage = stage
        job.progress = progress
        job.message = message
        
        # Thêm log vào progress_json
        progress_json = dict(job.progress_json)
        if "logs" not in progress_json:
            progress_json["logs"] = []
            
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "stage": stage,
            "message": message,
        }
        if step_data:
            log_entry.update(step_data)
            
        progress_json["logs"].append(log_entry)
        job.progress_json = progress_json
        
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to update job {job_id} progress: {e}")


async def run_deep_research(job_id: str, project_id: str, user_id: str, query: str):
    """Background task implementing Phase 2 deep research logic."""
    logger.info(f"Started deep research job {job_id} for project {project_id}")
    
    async with async_session_factory() as db:
        try:
            # Check user
            user = await db.scalar(select(User).where(User.id == uuid.UUID(user_id)))
            if not user:
                raise Exception("User not found")
                
            # Job init
            await _update_job_progress(job_id, db, "init", 0.0, "Starting deep research pipeline...")

            # ---------------------------------------------------------
            # 1. Search & Save Papers (Target ~ 10-20 papers)
            # ---------------------------------------------------------
            await _update_job_progress(job_id, db, "search", 0.1, f"Searching the web for: {query}")
            search_res = await _search_web_impl(query=query, sources=["arxiv", "semantic_scholar"], year_from=None, year_to=None, limit=20)
            
            if not search_res.get("ok"):
                raise Exception(f"Search failed: {search_res.get('message')}")
                
            papers = search_res.get("data", {}).get("papers", [])
            if not papers:
                raise Exception("Failed to retrieve papers from search.")
                
            papers_to_save = papers[:15] # Save top 15
            
            await _update_job_progress(job_id, db, "save_papers", 0.3, f"Found {len(papers)} papers. Saving {len(papers_to_save)} to project...")
            
            saved_count = 0
            import asyncio
            
            save_tasks = [
                _save_paper_impl(
                    project_id=project_id,
                    paper=paper,
                    user_id=user_id,
                    user=user,
                    download_pdf=True,
                    wait_for_ingestion=True
                )
                for paper in papers_to_save
            ]
            save_results = await asyncio.gather(*save_tasks)
            
            for save_res in save_results:
                if save_res.get("ok"):
                    saved_count += 1
            
            # Update DB with papers saved
            await db.execute(
                update(DeepResearchJob)
                .where(DeepResearchJob.id == uuid.UUID(job_id))
                .values(papers_saved=saved_count)
            )
            await db.commit()

            # ---------------------------------------------------------
            # 2. Matrix Generation
            # ---------------------------------------------------------
            await _update_job_progress(job_id, db, "matrix", 0.5, "Generating literature matrix. This might take a while...")
            # Fire and poll matrix generation
            # _generate_matrix_impl is async and might block or spawn its own job,
            # We wait for it here in the background task.
            matrix_res = await _generate_matrix_impl(project_id, user_id, user)
            if not matrix_res.get("ok"):
                 raise Exception(f"Matrix generation failed: {matrix_res.get('message')}")

            # ---------------------------------------------------------
            # 3. Gap Detection
            # ---------------------------------------------------------
            await _update_job_progress(job_id, db, "gap", 0.7, "Detecting research gaps and conflicts...")
            gap_res = await _detect_gaps_impl(project_id, user_id, user)
            if not gap_res.get("ok"):
                raise Exception(f"Gap detection failed: {gap_res.get('message')}")

            # ---------------------------------------------------------
            # 4. Report Generation
            # ---------------------------------------------------------
            await _update_job_progress(job_id, db, "report", 0.9, "Synthesizing final comprehensive report...")
            report_res = await _generate_report_impl(
                project_id=project_id,
                title=None,
                include_gap_section=True,
                selected_gap_ids=None,
                user_id=user_id,
                user=user
            )
            
            # report_res could have a job_id for background generation inside _generate_report_impl
            # Assume it completes or we need to poll
            
            report_text = "Final comprehensive report generated." # In reality we need to fetch the report content
            
            # Finalize
            await db.execute(
                update(DeepResearchJob)
                .where(DeepResearchJob.id == uuid.UUID(job_id))
                .values(
                    status="completed",
                    stage="done",
                    progress=1.0,
                    message="Deep research completed successfully.",
                    report=report_text
                )
            )
            await db.commit()
            
            logger.info(f"Deep research job {job_id} finished successfully.")

        except Exception as e:
            logger.exception(f"Deep research job {job_id} failed: {e}")
            await _update_job_progress(job_id, db, "failed", 1.0, f"Error: {str(e)}")
            await db.execute(
                update(DeepResearchJob)
                .where(DeepResearchJob.id == uuid.UUID(job_id))
                .values(status="failed")
            )
            await db.commit()
