"""Tool: qa_search_papers — RAG Q&A over saved project papers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.ai.provider import get_provider
from app.services.assistant_tools.ids import coerce_uuid
from app.services.hybrid_retrieval import retrieve_project_evidence

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: AssistantRunner | None = None) -> dict:
    project_id = coerce_uuid(args["project_id"])
    question = args["question"]

    chunks = await retrieve_project_evidence(db, project_id, question, limit=10)
    chunk_text = "\n\n".join(
        (
            f"[paper {str(chunk.project_paper_id)[:8]} | "
            f"{chunk.section_label or chunk.content_type}]\n{chunk.chunk_text}"
        )
        for chunk in chunks[:6]
    )

    system = (
        "You are a research assistant. Answer the user's question based ONLY on "
        "the provided evidence. Cite the paper ID at the end of each claim in "
        "the format [paper XXXXXXXX] (the 8-char prefix shown in evidence). "
        "If the evidence doesn't support an answer, say so."
    )
    user_msg = f"Question: {question}\n\nEvidence:\n{chunk_text}"

    provider = get_provider()
    answer = await provider.complete(
        messages=[{"role": "user", "content": user_msg}],
        system=system,
        max_tokens=800,
    )

    return {
        "answer": answer,
        "cited_paper_ids": [str(c.project_paper_id) for c in chunks[:6]],
        "evidence_count": len(chunks[:6]),
    }
