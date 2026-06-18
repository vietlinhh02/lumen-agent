"""ResearchPipeline — deterministic orchestrator for end-to-end research.

Runs the full search->screen->save->matrix->gap->report flow as Python code,
not as LLM tool calls. This follows the recommended production pattern:
deterministic orchestration for workflow control, LLM only for extraction/
analysis inside individual stages.

Each stage emits ProgressEvent so the UI sees real-time updates.

Cancellation: if cancel_event is set at any await point, the pipeline
raises asyncio.CancelledError and aborts cleanly.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Optional

from app.agents.assistant.events import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    MessageEvent,
    ProgressEvent,
    ToolEvent,
)
from app.agents.assistant.tools.context import get_user
from app.db.models import User

logger = logging.getLogger(__name__)


# ── Config ─────────────────────────────────────────────────────────────────────


@dataclass
class ResearchPipelineConfig:
    """Configuration for the research pipeline."""

    project_id: str
    query: str
    max_papers_to_save: int = 10
    relevance_threshold: str = "medium"  # "high" | "medium" | "low"
    include_gap_section: bool = True
    auto_generate_report: bool = True
    sources: Optional[list[str]] = None


# ── Pipeline ───────────────────────────────────────────────────────────────────


class ResearchPipeline:
    """Deterministic orchestrator that runs search->screen->save->matrix->gap->report.

    Args:
        config: Pipeline configuration.
        cancel_event: Optional asyncio.Event to check for cancellation at each stage.
    """

    def __init__(
        self,
        config: ResearchPipelineConfig,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> None:
        self.config = config
        self.cancel_event = cancel_event or asyncio.Event()

    async def run(self) -> AsyncGenerator[BaseEvent, None]:
        """Run the full pipeline, yielding events.

        Yields:
            ProgressEvent for each stage with progress fraction and human-readable
            message. MessageEvent for the final summary. DoneEvent on completion.
        """
        try:
            # ── Stage 1: Search ─────────────────────────────────────────────────
            yield ProgressEvent(
                stage="search",
                progress=0.0,
                message=f"Searching papers for: {self.config.query}",
            )

            search_outcome = await self._search_papers()
            papers = self._extract_papers(search_outcome)

            yield ProgressEvent(
                stage="search",
                progress=0.15,
                message=f"Found {len(papers)} papers from search",
                data={"count": len(papers)},
            )

            if self.cancel_event.is_set():
                yield ErrorEvent(code="CANCELLED", message="Pipeline cancelled")
                yield DoneEvent(summary="Cancelled.")
                return

            if not papers:
                yield MessageEvent(
                    role="assistant",
                    content="No papers found for your query. Try a different search term.",
                )
                yield DoneEvent()
                return

            # ── Stage 2: Screen by relevance ───────────────────────────────────
            yield ProgressEvent(
                stage="screen",
                progress=0.15,
                message="Screening papers by relevance to your topic...",
            )

            screened = await self._screen_papers(papers)

            yield ProgressEvent(
                stage="screen",
                progress=0.30,
                message=f"{len(screened)} papers passed relevance screen",
                data={"count": len(screened)},
            )

            if self.cancel_event.is_set():
                yield ErrorEvent(code="CANCELLED", message="Pipeline cancelled")
                yield DoneEvent(summary="Cancelled.")
                return

            if not screened:
                yield MessageEvent(
                    role="assistant",
                    content=(
                        "No papers passed the relevance screen for your topic. "
                        "Try a broader or more specific search query."
                    ),
                )
                yield DoneEvent()
                return

            # ── Stage 3: Save top-N to project ─────────────────────────────────
            yield ProgressEvent(
                stage="save",
                progress=0.30,
                message=f"Saving top {min(len(screened), self.config.max_papers_to_save)} papers to project...",
            )

            saved_ids = await self._save_papers(screened)

            yield ProgressEvent(
                stage="save",
                progress=0.45,
                message=f"Saved {len(saved_ids)} papers to project",
                data={"count": len(saved_ids), "project_paper_ids": saved_ids},
            )

            if self.cancel_event.is_set():
                yield ErrorEvent(code="CANCELLED", message="Pipeline cancelled")
                yield DoneEvent(summary="Cancelled.")
                return

            if not saved_ids:
                yield MessageEvent(
                    role="assistant",
                    content="Failed to save any papers. Please try again.",
                )
                yield DoneEvent()
                return

            # ── Stage 4: Generate matrix ───────────────────────────────────────
            yield ProgressEvent(
                stage="matrix",
                progress=0.45,
                message="Generating literature matrix from saved papers...",
            )

            matrix_result = await self._generate_matrix()

            yield ProgressEvent(
                stage="matrix",
                progress=0.65,
                message=f"Matrix generated: {matrix_result.get('created_count', 0)} rows",
                data={"created_count": matrix_result.get("created_count", 0)},
            )

            if self.cancel_event.is_set():
                yield ErrorEvent(code="CANCELLED", message="Pipeline cancelled")
                yield DoneEvent(summary="Cancelled.")
                return

            # ── Stage 5: Detect gaps ───────────────────────────────────────────
            yield ProgressEvent(
                stage="gap",
                progress=0.65,
                message="Detecting research gaps from the matrix...",
            )

            gap_result = await self._detect_gaps()

            yield ProgressEvent(
                stage="gap",
                progress=0.80,
                message=f"Detected {gap_result.get('gap_count', 0)} research gaps",
                data={"gap_count": gap_result.get("gap_count", 0)},
            )

            if self.cancel_event.is_set():
                yield ErrorEvent(code="CANCELLED", message="Pipeline cancelled")
                yield DoneEvent(summary="Cancelled.")
                return

            # ── Stage 6: Generate report ───────────────────────────────────────
            report_id: Optional[str] = None
            if self.config.auto_generate_report:
                yield ProgressEvent(
                    stage="report",
                    progress=0.80,
                    message="Generating literature review report...",
                )

                report_result = await self._generate_report()

                report_id = report_result.get("report_id")
                validation = report_result.get("validation_status", "unknown")

                yield ProgressEvent(
                    stage="report",
                    progress=0.95,
                    message=f"Report generated. Validation: {validation}",
                    data={
                        "report_id": report_id,
                        "validation_status": validation,
                    },
                )

                if self.cancel_event.is_set():
                    yield ErrorEvent(code="CANCELLED", message="Pipeline cancelled")
                    yield DoneEvent(summary="Cancelled.")
                    return

            # ── Final summary ───────────────────────────────────────────────────
            summary = self._build_summary(
                papers_found=len(papers),
                papers_saved=len(saved_ids),
                matrix_rows=matrix_result.get("created_count", 0),
                gaps=gap_result.get("gap_count", 0),
                report_id=report_id,
            )
            yield MessageEvent(role="assistant", content=summary)

        except asyncio.CancelledError:
            yield ErrorEvent(code="PIPELINE_CANCELLED", message="Pipeline was cancelled")
            yield DoneEvent(summary="Cancelled.")
            raise
        except Exception as exc:
            logger.exception("Research pipeline failed at stage")
            yield ErrorEvent(
                code="PIPELINE_FAILED",
                message=f"Pipeline failed: {exc}",
            )
            yield DoneEvent(summary="Pipeline failed.")

    # ── Stage helpers ──────────────────────────────────────────────────────────

    async def _search_papers(self) -> Any:
        """Search papers using the paper search service."""
        from app.schemas.paper import PaperSearchRequest
        from app.services.paper_search import search_and_download

        request = PaperSearchRequest(
            query=self.config.query,
            sources=self.config.sources or ["semantic_scholar", "exa"],
            limit=30,
            download_pdfs=False,
        )

        outcome = await search_and_download(request)
        return outcome

    def _extract_papers(self, outcome: Any) -> list[dict[str, Any]]:
        """Extract papers from SearchOutcome as dicts."""
        papers = []
        for raw in outcome.raw_papers:
            papers.append({
                "paper_id": raw.semantic_scholar_id or raw.arxiv_id or raw.doi or "",
                "title": raw.title,
                "authors": raw.authors,
                "year": raw.year,
                "doi": raw.doi,
                "abstract": raw.abstract,
                "source": raw.source_name,
                "url": raw.url,
                "citation_count": raw.citation_count,
            })
        return papers

    async def _screen_papers(self, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Screen papers by relevance using LLM."""
        from app.ai.prompts import PAPER_SCREEN_SYSTEM, PAPER_SCREEN_USER
        from app.ai.provider import get_provider

        user = get_user()
        if not user:
            logger.warning("No authenticated user for screening, accepting all")
            return papers[: self.config.max_papers_to_save]

        # Get project topic from context for better screening
        project_topic = self.config.query
        research_question = ""

        user_content = PAPER_SCREEN_USER.format(
            topic=project_topic,
            research_question=research_question,
            paper_list=self._format_paper_list(papers),
        )

        provider = get_provider()

        try:
            result = await provider.complete_structured(
                messages=[{"role": "user", "content": user_content}],
                schema={
                    "type": "object",
                    "properties": {
                        "scores": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "index": {"type": "integer"},
                                    "score": {"type": "string", "enum": ["high", "medium", "low"]},
                                },
                                "required": ["index", "score"],
                            },
                        }
                    },
                    "required": ["scores"],
                },
                tool_name="screen_papers",
                system=PAPER_SCREEN_SYSTEM,
                max_tokens=500,
            )
        except Exception as exc:
            logger.warning("Paper screening failed: %s, accepting all", exc)
            return papers[: self.config.max_papers_to_save]

        scores = result.get("scores", [])
        score_map: dict[int, str] = {s["index"]: s["score"] for s in scores}
        threshold = {"high": 3, "medium": 2, "low": 1}.get(self.config.relevance_threshold, 2)

        screened = []
        for i, paper in enumerate(papers):
            score = score_map.get(i + 1, "low")
            rank = {"high": 3, "medium": 2, "low": 1}.get(score, 0)
            if rank >= threshold:
                screened.append(paper)

        return screened

    def _format_paper_list(self, papers: list[dict[str, Any]]) -> str:
        """Format paper list for screening prompt."""
        lines = []
        for i, paper in enumerate(papers):
            abstract = (paper.get("abstract") or "")[:400]
            lines.append(f"[{i+1}] Title: {paper.get('title', 'Unknown')}\nAbstract: {abstract}")
        return "\n\n".join(lines)

    async def _save_papers(self, papers: list[dict[str, Any]]) -> list[str]:
        """Save papers to project, return list of project_paper_ids."""
        from uuid import UUID as PyUUID

        from app.db.session import async_session_factory
        from app.schemas.project import SavePaperRequest
        from app.services.project import save_paper_to_project

        user = get_user()
        if not user:
            logger.warning("No authenticated user, cannot save papers")
            return []

        pid = PyUUID(self.config.project_id)
        saved_ids: list[str] = []

        async with async_session_factory() as db:
            for paper in papers[: self.config.max_papers_to_save]:
                try:
                    save_request = SavePaperRequest(
                        paper_title=paper.get("title", ""),
                        paper_abstract=paper.get("abstract"),
                        paper_year=paper.get("year"),
                        paper_doi=paper.get("doi"),
                        paper_arxiv_id=paper.get("arxiv_id"),
                        paper_semantic_scholar_id=paper.get("paper_id"),
                        paper_url=paper.get("url"),
                        paper_citation_count=paper.get("citation_count"),
                        paper_authors=paper.get("authors", []),
                        paper_source_names=[paper.get("source", "unknown")],
                    )

                    result = await save_paper_to_project(
                        db=db,
                        user=user,
                        project_id=pid,
                        data=save_request,
                    )

                    if result:
                        saved_ids.append(str(result.project_paper_id))
                except Exception as exc:
                    logger.warning("Failed to save paper %s: %s", paper.get("title", ""), exc)

        return saved_ids

    async def _generate_matrix(self) -> dict[str, Any]:
        """Generate matrix via background job with polling."""
        from uuid import UUID as PyUUID

        from app.db.models import BackgroundJob
        from app.db.session import async_session_factory
        from sqlalchemy import select

        user = get_user()
        if not user:
            return {"created_count": 0}

        pid = PyUUID(self.config.project_id)

        async with async_session_factory() as db:
            job = BackgroundJob(
                job_type="matrix_generate",
                project_id=pid,
                user_id=user.id,
                status="pending",
                total=1,
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
            job_id = job.id

        # Launch background task
        from app.routers.matrix import _run_matrix_job

        asyncio.ensure_future(
            _run_matrix_job(job_id, pid, user.id, self.config.query)
        )

        # Poll for completion
        return await self._poll_job(job_id, max_wait=180.0, interval=3.0)

    async def _detect_gaps(self) -> dict[str, Any]:
        """Detect gaps via background job with polling."""
        from uuid import UUID as PyUUID

        from app.db.models import BackgroundJob
        from app.db.session import async_session_factory
        from sqlalchemy import select

        user = get_user()
        if not user:
            return {"gap_count": 0}

        pid = PyUUID(self.config.project_id)

        async with async_session_factory() as db:
            job = BackgroundJob(
                job_type="gap_generate",
                project_id=pid,
                user_id=user.id,
                status="pending",
                total=1,
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
            job_id = job.id

        # Launch background task
        from app.routers.gaps import _run_gap_job

        asyncio.ensure_future(
            _run_gap_job(job_id, pid, user.id, self.config.query, None)
        )

        # Poll for completion
        return await self._poll_job(job_id, max_wait=120.0, interval=2.0)

    async def _generate_report(self) -> dict[str, Any]:
        """Generate report via background job with polling."""
        from uuid import UUID as PyUUID

        from app.db.models import BackgroundJob
        from app.db.session import async_session_factory
        from sqlalchemy import select

        user = get_user()
        if not user:
            return {"report_id": None}

        pid = PyUUID(self.config.project_id)

        async with async_session_factory() as db:
            job = BackgroundJob(
                job_type="report_generate",
                project_id=pid,
                user_id=user.id,
                status="pending",
                total=1,
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
            job_id = job.id

        # Launch background task
        from app.routers.reports import _run_report_job

        asyncio.ensure_future(
            _run_report_job(
                job_id,
                pid,
                user.id,
                self.config.query,
                None,  # research_question
                None,  # title
                self.config.include_gap_section,
                None,  # selected_gap_ids
            )
        )

        # Poll for completion
        return await self._poll_job(job_id, max_wait=120.0, interval=2.0)

    async def _poll_job(
        self,
        job_id: Any,
        max_wait: float = 120.0,
        interval: float = 2.0,
    ) -> dict[str, Any]:
        """Poll a background job until completion or failure."""
        from app.db.models import BackgroundJob
        from app.db.session import async_session_factory
        from sqlalchemy import select

        elapsed = 0.0

        while elapsed < max_wait:
            if self.cancel_event.is_set():
                raise asyncio.CancelledError("Job polling cancelled")

            await asyncio.sleep(interval)
            elapsed += interval

            async with async_session_factory() as db:
                result = await db.execute(
                    select(BackgroundJob).where(BackgroundJob.id == job_id)
                )
                job = result.scalar_one_or_none()

                if job is None:
                    return {"status": "failed", "error": "Job not found"}

                if job.status == "completed":
                    return {
                        "status": "completed",
                        "result": job.result or {},
                        "gap_count": (job.result or {}).get("gap_count"),
                        "created_count": (job.result or {}).get("created_count"),
                        "report_id": (job.result or {}).get("report_id"),
                        "validation_status": (job.result or {}).get("validation_status"),
                    }

                if job.status == "failed":
                    return {
                        "status": "failed",
                        "error": job.error_message or "Unknown error",
                    }

        return {"status": "timeout", "error": f"Job did not complete within {max_wait}s"}

    def _build_summary(
        self,
        papers_found: int,
        papers_saved: int,
        matrix_rows: int,
        gaps: int,
        report_id: Optional[str],
    ) -> str:
        """Build the final summary message."""
        lines = [
            "## Research Pipeline Complete",
            "",
            f"- Papers found: {papers_found}",
            f"- Papers saved: {papers_saved}",
            f"- Matrix rows: {matrix_rows}",
            f"- Research gaps: {gaps}",
        ]

        if report_id:
            lines.append(f"- Report: generated (view at /projects/{self.config.project_id}/report/{report_id})")

        return "\n".join(lines)
