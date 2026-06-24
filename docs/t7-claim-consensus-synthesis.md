# T7: Claim and Consensus Synthesis

> Feature gap analysis and integration plan for the Claim and Consensus
> Synthesis feature (T7 in `docs/feature-opportunity-research.md`).

Date: 2026-06-24
Status: **Not started** — research/design phase
Owner: TBD
Priority: P1
Build order: #8 (after T11 Methods & Reproducibility Package)

---

## 1. Why this feature gap exists

### 1.1 The problem: data without synthesis

The current app already produces a strong set of "primary" artifacts:

- **Literature matrix rows** — `research_problem`, `method`,
  `dataset_or_context`, `key_result`, `limitation`, `contribution`,
  `relevance` per paper.
- **Research gaps** — title, description, suggested direction, evidence
  summary, plus a list of evidence entries pointing to specific papers.
- **Conflicting findings** — paired (paper_a, paper_b) claims with
  `claim_a`, `claim_b`, `shared_context`, and `possible_explanation`.
- **Knowledge graph** — concept-level relations across project papers.

These artifacts are **raw observations**. A user reading them still has
to do the synthesis work in their head: *what does the field agree on?
what does it disagree on? where is evidence thin?* That is exactly the
work a literature review is supposed to save.

Competitors solve this with a "Claims" or "Consensus" view:

- **Consensus** surfaces a top-level *Consensus / Counterpoint* page per
  question, with supporting and contradicting papers, and a confidence
  bar driven by paper count + quality + recency.
- **Research Vault** extracts every paper into `Claim → Evidence →
  Context` triples, then groups them into a queryable library.
- **aakashsharan/scientific-literature-intelligence-system** adds
  explicit *strength*, *direction*, and *confidence* scores per claim.

The current app has the *inputs* for all of this (matrix rows,
conflicts, evidence, embeddings) but no *output* — there is no page
that says "the field believes X, but 2 papers argue Y, and 1 paper
alone claims Z."

### 1.2 What "gap" specifically means in the current code

The conflict-detection service already produces structured
`claim_a` / `claim_b` pairs, and the matrix rows are the canonical
extraction target. The gap is that:

1. **Claims are never extracted as a first-class object.** They live
   only as fields inside a matrix row or as a pair inside a conflict
   record. There is no `Claim` table, no claim-level confidence, no
   claim-level clustering.
2. **There is no clustering step.** A claim that appears in 6 matrix
   rows with slightly different wording is treated as 6 independent
   facts.
3. **There is no aggregate confidence or recency view.** The user
   cannot ask "how confident am I that this claim is true across the
   literature?" — they can only see individual confidence badges on
   each matrix row.
4. **There is no consensus / contradiction / weak-evidence
   categorization.** The conflict table only shows pairwise
   contradictions; the matrix only shows per-paper fields; neither
   shows "this claim is supported by 8/12 papers, contradicted by 2/12,
   and unaddressed by 2/12."

### 1.3 Why now

The roadmap lists T7 at build order #8, after T11 (Methods &
Reproducibility Package). The reason for that ordering is that
synthesis is only valuable once:

- The matrix is **typed** (T4) so claims can come from custom fields
  as well as the 7 default fields.
- The evidence drawer (T3) can back every claim with a paper-and-quote
  trace.
- The methods artifact (T11) documents *how* the synthesis was
  produced, so it is reproducible.

T7 is the natural "synthesis" payoff at the top of the stack. Without
it, T3, T4, and T11 produce a lot of well-grounded raw material that
the user still has to assemble by hand.

---

## 2. How it applies to the current project

### 2.1 What the project already gives us

Most of the inputs and a surprising amount of the infrastructure are
already in place:

- **Matrix rows with `extraction_confidence`** —
  `app/db/models.py` lines 435–490. Each row carries
  `extraction_confidence ∈ {low, medium, high}` and the seven default
  fields.
- **Conflicting findings with `claim_a`, `claim_b`,
  `possible_explanation`, `confidence`** —
  `app/db/models.py` `ConflictingFinding` table; detection service at
  `app/services/conflict_detection.py`.
- **Gap evidence with `evidence_type` and `note`** —
  `GapEvidence` table; detection service at
  `app/services/gap_detection.py`.
- **Full-text chunks with `content_type` and `section_label`** —
  `app/services/hybrid_retrieval.py` already returns them by paper.
- **Per-paper embedding pipeline** — chunks are embedded once at
  ingest; clustering can reuse those embeddings.
- **Project-scoped data model** — every artifact already has
  `project_id`, so a "Claims" page can be added without breaking
  cross-project boundaries.
- **Hybrid retrieval with per-paper evidence** — the conflict
  service already does the per-paper chunk query we need for the
  evidence drawer in T3.
- **LLM provider with `complete_structured()`** —
  `app/ai/provider.py` — supports the same JSON-schema constrained
  output we need for claim normalization.

In other words: **the building blocks exist; what is missing is the
synthesis layer on top.**

### 2.2 What needs to change

In order of risk:

1. **Data layer.** Introduce a new first-class object: `Claim`.

   Option A — single table:
   ```python
   class Claim(Base):
       id, project_id, canonical_text, claim_type (support/contradict/mixed/weak),
       support_count, contradict_count, neutral_count, confidence, created_at
   ```
   Plus a `ClaimEvidence(claim_id, project_paper_id, project_paper_chunk_id,
   polarity ∈ {support, contradict, neutral}, snippet)` join table.

   Option B — add columns to existing tables: reject. The current
   matrix/conflict/gap tables are paper- or pair-scoped; shoehorning
   claim-level fields into them would muddy the schema.

   Recommendation: **Option A**. The `Claim` + `ClaimEvidence` shape
   maps directly onto the "Claim → Evidence → Context" pattern from
   Research Vault and onto the consensus/counterpoint model from
   Consensus.

2. **Claim extraction.** Mine claims from three sources, in order of
   trust:

   - **(a) Existing conflicts** — `ConflictingFinding.claim_a` and
     `claim_b` already have a `claim` and a polarity (contradict each
     other). Lift these directly into `Claim` rows with
     `claim_type = contradict` and one `ClaimEvidence` row per side.
   - **(b) Matrix rows** — for each row, treat `key_result` and
     `limitation` as candidate claims. Cluster across rows by text
     similarity to canonicalize.
   - **(c) Full-text chunks** — for projects with deep coverage, run
     an LLM pass over each paper's "results" and "conclusion" chunks
     to extract additional claim candidates. This is the slowest
     path; do it last or only for projects with sparse matrix data.

3. **Clustering and canonicalization.** Two-step pipeline:

   - **Step 1 — Embedding-based candidates.** For each candidate
     claim text, embed it with the project's existing embedding
     model. Cluster with HDBSCAN (density-based, no fixed k, handles
     noise) or Agglomerative Clustering with cosine distance.
   - **Step 2 — LLM canonicalization.** For each cluster with ≥ 2
     members, ask the LLM to produce a single canonical statement
     ("Papers X, Y, and Z report that …") and to label the cluster
     as `support` (all members agree), `contradict` (signs of
     disagreement), `mixed` (some agree, some differ in scope), or
     `weak` (cluster is too small or too low-confidence to assert).
     The prompt should be passed the cluster's member texts plus
     their polarity hints (from conflict lift or matrix extraction).

4. **Confidence scoring.** A first-slice formula:
   ```
   confidence = 0.5 · (n_supporting_papers / max(n_support, n_contradict, n_neutral))
              + 0.3 · avg_matrix_extraction_confidence   # low=0, medium=0.5, high=1
              + 0.2 · recency_score                      # exponential decay, half-life 5y
   ```
   The result is mapped back to `low / medium / high` at the API
   boundary. The formula is intentionally simple so it is easy to
   explain in the methods artifact (T11) and in the user-facing UI.

5. **API surface.** New endpoints:
   - `GET /projects/{id}/claims` — list claims for a project, with
     optional `?claim_type=contradict` filter and `?sort=confidence`.
   - `GET /projects/{id}/claims/{claim_id}` — single claim with full
     evidence list (paper, chunk, snippet, polarity).
   - `POST /projects/{id}/claims:generate` — kick off synthesis as a
     background job (reuses `BackgroundJob`).
   - `GET /projects/{id}/claims:aggregate` — returns
     `{"support": 12, "contradict": 3, "mixed": 4, "weak": 2}` for
     the project header chips.

6. **Frontend — new "Claims" page.**

   - **Header chips:** Support · Contradict · Mixed · Weak (counts).
   - **Main list:** claim rows, each with
     canonical text, claim-type badge, confidence bar, "View
     evidence (n)" button, recency tag.
   - **Evidence drawer** (T3-style): per-paper snippet with the
     quote highlighted, section label, retrieval reason, and a
     one-click "open paper" link.
   - **Conflict integration:** a dedicated "Contradictions" tab
     inside the same page that lifts the existing
     `ConflictingFinding` rows so users have one place to look.
   - **Drill-down by paper:** clicking a paper in a claim's evidence
     list shows every claim that paper participates in.

7. **Conflict reconciliation.** The existing
   `conflicting_findings` table is the source of truth for
   pairwise contradictions. T7 should:
   - Re-derive contradictions from the new `Claim.claim_type` field
     on every regeneration.
   - Keep the old table in sync (do not delete it) so the existing
     `/conflicts` endpoints keep working.
   - If a claim cluster contains a contradiction but no conflict
     record exists, optionally create one for backwards compatibility
     (gated by a flag, off by default).

8. **Recompute triggers.**
   - Manual: "Regenerate claims" button on the Claims page.
   - Implicit: when matrix rows or conflicts change (best-effort;
     can be lazy and re-derive on read for the first slice).

### 2.3 What it does NOT change

- The matrix row identity and schema are unchanged. T7 reads from
  `LiteratureMatrixRow`, does not write to it.
- `ConflictingFinding` and `ResearchGap` are unchanged at the table
  level. T7 lifts claims out of them but does not modify them.
- The hybrid retrieval service is unchanged. T7 reuses it for the
  evidence drawer.
- The knowledge graph service is unchanged. T7 may *consult* the
  graph for entity-level grouping in a later phase, but the first
  slice does not depend on it.
- The T2 audit endpoint, the T3 evidence drawer primitives, the T4
  schema, and the T11 methods artifact are unchanged at the API
  level. They each gain a new consumer (T7) but their contracts
  hold.

### 2.4 Risks specific to this project

| Risk | Mitigation |
|------|------------|
| Clustering produces noisy or over-merged clusters | Use HDBSCAN with conservative `min_cluster_size`; treat the LLM canonicalization as a quality gate, not a guarantee; expose "this cluster is not confident" in the UI. |
| LLM canonicalization drifts between runs | Pin temperature low (≤ 0.2); store the input texts alongside the canonical text so a re-run is reproducible. |
| Two clusters really are the same claim | Add a "merge claims" admin action; or run a second-pass cosine check across cluster centroids. |
| Recency score punishes older seminal work | Apply a soft cap; expose the formula in the UI so users see why a paper is weighted as it is. |
| Backwards-compat with existing conflict table | Dual-write is fine because the conflict detection service is idempotent. The Claims page is read-only over the existing conflicts table. |
| Performance with many papers | Pre-embed and cache claim vectors; cap full-text claim extraction to top-N papers by recency × extraction_confidence. |
| Ground-truth validation | Add a small "Did we get this right?" thumbs-up/down per claim, log into a feedback table; use it later to evaluate clustering quality. |

---

## 3. Integration direction

### 3.1 Goals

1. Surface a **consensus / counterpoint / weak-evidence view** of the
   project's literature that does not exist anywhere in the app today.
2. Reuse the existing matrix, conflict, gap, and evidence artifacts
   — do not duplicate them.
3. Make every claim **traceable** to the paper, chunk, and snippet
   that supports or contradicts it.
4. Ship a confidence score that is **explainable** in the UI and
   reproducible in the methods artifact.
5. Do not break the conflict, gap, matrix, audit, evidence, schema, or
   methods APIs.

### 3.2 Non-goals (explicitly out of scope for the first slice)

- Cross-project claim libraries / knowledge bases.
- User-authored claims (vs. system-extracted claims).
- Live re-clustering on every matrix edit (use the manual
  "Regenerate" trigger first; lazy re-derive later).
- Temporal trend lines ("this claim has gained / lost support over
  time"). Future slice.
- Multi-language claim alignment. First slice is English-only.
- Community voting / annotation of claims. Future slice, requires
  collaboration (T9).

### 3.3 Build phases

**Phase 1 — Read-only consensus view from existing data.**
- Add `Claim` and `ClaimEvidence` tables.
- Lift claims from `ConflictingFinding.claim_a/claim_b` and from
  `LiteratureMatrixRow.key_result/limitation` into the new tables
  (one-time backfill script + idempotent job).
- Add `GET /projects/{id}/claims` and
  `GET /projects/{id}/claims/{claim_id}` endpoints.
- Render a basic Claims page in the frontend with header chips and a
  flat list. No clustering yet — every matrix row produces one
  candidate claim, every conflict produces two.

**Phase 2 — Clustering and canonicalization.**
- Embed candidate claims, run HDBSCAN, LLM-canonicalize each cluster.
- Persist canonical text, claim_type, support/contradict/neutral
  counts, and confidence.
- Surface the canonical claim in the UI; demote the per-row
  candidates to "evidence entries".
- Add the "regenerate claims" background job.

**Phase 3 — Recency + extraction-quality scoring.**
- Add the recency_score component to the confidence formula.
- Add thumbs-up/down feedback collection.
- Add the `claims:aggregate` endpoint for header chips.

**Phase 4 — Tight integration with T3 and T11.**
- T3 evidence drawer gets a "claims containing this evidence" reverse
  lookup.
- T11 methods artifact includes the synthesis formula and the
  cluster count.
- T12 quality dashboard surfaces "claim coverage" (% of matrix rows
  that participated in any claim).

### 3.4 First implementation slice (what we would build first)

The smallest slice that is safe, useful, and ships value:

1. Add `Claim` and `ClaimEvidence` tables (one migration, two
   models).
2. One-time backfill script that lifts claims from
   `ConflictingFinding` and `LiteratureMatrixRow` into the new
   tables.
3. `GET /projects/{id}/claims` endpoint that returns the rows as-is,
   grouped by `claim_type`.
4. Frontend: a new `/projects/{id]/claims` route with a header
   chip strip and a flat list. No clustering, no canonicalization.
5. One test: create a project with 3 matrix rows and 1 conflict,
   run backfill, assert the new tables have 5 claims and the right
   evidence rows.

That slice is roughly the same size as the T2 audit and T4 first
slices, and it is the foundation everything else builds on. The
clustering and canonicalization in Phase 2 is where the synthesis
becomes interesting, but the read-only view in Phase 1 is already
useful on its own (it shows the user "here are 47 things your project
has claimed" — currently invisible).

### 3.5 How this unblocks later work

- **T3 Evidence viewer** — claims give T3 a curated list of
  "evidence items" worth surfacing in drawers.
- **T4 Custom schema** — claim extraction will use the project
  schema to know which matrix fields are claim-bearing (e.g. the
  user can mark a custom field as `claim_role=claim`).
- **T11 Methods & reproducibility** — the synthesis formula and
  cluster counts become first-class entries in the methods draft.
- **T12 Quality dashboard** — "claim coverage" and "average claim
  confidence" are direct quality signals.
- **T9 Collaboration** — once teams exist, the thumbs-up/down
  feedback becomes shared ground truth, and per-claim comments
  become a real review surface.

### 3.6 Open questions for the team

- Should claims be regenerated automatically on matrix change, or
  only on manual trigger? Auto is more useful but more expensive.
- Should the canonicalization prompt be language-specific, or is
  English-only acceptable for v1?
- Should `claim_type` allow free-text user overrides, or stay
  system-managed? User overrides are more flexible but introduce
  inconsistency.
- Should we expose the cluster similarity threshold to the user, or
  keep it internal? A "merge" / "split" button is a low-cost
  middle ground.
- Should `Claim` survive the matrix schema change in T4, or be
  re-keyed? Recommendation: keep IDs stable, re-key the
  `field_origin` pointer.

---

## 4. Summary

| Question | Answer |
|----------|--------|
| Why does this gap exist? | The app produces raw observations (matrix rows, conflicts, gaps) but never synthesizes them into a "what does the field believe?" view. |
| Why now? | T3, T4, and T11 produce well-grounded raw material that the user still has to assemble. T7 is the synthesis payoff at the top of that stack. |
| What does it change? | Adds `Claim` + `ClaimEvidence` tables, an embedding-based clustering step, an LLM canonicalization step, a confidence score, and a new Claims page. |
| What does it preserve? | Matrix rows, conflicts, gaps, evidence, audit, schema, and methods APIs are unchanged. T7 reads from them and writes only to its own tables. |
| What is the first slice? | Two new tables + backfill from existing conflicts/matrix + one read endpoint + one flat list page + one test. Roughly the size of the T2 audit and T4 first slices. |
| What does it unblock? | T3 evidence reverse-lookup, T4 schema-aware claim extraction, T11 methods formula, T12 quality dashboard, T9 collaboration feedback. |

---

## 5. References

- `docs/feature-opportunity-research.md` — original T7 definition
  and Feature Gap #7 detail.
- `app/db/models.py` — `LiteratureMatrixRow` (lines 435–490),
  `ConflictingFinding` (after `ResearchGap`), `ResearchGap`,
  `GapEvidence` models.
- `app/services/conflict_detection.py` — current pairwise
  contradiction detection with `claim_a` / `claim_b` and
  `possible_explanation` fields.
- `app/services/gap_detection.py` — current gap detection with
  `GapEvidence` rows.
- `app/services/hybrid_retrieval.py` — per-paper chunk retrieval
  used by the evidence drawer in T3.
- `app/ai/prompts.py` —
  `CONTRADICTION_DETECTION_CHUNK_SYSTEM` /
  `CONTRADICTION_DETECTION_CHUNK_USER` (lines 401–480) as the
  starting point for the canonicalization prompt.
- `app/routers/conflicts.py`, `app/routers/gaps.py` — existing
  read endpoints whose shape T7 should mirror.
- External: Consensus, aakashsharan/research-vault, and the
  scientific-literature-intelligence-system for the
  "Claim → Evidence → Context" pattern and the strength /
  direction / confidence scoring ideas (see
  `feature-opportunity-research.md` for URLs).
