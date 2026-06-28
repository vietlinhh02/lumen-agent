"""Tests for T4: Custom Extraction Schema Builder.

Covers the schema service (defaults, validation, type coercion, JSON-schema
generation), the persistence path (upsert_rows → custom_fields), and the
end-to-end matrix_extraction_node flow against a project with a custom
schema.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.nodes import matrix_extraction_node
from app.agents.state import ResearchState
from app.schemas.extraction_schema import (
    RESERVED_FIELD_KEYS,
    ExtractionField,
)
from app.services.extraction_schema import (
    build_extraction_json_schema,
    coerce_custom_value,
    default_fields,
    default_field_dicts,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_default_fields_contain_all_seven_reserved_keys():
    fields = default_fields()
    keys = {f.key for f in fields}
    assert keys == set(RESERVED_FIELD_KEYS)
    assert len(fields) == 7
    # Every reserved field is type='text', not required, no enum_values.
    for f in fields:
        assert f.type == "text"
        assert f.required is False
        assert f.enum_values is None


def test_default_field_dicts_serializable():
    dicts = default_field_dicts()
    assert isinstance(dicts, list)
    assert len(dicts) == 7
    assert all("key" in d and "label" in d and "type" in d for d in dicts)


# ---------------------------------------------------------------------------
# ExtractionField validation
# ---------------------------------------------------------------------------


def test_extraction_field_rejects_invalid_key():
    with pytest.raises(ValueError):
        ExtractionField(key="Invalid Key", label="x", type="text")
    with pytest.raises(ValueError):
        ExtractionField(key="1starts_with_digit", label="x", type="text")
    with pytest.raises(ValueError):
        ExtractionField(key="with-dash", label="x", type="text")


def test_extraction_field_enum_requires_values():
    with pytest.raises(ValueError):
        ExtractionField(key="domain", label="Domain", type="enum")
    f = ExtractionField(
        key="domain", label="Domain", type="enum",
        enum_values=["clinical", "biomedical"],
    )
    assert f.enum_values == ["clinical", "biomedical"]


def test_extraction_field_enum_dedupes_values():
    f = ExtractionField(
        key="domain", label="Domain", type="enum",
        enum_values=["clinical", "biomedical", "clinical"],
    )
    assert f.enum_values == ["clinical", "biomedical"]


def test_extraction_field_multi_select_dedupes():
    f = ExtractionField(
        key="tags", label="Tags", type="multi_select",
        enum_values=["a", "b", "a", "c", "b"],
    )
    assert f.enum_values == ["a", "b", "c"]


def test_extraction_field_non_enum_strips_enum_values():
    f = ExtractionField(
        key="notes", label="Notes", type="text",
        enum_values=["ignored"],
    )
    assert f.enum_values is None


# ---------------------------------------------------------------------------
# coerce_custom_value
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field_type", "raw", "expected"),
    [
        ("number", "42", 42.0),
        ("number", "3.14", 3.14),
        ("number", "abc", None),
        ("number", "", None),
        ("boolean", "true", True),
        ("boolean", "YES", True),
        ("boolean", "0", False),
        ("boolean", "no", False),
        ("boolean", "maybe", None),
    ],
)
def test_coerce_scalar_types(field_type, raw, expected):
    f = ExtractionField(key="x", label="X", type=field_type)  # type: ignore[arg-type]
    assert coerce_custom_value(f, raw) == expected


def test_coerce_enum_snap_case_insensitive():
    f = ExtractionField(
        key="phase", label="Phase", type="enum",
        enum_values=["Phase 1", "Phase 2", "Phase 3"],
    )
    assert coerce_custom_value(f, "phase 2") == "Phase 2"
    assert coerce_custom_value(f, "Phase 4") is None


def test_coerce_multi_select_parses_comma_separated():
    f = ExtractionField(
        key="tags", label="Tags", type="multi_select",
        enum_values=["red", "green", "blue"],
    )
    assert coerce_custom_value(f, "red, blue") == ["red", "blue"]
    assert coerce_custom_value(f, "red; green; yellow") == ["red", "green"]


def test_coerce_text_truncates_long_values():
    f = ExtractionField(key="note", label="Note", type="text")
    long_value = "x" * 5000
    out = coerce_custom_value(f, long_value)
    assert isinstance(out, str)
    assert len(out) == 4000


# ---------------------------------------------------------------------------
# JSON schema generation
# ---------------------------------------------------------------------------


def test_build_json_schema_includes_all_reserved_keys():
    fields = default_fields()
    schema = build_extraction_json_schema(fields)
    props = schema["properties"]
    for k in RESERVED_FIELD_KEYS:
        assert k in props
        assert props[k]["type"] == "string"
    assert "confidence" in props
    # Confidence is always exposed so the LLM can self-rate, but it
    # is NOT in ``required`` (the legacy schema didn't require it either).
    assert "confidence" not in schema["required"]


def test_build_json_schema_handles_custom_field_types():
    fields = default_fields() + [
        ExtractionField(key="sample_size", label="Sample size",
                        type="number", required=True),
        ExtractionField(key="design", label="Design", type="enum",
                        enum_values=["RCT", "cohort"]),
        ExtractionField(key="tags", label="Tags", type="multi_select",
                        enum_values=["a", "b"]),
        ExtractionField(key="open_access", label="Open access",
                        type="boolean"),
    ]
    schema = build_extraction_json_schema(fields)
    props = schema["properties"]
    assert props["sample_size"]["type"] == "number"
    assert props["design"]["type"] == "string"
    assert props["design"]["enum"] == ["RCT", "cohort"]
    assert props["tags"]["type"] == "array"
    assert props["open_access"]["type"] == "boolean"
    # sample_size is required → in schema's required list.
    assert "sample_size" in schema["required"]
    # Reserved keys always required.
    for k in RESERVED_FIELD_KEYS:
        assert k in schema["required"]


# ---------------------------------------------------------------------------
# end-to-end: matrix_extraction_node with a custom schema
# ---------------------------------------------------------------------------


def _make_chunk():
    from app.services.hybrid_retrieval import RetrievedChunk

    return RetrievedChunk(
        project_paper_id=uuid4(),
        paper_id=uuid4(),
        chunk_id=uuid4(),
        title="Test Paper",
        chunk_text="We used BERT for encoding on 500 patient records.",
        section_label="method",
        section_path=None,
        chunk_index=0,
        content_type="method",
        page_start=1,
        page_end=2,
        content_hash=None,
        score=0.8,
        keyword_score=0.4,
        vector_score=0.4,
    )


def _make_pp(pp_id=None, title="Test Paper"):
    pp = SimpleNamespace()
    pp.id = pp_id or uuid4()
    pp.status = "saved"
    pp.paper = SimpleNamespace()
    pp.paper.title = title
    pp.paper.abstract = "Test abstract"
    pp.paper.authors = ["Author A"]
    pp.paper.year = 2024
    pp.paper.venue = "Test Venue"
    pp.paper.updated_at = None
    pp.matrix_row = None
    return pp


def _mock_db_with_papers(papers):
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = papers
    db.execute = AsyncMock(return_value=mock_result)
    return db


@pytest.mark.asyncio
async def test_matrix_extraction_with_custom_schema_persists_custom_fields():
    """End-to-end: with a project schema that adds 3 custom fields, the LLM
    response should populate custom_fields with the typed values, and the
    row's ``custom_fields`` dict should land in the persisted dict."""
    pp_id = uuid4()
    pp = _make_pp(pp_id=pp_id)
    state = ResearchState(
        project_id=uuid4(),
        user_id=uuid4(),
        user_topic="RAG for medical QA",
    )

    custom_fields = [
        ExtractionField(key="sample_size", label="Sample size",
                        type="number"),
        ExtractionField(key="study_design", label="Study design",
                        type="enum", enum_values=["RCT", "cohort", "case_study"]),
        ExtractionField(key="intervention", label="Intervention",
                        type="text"),
    ]
    schema_resp = SimpleNamespace(
        project_id=state.project_id,
        version=2,
        fields=default_fields() + custom_fields,
        is_default=False,
    )

    captured: dict = {}

    async def _capture_upsert(db, project_id, rows):
        captured["rows"] = rows
        return len(rows)

    with (
        patch(
            "app.agents.nodes.retrieve_paper_evidence",
            new_callable=AsyncMock,
            return_value=[_make_chunk()],
        ),
        patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            side_effect=_capture_upsert,
        ),
        patch(
            "app.agents.nodes.get_effective_schema",
            new_callable=AsyncMock,
            return_value=schema_resp,
        ),
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured_with_usage.return_value = ({
            # Universal fields
            "research_problem": "Medical QA accuracy",
            "method": "Dense retrieval with BERT",
            "dataset_or_context": "PubMedQA",
            "key_result": "Improved accuracy by 5%",
            "limitation": "English only",
            "contribution": "Novel RAG pipeline",
            "relevance": "Directly relevant",
            "confidence": "high",
            # Custom fields
            "sample_size": 500,
            "study_design": "cohort",
            "intervention": "BERT-based retrieval",
        }, MagicMock(model="test-model"))

        with patch(
            "app.agents.nodes.get_provider",
            return_value=mock_provider,
        ), patch(
            "app.agents.nodes.get_matrix_verifier_provider",
            return_value=None,
        ):
            result = await matrix_extraction_node(state, _mock_db_with_papers([pp]))

    assert result["matrix_status"] == "completed"
    assert "rows" in captured
    assert len(captured["rows"]) == 1
    row = captured["rows"][0]
    assert row["project_paper_id"] == pp_id
    assert row["custom_fields"] == {
        "sample_size": 500.0,
        "study_design": "cohort",
        "intervention": "BERT-based retrieval",
    }
    # The seven reserved fields are still top-level.
    assert row["research_problem"] == "Medical QA accuracy"
    assert row["method"] == "Dense retrieval with BERT"


@pytest.mark.asyncio
async def test_matrix_extraction_falls_back_to_defaults_when_schema_load_fails():
    """If get_effective_schema raises (mock DB, transient error), the node
    should still succeed using the seven system defaults."""
    pp_id = uuid4()
    pp = _make_pp(pp_id=pp_id)
    state = ResearchState(
        project_id=uuid4(),
        user_id=uuid4(),
        user_topic="RAG for medical QA",
    )

    with (
        patch(
            "app.agents.nodes.retrieve_paper_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=1,
        ),
        patch(
            "app.agents.nodes.get_effective_schema",
            new_callable=AsyncMock,
            side_effect=RuntimeError("simulated DB failure"),
        ),
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured_with_usage.return_value = ({
            "research_problem": "X",
            "method": "Y",
            "dataset_or_context": "Z",
            "key_result": "A",
            "limitation": "B",
            "contribution": "C",
            "relevance": "D",
            "confidence": "medium",
        }, MagicMock(model="test-model"))

        with patch(
            "app.agents.nodes.get_provider",
            return_value=mock_provider,
        ), patch(
            "app.agents.nodes.get_matrix_verifier_provider",
            return_value=None,
        ):
            result = await matrix_extraction_node(state, _mock_db_with_papers([pp]))

    assert result["matrix_status"] == "completed"
    assert result["matrix_rows"][0]["custom_fields"] == {}


@pytest.mark.asyncio
async def test_matrix_extraction_skips_unknown_custom_field_values():
    """Custom fields whose coerced value is None should not appear in the
    persisted dict."""
    pp_id = uuid4()
    pp = _make_pp(pp_id=pp_id)
    state = ResearchState(
        project_id=uuid4(),
        user_id=uuid4(),
        user_topic="test",
    )

    custom_fields = [
        ExtractionField(key="sample_size", label="Sample size",
                        type="number"),
        ExtractionField(key="design", label="Design", type="enum",
                        enum_values=["RCT", "cohort"]),
    ]
    schema_resp = SimpleNamespace(
        project_id=state.project_id, version=1,
        fields=default_fields() + custom_fields, is_default=False,
    )

    captured: dict = {}

    async def _capture_upsert(db, project_id, rows):
        captured["rows"] = rows
        return len(rows)

    with (
        patch(
            "app.agents.nodes.retrieve_paper_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            side_effect=_capture_upsert,
        ),
        patch(
            "app.agents.nodes.get_effective_schema",
            new_callable=AsyncMock,
            return_value=schema_resp,
        ),
    ):
        mock_provider = AsyncMock()
        # sample_size is non-numeric → coerced to None → dropped.
        # design is an unknown enum → coerced to None → dropped.
        mock_provider.complete_structured_with_usage.return_value = ({
            "research_problem": "X",
            "method": "Y",
            "dataset_or_context": "Z",
            "key_result": "A",
            "limitation": "B",
            "contribution": "C",
            "relevance": "D",
            "confidence": "medium",
            "sample_size": "unknown",
            "design": "observational",
        }, MagicMock(model="test-model"))

        with patch(
            "app.agents.nodes.get_provider",
            return_value=mock_provider,
        ), patch(
            "app.agents.nodes.get_matrix_verifier_provider",
            return_value=None,
        ):
            await matrix_extraction_node(state, _mock_db_with_papers([pp]))

    assert captured["rows"][0]["custom_fields"] == {}


# ---------------------------------------------------------------------------
# upsert_rows persistence path
# ---------------------------------------------------------------------------


class _FakeRow:
    """Capture the values that upsert_rows passes to the INSERT."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.mark.asyncio
async def test_upsert_rows_persists_custom_fields(monkeypatch):
    """upsert_rows must include custom_fields in both the INSERT and the
    ON CONFLICT UPDATE so the dynamic fields survive re-extraction."""
    from app.services import literature_matrix as lm

    captured_inserts: list[dict] = []
    captured_sets: list[dict] = []

    class _FakeInsert:
        def __init__(self, _model):
            self._values: dict = {}
            self._set: dict = {}

        def values(self, **kwargs):
            self._values.update(kwargs)
            return self

        def on_conflict_do_update(self, *, index_elements, set_):
            self._set = dict(set_)
            return self

        def __await__(self):
            async def _coro():
                captured_inserts.append(self._values)
                captured_sets.append(self._set)
                result = MagicMock()
                result.rowcount = 1
                return result
            return _coro().__await__()

    monkeypatch.setattr(lm, "pg_insert", lambda model: _FakeInsert(model))

    db = AsyncMock()

    async def fake_execute(stmt):
        return await stmt

    db.execute = fake_execute
    db.commit = AsyncMock()

    pp_id = uuid4()
    await lm.upsert_rows(db, uuid4(), [
        {
            "project_paper_id": pp_id,
            "research_problem": "X",
            "method": "Y",
            "dataset_or_context": "Z",
            "key_result": "A",
            "limitation": "B",
            "contribution": "C",
            "relevance": "D",
            "custom_fields": {"sample_size": 500.0, "design": "cohort"},
            "content_hash": "abc",
            "extraction_confidence": "high",
        }
    ])

    assert captured_inserts, "upsert_rows should have called execute()"
    insert_values = captured_inserts[0]
    set_values = captured_sets[0]
    assert insert_values["custom_fields"] == {
        "sample_size": 500.0, "design": "cohort",
    }
    assert set_values["custom_fields"] == {
        "sample_size": 500.0, "design": "cohort",
    }
    # Reserved fields still round-trip in both branches.
    for k in (
        "research_problem", "method", "dataset_or_context",
        "key_result", "limitation", "contribution", "relevance",
    ):
        assert insert_values[k] is not None
        assert set_values[k] is not None
