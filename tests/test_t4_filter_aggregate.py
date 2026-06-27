"""Tests for T4 Phase 3+4 additions: filter, aggregate, export,
schema coverage, and audit integration.

Covers the ``app.services.literature_matrix`` filter / aggregate /
coverage helpers and the matrix router endpoints that depend on them.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.schemas.extraction_schema import ExtractionField
from app.services.literature_matrix import (
    RESERVED_FIELD_KEYS,
    aggregate_by_field,
    field_coverage,
    filter_rows,
)


# ── filter_rows ───────────────────────────────────────────────────────────


def _row(pp_id=None, *, method="RAG", key_result="+5%", custom=None, **kwargs):
    pp = SimpleNamespace()
    pp.id = pp_id or uuid4()
    base = {
        "id": uuid4(),
        "project_paper_id": pp.id,
        "research_problem": "x",
        "method": method,
        "dataset_or_context": "d",
        "key_result": key_result,
        "limitation": "l",
        "contribution": "c",
        "relevance": "r",
        "custom_fields": custom or {},
        "project_paper": pp,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_filter_rows_eq_on_reserved_field():
    rows = [
        _row(method="RAG"),
        _row(method="BM25"),
        _row(method="RAG"),
    ]
    db = AsyncMock()
    with patch(
        "app.services.literature_matrix.get_by_project",
        AsyncMock(return_value=rows),
    ):
        hits = await filter_rows(db, uuid4(), "method", "eq", "RAG")
    assert len(hits) == 2


@pytest.mark.asyncio
async def test_filter_rows_neq_returns_mismatches():
    rows = [_row(method="RAG"), _row(method="BM25"), _row(method="Dense")]
    db = AsyncMock()
    with patch(
        "app.services.literature_matrix.get_by_project",
        AsyncMock(return_value=rows),
    ):
        hits = await filter_rows(db, uuid4(), "method", "neq", "RAG")
    assert len(hits) == 2


@pytest.mark.asyncio
async def test_filter_rows_contains():
    rows = [
        _row(custom={"design": "RCT cohort study"}),
        _row(custom={"design": "case report"}),
        _row(custom={}),
    ]
    db = AsyncMock()
    with patch(
        "app.services.literature_matrix.get_by_project",
        AsyncMock(return_value=rows),
    ):
        hits = await filter_rows(db, uuid4(), "design", "contains", "cohort")
    assert len(hits) == 1


@pytest.mark.asyncio
async def test_filter_rows_gt_number():
    rows = [
        _row(custom={"sample_size": 100}),
        _row(custom={"sample_size": 250}),
        _row(custom={"sample_size": 1000}),
    ]
    db = AsyncMock()
    with patch(
        "app.services.literature_matrix.get_by_project",
        AsyncMock(return_value=rows),
    ):
        hits = await filter_rows(db, uuid4(), "sample_size", "gt", 200)
    assert len(hits) == 2


@pytest.mark.asyncio
async def test_filter_rows_in_list():
    rows = [
        _row(custom={"country": "US"}),
        _row(custom={"country": "VN"}),
        _row(custom={"country": "DE"}),
    ]
    db = AsyncMock()
    with patch(
        "app.services.literature_matrix.get_by_project",
        AsyncMock(return_value=rows),
    ):
        hits = await filter_rows(db, uuid4(), "country", "in", ["VN", "DE"])
    assert len(hits) == 2


@pytest.mark.asyncio
async def test_filter_rows_skips_null_values_when_eq_null():
    """Rows with a null value match ``op='eq'`` with target=None."""
    rows = [
        _row(custom={}),
        _row(custom={"x": "y"}),
    ]
    db = AsyncMock()
    with patch(
        "app.services.literature_matrix.get_by_project",
        AsyncMock(return_value=rows),
    ):
        hits = await filter_rows(db, uuid4(), "x", "eq", None)
    assert len(hits) == 1  # only the row with x is missing


# ── aggregate_by_field ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aggregate_counts_by_reserved_field():
    rows = [
        _row(method="RAG"),
        _row(method="RAG"),
        _row(method="BM25"),
    ]
    db = AsyncMock()
    with patch(
        "app.services.literature_matrix.get_by_project",
        AsyncMock(return_value=rows),
    ):
        buckets, total = await aggregate_by_field(db, uuid4(), "method")
    assert total == 3
    assert buckets == {"RAG": 2, "BM25": 1}


@pytest.mark.asyncio
async def test_aggregate_groups_by_secondary_field():
    rows = [
        _row(method="RAG", custom={"study_type": "clinical"}),
        _row(method="RAG", custom={"study_type": "clinical"}),
        _row(method="RAG", custom={"study_type": "preclinical"}),
    ]
    db = AsyncMock()
    with patch(
        "app.services.literature_matrix.get_by_project",
        AsyncMock(return_value=rows),
    ):
        buckets, _ = await aggregate_by_field(db, uuid4(), "method", group_by="study_type")
    assert buckets == {
        "RAG|clinical": 2,
        "RAG|preclinical": 1,
    }


@pytest.mark.asyncio
async def test_aggregate_excludes_missing_values():
    rows = [
        _row(custom={"design": "RCT"}),
        _row(custom={}),  # design missing
        _row(custom={"design": "cohort"}),
    ]
    db = AsyncMock()
    with patch(
        "app.services.literature_matrix.get_by_project",
        AsyncMock(return_value=rows),
    ):
        buckets, total = await aggregate_by_field(db, uuid4(), "design")
    assert total == 3  # total is row count, not bucket count
    assert sum(buckets.values()) == 2


# ── field_coverage ───────────────────────────────────────────────────────


def test_field_coverage_for_reserved_and_custom():
    fields = [
        ExtractionField(key="research_problem", label="Research Problem", type="text"),
        ExtractionField(key="sample_size", label="Sample size", type="number"),
    ]
    rows: list = [
        _row(research_problem="A", custom={"sample_size": 100}),
        _row(research_problem="B", custom={"sample_size": 200}),
        _row(research_problem=None, custom={}),
    ]
    coverage = field_coverage(rows, fields)  # type: ignore[arg-type]
    assert coverage["rows_total"] == 3
    by_key = {f["key"]: f for f in coverage["fields"]}
    assert by_key["research_problem"]["populated"] == 2
    assert by_key["research_problem"]["is_reserved"] is True
    assert by_key["sample_size"]["populated"] == 2
    assert by_key["sample_size"]["is_reserved"] is False
    assert by_key["sample_size"]["type"] == "number"


def test_field_coverage_handles_empty_rows():
    fields = [
        ExtractionField(key="x", label="X", type="text"),
    ]
    coverage = field_coverage([], fields)  # type: ignore[arg-type]
    assert coverage["rows_total"] == 0
    assert coverage["fields"] == []


# ── reserved keys constant ──────────────────────────────────────────────


def test_reserved_field_keys_includes_seven_defaults():
    expected = {
        "research_problem",
        "method",
        "dataset_or_context",
        "key_result",
        "limitation",
        "contribution",
        "relevance",
    }
    assert expected.issubset(set(RESERVED_FIELD_KEYS))
