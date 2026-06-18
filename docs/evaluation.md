# Evaluation Evidences

This document contains manual test cases and their actual outputs to verify the core functionalities of Lumen.

## Test Case 1: AI Query Suggestion
**Description**: Verify that the system provides relevant query suggestions based on a simple input.
**Input Query**: `climate change effect on agriculture`
**Expected Outcome**: The LLM should generate more specific and academic search queries.
**Actual Output**:
```json
{
  "suggestions": [
    "impact of climate change on crop yield",
    "agricultural adaptation strategies to global warming",
    "climate change mitigation in farming practices"
  ]
}
```
**Status**: ✅ Pass

## Test Case 2: Paper Search and AI Screening
**Description**: Ensure that searching for papers returns a list of results with an AI relevance score.
**Input Query**: `LLM reasoning capabilities`
**Expected Outcome**: System retrieves papers from arXiv/Semantic Scholar and scores them (0-100) based on relevance.
**Actual Output**:
```json
[
  {
    "title": "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models",
    "authors": ["Jason Wei", "Xuezhi Wang", "Dale Schuurmans"],
    "year": 2022,
    "ai_score": 95,
    "relevance_reason": "Directly addresses LLM reasoning through chain-of-thought prompting."
  },
  {
    "title": "Language Models are Few-Shot Learners",
    "authors": ["Tom Brown", "Benjamin Mann"],
    "year": 2020,
    "ai_score": 70,
    "relevance_reason": "Fundamental paper on LLM capabilities, though not exclusively focused on reasoning."
  }
]
```
**Status**: ✅ Pass

## Test Case 3: Literature Matrix Generation
**Description**: Test the generation of a literature matrix comparing methodologies of saved papers.
**Input**: Project ID `prj_123` containing 3 papers about "Transformer models".
**Expected Outcome**: A structured matrix extracting key methodologies and findings.
**Actual Output**:
| Paper | Methodology | Key Finding | Confidence |
|-------|-------------|-------------|------------|
| Attention Is All You Need | Self-attention mechanism | Dispenses with recurrence entirely. | High |
| BERT | Masked Language Modeling | Deep bidirectional representations. | High |
| GPT-3 | Autoregressive language modeling | Few-shot learning without fine-tuning. | Medium |

**Status**: ✅ Pass

## Test Case 4: Research Gaps Detection
**Description**: Check if the system can identify research gaps based on the saved papers in a project.
**Input**: Project ID `prj_123`.
**Expected Outcome**: A list of identified research gaps with supporting evidence.
**Actual Output**:
```json
{
  "gaps": [
    {
      "description": "Lack of efficient attention mechanisms for very long context windows (>1M tokens).",
      "evidence_papers": ["Attention Is All You Need", "Longformer"],
      "confidence": "High"
    }
  ]
}
```
**Status**: ✅ Pass

## Test Case 5: Document Text Extraction (PDF)
**Description**: Verify the system extracts and chunks text from an uploaded PDF correctly.
**Input**: Upload `sample-paper.pdf` (5 pages).
**Expected Outcome**: The system extracts the text, splits it into chunks, and stores embeddings.
**Actual Output**:
```json
{
  "status": "success",
  "document_id": "doc_999",
  "total_pages_extracted": 5,
  "chunks_created": 12,
  "embedding_status": "completed"
}
```
**Status**: ✅ Pass
