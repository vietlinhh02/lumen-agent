# T3: Full-Text Evidence Viewer With Quote Anchors

> Feature gap analysis and integration plan for the Full-Text Evidence
> Viewer with Quote Anchors (T3 in `docs/feature-opportunity-research.md`).

Date: 2026-06-24
Status: **Backend infrastructure in place; frontend UI and API
exposure not shipped.** First slice not started.
Owner: TBD
Priority: P0 (highest)
Build order: #1 (the first P0 feature to build)

---

## 1. Why this feature gap exists

### 1.1 The problem: claims without receipts

The current app's strongest pitch is *citation safety*: generated
reports cite only saved project papers, and the backend rejects
invalid citation IDs. That promise is invisible to the user today,
because every place a claim appears — matrix cell, gap description,
conflict `claim_a` / `claim_b`, report paragraph — shows *which paper*
but not *which part of the paper*.

The user has to leave the app, open the PDF, scroll to the cited
page, and find the supporting sentence by hand. Every citation is a
trust-me. There is no trace from claim back to chunk, page, and
quote.

This is what competitors solve cleanly:

- **SciSpace** lets the user click a claim and see the supporting
  sentence highlighted in the PDF, with a verification badge.
- **Elicit** pairs every extracted answer with a quote card that
  links to the source sentence.
- **Madhav-000-s/RAG-research-paper-Intelligence-engine** has a split
  PDF viewer where clicking a generated citation jumps back to the
  cited page and section.

The app's claim that it is "more than a chatbot" depends on making
this traceability visible. Right now it is invisible.

### 1.2 What "gap" means in the current code

A careful audit of the current state shows that **the backend is
closer than it looks**, but the frontend and the API are missing:

| Layer | Current state | Missing |
|-------|--------------|---------|
| **Storage** | `PaperChunk` rows carry `chunk_text`, `content_type`, `section_label`, `embedding`, `chunk_metadata` (incl. page info when the PDF parser produced it). | Nothing at the storage layer. |
| **Retrieval** | `retrieve_paper_evidence()` in `app/services/hybrid_retrieval.py:205` returns ranked `RetrievedChunk` per paper. | The function is **not exposed via an HTTP endpoint**. It is only called internally from `conflict_detection.py` and `agents/nodes.py`. |
| **Matrix extraction** | The agent emits `key_result`, `limitation`, etc. | The agent does **not** return or persist the chunks that produced those fields. |
| **Matrix response** | `MatrixRowResponse` (in `app/schemas/matrix.py`) carries 7 free-text fields plus `extraction_confidence`. | No `top_evidence` field, no per-row evidence list. |
| **Matrix UI** | `MatrixTable.tsx` renders the 7 columns. | No "View evidence" action, no drawer, no quote rendering. |
| **Gap UI** | `GapCard.tsx` shows `evidence_summary` text and an `evidence[]` list with `evidence_type` + `note`. | The evidence list is **gap-level** and **free-form text**. It is not chunk-level, has no quote, no page, no section, no link back to the PDF. |
| **Conflict UI** | Conflict detection produces `claim_a`, `claim_b`, `shared_context`, and `possible_explanation`. | The UI does not show the chunks the detector used to produce those claims. |
| **Report UI** | `ReportContent.tsx` renders generated Markdown with citation links. | Citations are not clickable in the way SciSpace/Elicit-style links are — there is no "jump to PDF page" handler. |
| **User feedback** | Nothing. | No "accepted / weak / wrong" mark per evidence item. No persistence of user ratings. |

In short: **everything below the data layer works; nothing above the
retrieval function exists in the UI or the API.** The first slice of
T3 is to bridge exactly that gap.

### 1.3 Why now

T3 is build order #1 in `feature-opportunity-research.md`, ahead of
the just-shipped T2 audit and the still-pending T4 custom schema. The
reason is:

- T3 is **the user's payoff for every other P0/P1 feature**. The
  matrix (T4), the audit (T2), the synthesis (T7), the methods
  package (T11) all become more convincing when the user can click
  through from claim to quote.
- The backend is mostly there. The first slice is a small API + UI
  delta on top of `retrieve_paper_evidence`, which means it is
  comparable in size to T2 and T4 first slices.
- Without T3, the user still has to leave the app to verify a
  citation, and the app's strongest differentiator (citation safety)
  remains invisible.

---

## 2. How it applies to the current project

### 2.1 What the project already gives us

A surprising amount of T3 is already implemented at the bottom of
the stack:

- **Chunks with metadata.** `PaperChunk` (see `app/db/models.py`)
  stores `chunk_text`, `content_type` (e.g. `method`, `results`,
  `limitation`, `narrative`), `section_label`, `embedding`, and
  `chunk_metadata` (JSONB — currently used by the PDF parser to
  stash page info when available).
- **Per-paper retrieval.** `retrieve_paper_evidence()` in
  `app/services/hybrid_retrieval.py:205` returns ranked chunks for
  one paper, optionally filtered by `content_types`. It is already
  Jina-aware and uses the project embedding provider.
- **Internal callers.** `app/services/conflict_detection.py:302`
  uses it to build chunk context for the detector prompt, and
  `app/agents/nodes.py:648` uses it for matrix extraction. So the
  retrieval path is exercised in production today.
- **`RetrievedChunk` Pydantic model.** Carries
  `project_paper_id`, `paper_id`, `paper_title`, `chunk_text`,
  `content_type`, `section_label`, `score`, `keyword_score`,
  `vector_score`, `chunk_metadata`.
- **Hybrid scoring.** Already combines vector cosine distance with
  keyword overlap and content-type weighting, which is exactly the
  ranking the evidence viewer wants.
- **Knowledge-graph context hook.** `_build_project_graph_context`
  in `conflict_detection.py` already shows how to enrich chunk
  context with graph-derived terms; we can reuse the same hook in
  the evidence API.

### 2.2 What needs to change

In order of risk:

1. **API layer — expose retrieval.** A new endpoint:
   `GET /projects/{id}/matrix/{row_id}/evidence`

   - Query params: `limit` (default 5), `content_types` (CSV, optional),
     `include_graph` (bool, default false).
   - Returns: `{"items": [RetrievedChunk, ...], "paper_title": str,
     "project_paper_id": UUID}`.
   - Server-side: load the matrix row → derive a query from
     `research_problem`, `method`, `key_result`, `limitation` →
     call `retrieve_paper_evidence` for the row's
     `project_paper_id` → optionally enrich with
     `build_graph_context` → return.

   This is the smallest delta that ships the first slice. It does
   not require a DB migration.

2. **Matrix response — attach top evidence (optional).** Two paths:

   - **Cheap path:** leave `MatrixRowResponse` alone, let the
     frontend call `/matrix/{row_id}/evidence` on demand. Fastest,
     but every "View evidence" click is a separate request.
   - **Inline path:** add `top_evidence: list[RetrievedChunk] = []`
     to `MatrixRowResponse` and have `list_matrix_rows` populate
     it. Costs N retrievals per list call; mitigable with a
     background-job warmup.

   Recommendation: **cheap path first** (matches the "smallest
   useful slice" discipline). Switch to inline when the UI proves
   out and we know which fields actually drive evidence clicks.

3. **Frontend — evidence drawer component.** New shared component:
   `components/evidence/EvidenceDrawer.tsx` (or similar). It:

   - Renders a list of evidence items, each with:
     - Paper title (or short id fallback)
     - Section label + content type badge
     - Quote (chunk_text, possibly truncated with a "show more" if
       long)
     - Page number when `chunk_metadata.page` exists
     - "Open paper" link (uses existing paper-detail route)
     - Three buttons: **Accept** / **Weak** / **Wrong**
   - Loads evidence via the new endpoint on open.
   - Slides in from the right (existing project layout already
     supports side panels; check `frontend/app/(app)/projects/[id]/layout.tsx`).
   - Reusable: the same drawer is used by matrix, gap, conflict, and
     report surfaces, with a tiny per-surface wrapper.

4. **Matrix table — "View evidence" action.** Add a new column or
   row-action in `MatrixTable.tsx`:

   - A small icon button on each row that opens the evidence
     drawer with `row_id` as the prop.
   - Disabled state when the row has no `project_paper_id` (should
     never happen, but be defensive).

5. **Gap card — replace free-form evidence with chunk-level items.**
   `GapCard.tsx` currently renders `evidence_summary` (text) plus
   `evidence[]` (`evidence_type` + `note` per paper). Refactor:

   - Keep `evidence_summary` as the high-level paragraph.
   - Replace each `evidence` entry with a button that opens the
     same `EvidenceDrawer` scoped to that paper + gap title.
   - The drawer fetches chunks for `project_paper_id` filtered by
     `content_types` aligned to the gap's `suggested_direction`.

6. **Conflict UI — surface detector chunks.** The conflict
   detection service already builds `chunk_context`. Persist the
   top chunks per side in a new `ConflictingFindingChunk` table:

   ```python
   class ConflictingFindingChunk(Base):
       id, conflict_id, project_paper_id, polarity (a|b),
       chunk_id, snippet, content_type, section_label, score
   ```

   Backfill on the next detection run; the existing service can
   write to it without changing its return type. The conflicts
   page then renders the same `EvidenceDrawer` per side.

7. **Report — clickable citations.** `ReportContent.tsx` already
   parses citation markers. Add a handler:

   - On click, look up the cited paper in the project's saved
     papers, then open the PDF viewer at the cited chunk's page.
   - Use `paper_pdf_path` (already computed in the recent
     `feature/UIStructure` fix) as the source URL.
   - This is the "click and jump" experience from the
     RAG-research-paper-Intelligence-engine reference.

8. **User feedback — accepted/weak/wrong marking.** New table:

   ```python
   class EvidenceRating(Base):
       id, project_id, user_id, source_kind (matrix_row | gap |
           conflict | report_paragraph), source_id, project_paper_id,
       chunk_id, rating (accepted | weak | wrong), note (text,
       nullable), created_at, updated_at
   ```

   The drawer posts ratings here. Ratings surface in the UI as a
   small icon next to the quote, and feed T12's quality dashboard.

### 2.3 What it does NOT change

- The matrix row's seven default fields, `extraction_confidence`,
  `content_hash`, and `created_by` are unchanged.
- The chunk storage layer is unchanged. We are only adding a new
  reader of chunks, not a new writer.
- The conflict detection prompt and gap detection prompt are
  unchanged for the first slice; only their *output persistence*
  gains chunk records (Phase 6 above).
- `retrieve_paper_evidence` is unchanged. New callers wrap it.
- The T2 audit endpoint is unchanged. It can later consume
  `EvidenceRating` to surface "rated weak" counts, but that is
  out of scope for the first slice.
- The T4 custom-schema work is unchanged at the API level. When T4
  ships, the evidence drawer just gains more trigger points
  (one per claim-bearing field).

### 2.4 Risks specific to this project

| Risk | Mitigation |
|------|------------|
| Chunks without page numbers are common (PDF parser may not always emit them) | Render the quote without a page badge; never block the drawer on missing metadata. |
| "View evidence" latency: per-click embedding search | Cap `limit` to 5, cache the most recent N retrievals per session in the store, reuse the matrix-extraction-time chunks when they exist (Phase 2 inline path). |
| Users mark everything "wrong" because they disagree with the claim, not the chunk | The rating UI should be explicit: "Is this *quote* relevant evidence for the *claim*?" not "Do you agree with the claim?". |
| Drawer takes over the screen on small viewports | Use the existing slide-over pattern from the project layout; ensure it scrolls independently. |
| Click-to-PDF requires opening a new tab or modal — risk of disrupting reading flow | Open in a side-by-side panel if available; otherwise a new tab is acceptable for v1. |
| User ratings become noisy ground truth | Treat them as weak supervision; aggregate by `(source_kind, source_id)` and surface both per-user and consensus ratings. |

---

## 3. Integration direction

### 3.1 Goals

1. Make every claim in the app — matrix cell, gap, conflict, report
   paragraph — **one click away** from the supporting quote, page,
   and section.
2. Reuse the existing retrieval, chunk, and embedding infrastructure.
   Do not fork a parallel path.
3. Ship a **shared evidence drawer** that every surface uses, so the
   UX is consistent.
4. Capture **user feedback** (accepted / weak / wrong) per evidence
   item, so future T12 quality signals have ground truth.
5. Do not break the matrix, gap, conflict, audit, or report APIs.

### 3.2 Non-goals (out of scope for the first slice)

- Inline `top_evidence` on `MatrixRowResponse` (deferred — cheap
  path first).
- Cross-paper evidence aggregation (deferred to T7 synthesis).
- PDF highlighter that runs *inside* the app (we link out or open
  in a panel for v1).
- Auto-recompute of extraction when an evidence item is marked
  "wrong" (operator-driven rerun only).
- Per-user confidence scoring blended with user ratings (T12 work).
- Bulk evidence export (deferred to T5 import/export).

### 3.3 Build phases

**Phase 1 — Read-only evidence from matrix (cheapest path).**
- Add `GET /projects/{id}/matrix/{row_id}/evidence` endpoint.
- Add `EvidenceDrawer` component (read-only, no ratings yet).
- Add "View evidence" icon to each row in `MatrixTable.tsx`.
- Add 1 test: matrix row → evidence endpoint → 200 with ≥ 1 chunk
  when chunks exist.

**Phase 2 — Reuse the drawer in gaps and conflicts.**
- Add `ConflictingFindingChunk` table and persistence.
- Refactor `GapCard.tsx` evidence rendering to use the drawer.
- Refactor the conflicts page to use the drawer per side.
- 2 tests: gap + conflict render evidence correctly.

**Phase 3 — User ratings.**
- Add `EvidenceRating` table.
- Wire Accept / Weak / Wrong buttons.
- Add a "Why was this rated weak?" inline note.
- Surface the rating in the drawer and in the project header chips.

**Phase 4 — Clickable citations in reports.**
- Refactor `ReportContent.tsx` citation rendering to open the PDF
  at the chunk's page (uses `paper_pdf_path` from the recent
  `feature/UIStructure` fix).
- Pass the chunk's `content_type` and `section_label` to the PDF
  viewer so the panel can highlight the right region when the
  viewer supports it.

**Phase 5 — Inline evidence on matrix rows (optional).**
- Add `top_evidence` to `MatrixRowResponse`.
- Warm the cache during matrix extraction (the agent already has
  the chunks in scope).
- Trade-off: cheaper UX vs. heavier list endpoint. Decide after
  measuring real usage.

### 3.4 First implementation slice

The smallest slice that is safe, useful, and ships value:

1. New endpoint `GET /projects/{id}/matrix/{row_id}/evidence` that
   wraps `retrieve_paper_evidence` with a query derived from the
   row's fields.
2. New `EvidenceDrawer` component (read-only).
3. New "View evidence" icon on each row in `MatrixTable.tsx`.
4. One test: given a row with chunks, the endpoint returns ≥ 1
   chunk and the chunk has `chunk_text`, `content_type`,
   `section_label`.
5. Manual smoke: open a project with ≥ 1 saved paper that has
   chunks, click "View evidence", see a quote with a section label.

That is roughly the same size as the T2 audit, T4 first slice, and
T7 first slice. It is the minimum that turns T3 from "feature
research" into "feature shipping."

### 3.5 How this unblocks later work

- **T4 Custom schema** — the drawer can open per-field, not
  per-row, once the schema knows which fields are claim-bearing.
- **T7 Claim synthesis** — clusters gain a "View evidence" link
  per cluster that reuses the same drawer.
- **T11 Methods & reproducibility** — ratings become a first-class
  audit line: "Of the 47 evidence items shown, the reviewer
  accepted 31, rated 9 weak, and rated 7 wrong."
- **T12 Quality dashboard** — `EvidenceRating` becomes a quality
  signal that no other product in the comparison set surfaces.
- **T9 Collaboration** — ratings become shared when teams exist,
  so two reviewers can see where they disagree.

### 3.6 Open questions for the team

- Should the drawer be a side panel, modal, or full-page route?
  Side panel is consistent with the existing layout; modal is
  faster to ship.
- Should "Open paper" jump to the cited page, the cited chunk, or
  the paper's saved view? All three are easy; pick one for v1.
- Should ratings be private (per user) or shared (project-wide)?
  Private is safer for v1; shared unlocks T9 collaboration sooner.
- Should the drawer cache chunks across navigation? Yes, via the
  existing assistant-store pattern.
- Should evidence be re-retrieved on every open, or cached for the
  matrix row's lifetime (until `content_hash` changes)?
  Cache-on-content-hash is the principled answer; re-retrieve is
  the cheap answer. Cache is the v1 choice.

---

## 4. Current integration status (as of 2026-06-24)

A focused audit of the codebase at the time of writing:

| Sub-feature | Shipped? | Evidence |
|-------------|----------|----------|
| Chunks with metadata | **Yes** | `PaperChunk` model + `chunk_metadata` JSONB |
| Per-paper retrieval function | **Yes** | `app/services/hybrid_retrieval.py:205` |
| Internal callers use retrieval | **Yes** | `conflict_detection.py:302`, `agents/nodes.py:648` |
| Evidence HTTP endpoint | **No** | No `*.py` file in `app/routers/` exposes `retrieve_paper_evidence` |
| `top_evidence` on matrix row | **No** | `app/schemas/matrix.py` does not include the field |
| "View evidence" in matrix table | **No** | `MatrixTable.tsx` has no evidence-related code |
| Shared `EvidenceDrawer` component | **No** | `frontend/components/` has no `evidence/` directory |
| Quote / page / section in gaps | **No** | `GapCard.tsx` renders gap-level free text only |
| Quote / page / section in conflicts | **No** | No conflict chunk persistence, no per-side UI |
| Clickable citations in reports | **No** | `ReportContent.tsx` does not open the PDF viewer |
| User ratings (accepted/weak/wrong) | **No** | No `EvidenceRating` table, no UI |

**Headline:** **0/11 sub-features shipped.** Backend infrastructure
is fully in place; API exposure and frontend UI are entirely
missing. The first slice is the bridge between these two halves.

---

## 5. Summary

| Question | Answer |
|----------|--------|
| Why does this gap exist? | The app's strongest pitch (citation safety) is invisible to users because claims show only paper IDs, not quote + page + section. |
| Why now? | T3 is build order #1 and the user's payoff for every other feature. Without it, T2, T4, T7, T11 all stay second-class. |
| What does it change? | Adds an evidence HTTP endpoint, a shared `EvidenceDrawer`, a "View evidence" action in matrix, and an `EvidenceRating` table. Reuses `retrieve_paper_evidence`. |
| What does it preserve? | All existing matrix, gap, conflict, audit, and report APIs. The chunk storage layer is unchanged. |
| What is the first slice? | One new endpoint + one new drawer component + one new icon in the matrix table + 1 test. Roughly the size of the T2 / T4 / T7 first slices. |
| What does it unblock? | T4 per-field evidence, T7 cluster-level evidence, T11 ratings as audit data, T12 quality signals, T9 shared ratings. |
| Is T3 shipped? | **No.** Backend retrieval works internally; API exposure and frontend UI are missing. The first slice above closes that gap. |

---

## 6. References

- `docs/feature-opportunity-research.md` — original T3 definition
  and Feature Gap #3 detail.
- `app/services/hybrid_retrieval.py` —
  `retrieve_paper_evidence()` at line 205.
- `app/services/conflict_detection.py` — internal chunk usage at
  line 302; `ConflictingFindingChunk` table does not yet exist.
- `app/services/gap_detection.py` — `GapEvidence` table is
  gap-level only.
- `app/agents/nodes.py` — internal chunk usage at line 648.
- `app/schemas/matrix.py` — `MatrixRowResponse` (no
  `top_evidence` field).
- `app/routers/matrix.py` — matrix CRUD endpoints (no evidence
  endpoint).
- `frontend/components/matrix/MatrixTable.tsx` — current matrix
  table (no "View evidence" action).
- `frontend/components/gaps/GapCard.tsx` — current gap card
  (free-form evidence only).
- `frontend/components/reports/ReportContent.tsx` — current report
  view (no clickable citation jump).
- External: SciSpace, Elicit,
  Madhav-000-s/RAG-research-paper-Intelligence-engine for the
  clickable-citation UX pattern (see
  `feature-opportunity-research.md` for URLs).