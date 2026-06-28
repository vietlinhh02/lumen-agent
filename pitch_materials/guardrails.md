# Data Guardrails Plan

Lumen implements a strict 3-layered defense system to prevent "Garbage In, Garbage Out" (GIGO) and completely eliminate RAG hallucinations.

## 1. Frontend Soft Guardrail (Preventive)
Educates users and adds friction when attempting to save irrelevant papers to a project.
- **Mechanism:** Before saving a paper, the system checks the AI screening score. If the score is "low", a confirmation modal warns the user: *"AI has evaluated this paper as having low relevance... Are you sure you want to save it?"*

## 2. Literature Matrix Auto-Tagging (Detective)
Makes it visually obvious if an irrelevant paper slipped into the project corpus.
- **Mechanism:** The Matrix generation forces the AI to output a `confidence` level. Low confidence/irrelevant rows are highlighted visually (grayed out with a warning icon) with a quick 1-click "Remove from Project" action.

## 3. RAG Retrieval Strict Filtering (Protective)
The ultimate failsafe to prevent hallucinations in final reports.
- **Mechanism:** Hybrid retrieval queries (SQLAlchemy) strictly filter out `ProjectPaper`s flagged as low relevance. The Report Generation LLM simply cannot access or cite bad data, ensuring absolute purity in the final literature review.
