"""Pydantic schemas for all structured LLM outputs.

Each schema is used in two ways:
  1. As a tool input_schema (via .model_json_schema()) when calling complete_structured().
  2. As a validator after the raw dict is returned from the LLM.

Rules enforced here (not just in prompts):
  - evidence_paper_ids must be non-empty for gaps.
  - citation_paper_ids must be non-empty for paragraphs.
  - confidence / risk_level are validated enums.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


# ── Query Planning ─────────────────────────────────────────────────────────────


class QueryPlanOutput(BaseModel):
    """Output of the QueryPlanner node."""

    detected_language: str = Field(description="ISO 639-1 language code detected in the topic.")
    english_query: str = Field(description="Optimized English search query.")
    original_language_query: str | None = Field(
        default=None,
        description="Query in the original language if non-English, else null.",
    )
    core_concepts: list[str] = Field(
        description="Key concepts extracted from the topic (3–6 items).",
        min_length=1,
        max_length=8,
    )
    suggested_sources: list[Literal["semantic_scholar", "exa"]] = Field(
        description="Academic sources best suited for this topic.",
        min_length=1,
    )


# ── Literature Matrix ──────────────────────────────────────────────────────────


class MatrixRowOutput(BaseModel):
    """Structured extraction for one saved paper.

    If a field cannot be extracted from the available text, the model should
    return 'not specified' rather than guessing.
    """

    research_problem: str = Field(description="What problem the paper addresses.")
    method: str = Field(description="Main method or approach used.")
    dataset_or_context: str = Field(description="Dataset, domain, or study setting.")
    key_result: str = Field(description="Main finding or contribution.")
    limitation: str = Field(description="Stated or inferred limitation.")
    contribution: str = Field(description="What the paper uniquely adds to the field.")
    relevance: str = Field(description="Why this paper matters to the project topic.")
    confidence: Literal["high", "medium", "low"] = Field(
        description="Extraction confidence based on available text quality."
    )


# ── Research Facets ────────────────────────────────────────────────────────────


class FacetOutput(BaseModel):
    """Research facets extracted during enrichment."""

    method_family: str | None = Field(default=None, description="High-level method category.")
    domain: str | None = Field(default=None, description="Application domain.")
    dataset_names: list[str] = Field(default_factory=list, description="Named datasets used.")
    metric_names: list[str] = Field(default_factory=list, description="Evaluation metrics reported.")
    limitation_types: list[str] = Field(default_factory=list, description="Categories of limitation.")
    contribution_type: str | None = Field(default=None, description="Type of contribution (empirical, survey, etc.).")
    extraction_confidence: Literal["high", "medium", "low"] = Field(default="medium")


# ── Research Gaps ──────────────────────────────────────────────────────────────


class GapOutput(BaseModel):
    """One evidence-backed research gap.

    evidence_paper_ids must reference saved project_paper IDs.
    The backend rejects gaps where this list is empty.
    """

    title: str = Field(description="Short, specific gap title.")
    description: str = Field(description="Explanation of what is missing and why it matters.")
    evidence_paper_ids: Annotated[list[uuid.UUID], Field(min_length=1)] = Field(
        description="IDs of saved project papers that reveal this gap. Must not be empty."
    )
    evidence_summary: str = Field(
        description="1–2 sentence summary of how the evidence papers expose this gap."
    )
    suggested_direction: str = Field(description="What future study could address this gap.")
    confidence: Literal["high", "medium", "low"] = Field(
        description="Confidence that this gap is real based on evidence."
    )

    @field_validator("evidence_paper_ids")
    @classmethod
    def must_have_evidence(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if not v:
            raise ValueError("evidence_paper_ids must contain at least one paper ID")
        return v


class GapListOutput(BaseModel):
    """Wrapper so the LLM returns a list of gaps as a single tool call."""

    gaps: list[GapOutput] = Field(min_length=0)


# ── Conflicting Findings ───────────────────────────────────────────────────────


class ConflictOutput(BaseModel):
    """One potential conflicting finding between two papers."""

    title: str
    description: str
    paper_a_id: uuid.UUID = Field(description="project_paper_id of the first paper.")
    paper_b_id: uuid.UUID = Field(description="project_paper_id of the second paper.")
    shared_context: str | None = Field(default=None, description="Shared dataset or method scope.")
    claim_a: str | None = Field(default=None)
    claim_b: str | None = Field(default=None)
    possible_explanation: str | None = Field(default=None)
    confidence: Literal["high", "medium", "low"] = Field(default="medium")


class ConflictListOutput(BaseModel):
    conflicts: list[ConflictOutput] = Field(min_length=0)


# ── Report Generation ──────────────────────────────────────────────────────────


class CitedParagraph(BaseModel):
    """One paragraph in a review section with explicit citation IDs.

    citation_paper_ids must reference saved project_paper IDs.
    The citation guardrail service validates each ID before export.
    """

    text: str = Field(description="Paragraph text. Claims must correspond to cited papers.")
    citation_paper_ids: Annotated[list[uuid.UUID], Field(min_length=1)] = Field(
        description="IDs of project papers cited in this paragraph. Must not be empty."
    )

    @field_validator("citation_paper_ids")
    @classmethod
    def must_cite_something(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if not v:
            raise ValueError("Every paragraph must cite at least one paper.")
        return v


class ReviewSectionOutput(BaseModel):
    heading: str
    paragraphs: list[CitedParagraph] = Field(min_length=1)


class ReviewOutput(BaseModel):
    """Full structured review returned by ReviewWriterAgent."""

    sections: list[ReviewSectionOutput] = Field(min_length=1)
