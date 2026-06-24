"""Tests for T7: Claim and Consensus Synthesis Service."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models import (
    Claim,
    ClaimEvidence,
    ConflictingFinding,
    LiteratureMatrixRow,
)
from app.services.claim_synthesis import (
    lift_claims_from_conflicts,
    lift_claims_from_matrix,
    run_claim_synthesis,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures / Mocks
# ---------------------------------------------------------------------------

def _mock_db_sequential(results):
    """Create a mock DB that returns different results on successive execute() calls."""
    db = MagicMock()
    call_index = {"i": 0}

    async def mock_execute(stmt):
        idx = call_index["i"]
        call_index["i"] += 1
        if idx < len(results):
            return results[idx]
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        return r

    db.execute = mock_execute
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    
    # Keep track of added models
    db.added_items = []
    def mock_add(item):
        db.added_items.append(item)
    db.add = mock_add
    
    def mock_add_all(items):
        db.added_items.extend(items)
    db.add_all = mock_add_all
    
    return db


def _result_with_rows(rows):
    """Create a mock DB result that returns `rows` from scalars().all()."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return r


@pytest.fixture
def project_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def paper_a_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def paper_b_id() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Service Tests
# ---------------------------------------------------------------------------


async def test_lift_from_conflicts(project_id, paper_a_id, paper_b_id):
    """Test lifting claims from ConflictingFinding (creates 2 claims per conflict)."""
    cf = ConflictingFinding(
        project_id=project_id,
        title="Contradictory Results",
        description="Paper A vs Paper B",
        paper_a_id=paper_a_id,
        paper_b_id=paper_b_id,
        claim_a="Method X improves performance",
        claim_b="Method X reduces performance",
        confidence="high",
    )
    
    db = _mock_db_sequential([_result_with_rows([cf])])

    claims = await lift_claims_from_conflicts(db, project_id)
    assert len(claims) == 2

    # Check the claims were pushed to db.add
    added_claims = [i for i in db.added_items if isinstance(i, Claim)]
    added_evidence = [i for i in db.added_items if isinstance(i, ClaimEvidence)]
    
    assert len(added_claims) == 2
    assert len(added_evidence) == 4  # 2 per claim (1 support, 1 contradict)

    c1 = next(c for c in added_claims if c.canonical_text == "Method X improves performance")
    assert c1.claim_type == "contradict"
    assert c1.source_type == "conflict"
    assert c1.confidence == "high"


async def test_lift_from_matrix_key_result(project_id, paper_a_id):
    """Test lifting claims from LiteratureMatrixRow.key_result (creates support claims)."""
    row = LiteratureMatrixRow(
        project_id=project_id,
        project_paper_id=paper_a_id,
        key_result="New algorithm is 20% faster",
        extraction_confidence="high",
        created_by="system",
    )
    
    db = _mock_db_sequential([_result_with_rows([row])])

    claims = await lift_claims_from_matrix(db, project_id)
    assert len(claims) == 1

    added_claims = [i for i in db.added_items if isinstance(i, Claim)]
    assert len(added_claims) == 1
    
    c = added_claims[0]
    assert c.canonical_text == "New algorithm is 20% faster"
    assert c.claim_type == "support"
    assert c.source_type == "matrix"
    assert c.confidence == "high"


async def test_lift_from_matrix_limitation(project_id, paper_b_id):
    """Test lifting claims from LiteratureMatrixRow.limitation (creates weak claims)."""
    row = LiteratureMatrixRow(
        project_id=project_id,
        project_paper_id=paper_b_id,
        limitation="Only tested on small datasets",
        extraction_confidence="low",
        created_by="system",
    )
    db = _mock_db_sequential([_result_with_rows([row])])

    claims = await lift_claims_from_matrix(db, project_id)
    assert len(claims) == 1

    added_claims = [i for i in db.added_items if isinstance(i, Claim)]
    c = added_claims[0]
    assert c.canonical_text == "Only tested on small datasets"
    assert c.claim_type == "weak"


async def test_full_synthesis_orchestrator(project_id, paper_a_id, paper_b_id):
    """Test the full orchestrator: clears existing claims and runs both extractions."""
    row = LiteratureMatrixRow(
        project_id=project_id,
        project_paper_id=paper_a_id,
        key_result="Matrix Result A",
        created_by="system",
    )
    cf = ConflictingFinding(
        project_id=project_id,
        paper_a_id=paper_a_id,
        paper_b_id=paper_b_id,
        claim_a="Conflict A",
        claim_b="Conflict B",
    )
    
    # orchestrator does:
    # 1. delete() -> mock_db.execute returns magicmock
    # 2. lift_claims_from_conflicts -> mock_db.execute returns conflicts
    # 3. lift_claims_from_matrix -> mock_db.execute returns matrix rows
    
    # mock_db_sequential will yield in order:
    del_result = MagicMock() 
    cf_result = _result_with_rows([cf])
    matrix_result = _result_with_rows([row])
    
    db = _mock_db_sequential([del_result, cf_result, matrix_result])

    total = await run_claim_synthesis(db, project_id)
    
    assert total == 3 # 2 from conflict, 1 from matrix


async def test_synthesis_empty_project(project_id):
    """Test synthesis gracefully handles empty projects."""
    db = _mock_db_sequential([MagicMock(), _result_with_rows([]), _result_with_rows([])])
    total = await run_claim_synthesis(db, project_id)
    assert total == 0
