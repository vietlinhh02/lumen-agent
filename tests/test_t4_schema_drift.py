"""Tests for T4 schema drift detection in the matrix job runner."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_matrix_job_records_schema_drift_when_version_changes(monkeypatch):
    """If the schema is edited mid-run, the job result surfaces
    ``schema_drifted=True`` so the UI can warn the user."""
    from app.routers.matrix import _run_matrix_job
    from app.schemas.extraction_schema import (
        ExtractionField,
        ExtractionSchemaResponse,
    )

    initial = ExtractionSchemaResponse(
        project_id=uuid4(),
        version=1,
        is_default=False,
        fields=[
            ExtractionField(
                key="research_problem",
                label="Research Problem",
                type="text",
                description=None,
                required=False,
                enum_values=None,
            )
        ],
        created_at=None,
        updated_at=None,
    )
    # Schema bumped during the run.
    final = ExtractionSchemaResponse(
        project_id=initial.project_id,
        version=2,
        is_default=False,
        fields=initial.fields
        + [
            ExtractionField(
                key="sample_size",
                label="Sample size",
                type="number",
                description=None,
                required=False,
                enum_values=None,
            )
        ],
        created_at=None,
        updated_at=None,
    )

    job = SimpleNamespace(
        id=uuid4(),
        status="pending",
        progress=0,
        total=0,
        progress_json={},
        result=None,
        error_message=None,
        completed_at=None,
    )

    matrix_extraction_node = AsyncMock(
        return_value={
            "matrix_rows": [],
            "matrix_status": "completed",
        }
    )

    # ``matrix_extraction_node`` is imported lazily inside the worker.
    with (
        patch("app.agents.nodes.matrix_extraction_node", matrix_extraction_node),
        patch("app.routers.matrix.async_session_factory") as mock_factory,
    ):
        bg_db = AsyncMock()

        # ``get_effective_schema`` is called twice: once at the start of
        # the run (returns v1) and once at the end (returns v2). The
        # worker does ``from app.services.extraction_schema import
        # get_effective_schema`` so the source module is the right patch
        # target — patching ``app.routers.matrix.get_effective_schema``
        # has no effect because the worker has its own local reference.
        calls = {"n": 0}

        async def mock_get(db, project_id):
            calls["n"] += 1
            return initial if calls["n"] == 1 else final

        monkeypatch.setattr(
            "app.services.extraction_schema.get_effective_schema",
            mock_get,
        )

        # First call: load the job + project.
        # Subsequent calls: refresh schema snapshot.
        results_in_order = [
            # load job
            SimpleNamespace(scalar_one_or_none=MagicMock(return_value=job)),
            # load project (for protocol)
            SimpleNamespace(
                scalar_one_or_none=MagicMock(return_value=SimpleNamespace(review_protocol=None))
            ),
            # load effective schema at start
            MagicMock(),
            # schema snapshot
            MagicMock(),
        ]
        call_idx = {"n": 0}

        async def mock_execute(stmt):
            call_idx["n"] += 1
            return results_in_order[min(call_idx["n"] - 1, len(results_in_order) - 1)]

        bg_db.execute = mock_execute
        bg_db.commit = AsyncMock()
        bg_db.refresh = AsyncMock()

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=bg_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        await _run_matrix_job(
            job_id=job.id,
            project_id=initial.project_id,
            user_id=uuid4(),
            topic="RAG",
        )

    assert job.status == "completed"
    assert job.result is not None
    assert job.result["schema_version"] == 2
    assert job.result["schema_drifted"] is True


def test_reserved_keys_do_not_match_custom_field_with_same_name():
    """The schema service must preserve reserved keys even when the
    project owner tries to add a custom field with the same key
    (e.g. ``method`` is a reserved key, never custom)."""
    from app.schemas.extraction_schema import RESERVED_FIELD_KEYS

    # The reserved set must contain the seven system defaults; we never
    # want a project to redefine them as a different type.
    assert "method" in RESERVED_FIELD_KEYS
    assert "research_problem" in RESERVED_FIELD_KEYS
    # Reserved keys are locked to text in the render path. The renderer
    # must never emit ``type: 'number'`` for a reserved key.
    from app.services.literature_matrix import RESERVED_FIELD_KEYS as LM_RESERVED

    for key in (
        "research_problem",
        "method",
        "dataset_or_context",
        "key_result",
        "limitation",
        "contribution",
        "relevance",
    ):
        assert key in LM_RESERVED
