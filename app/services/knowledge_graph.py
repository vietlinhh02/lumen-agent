"""Build knowledge graph from matrix rows and paper metadata."""

from __future__ import annotations

import logging
from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ProjectPaper

logger = logging.getLogger(__name__)

# ── Node type constants ──────────────────────────────────────────────────────

NODE_TYPE_PAPER = "paper"
NODE_TYPE_METHOD = "method"
NODE_TYPE_DATASET = "dataset"
NODE_TYPE_LIMITATION = "limitation"

EDGE_USES_METHOD = "uses_method"
EDGE_EVALUATES_DATASET = "evaluates_dataset"
EDGE_HAS_LIMITATION = "has_limitation"
EDGE_SHARES_METHOD = "shares_method"
EDGE_SHARES_DATASET = "shares_dataset"

_CONCEPT_TYPES = {NODE_TYPE_METHOD, NODE_TYPE_DATASET, NODE_TYPE_LIMITATION}


async def build_knowledge_graph(
    db: AsyncSession,
    project_id: UUID,
    node_types: list[str] | None = None,
    min_connections: int = 1,
) -> dict:
    """Build a graph payload from saved papers and their matrix rows.

    Returns ``{ nodes: [...], links: [...], stats: {...} }``.
    """
    allowed_types = (
        set(node_types)
        if node_types
        else {
            NODE_TYPE_PAPER,
            NODE_TYPE_METHOD,
            NODE_TYPE_DATASET,
            NODE_TYPE_LIMITATION,
        }
    )

    # 1. Load saved project_papers with matrix rows
    stmt = (
        select(ProjectPaper)
        .options(
            selectinload(ProjectPaper.paper),
            selectinload(ProjectPaper.matrix_row),
        )
        .where(
            ProjectPaper.project_id == project_id,
            ProjectPaper.status == "saved",
        )
    )
    project_papers = (await db.execute(stmt)).scalars().all()

    if not project_papers:
        return {"nodes": [], "links": [], "stats": _empty_stats()}

    # 2. Build nodes and edges
    nodes: list[dict] = []
    links: list[dict] = []
    node_ids_seen: set[str] = set()

    # Track concept → paper mapping for shared-concept edges
    method_to_papers: dict[str, list[str]] = defaultdict(list)
    dataset_to_papers: dict[str, list[str]] = defaultdict(list)

    # Connection counts per node
    connection_counts: dict[str, int] = defaultdict(int)

    for pp in project_papers:
        paper = pp.paper
        matrix = pp.matrix_row
        paper_node_id = str(pp.id)

        # Paper node
        if NODE_TYPE_PAPER in allowed_types and paper_node_id not in node_ids_seen:
            nodes.append(
                {
                    "id": paper_node_id,
                    "label": _truncate(paper.title, 36),
                    "full_label": paper.title,
                    "type": NODE_TYPE_PAPER,
                    "year": paper.year,
                    "abstract": paper.abstract,
                    "authors": _format_authors(paper.authors),
                    "venue": paper.venue,
                    "url": paper.url,
                    "project_paper_id": paper_node_id,
                }
            )
            node_ids_seen.add(paper_node_id)

        if not matrix:
            continue

        # Method node
        method = _clean_value(matrix.method)
        if method and NODE_TYPE_METHOD in allowed_types:
            method_node_id = f"method:{method.lower()}"
            if method_node_id not in node_ids_seen:
                nodes.append(
                    {
                        "id": method_node_id,
                        "label": _truncate(method, 32),
                        "full_label": method,
                        "type": NODE_TYPE_METHOD,
                    }
                )
                node_ids_seen.add(method_node_id)

            links.append(
                {
                    "source": paper_node_id,
                    "target": method_node_id,
                    "relation": EDGE_USES_METHOD,
                }
            )
            connection_counts[paper_node_id] += 1
            connection_counts[method_node_id] += 1
            method_to_papers[method.lower()].append(paper_node_id)

        # Dataset node
        dataset = _clean_value(matrix.dataset_or_context)
        if dataset and NODE_TYPE_DATASET in allowed_types:
            dataset_node_id = f"dataset:{dataset.lower()}"
            if dataset_node_id not in node_ids_seen:
                nodes.append(
                    {
                        "id": dataset_node_id,
                        "label": _truncate(dataset, 32),
                        "full_label": dataset,
                        "type": NODE_TYPE_DATASET,
                    }
                )
                node_ids_seen.add(dataset_node_id)

            links.append(
                {
                    "source": paper_node_id,
                    "target": dataset_node_id,
                    "relation": EDGE_EVALUATES_DATASET,
                }
            )
            connection_counts[paper_node_id] += 1
            connection_counts[dataset_node_id] += 1
            dataset_to_papers[dataset.lower()].append(paper_node_id)

        # Limitation node
        limitation = _clean_value(matrix.limitation)
        if limitation and NODE_TYPE_LIMITATION in allowed_types:
            lim_node_id = f"limitation:{limitation.lower()}"
            if lim_node_id not in node_ids_seen:
                nodes.append(
                    {
                        "id": lim_node_id,
                        "label": _truncate(limitation, 34),
                        "full_label": limitation,
                        "type": NODE_TYPE_LIMITATION,
                    }
                )
                node_ids_seen.add(lim_node_id)

            links.append(
                {
                    "source": paper_node_id,
                    "target": lim_node_id,
                    "relation": EDGE_HAS_LIMITATION,
                }
            )
            connection_counts[paper_node_id] += 1
            connection_counts[lim_node_id] += 1

    # 3. Add paper↔paper edges for shared concepts
    paper_set = {str(pp.id) for pp in project_papers}

    for _method_key, paper_ids in method_to_papers.items():
        if len(paper_ids) >= 2:
            for i in range(len(paper_ids)):
                for j in range(i + 1, len(paper_ids)):
                    if paper_ids[i] in paper_set and paper_ids[j] in paper_set:
                        links.append(
                            {
                                "source": paper_ids[i],
                                "target": paper_ids[j],
                                "relation": EDGE_SHARES_METHOD,
                            }
                        )
                        connection_counts[paper_ids[i]] += 1
                        connection_counts[paper_ids[j]] += 1

    for _dataset_key, paper_ids in dataset_to_papers.items():
        if len(paper_ids) >= 2:
            for i in range(len(paper_ids)):
                for j in range(i + 1, len(paper_ids)):
                    if paper_ids[i] in paper_set and paper_ids[j] in paper_set:
                        links.append(
                            {
                                "source": paper_ids[i],
                                "target": paper_ids[j],
                                "relation": EDGE_SHARES_DATASET,
                            }
                        )
                        connection_counts[paper_ids[i]] += 1
                        connection_counts[paper_ids[j]] += 1

    # 4. Filter by min_connections
    if min_connections > 1:
        connected_ids = {nid for nid, cnt in connection_counts.items() if cnt >= min_connections}
        nodes = [n for n in nodes if n["id"] in connected_ids]
        links = [
            lnk
            for lnk in links
            if lnk["source"] in connected_ids and lnk["target"] in connected_ids
        ]

    # 5. Attach connection count to nodes
    for node in nodes:
        node["connections"] = connection_counts.get(node["id"], 0)

    # 6. Compute stats
    stats = {
        "paper_count": sum(1 for n in nodes if n["type"] == NODE_TYPE_PAPER),
        "method_count": sum(1 for n in nodes if n["type"] == NODE_TYPE_METHOD),
        "dataset_count": sum(1 for n in nodes if n["type"] == NODE_TYPE_DATASET),
        "limitation_count": sum(1 for n in nodes if n["type"] == NODE_TYPE_LIMITATION),
        "total_edges": len(links),
    }

    return {"nodes": nodes, "links": links, "stats": stats}


async def expand_query_with_graph_context(
    db: AsyncSession,
    project_id: UUID,
    query: str,
    max_terms: int = 8,
) -> str:
    """Expand a retrieval query with project graph concepts.

    The graph remains computed from current matrix rows, but retrieval can now
    use the same concept structure that the visual map shows.
    """
    graph = await build_knowledge_graph(db, project_id)
    concept_terms = _rank_graph_concepts(
        graph["nodes"],
        query,
        max_terms=max_terms,
    )
    if not concept_terms:
        return query
    return f"{query} {' '.join(concept_terms)}"


async def build_graph_context(
    db: AsyncSession,
    project_id: UUID,
    query: str | None = None,
    max_concepts_per_type: int = 5,
    max_relationships: int = 8,
) -> str:
    """Return prompt-ready graph context for downstream AI tasks."""
    graph = await build_knowledge_graph(db, project_id)
    nodes = graph["nodes"]
    links = graph["links"]
    if not nodes:
        return "No knowledge graph context available."

    node_by_id = {node["id"]: node for node in nodes}
    query_text = query or ""

    def top_concepts(node_type: str) -> list[str]:
        candidates = [node for node in nodes if node["type"] == node_type]
        ranked = sorted(
            candidates,
            key=lambda node: _concept_rank(node, query_text),
            reverse=True,
        )
        return [
            _compact_label(str(node.get("full_label") or node.get("label")))
            for node in ranked[:max_concepts_per_type]
            if node.get("full_label") or node.get("label")
        ]

    relationship_lines: list[str] = []
    for link in links:
        if link["relation"] not in {EDGE_SHARES_METHOD, EDGE_SHARES_DATASET}:
            continue
        source = node_by_id.get(link["source"])
        target = node_by_id.get(link["target"])
        if not source or not target:
            continue
        relation = "shared method" if link["relation"] == EDGE_SHARES_METHOD else "shared dataset"
        source_label = _compact_label(str(source.get("full_label") or source.get("label")))
        target_label = _compact_label(str(target.get("full_label") or target.get("label")))
        relationship_lines.append(f"- {source_label} <-> {target_label}: {relation}")
        if len(relationship_lines) >= max_relationships:
            break

    sections = ["Knowledge graph context:"]
    for label, node_type in (
        ("Central methods", NODE_TYPE_METHOD),
        ("Central datasets or contexts", NODE_TYPE_DATASET),
        ("Recurring limitations", NODE_TYPE_LIMITATION),
    ):
        concepts = top_concepts(node_type)
        if concepts:
            sections.append(f"{label}: {', '.join(concepts)}")
    if relationship_lines:
        sections.append("Shared paper relationships:\n" + "\n".join(relationship_lines))

    return "\n".join(sections)


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


def _rank_graph_concepts(nodes: list[dict], query: str, max_terms: int) -> list[str]:
    ranked = sorted(
        [node for node in nodes if node.get("type") in _CONCEPT_TYPES],
        key=lambda node: _concept_rank(node, query),
        reverse=True,
    )
    terms: list[str] = []
    seen: set[str] = set()
    for node in ranked:
        label = _compact_label(str(node.get("full_label") or node.get("label") or ""))
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(label)
        if len(terms) >= max_terms:
            break
    return terms


def _concept_rank(node: dict, query: str) -> float:
    label = str(node.get("full_label") or node.get("label") or "")
    query_tokens = set(_simple_tokens(query))
    label_tokens = set(_simple_tokens(label))
    overlap = len(query_tokens & label_tokens)
    return overlap * 10.0 + float(node.get("connections", 0))


def _simple_tokens(text: str) -> list[str]:
    return [part.lower() for part in text.replace("/", " ").replace("-", " ").split() if part]


def _compact_label(text: str, max_words: int = 10, max_chars: int = 120) -> str:
    words = text.strip().split()
    compact = " ".join(words[:max_words])
    if len(compact) > max_chars:
        compact = compact[: max_chars - 1].rstrip()
    return compact


def _clean_value(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    normalized = cleaned.lower()
    invalid_prefixes = (
        "not specified",
        "n/a",
        "none",
        "unknown",
        "not available",
        "unspecified",
    )
    if not normalized or any(normalized.startswith(prefix) for prefix in invalid_prefixes):
        return None
    return cleaned


def _format_authors(authors: list | None) -> str:
    if not authors:
        return ""
    names = []
    for a in authors:
        if isinstance(a, dict):
            names.append(a.get("name", str(a)))
        else:
            names.append(str(a))
    if len(names) > 3:
        return ", ".join(names[:3]) + " et al."
    return ", ".join(names)


def _empty_stats() -> dict:
    return {
        "paper_count": 0,
        "method_count": 0,
        "dataset_count": 0,
        "limitation_count": 0,
        "total_edges": 0,
    }
