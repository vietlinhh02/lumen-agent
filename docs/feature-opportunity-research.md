# Feature Opportunity Research

Date: 2026-06-22

## Purpose

This document summarizes what the current web app already does and what a
similar AI literature-review product still needs to solve before it feels like
a complete research workspace. It is based on the current repository structure,
project docs, and a short benchmark of comparable products.

## Current App Feature Inventory

### Core Research Workflow

The app already implements the main literature-review pipeline:

1. User authentication and profile management.
2. Project creation and project-scoped research workspaces.
3. Paper search across academic sources.
4. Search sessions with pagination, screening, auto-save, and PDF download.
5. Saved-paper management with deduplication.
6. PDF download, full-text ingestion, chunking, section detection, cleanup, and
   embeddings.
7. Literature matrix generation, list, edit, and delete.
8. Knowledge graph generation from project papers and matrix rows.
9. Research-gap generation with evidence validation.
10. Conflict detection across papers.
11. Report generation with citation validation and Markdown export.
12. Dashboard stats and project workflow guidance.
13. Admin user management.
14. Assistant chat surface with sessions, project linking, event history, and
    SSE streaming.

### Current Frontend Surfaces

The Next.js app has pages for:

- Landing page.
- Login and registration.
- Dashboard.
- Project list and project creation.
- Project detail workspace.
- Project-scoped papers, search, matrix, map, gaps, and reports.
- Global saved-papers view.
- Assistant session list and assistant chat sessions.
- Settings and admin user management.

### Current Backend Surfaces

The FastAPI app exposes routers for:

- Health checks.
- Auth.
- Projects.
- Paper search.
- Search sessions.
- Agent workflow runs.
- Matrix generation and editing.
- Gap generation.
- Conflict generation.
- Report generation and export.
- Admin users.
- Knowledge graph.
- Stats.
- Assistant sessions and chat.

### Current Technical Differentiators

- The product is workflow-first, not just chatbot-first.
- Project boundaries are used as citation boundaries.
- Papers are real source records; generated reports cite saved project papers.
- Matrix rows store structured evidence before prose generation.
- Hybrid retrieval carries project-paper IDs into downstream AI features.
- Backend citation validation rejects invalid generated citation IDs.

## Benchmark Findings

### Elicit

Elicit's systematic review workflow is explicitly step-based: gather papers,
define screening criteria, evaluate screening decisions, define extraction
criteria, and extract data. It supports editable AI suggestions, supporting
quotes for extracted answers, CSV export from any step, independent step runs,
living reviews, shareable projects, and real-time team editing.

Source: https://elicit.com/blog/systematic-review

### Consensus

Consensus positions itself around evidence-backed literature review: search,
screen, extract, synthesize, and keep claims tied to source papers. Its Deep
Review breaks a question into sub-questions, runs multiple targeted searches,
reviews a large candidate set, synthesizes a structured review, and exposes
visuals for consensus, key authors, claims, evidence, and gaps. It also supports
advanced filters, uploaded-paper search, export formats, and customizable
citation formats.

Sources:

- https://consensus.app/home/features/literature-review/
- https://help.consensus.app/en/articles/11740827-how-to-use-deep-review

### SciSpace

SciSpace emphasizes an end-to-end research workspace: cited AI answers, chat
with paper PDFs, data extraction from PDFs, table comparison, abstract
inspection, PDF download, and exports to CSV, XLSX, and BibTeX. Its framing is
strong on reading support, paper comparison, and helping users verify claims
against paper content.

Source: https://scispace.com/search

### Litmaps

Litmaps focuses on literature mapping. It starts from seed papers or imported
reference-manager collections, builds citation/reference maps, recommends
related articles, lets users grow maps by adding useful papers, and supports
monitoring alerts for newly published relevant articles.

Sources:

- https://docs.litmaps.com/en/articles/9057179-create-a-litmap
- https://docs.litmaps.com/en/articles/9126249-monitor-get-alerts-for-important-research

## Open-Source GitHub Benchmarks

These repositories are useful implementation references. They should not be
copied directly; use them to understand workflow shape, data models, and UI
patterns before building equivalent features in this app's architecture.

### PHACDataHub/CAN-SR

Repository: https://github.com/PHACDataHub/CAN-SR

CAN-SR is the closest public reference to this app's serious systematic-review
direction. It uses Next.js and FastAPI, then structures the product around
review setup, citation upload, L1 title/abstract screening, L2 full-text
screening, data extraction, human validation, and auditability.

Use it to study:

- Review protocol and inclusion/exclusion criteria setup.
- AI-assisted screening with human approval.
- L1/L2 screening stages.
- Data extraction templates.
- Team-oriented systematic-review workflow.

### NamanBhoj/ForYourResearch

Repository: https://github.com/NamanBhoj/ForYourResearch

ForYourResearch focuses on Semantic Scholar search, title/abstract screening,
full-text screening, manual relevance tagging, saved search libraries, parsed
paper viewing, and screening statistics.

Use it to study:

- Screening UI and manual override flow.
- Relevance tagging.
- Saved search library behavior.
- Screening stats and visual summaries.

### Madhav-000-s/RAG-research-paper-Intelligence-engine

Repository: https://github.com/Madhav-000-s/RAG-research-paper-Intelligence-engine

This repo is useful for the evidence-viewer direction. It implements PDF
ingestion, hybrid retrieval, citation-forced generation, and a split PDF viewer
where clicking a generated citation jumps back to the cited page and section.

Use it to study:

- PDF viewer plus chat/evidence layout.
- Chunk metadata with page and section references.
- Inline citation parsing.
- Retrieval and citation evaluation metrics.

### aakashsharan/research-vault

Repository: https://github.com/aakashsharan/research-vault

Research Vault is relevant for claim-level synthesis. It extracts structured
patterns from papers as Claim, Evidence, and Context, stores them in a hybrid
relational/vector setup, then supports natural-language queries across the
research library.

Use it to study:

- Claim -> Evidence -> Context extraction.
- Review/approval flow for extracted patterns.
- Cross-paper synthesis over structured facts.
- Library-level question answering with citations.

### HuberyLL/SCIOS

Repository: https://github.com/HuberyLL/SCIOS

SCIOS is useful for broader research-landscape UX. It creates topic workspaces
with a tech tree, collaboration network, research gaps, and an interactive
assistant that can search papers and work in a local sandbox.

Use it to study:

- Research landscape visualizations.
- Gap visualization and evidence cards.
- Assistant workspace patterns.
- Task progress UI for long-running research analysis.

### kaneko-ai/jarvis-ml-pipeline

Repository: https://github.com/kaneko-ai/jarvis-ml-pipeline

JARVIS is more CLI/research-OS oriented than this app, but it is valuable for
feature ideas around multi-source search, evidence grading, citation network
analysis, PRISMA diagrams, Zotero sync, BibTeX export, Obsidian export, and
daily digests.

Use it to study:

- PRISMA diagram generation.
- Evidence grading.
- Citation graph and citation stance.
- Zotero/BibTeX/Obsidian export.
- Scheduled paper digest workflows.

## Task Index

This is the working task list for future feature development. The priorities
reflect product impact and how much existing app data each feature can reuse.

### T1: Review Protocol and Screening Criteria

- Priority: P1.
- Outcome: project-level protocol, criteria, and screening reasons.
- References: CAN-SR, Elicit.

### T2: PRISMA-Style Search and Screening Audit

- Priority: P0.
- Outcome: defensible search, screen, include, and exclude flow.
- References: CAN-SR, JARVIS, Consensus.

### T3: Full-Text Evidence Viewer With Quote Anchors

- Priority: P0.
- Outcome: quote, page, and section evidence behind matrix, gaps, and reports.
- References: RAG Research Paper Engine, SciSpace, Elicit.

### T4: Custom Extraction Schema Builder

- Priority: P1.
- Outcome: user-defined matrix extraction fields per project.
- References: CAN-SR, Elicit, Consensus.

### T5: Reference Manager Import and Export

- Priority: P0.
- Outcome: BibTeX, RIS, and CSV import/export for papers and matrix rows.
- References: JARVIS, Litmaps, Consensus, SciSpace.

### T6: Living Review Alerts

- Priority: P2.
- Outcome: saved searches that surface newly published papers.
- References: Litmaps Monitor, Elicit Alerts, JARVIS.

### T7: Claim and Consensus Synthesis

- Priority: P1.
- Outcome: claim-level support, contradiction, and weak-evidence view.
- References: Research Vault, Consensus.

### T8: Paper Reading and Annotation Workspace

- Priority: P2.
- Outcome: tags, notes, highlights, reading status, and decision history.
- References: ForYourResearch, SciSpace, Research Vault.

### T9: Collaboration and Review Handoff

- Priority: P2.
- Outcome: project sharing, roles, assignments, and comments.
- References: CAN-SR, Elicit, Litmaps.

### T10: Multi-Format Report Export

- Priority: P2.
- Outcome: DOCX, PDF, LaTeX, and citation-style controls.
- References: Consensus, SciSpace, JARVIS.

### T11: Methods Section and Reproducibility Package

- Priority: P1.
- Outcome: methods draft and audit package from stored workflow data.
- References: CAN-SR, SciSpace, Consensus.

### T12: Evaluation and Quality Dashboard

- Priority: P0.
- Outcome: coverage, confidence, citation validity, and failed-job status.
- References: RAG Research Paper Engine, CAN-SR, JARVIS.

Recommended build order:

1. T3 Evidence viewer.
2. T2 PRISMA-style audit.
3. T5 Reference import/export.
4. T12 Quality dashboard.
5. T1 Protocol and screening criteria.
6. T4 Custom extraction schema.
7. T11 Methods and reproducibility package.
8. T7 Claim and consensus synthesis.
9. T6 Living review alerts.
10. T8 Paper annotation workspace.
11. T9 Collaboration.
12. T10 Multi-format report export.

## Feature Gaps and Opportunities

### 1. Review Protocol and Screening Criteria

Current state:

- The app can search, screen, and save papers.
- It does not yet make the user's review protocol explicit.

Why it matters:

- Serious literature reviews need clear inclusion/exclusion criteria,
  research questions, search strategy, source list, and screening reasons.
- Without this, the review is harder to defend or reproduce.

Feature proposal:

- Add a project-level review protocol page.
- Store research questions, inclusion criteria, exclusion criteria, population,
  intervention/topic, comparison, outcome, date range, source list, and notes.
- Generate AI-suggested criteria from the project topic, but keep user approval
  required.
- Require exclusion reasons during screening and save them in a controlled list.

First implementation slice:

- Add protocol fields to project metadata.
- Add a "Protocol" tab in the project workspace.
- Add exclusion reason selection to search-session screening.

Reference implementations:

- PHACDataHub/CAN-SR for review setup, inclusion/exclusion criteria, and L1/L2
  screening stages.
- Elicit for AI-suggested screening criteria that remain editable by users.

### 2. PRISMA-Style Search and Screening Audit

Current state:

- Search sessions exist.
- Background jobs and source diagnostics exist.
- There is no researcher-facing audit artifact that explains the review flow.

Why it matters:

- Users need to explain how many papers were found, deduplicated, screened,
  excluded, included, and used in synthesis.

Feature proposal:

- Add a PRISMA-like flow summary per project.
- Track counts by source, query, duplicate removal, title/abstract screening,
  full-text screening, saved papers, matrix rows, and cited papers.
- Export an audit summary as Markdown/CSV.

First implementation slice:

- Create a read-only project audit endpoint from existing search sessions and
  project-paper state.
- Render the flow in the project dashboard.

Reference implementations:

- PHACDataHub/CAN-SR for audit-oriented systematic-review workflow.
- kaneko-ai/jarvis-ml-pipeline for PRISMA diagram/export ideas.
- Consensus Deep Review for explaining searches, selected papers, and gaps in
  a structured report.

### 3. Full-Text Evidence Viewer With Quote Anchors

Current state:

- The backend ingests full text and stores chunks.
- Matrix/gap/report features use evidence internally.
- The UI has paper/full-text views, but extracted claims are not consistently
  anchored back to exact quote context everywhere.

Why it matters:

- Competing products make verification fast by showing supporting quotes inline.
- This app's strongest claim is citation safety; quote-level traceability would
  make that claim visible.

Feature proposal:

- Add evidence drawers for matrix cells, gap claims, conflict claims, and report
  paragraphs.
- Each evidence item should show paper title, section, page if available, quote,
  retrieval reason, and confidence.
- Let users mark evidence as accepted, weak, or wrong.

First implementation slice:

- Extend matrix row responses with top evidence chunks.
- Add a "View evidence" action in the matrix table.

Reference implementations:

- Madhav-000-s/RAG-research-paper-Intelligence-engine for clickable citations
  that jump to PDF page and section.
- SciSpace for claim verification against paper content.
- Elicit for supporting quotes next to extracted answers.

### 4. Custom Extraction Schema Builder

Current state:

- Matrix fields are fixed: problem, method, dataset/context, result,
  limitation, contribution, and relevance.

Why it matters:

- Different domains need different extraction fields: sample size, population,
  intervention, outcome, model, benchmark, effect size, country, data source,
  risk of bias, and so on.

Feature proposal:

- Add per-project extraction columns.
- Support field types: text, number, enum, multi-select, boolean, citation,
  quote, and confidence.
- Generate suggested fields from project protocol.
- Use the schema during extraction and export.

First implementation slice:

- Store project extraction-field definitions as JSON.
- Let users add fields before matrix generation.
- Map existing fixed fields into default columns.

Reference implementations:

- PHACDataHub/CAN-SR for customizable extraction templates.
- Elicit for user-defined extraction fields based on review questions.
- Consensus for structured study snapshots such as methods, outcomes,
  populations, and sample sizes.

### 5. Reference Manager Import and Export

Current state:

- The app can export reports as Markdown.
- Search/report exports exist in limited form.
- There is no visible Zotero/Mendeley/EndNote-style workflow.

Why it matters:

- Researchers often start with existing libraries, not blank projects.
- Export to BibTeX/RIS/CSV is expected for academic workflows.

Feature proposal:

- Import BibTeX, RIS, CSV, and DOI lists into a project.
- Export saved papers, matrix rows, and report references to BibTeX/RIS/CSV.
- Later: Zotero sync or one-click Zotero import/export.

First implementation slice:

- Add BibTeX/RIS export for project papers.
- Add CSV export for matrix rows and gap evidence.

Reference implementations:

- kaneko-ai/jarvis-ml-pipeline for Zotero sync, BibTeX export, and Obsidian
  export ideas.
- Litmaps for reference-manager import and Zotero sync workflow.
- Consensus and SciSpace for CSV/RIS/BibTeX export expectations.

### 6. Living Review Alerts

Current state:

- Search sessions are manual.
- There is no ongoing monitor for new relevant papers.

Why it matters:

- Literature reviews become stale quickly.
- Litmaps and Elicit use alerts/monitoring as a major retention feature.

Feature proposal:

- Let users turn a project search strategy into a weekly/monthly monitor.
- Store alert runs and new candidate papers.
- Show "new since last review" candidates in the project workspace.

First implementation slice:

- Add saved search queries to projects.
- Add a manual "Run monitor now" action before scheduled jobs.

Reference implementations:

- Litmaps Monitor for search-based paper alerts.
- Elicit Alerts for living-review positioning.
- kaneko-ai/jarvis-ml-pipeline for scheduled daily digest mechanics.

### 7. Claim and Consensus Synthesis

Current state:

- The app detects gaps and conflicts.
- It does not expose a claim-level consensus table.

Why it matters:

- Users need to know what the field agrees on, disagrees on, and where evidence
  is weak before writing.

Feature proposal:

- Extract claims from matrix rows and full-text chunks.
- Cluster similar claims.
- Show support, contradict, and mixed evidence groups.
- Add confidence based on number of papers, quality of evidence, and recency.

First implementation slice:

- Build a project "Claims" page from existing matrix and conflict services.
- Start with generated claim clusters and evidence paper IDs.

Reference implementations:

- aakashsharan/research-vault for Claim -> Evidence -> Context extraction.
- Consensus for claims/evidence and consensus/counterpoint presentation.
- SaiVenkataGaneshBandaluppi/scientific-literature-intelligence-system for
  claim strength, direction, confidence, and conflict-detection ideas.

### 8. Paper Reading and Annotation Workspace

Current state:

- Papers can be saved and full text can be viewed.
- There is no full researcher reading workflow: highlights, notes, tags, or
  decision history.

Why it matters:

- Researchers need to read, annotate, and remember why a paper was included.

Feature proposal:

- Add paper notes, tags, manual highlights, reading status, and decision log.
- Connect notes to matrix fields and report paragraphs.
- Support "send note to matrix" and "use highlight as evidence".

First implementation slice:

- Add paper-level tags, reading status, and private notes.
- Surface them in project paper list and project detail.

Reference implementations:

- NamanBhoj/ForYourResearch for parsed paper viewer and manual relevance
  tagging.
- SciSpace for PDF reading and paper Q&A patterns.
- Research Vault for review/approval of extracted paper patterns.

### 9. Collaboration and Review Handoff

Current state:

- Admin user management exists.
- Projects appear user-owned rather than collaborative.

Why it matters:

- Systematic reviews are often team work, especially screening and extraction.

Feature proposal:

- Add project collaborators with roles: owner, editor, reviewer, viewer.
- Add assignment for screening/extraction tasks.
- Add comments on papers, matrix rows, gaps, and report sections.

First implementation slice:

- Add project sharing with viewer/editor roles.
- Add comments only on matrix rows first.

Reference implementations:

- PHACDataHub/CAN-SR for team systematic-review workflow.
- Elicit Team/Enterprise for shared review projects and real-time editing
  expectations.
- ResearchRabbit/Litmaps for collection sharing and collaborative discovery
  behavior.

### 10. Multi-Format Report Export

Current state:

- Markdown export exists.

Why it matters:

- Researchers commonly need DOCX, PDF, LaTeX, BibTeX, RIS, CSV, and sometimes
  journal-style citation formats.

Feature proposal:

- Export report to DOCX and PDF.
- Export references to BibTeX/RIS.
- Support citation styles: APA, MLA, Chicago, Harvard, IEEE/numeric, and LaTeX.

First implementation slice:

- Add BibTeX/RIS reference export.
- Add DOCX export from existing Markdown report.

Reference implementations:

- Consensus Deep Review for export formats and citation-style controls.
- SciSpace for CSV, XLSX, and BibTeX export expectations.
- kaneko-ai/jarvis-ml-pipeline for BibTeX and Obsidian export ideas.

### 11. Methods Section and Reproducibility Package

Current state:

- The app stores enough data to explain parts of the workflow.
- It does not generate a reproducible methods artifact.

Why it matters:

- Academic users need to describe sources, queries, dates, filters, screening
  criteria, extraction criteria, model settings, and validation rules.

Feature proposal:

- Generate a project methods section from stored protocol, search sessions,
  source diagnostics, screening decisions, extraction schema, and report
  validation status.
- Export an audit package with CSV tables and a Markdown methods appendix.

First implementation slice:

- Add a "Methods draft" panel under Reports.
- Build it from existing stored search sessions and project metadata.

Reference implementations:

- PHACDataHub/CAN-SR for auditability and reproducibility framing.
- SciSpace systematic-review agent references for PRISMA/PRISMA-S style
  methods artifacts.
- Consensus Deep Review for generated methods/results/discussion structure.

### 12. Evaluation and Quality Dashboard

Current state:

- Tests exist for core backend services.
- Docs mention RAG/evaluation, but there is no user-facing quality dashboard.

Why it matters:

- AI research products need visible quality signals: missing PDFs, extraction
  confidence, weak citations, unsupported claims, stale alerts, and failed jobs.

Feature proposal:

- Add a project quality dashboard.
- Track evidence coverage, full-text coverage, matrix completeness, citation
  validity, failed jobs, low-confidence rows, and unverified claims.

First implementation slice:

- Add quality cards on project detail from existing counts and validation
  statuses.

Reference implementations:

- Madhav-000-s/RAG-research-paper-Intelligence-engine for retrieval recall,
  citation precision, and citation recall evaluation.
- PHACDataHub/CAN-SR for human validation and quality assurance workflow.
- kaneko-ai/jarvis-ml-pipeline for evidence grading and paper scoring.

## Recommended Priority

### P0: Make Current Strengths Visible

1. Full-text evidence viewer with quote anchors.
2. PRISMA-style audit summary.
3. BibTeX/RIS/CSV export for project papers and matrix rows.
4. Project quality dashboard.

These reuse data the app already has and improve trust quickly.

### P1: Make the Workflow More Defensible

1. Review protocol and screening criteria.
2. Custom extraction schema builder.
3. Methods section and reproducibility package.
4. Claim and consensus synthesis.

These make the app closer to a serious literature-review system instead of a
demo pipeline.

### P2: Make It Sticky for Real Researchers

1. Living review alerts.
2. Paper reading and annotation workspace.
3. Collaboration and project sharing.
4. DOCX/PDF/LaTeX export and citation-style controls.

These are larger product features and should come after the evidence/audit
foundation is clear.

## Suggested Next Build Plan

If the goal is to add useful new features without over-expanding scope, start
with one vertical slice:

1. Add project audit endpoint.
2. Render a PRISMA-style project audit panel.
3. Add CSV export for the audit counts and screened paper decisions.
4. Add one test for audit counts using existing search-session/project-paper
   fixtures.

This is small enough to implement safely and directly supports the core product
promise: a literature review that can be defended, not just generated.
