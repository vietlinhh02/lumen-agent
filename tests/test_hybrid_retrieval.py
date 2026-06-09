from app.services.hybrid_retrieval import _combined_score, _cosine, _vector_score


def test_combined_score_boosts_evidence_heavy_sections() -> None:
    narrative = _combined_score(keyword_score=0.2, vector_score=0.2, content_type="narrative")
    limitation = _combined_score(keyword_score=0.2, vector_score=0.2, content_type="limitation")
    results = _combined_score(keyword_score=0.2, vector_score=0.2, content_type="results")

    assert limitation > results > narrative


def test_vector_score_handles_invalid_or_missing_embedding() -> None:
    query_embedding = [1.0, 0.0]

    assert _vector_score(query_embedding, None) == 0.0
    assert _vector_score(query_embedding, "not-json") == 0.0


def test_cosine_scores_matching_vectors() -> None:
    assert _cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
