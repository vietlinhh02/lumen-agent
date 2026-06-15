from app.services.hybrid_retrieval import _combined_score, _keyword_score, _tokens


def test_combined_score_boosts_evidence_heavy_sections() -> None:
    narrative = _combined_score(keyword_score=0.2, vector_score=0.2, content_type="narrative")
    limitation = _combined_score(keyword_score=0.2, vector_score=0.2, content_type="limitation")
    results = _combined_score(keyword_score=0.2, vector_score=0.2, content_type="results")

    assert limitation > results > narrative


def test_keyword_score_handles_empty_query() -> None:
    from types import SimpleNamespace

    paper = SimpleNamespace(title="test", abstract="test")
    chunk = SimpleNamespace(section_label="method", content_type="method", chunk_text="test")
    assert _keyword_score(set(), paper, chunk) == 0.0


def test_keyword_score_matches_tokens() -> None:
    from types import SimpleNamespace

    paper = SimpleNamespace(title="RAG for QA", abstract="retrieval augmented generation")
    chunk = SimpleNamespace(section_label="method", content_type="method", chunk_text="we use RAG")
    tokens = _tokens("RAG retrieval")
    score = _keyword_score(tokens, paper, chunk)
    assert score > 0.0


def test_tokens_basic() -> None:
    tokens = _tokens("RAG for Medical QA 2024!")
    assert "rag" in tokens
    assert "for" in tokens
    assert "medical" in tokens
    assert "qa" in tokens
    assert "2024" in tokens
