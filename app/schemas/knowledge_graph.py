"""Pydantic models for knowledge graph API endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GraphNodeResponse(BaseModel):
    id: str
    label: str
    full_label: str | None = None
    type: str
    year: int | None = None
    abstract: str | None = None
    authors: str | None = None
    venue: str | None = None
    url: str | None = None
    project_paper_id: str | None = None
    connections: int = 0


class GraphLinkResponse(BaseModel):
    source: str
    target: str
    relation: str


class GraphStatsResponse(BaseModel):
    paper_count: int = 0
    method_count: int = 0
    dataset_count: int = 0
    limitation_count: int = 0
    total_edges: int = 0


class KnowledgeGraphResponse(BaseModel):
    nodes: list[GraphNodeResponse] = Field(default_factory=list)
    links: list[GraphLinkResponse] = Field(default_factory=list)
    stats: GraphStatsResponse = Field(default_factory=GraphStatsResponse)
