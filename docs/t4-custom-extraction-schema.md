# T4: Custom Extraction Schema Builder

> Feature gap analysis and integration plan for the Custom Extraction Schema
> Builder (T4 in `docs/feature-opportunity-research.md`).

Date: 2026-06-24
Status: **Implemented** — backend models, REST endpoints, AI extraction, and frontend UI are in place
Owner: TBD
Priority: P1
Build order: #6 (after T1 Review Protocol & Screening Criteria)

---

## 1. Why this feature gap exists

### 1.1 The problem with a fixed extraction schema

Literature reviews look different in every domain. The current matrix schema
hard-codes seven fields:

| Field | What it captures |
|-------|------------------|
| `research_problem` | What problem the paper attacks |
| `method` | How the paper attacks it |
| `dataset_or_context` | What data / setting it uses |
| `key_result` | What it found |
| `limitation` | What it admits it cannot do |
| `contribution` | What it adds to the field |
| `relevance` | Why it matters to the review |

This is a reasonable default for **general computer-science / engineering**
reviews, but it forces every other domain to either:

1. **Stuff domain-specific facts into the wrong column.** A clinical
   systematic review ends up writing `"sample size: 124, population:
   adults with type-2 diabetes"` into the free-text `method` field, which
   then cannot be filtered, sorted, or aggregated.
2. **Leave the field blank.** A ML benchmark review cannot record
   `model`, `benchmark`, or `metric` because the matrix has no slot for
   them, so the only place to record them is the paper's free-text notes.
3. **Maintain the extraction in a separate spreadsheet.** Once a reviewer
   needs fields that are filterable, they export the matrix to CSV and
   add columns in Excel. The platform's value drops because the
   authoritative copy of the data lives outside the system.

This is a real loss of product surface. A literature-review workspace is
valuable precisely because it can **query, filter, and aggregate across
papers** — capabilities that collapse when every domain is forced to use
the same seven free-text fields.

### 1.2 What competing products do

| Product | Approach |
|---------|----------|
| **Elicit** | Per-review extraction columns. The reviewer defines the fields ("Sample size", "Population", "Outcome") and Elicit fills them. AI suggestions are editable, and every cell shows the supporting quote. |
| **Consensus** | Structured study snapshots. Each paper is summarized into a fixed set of method/outcome/population/sample-size cards, and these cards become filterable columns. |
| **PHACDataHub/CAN-SR** | Customizable extraction templates. The team defines a JSON template of fields and field types (text / number / enum / boolean), and the screening/extraction workflow uses it. |
| **JARVIS** | CLI/research-OS style: extraction schemas are versioned YAML files, exported to CSV/JSON for downstream analysis. |

The pattern is clear: **schema is a per-review (or per-project) artifact,
not a global constant.** That is what the current app is missing.

### 1.3 Why it is a gap, not just a nice-to-have

The app's strongest pitch is that it is "more than a chatbot" — it is a
defensible research workspace. Defensible reviews need:

- **Filterable evidence** — "show me all RCTs with sample size > 100".
- **Aggregable results** — "what % of included papers use a transformer
  backbone?".
- **Auditable extraction** — the reviewer must be able to show *which
  field, with which definition, was filled with what evidence*.

None of these are possible today. The seven free-text columns are
human-readable but not machine-queryable in any meaningful way.

### 1.4 What "gap" specifically means in the current code

The current implementation hard-wires the schema in three places:

1. **DB model** (`app/db/models.py`):

   ```python
   class LiteratureMatrixRow(Base):
       research_problem: Mapped[str | None] = mapped_column(Text, nullable=True)
       method: Mapped[str | None] = mapped_column(Text, nullable=True)
       dataset_or_context: Mapped[str | None] = mapped_column(Text, nullable=True)
       key_result: Mapped[str | None] = mapped_column(Text, nullable=True)
       limitation: Mapped[str | None] = mapped_column(Text, nullable=True)
       contribution: Mapped[str | None] = mapped_column(Text, nullable=True)
       relevance: Mapped[str | None] = mapped_column(Text, nullable=True)
   ```

2. **Pydantic schemas** (`app/schemas/matrix.py`):
   `MatrixRowResponse`, `MatrixRowUpdate` both enumerate the same seven
   fields by name.

3. **AI extraction** (`app/agents/nodes.py`):
   `_normalize_matrix_extraction()` and the `MatrixRowOutput` structured
   output both expect the same seven fields, and the verification prompt
   re-asserts them.

Changing the schema today means a **database migration + a code change +
a prompt rewrite**, all coupled. There is no user-facing knob.

---

## 2. How it applies to the current project

### 2.1 What the project already gives us

The good news is that the current architecture is closer to T4 than it
looks. Most of the supporting pieces are already in place:

- **Project-scoped data model.** Matrix rows are scoped to a project
  (`project_id` foreign key), so a per-project schema fits naturally.
- **Background jobs** (`BackgroundJob` table) already handle
  asynchronous matrix generation with progress reporting — a custom
  schema can plug into the same job system.
- **Citation validation** and **hybrid retrieval** are project-scoped,
  so custom-field extraction can reuse the same chunk evidence as the
  fixed fields.
- **AI provider abstraction** (`app/ai/provider.py`) already supports
  `complete_structured()` with a JSON schema — we can pass a
  project-specific schema per call.
- **`MatrixRowUpdate`** is already a partial-update Pydantic model, so
  custom fields can be added without breaking existing callers.
- **T2 PRISMA-style audit** (just shipped) gives us a place to surface
  "this project uses a custom extraction schema with 12 fields" as an
  audit line item.

### 2.2 What needs to change

In order of risk:

1. **Data layer.** Replace the seven hard-coded columns with either:
   - **Option A: JSONB column.** Add `custom_fields: JSONB` to
     `LiteratureMatrixRow` and treat the seven fixed fields as
     convention-only defaults. Schema lives in a new
     `ProjectExtractionSchema` table.
   - **Option B: EAV table.** Add `MatrixCell(row_id, field_key, value,
     field_type)` so the database itself is type-aware per field.
   - **Option C: Hybrid.** Keep the seven fixed columns for backwards
     compatibility, add `custom_fields: JSONB` for project-specific
     extras, and add `ProjectExtractionSchema` for the schema definition.

   Recommendation: **Option C** for the first slice. It preserves
   backwards compatibility, lets existing matrix data keep working, and
   gives us a path to migrate fully to JSONB in a later phase without a
   breaking change.

2. **Schema definition API.** New endpoints:
   - `GET /projects/{id}/extraction-schema` — return the project's
     effective schema (project override merged over system defaults).
   - `PUT /projects/{id}/extraction-schema` — replace the project's
     schema. Body: `{fields: [{key, label, type, description, required,
     enum_values?}, ...]}`.
   - `POST /projects/{id}/extraction-schema:suggest` — ask the LLM to
     suggest fields from the project topic + protocol + sample papers.

3. **AI extraction prompt.** Today the extraction prompt hard-codes
   the seven fields. Change it to:
   - Read the project's effective schema.
   - Pass the schema as a JSON-schema constraint to
     `complete_structured()`.
   - Validate that the LLM's output covers every required field before
     persisting.

4. **Frontend.**
   - **Project settings → "Extraction fields"** page: add/remove/reorder
     custom fields, set type, mark required, add description, define
     enum values.
   - **Matrix table** renders columns from the schema. The seven fixed
     fields become a "default set" that can be hidden, reordered, or
     extended.
   - **Field-type-aware cell editor:** text → textarea; number → numeric
     input; enum → dropdown; multi-select → chip input; boolean →
     toggle; quote → textarea with paper-evidence link.

5. **Filtering / aggregation.** New endpoints:
   - `GET /projects/{id}/matrix:filter?fields=model&op=eq&value=transformer`
   - `GET /projects/{id}/matrix:aggregate?field=benchmark&group_by=venue`
   - These reuse the `audit.py` count-style pattern.

6. **Migration path.**
   - Existing rows keep their seven fixed columns. They are read
     through a backwards-compat shim that maps the fixed columns into
     the schema-default field set.
   - New projects start with the system default schema unless the
     reviewer customizes it.
   - Switching schema in an existing project: keep the seven fixed
     columns, add the new fields as JSONB; offer a "migrate values"
     action if the user defines a field with the same `key` as a
     default.

### 2.3 What it does NOT change

- The matrix row's identity (`LiteratureMatrixRow.id`), `project_paper_id`
  link, `extraction_confidence`, `content_hash`, and `created_by` are
  unchanged.
- The background job system that fans out extraction is unchanged.
- The audit endpoint, gap detection, conflict detection, and report
  generation are unchanged at the API level. Internally they should
  switch from reading named columns to reading the schema-resolved
  fields, but the public contract is the same.
- The seven fixed fields stay as **system-default schema entries** with
  reserved keys. They cannot be deleted, only hidden.

### 2.4 Risks specific to this project

| Risk | Mitigation |
|------|------------|
| LLM ignores the schema and returns only the seven default fields | Add a JSON-schema validator step before persisting; if validation fails, retry with a stricter prompt. |
| Reviewer renames a field and loses existing values | Make `key` immutable after creation. Allow `label` and `description` edits. |
| Conflicting field types across re-runs | Store `field_type` with the value, validate on read, refuse to coerce silently. |
| Performance hit on JSONB reads at scale | Add a GIN index on `custom_fields`; the seven fixed columns stay as btree-indexed for sort/filter speed. |
| Backwards-compat with T2 audit | Audit counts stay correct because they read by `project_id`, not by field key. |
| Frontend re-render cost | The matrix is already server-paginated in many flows; keep the column set small (≤ 15 visible) and add a "column chooser" overflow. |

---

## 3. Integration direction

### 3.1 Goals

1. Let any reviewer define a project-specific extraction schema with
   typed fields.
2. Keep the seven default fields as a stable, immovable baseline.
3. Make custom-field extraction **as reliable as default-field
   extraction** — same confidence reporting, same evidence chain, same
   retry/verification flow.
4. Open the door to filter, sort, aggregate, and export by any field,
   not just the seven defaults.
5. Do all of the above without breaking the shipped T2 audit, the
   matrix CRUD endpoints, or the existing background-job pipeline.

### 3.2 Non-goals (explicitly out of scope for the first slice)

- Multi-version schema history with diff/restore.
- Per-user custom schemas inside a shared project.
- Cross-project schema libraries / templates marketplace.
- Conditional fields (field B is required only if field A is "yes").
- Cross-field validation rules (field B must be > field A).

These can come in later slices once the basic per-project schema works.

### 3.3 Build phases

**Phase 1 — Foundation (no UI, behind a flag).**
- Add `ProjectExtractionSchema` table and `LiteratureMatrixRow.custom_fields JSONB`.
- Add `GET/PUT /projects/{id}/extraction-schema` endpoints.
- Make `MatrixRowResponse` resolve fields through the effective schema
  (defaults + project overrides), so the existing API keeps working
  with the same JSON shape.
- AI extraction prompt: pass the project schema to `complete_structured()`.
- Migration script to backfill the default schema for existing
  projects.

**Phase 2 — UI for schema editor.**
- New "Extraction fields" page in project settings.
- Add / remove / reorder fields, set type, mark required, define enum
  values.
- "Suggest fields" action that asks the LLM for field suggestions
  based on project topic + protocol + first 5 saved-paper abstracts.
- Matrix table renders columns from the schema; column chooser allows
  hiding/reordering.

**Phase 3 — Typed cells and filter/aggregate.**
- Field-type-aware cell editor in the matrix table.
- `GET /matrix:filter` and `GET /matrix:aggregate` endpoints.
- Update the export pipeline (Markdown / CSV / future BibTeX/RIS) to
  emit one column per schema field.

**Phase 4 — Verification and audit integration.**
- Re-run verifier prompt against project schema, not hard-coded fields.
- Surface custom-field coverage in the T2 audit panel ("12 fields
  defined, 9 fully populated, 3 partially populated").
- Add a "schema drift" warning if a project's schema has been edited
  since the last matrix run.

### 3.4 First implementation slice (what we would build first)

The smallest slice that is safe, useful, and ships value:

1. Add `ProjectExtractionSchema` table.
2. Add `LiteratureMatrixRow.custom_fields JSONB` column (nullable,
   default `'{}'`).
3. Add `GET/PUT /projects/{id}/extraction-schema` with a fixed field-type
   vocabulary: `text`, `number`, `enum`, `multi_select`, `boolean`,
   `quote`, `citation`.
4. Make `MatrixRowResponse` resolve fields through the effective schema
   so the existing GET endpoint returns the same JSON shape.
5. Update the AI extraction prompt to include the project's schema and
   pass it to `complete_structured()`.
6. Add one test: create a project with a 3-field custom schema, run
   matrix extraction, assert the resulting row's `custom_fields`
   contains all 3 keys with the right types.

That is roughly the same size as the T2 audit slice (one table + one
endpoint + one prompt change + one test), and it directly enables the
T3 evidence viewer (which will use the schema to know which fields
deserve a "view evidence" drawer).

### 3.5 How this unblocks later work

- **T3 Evidence viewer** can use the schema to know which fields
  deserve an evidence drawer and which evidence chunks map to which
  field.
- **T5 Reference export** can emit one column per schema field for
  CSV/BibTeX/RIS export.
- **T11 Methods & reproducibility** can list the project's schema as
  part of the methods artifact, so the reader knows what was extracted
  and how.
- **T12 Quality dashboard** can show "field coverage" — how many of
  the schema's required fields are populated per row.
- **T1 Review protocol** can pre-populate the schema editor with
  PICO-style fields (Population / Intervention / Comparison /
  Outcome) when the user enables a "clinical review" template.

### 3.6 Open questions for the team

- Should `key` be immutable, or should we allow rename with a
  best-effort value migration?
- Should enum fields be `text` with a `enum_values` list, or should
  they be a first-class type?
- Should we ship a small library of pre-built schemas (clinical
  PICO, ML benchmark, social-science survey) or start blank?
- Should the schema be defined at the project level or at the
  extraction-job level (so a project can run with multiple schemas over
  time)?

---

## 4. Summary

| Question | Answer |
|----------|--------|
| Why does this gap exist? | The matrix hard-codes 7 free-text fields. Different domains need different fields, and the current schema cannot capture them in a queryable way. |
| Why now? | T2 audit just shipped. T3 evidence viewer is next. T4 is the natural foundation for typed, filterable, aggregable evidence — without it, T3 is a UI band-aid. |
| What does it change? | Adds `ProjectExtractionSchema` table + JSONB `custom_fields` column. AI extraction accepts project-specific JSON schema. UI gets a schema editor. |
| What does it preserve? | The 7 default fields stay. The matrix row identity stays. The background-job pipeline stays. The audit endpoint stays. |
| What is the first slice? | New schema table + JSONB column + 2 endpoints + prompt change + 1 test. Roughly the size of the T2 audit slice. |
| What does it unblock? | T3 evidence viewer, T5 export, T11 methods artifact, T12 quality dashboard, T1 protocol templates. |

---

## 5. References

- `docs/feature-opportunity-research.md` — original T4 definition and
  Feature Gap #4 detail.
- `app/db/models.py` — current `LiteratureMatrixRow` model (lines
  435–490).
- `app/schemas/matrix.py` — current `MatrixRowResponse` /
  `MatrixRowUpdate` / `MatrixRowOutput` shape.
- `app/agents/nodes.py` — current `_normalize_matrix_extraction` and
  `matrix_extraction_node` (lines 490–800).
- `app/routers/matrix.py` — current matrix CRUD + generation endpoints.
- External: Elicit, Consensus, PHACDataHub/CAN-SR, JARVIS extraction
  schema designs (see `feature-opportunity-research.md` for URLs).
