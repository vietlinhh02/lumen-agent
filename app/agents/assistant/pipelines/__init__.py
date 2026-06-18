"""Pipeline orchestrators for the Assistant.

Deterministic workflow orchestrators that run multi-stage pipelines as Python
code, not as LLM tool calls. Each pipeline emits ProgressEvent for real-time
UI feedback.

Usage:
    from app.agents.assistant.pipelines import ResearchPipeline, ResearchPipelineConfig

    config = ResearchPipelineConfig(
        project_id="...",
        query="LLM evaluation",
    )
    pipeline = ResearchPipeline(config)
    async for event in pipeline.run():
        print(event)
"""

from __future__ import annotations

from app.agents.assistant.pipelines.research_pipeline import (
    ResearchPipeline,
    ResearchPipelineConfig,
)

__all__ = [
    "ResearchPipeline",
    "ResearchPipelineConfig",
]
