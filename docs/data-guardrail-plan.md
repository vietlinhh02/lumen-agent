# Data Guardrail Implementation Plan: Preventing RAG Hallucinations

## Objective
To ensure the purity of the research corpus by implementing a 3-layered defense system that restricts irrelevant papers from being saved, clearly identifies them in the Literature Matrix, and completely excludes them from the RAG retrieval pipeline. This will eliminate "Garbage In, Garbage Out" (GIGO) scenarios.

---

## Task Breakdown

### Phase 1: Frontend Soft Guardrail (Preventive)
**Goal:** Educate users and add friction when they attempt to save irrelevant papers.

- [ ] **Task 1.1: Read Screening Scores in Save Action**
  - **Location:** `frontend/lib/stores/search-store.ts` (inside `savePaper` action) or the UI component.
  - **Action:** Before dispatching the POST request to `/projects/{id}/papers`, check if the paper's index in the current `sessionData.screening_scores` array evaluates to `"low"`.
- [ ] **Task 1.2: Implement Confirmation Modal**
  - **Location:** `frontend/components/papers/SearchPaperCard.tsx` (or where the save button lives).
  - **Action:** If the score is `"low"`, halt the save process and display a warning modal: *"AI has evaluated this paper as having low relevance to your project topic. Saving irrelevant papers may degrade the quality of your Literature Review. Are you sure you want to save it?"*
  - **Action:** Provide two buttons: `Cancel` (default/highlighted) and `Save anyway`.

### Phase 2: Literature Matrix Auto-Tagging (Detective)
**Goal:** Make it visually obvious if an irrelevant paper slipped into the project corpus, allowing easy 1-click removal.

- [ ] **Task 2.1: Matrix Output Schema Enforcement**
  - **Location:** `app/ai/structured_outputs.py`
  - **Action:** Ensure the `confidence` or `relevance` field in `MatrixRowOutput` clearly forces the AI to output a low confidence or specific flag if the paper's content is unrelated to the project's topic.
- [ ] **Task 2.2: Matrix UI Highlighting**
  - **Location:** `frontend/components/matrix/` (Matrix Table components)
  - **Action:** Apply conditional styling (e.g., grayed-out background, warning icon) to rows where the AI's extraction confidence is `"low"`.
- [ ] **Task 2.3: Quick Delete Action**
  - **Location:** `frontend/components/matrix/`
  - **Action:** Add a prominent "Remove from Project" button directly on grayed-out rows to encourage users to clean their corpus.

### Phase 3: RAG Retrieval Strict Filtering (Protective)
**Goal:** The ultimate failsafe. Ensure that even if garbage exists in the database, the RAG system refuses to serve it to the Report Generation LLM.

- [ ] **Task 3.1: Propagate Relevance to DB Models**
  - **Location:** `app/db/models.py`
  - **Action:** Ensure `ProjectPaper` has a robust `relevance_label` or `status` field that can be updated either manually or via Matrix generation.
- [ ] **Task 3.2: Update Hybrid Retrieval Filters**
  - **Location:** `app/services/hybrid_retrieval.py` (`retrieve_project_evidence` function)
  - **Action:** Modify the SQLAlchemy query that fetches chunks for vector similarity search. Add a strict `WHERE` clause to permanently exclude chunks belonging to `ProjectPaper`s that are flagged as irrelevant or low relevance.
  - *Example logic:* `stmt = stmt.where(ProjectPaper.relevance_label != 'low')`
- [ ] **Task 3.3: Sync Matrix Relevance with ProjectPaper (Optional but recommended)**
  - **Location:** `app/services/matrix.py` (or wherever matrix extraction occurs)
  - **Action:** If the Matrix extraction LLM determines a paper is completely irrelevant, automatically update the `ProjectPaper.relevance_label` in the database to `"low"`, so Phase 3 filtering triggers immediately without user intervention.

---

## Definition of Done (DoD)
1. A user trying to save a "low relevance" paper receives a pop-up warning.
2. The Literature Matrix visually distinguishes irrelevant papers.
3. The Report Generation pipeline no longer retrieves or cites any paper that has been flagged as low relevance.
