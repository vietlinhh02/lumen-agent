"""Tests for T3 Phase 2 — gap + conflict evidence."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.routers import conflicts as conflicts_router
from app.routers import gaps as gaps_router
from app.services import conflict_detection
from app.services.hybrid_retrieval import RetrievedChunk


def _chunk(pp_id, *, text="Accuracy dropped to 60% on the held-out set.", ct="results",
           section="Results", score=0.7):
    return RetrievedChunk(
        project_paper_id=pp_id,
        paper_id=uuid4(),
        chunk_id=uuid4(),
        title="P",
        chunk_text=text,
        section_label=section,
        section_path=None,
        chunk_index=0,
        content_type=ct,
        page_start=None,
        page_end=None,
        content_hash=None,
        score=score,
        keyword_score=0.3,
        vector_score=0.4,
    )


def _result(value=None, scalars_all=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    if scalars_all is not None:
        r.scalars.return_value.all.return_value = scalars_all
    return r


# ── Gap evidence endpoint ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gap_evidence_endpoint_returns_chunks():
    ppid = uuid4()
    gap = SimpleNamespace(
        id=uuid4(),
        title="No long-horizon evaluation",
        description="Papers only test short horizons.",
        suggested_direction="Evaluate over 12-month horizons.",
        evidence_entries=[
            SimpleNamespace(project_paper_id=ppid, evidence_type="limitation")
        ],
    )
    project = SimpleNamespace(id=uuid4())
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(project),                       # owner check
            _result(gap),                           # load gap
            _result(SimpleNamespace(paper_id=uuid4())),  # _get_gap_paper_title pp
            _result(SimpleNamespace(title="Paper X")),   # _get_gap_paper_title paper
        ]
    )

    chunk = _chunk(ppid, ct="limitation", section="Limitations")
    with patch.object(
        gaps_router, "retrieve_paper_evidence", AsyncMock(return_value=[chunk])
    ) as ret:
        resp = await gaps_router.get_gap_evidence(
            project_id=str(project.id),
            gap_id=str(gap.id),
            project_paper_id=str(ppid),
            db=db,
            user=MagicMock(),
        )

    assert resp.paper_title == "Paper X"
    assert len(resp.items) == 1
    assert resp.items[0].content_type == "limitation"
    assert resp.items[0].section_label == "Limitations"
    # evidence_type 'limitation' maps to a limitation content-type filter.
    assert ret.await_args.kwargs["content_types"] == ["limitation"]


# ── Conflict chunk persistence ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_persist_conflicts_writes_evidence_chunks():
    pa, pb = uuid4(), uuid4()
    conflicts = [
        {
            "title": "Opposing accuracy claims",
            "description": "A says up, B says down.",
            "paper_a_id": pa,
            "paper_b_id": pb,
            "shared_context": "same dataset",
            "claim_a": "accuracy improved",
            "claim_b": "accuracy dropped",
            "possible_explanation": None,
            "confidence": "high",
            "_chunks_a": [_chunk(pa, text="improved to 90%")],
            "_chunks_b": [_chunk(pb, text="dropped to 60%"), _chunk(pb, text="worse on OOD")],
        }
    ]
    db = MagicMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    await conflict_detection._persist_conflicts(db, uuid4(), conflicts)

    finding = db.add.call_args.args[0]
    chunks = finding.evidence_chunks
    assert len(chunks) == 3
    a = [c for c in chunks if c.polarity == "a"]
    b = [c for c in chunks if c.polarity == "b"]
    assert len(a) == 1 and len(b) == 2
    assert a[0].snippet == "improved to 90%"
    assert a[0].project_paper_id == pa
    # private keys are stripped so later serialization stays JSON-safe.
    assert "_chunks_a" not in conflicts[0]
    assert "_chunks_b" not in conflicts[0]


# ── Conflict evidence endpoint ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_conflict_evidence_endpoint_groups_by_polarity():
    pa, pb = uuid4(), uuid4()
    finding = SimpleNamespace(id=uuid4(), paper_a_id=pa, paper_b_id=pb)
    project = SimpleNamespace(id=uuid4())
    rows = [
        SimpleNamespace(polarity="a", chunk_id=uuid4(), project_paper_id=pa, snippet="up 90%",
                        content_type="results", section_label="Results", score=0.8),
        SimpleNamespace(polarity="b", chunk_id=uuid4(), project_paper_id=pb, snippet="down 60%",
                        content_type="results", section_label="Results", score=0.7),
        SimpleNamespace(polarity="b", chunk_id=uuid4(), project_paper_id=pb, snippet="worse OOD",
                        content_type="narrative", section_label="Discussion", score=0.6),
    ]
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(finding),                              # load finding
            _result(project),                              # owner check
            _result(scalars_all=rows),                     # chunks
            _result(SimpleNamespace(paper_id=uuid4())),    # title A pp
            _result(SimpleNamespace(title="Paper A")),     # title A paper
            _result(SimpleNamespace(paper_id=uuid4())),    # title B pp
            _result(SimpleNamespace(title="Paper B")),     # title B paper
        ]
    )

    resp = await conflicts_router.get_conflict_evidence(
        project_id=str(project.id),
        conflict_id=str(finding.id),
        db=db,
        user=MagicMock(),
    )

    assert resp.paper_a_title == "Paper A"
    assert resp.paper_b_title == "Paper B"
    assert len(resp.claim_a) == 1
    assert len(resp.claim_b) == 2
    assert resp.claim_a[0].chunk_text == "up 90%"
