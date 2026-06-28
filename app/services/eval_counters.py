"""In-memory evaluation counters for the /api/stats/eval endpoint.

Process-local singleton. Resets on restart.
Covers three metric families:
  - citation_guardrail: pass/fail counts from report_generation
  - rag_injector: latency samples from the assistant RAG injector
  - assistant_sessions: wall-time and success/failure counts
"""

from __future__ import annotations



import asyncio
from sqlalchemy import text
from app.db.session import async_session_factory

async def _insert_eval_log(metric_type: str, value1: float, value2: float = 0.0):
    try:
        async with async_session_factory() as db:
            await db.execute(
                text("INSERT INTO eval_logs (metric_type, value1, value2) VALUES (:m, :v1, :v2)"),
                {"m": metric_type, "v1": value1, "v2": value2}
            )
            await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Failed to log eval metric: %s", e)

class EvalCounters:
    """Helper for dispatching DB eval logs."""
    
    class _LatencyTracker:
        def record(self, elapsed_ms: float) -> None:
            asyncio.create_task(_insert_eval_log("rag_latency", elapsed_ms))
            
    class _CitationCounter:
        def record(self, total: int, invalid: int) -> None:
            asyncio.create_task(_insert_eval_log("citation_check", float(total), float(invalid)))
            
    class _SessionCounter:
        def record(self, wall_time_s: float, success: bool) -> None:
            asyncio.create_task(_insert_eval_log("assistant_session", wall_time_s, 1.0 if success else 0.0))

    def __init__(self):
        self.citation = self._CitationCounter()
        self.rag_injector = self._LatencyTracker()
        self.sessions = self._SessionCounter()

eval_counters = EvalCounters()
