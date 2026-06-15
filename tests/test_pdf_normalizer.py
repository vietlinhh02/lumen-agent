import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

from app.services.pdf_ingestion import Section, _detect_sections
from app.services.pdf_normalizer import (
    _DEFAULT_MAX_TOKENS,
    _LLM_CONTEXT_MAX_CHARS,
    _approx_tokens,
    _chunk_raw_evidence,
    _detect_sections_with_llm,
    _embedding_text,
    _get_normalization_lock,
    _llm_context,
    _policy_for_section,
    _split_section_text,
    _tokens_to_chars,
    normalize_project_papers,
)


class FakeStructureProvider:
    async def complete_structured(self, **kwargs):
        content = kwargs["messages"][0]["content"]
        headings = []
        for line in content.splitlines():
            if ": " not in line:
                continue
            index_text, text = line.split(": ", 1)
            if text in {"Abstract", "1 Introduction", "2 Method", "3 Results", "References"}:
                headings.append(
                    {
                        "line_index": int(index_text),
                        "title": text,
                    }
                )
        return {"headings": headings}


class NoisyStructureProvider:
    async def complete_structured(self, **kwargs):
        return {
            "headings": [
                {"line_index": 0, "title": "B"},
                {"line_index": 2, "title": "C"},
                {"line_index": 4, "title": "Paper Strcuture"},
            ]
        }


def test_duplicate_project_normalization_skips_without_db_work() -> None:
    async def run_check() -> None:
        project_id = uuid4()
        lock = _get_normalization_lock(project_id)
        await lock.acquire()
        try:
            result = await normalize_project_papers(db=AsyncMock(), project_id=project_id)
        finally:
            lock.release()

        assert result == {"processed": 0, "skipped": 0, "failed": 0}

    asyncio.run(run_check())


def test_llm_context_keeps_tail_for_long_papers() -> None:
    raw_text = "A" * 60000 + "LIMITATION_SENTINEL"

    context = _llm_context(raw_text)

    assert len(context) > _LLM_CONTEXT_MAX_CHARS
    assert len(context) < len(raw_text)
    assert "LIMITATION_SENTINEL" in context


def test_raw_evidence_chunking_uses_text_after_llm_context_limit() -> None:
    raw_text = (
        "Introduction\n"
        + ("A " * 20000)
        + "\n\nLimitations\n"
        + "TAIL_SENTINEL shows the paper ending is preserved and is a long enough "
        + "section to pass filtering."
    )
    sections = [
        Section(name="Introduction", start_line=0, end_line=2),
        Section(name="Limitations", start_line=3, end_line=4),
    ]

    chunks = _chunk_raw_evidence(raw_text, sections)

    assert any("TAIL_SENTINEL" in chunk["text"] for chunk in chunks)


def test_split_section_text_keeps_chunks_within_budget_for_long_paragraph() -> None:
    paragraph = "x " * (_DEFAULT_MAX_TOKENS * 2 + 100)

    chunks = _split_section_text(paragraph)

    assert len(chunks) > 1
    assert all(_approx_tokens(chunk) <= _DEFAULT_MAX_TOKENS + 10 for chunk in chunks)


def test_adaptive_chunking_marks_tables_and_limitations() -> None:
    raw_text = (
        "Results\n"
        "Table 1: Accuracy F1 Recall on benchmark A 0.91 0.88 0.85\n"
        "Table 2: Accuracy on benchmark B 0.87 0.83 0.80\n"
        "The method improves recall on the Vietnamese benchmark significantly.\n\n"
        "Limitations\n"
        "The study does not evaluate low-resource clinical datasets, which limits generalizability."
    )
    sections = [
        Section(name="Results", start_line=0, end_line=4),
        Section(name="Limitations", start_line=5, end_line=6),
    ]

    chunks = _chunk_raw_evidence(raw_text, sections)

    assert any(chunk["content_type"] == "table" for chunk in chunks)
    assert any(chunk["content_type"] == "limitation" for chunk in chunks)
    assert all(chunk["pipeline_version"] == "paper-tree-v2" for chunk in chunks)
    assert all(chunk["content_hash"] for chunk in chunks)
    assert not any(chunk["text"] == "Table 1" for chunk in chunks)


def test_references_are_stored_but_not_embedded() -> None:
    raw_text = "References\n[1] Smith 2024. Retrieval augmented generation."
    sections = [Section(name="References", start_line=0, end_line=1)]

    chunks = _chunk_raw_evidence(raw_text, sections)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["content_type"] == "reference"
    assert chunk["embed"] is False
    assert chunk["pipeline_version"] == "paper-tree-v2"


def test_detect_sections_handles_connector_headings_and_ignores_ceur_noise() -> None:
    raw_text = "\n".join(
        [
            "Abstract",
            "abstract body",
            "1. Introduction",
            "intro body",
            "C E U R",
            "W Pr o o r c k e s e h d o in p gs",
            "2. Methodology",
            "method body",
            "3. Results and Evaluation",
            "result body",
            "4. Conclusion and Future Work",
            "conclusion body",
            "References",
            "[1] reference",
        ]
    )

    sections = _detect_sections(raw_text)
    section_names = [section.name for section in sections]

    assert "C e u r" not in section_names
    assert section_names == [
        "Abstract",
        "Introduction",
        "Methodology",
        "Results and evaluation",
        "Conclusion and future work",
        "References",
    ]


def test_results_heading_gets_results_policy_after_detection() -> None:
    raw_text = "\n".join(
        [
            "2. Methodology",
            "method body " * 50,
            "3. Results and Evaluation",
            "Increasing LoRA parameters improves BLEU score significantly on the benchmark.",
            "4. Conclusion and Future Work",
            "future work body " * 50,
        ]
    )

    chunks = _chunk_raw_evidence(raw_text, _detect_sections(raw_text))

    assert any(chunk["content_type"] == "results" for chunk in chunks)
    assert any(chunk["content_type"] == "limitation" for chunk in chunks)


def test_detect_sections_handles_springer_inline_abstract_and_numbered_headings() -> None:
    raw_text = "\n".join(
        [
            "Title",
            "Abstract. We present an effective approach for adapting SAM2.",
            "1 Introduction",
            "intro body",
            "2 Related Work",
            "related body",
            "3 Method",
            "method body",
            "4 Results",
            "result body",
            "5 Conclusion",
            "conclusion body",
            "References",
            "[1] reference",
        ]
    )

    sections = _detect_sections(raw_text)
    section_names = [section.name for section in sections]

    assert section_names == [
        "Abstract",
        "Introduction",
        "Related work",
        "Method",
        "Results",
        "Conclusion",
        "References",
    ]


def test_llm_section_parser_uses_validated_line_indices() -> None:
    raw_text = "\n".join(
        [
            "Paper Title",
            "Abstract",
            "abstract body",
            "1 Introduction",
            "intro body",
            "2 Method",
            "method body",
            "3 Results",
            "result body",
            "References",
            "[1] reference",
        ]
    )

    sections = asyncio.run(
        _detect_sections_with_llm(FakeStructureProvider(), "Paper Title", raw_text)
    )

    assert sections == [
        Section(name="Abstract", start_line=1, end_line=2),
        Section(name="Introduction", start_line=3, end_line=4),
        Section(name="Method", start_line=5, end_line=6),
        Section(name="Results", start_line=7, end_line=8),
        Section(name="References", start_line=9, end_line=10),
    ]


def test_llm_section_parser_falls_back_when_headings_are_noisy() -> None:
    raw_text = "\n".join(
        [
            "Abstract",
            "abstract body",
            "1 Introduction",
            "intro body",
            "2 Method",
            "method body",
            "References",
            "[1] reference",
        ]
    )

    sections = asyncio.run(
        _detect_sections_with_llm(NoisyStructureProvider(), "Paper Title", raw_text)
    )

    assert sections == _detect_sections(raw_text)


# ── New tests for token-aware chunking and parent heading context ──────────


def test_token_conversion_roundtrip() -> None:
    assert _tokens_to_chars(100) == 400
    assert _approx_tokens("a" * 400) == 100


def test_chunk_policy_uses_token_limits() -> None:
    policy = _policy_for_section("Method")
    assert policy.max_tokens == 400
    assert policy.overlap_tokens == 40
    assert policy.max_chars == 1600
    assert policy.overlap_chars == 160


def test_embedding_text_includes_section_path() -> None:
    chunk = {
        "text": "The method improves accuracy.",
        "section_label": "Method",
        "section_path": "Method > Training",
        "content_type": "method",
    }
    result = _embedding_text("Test Paper", chunk)
    assert "Method > Training" in result
    assert "Test Paper" in result
    assert "The method improves accuracy." in result


def test_chunk_carries_section_path() -> None:
    raw_text = (
        "Method\n"
        "Our approach uses a transformer architecture.\n\n"
        "Subsection Details\n"
        "We train for 100 epochs with learning rate 1e-4."
    )
    sections = [
        Section(name="Method", start_line=0, end_line=2),
        Section(name="Subsection Details", start_line=3, end_line=4),
    ]

    chunks = _chunk_raw_evidence(raw_text, sections)

    assert len(chunks) >= 1
    for chunk in chunks:
        assert "section_path" in chunk
        assert chunk["section_path"]


def test_abstract_section_gets_smaller_budget() -> None:
    policy = _policy_for_section("Abstract")
    assert policy.max_tokens == 300
    assert policy.overlap_tokens == 0
    assert policy.content_type == "abstract"
