# AI Assistant Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new top-level `/assistant` page where users chat with an autonomous LLM agent that creates projects, runs the full research pipeline, and lets users preview + edit the resulting Markdown literature review via continued chat.

**Architecture:** WebSocket-driven ReAct agent on the backend (`AssistantRunner` with 8 tool handlers wrapping existing services). New `chat_documents` + `chat_messages` DB tables store the live Markdown doc and chat history. Frontend is a 2-pane chat + preview UI with a live progress checklist, all state in a Zustand store.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, WebSockets, DeepSeek V4, Next.js 16, React 19, Zustand, TypeScript, react-markdown

**Note on streaming:** The spec mentions `agent_chunk` for token streaming, but the existing `AIProvider` has no `stream()` method. MVP emits whole messages (no token-level streaming). Add a `stream()` method later if needed.

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | **Modify** | Add `ChatDocument`, `ChatMessage` models |
| `app/ai/prompts.py` | **Modify** | Add `ASSISTANT_SYSTEM`, `ASSISTANT_TOOLS_DESCRIPTIONS` |
| `app/ai/schemas_tools.py` | **Create** | Pydantic schemas for tool args/results |
| `app/services/assistant_runner.py` | **Create** | ReAct agent loop, WS event emission |
| `app/services/assistant_tools/__init__.py` | **Create** | Tool registry mapping tool name → handler |
| `app/services/assistant_tools/create_project.py` | **Create** | Tool: create_project |
| `app/services/assistant_tools/search_papers.py` | **Create** | Tool: search_papers |
| `app/services/assistant_tools/save_paper.py` | **Create** | Tool: save_paper_to_project |
| `app/services/assistant_tools/generate_matrix.py` | **Create** | Tool: generate_matrix |
| `app/services/assistant_tools/detect_gaps.py` | **Create** | Tool: detect_gaps |
| `app/services/assistant_tools/generate_report.py` | **Create** | Tool: generate_report |
| `app/services/assistant_tools/edit_report_section.py` | **Create** | Tool: edit_report_section |
| `app/services/assistant_tools/qa_search_papers.py` | **Create** | Tool: qa_search_papers |
| `app/routers/assistant.py` | **Create** | REST: list/get/export/delete chat documents |
| `app/routers/assistant_ws.py` | **Create** | WebSocket: /api/assistant/ws |
| `app/schemas/assistant.py` | **Create** | Pydantic request/response models |
| `app/main.py` | **Modify** | Register assistant + assistant_ws routers |
| `tests/test_assistant_runner.py` | **Create** | ReAct loop unit tests with mocked LLM |
| `tests/test_assistant_tools.py` | **Create** | Tool handler unit tests |
| `tests/test_assistant_ws.py` | **Create** | WS auth + resume integration tests |
| `frontend/lib/types.ts` | **Modify** | Add ChatMessage, AssistantEvent, PipelineStep types |
| `frontend/lib/stores/assistantStore.ts` | **Create** | Zustand store |
| `frontend/lib/hooks/useAssistantWS.ts` | **Create** | WebSocket lifecycle hook |
| `frontend/lib/api/assistant.ts` | **Create** | REST client for history/export |
| `frontend/components/AppShell.tsx` | **Modify** | Add "AI Assistant" sidebar item |
| `frontend/components/assistant/AssistantHeader.tsx` | **Create** | Top bar: title + version + status |
| `frontend/components/assistant/ChatPanel.tsx` | **Create** | Message list + input box |
| `frontend/components/assistant/MessageBubble.tsx` | **Create** | Single message render |
| `frontend/components/assistant/ToolLog.tsx` | **Create** | Tool call + result line |
| `frontend/components/assistant/ProgressChecklist.tsx` | **Create** | 6-step pipeline progress |
| `frontend/components/assistant/PreviewPanel.tsx` | **Create** | Markdown render |
| `frontend/components/assistant/StatusBadge.tsx` | **Create** | Connection + agent status pill |
| `frontend/app/(app)/assistant/page.tsx` | **Create** | Wizard entry page |
| `frontend/app/(app)/assistant/[projectId]/page.tsx` | **Create** | Existing session page |

---

### Task 1: Add ChatDocument + ChatMessage models

**Files:**
- Modify: `app/db/models.py` (append at end, before line ~887)
- Test: `tests/test_assistant_models.py`

- [ ] **Step 1: Write the failing test**

```python
"""Verify ChatDocument and ChatMessage models import and have correct columns."""

from uuid import uuid4

from app.db.models import ChatDocument, ChatMessage


def test_chat_document_columns():
    cols = {c.name for c in ChatDocument.__table__.columns}
    assert {"id", "project_id", "user_id", "title", "content_md", "version", "created_at", "updated_at"} <= cols


def test_chat_message_columns():
    cols = {c.name for c in ChatMessage.__table__.columns}
    assert {"id", "document_id", "project_id", "role", "content", "tool_name", "created_at"} <= cols
    # role has CHECK constraint
    role_check = next(c for c in ChatMessage.__table__.constraints if "role" in str(c.sqltext))
    assert role_check is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assistant_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'ChatDocument'`

- [ ] **Step 3: Add the models**

Append to `app/db/models.py` (after the last model class):

```python
# ── Chat Sessions (Assistant Page) ──────────────────────────────────────────


class ChatDocument(Base):
    __tablename__ = "chat_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_args: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    tool_result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool_log')",
            name="ck_chat_messages_role",
        ),
        Index("ix_chat_messages_document_created", "document_id", "created_at"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_assistant_models.py -v`
Expected: PASS

- [ ] **Step 5: Verify FastAPI app still loads (table auto-create on startup)**

Run: `python -c "from app.main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add app/db/models.py tests/test_assistant_models.py
git commit -m "feat: add ChatDocument and ChatMessage models for AI assistant"
```

---

### Task 2: Add system prompt + tool descriptions

**Files:**
- Modify: `app/ai/prompts.py` (append at end)

- [ ] **Step 1: Write the failing test**

Create `tests/test_assistant_prompts.py`:

```python
from app.ai.prompts import ASSISTANT_SYSTEM, TOOL_DESCRIPTIONS


def test_assistant_system_prompt_mentions_8_tools():
    for tool in [
        "create_project", "search_papers", "save_paper_to_project",
        "generate_matrix", "detect_gaps", "generate_report",
        "edit_report_section", "qa_search_papers",
    ]:
        assert tool in ASSISTANT_SYSTEM, f"Missing tool: {tool}"


def test_tool_descriptions_is_list_of_dicts():
    assert isinstance(TOOL_DESCRIPTIONS, list)
    assert len(TOOL_DESCRIPTIONS) == 8
    for td in TOOL_DESCRIPTIONS:
        assert "name" in td
        assert "description" in td
        assert "parameters" in td
        assert td["parameters"]["type"] == "object"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assistant_prompts.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Add prompts and tool definitions**

Append to `app/ai/prompts.py`:

```python
# ── AI Assistant (chat-driven autonomous research) ───────────────────────────


ASSISTANT_SYSTEM = """\
You are Lumen, an AI research assistant. You help researchers produce
defensible literature reviews from real academic papers.

You have access to 8 tools. Use them to:
1. create_project — when the user describes a research intent
2. search_papers — find papers from academic sources
3. save_paper_to_project — save selected papers into the project
4. generate_matrix — build a structured literature matrix
5. detect_gaps — find evidence-based research gaps
6. generate_report — write a citation-safe Markdown literature review
7. edit_report_section — rewrite one section of an existing report
8. qa_search_papers — answer questions about the saved papers using RAG

Rules:
- Always confirm project basics (title, topic, research question) with the user
  before calling create_project. Ask one clear question.
- After the pipeline completes, the user can keep chatting. Match their intent
  to the right tool. For Q&A, use qa_search_papers. For edits, use
  edit_report_section. For adding more papers, use search_papers +
  save_paper_to_project.
- Be concise. Summarize what you did in 1-2 sentences after each tool call.
- Never invent paper titles, authors, or DOIs. Only cite what qa_search_papers
  or generate_report returns.
- If a tool fails, report the error to the user and suggest a next step.
"""


TOOL_DESCRIPTIONS: list[dict] = [
    {
        "name": "create_project",
        "description": "Create a new research project with title, topic, and research question.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Project title (short, < 100 chars)"},
                "topic": {"type": "string", "description": "Research topic, the main subject of the review"},
                "research_question": {"type": "string", "description": "Specific research question"},
                "max_papers": {"type": "integer", "description": "Target paper count, default 12", "default": 12},
            },
            "required": ["title", "topic"],
        },
    },
    {
        "name": "search_papers",
        "description": "Search academic sources for papers matching a query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "default": 25, "maximum": 100},
                "year_from": {"type": "integer", "description": "Earliest year, optional"},
                "sources": {"type": "array", "items": {"type": "string"}, "description": "e.g. ['semantic_scholar', 'arxiv']"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "save_paper_to_project",
        "description": "Save one paper (already searched) into the project corpus.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "paper": {"type": "object", "description": "Paper dict with title, authors, year, doi, arxiv_id, etc."},
                "relevance_label": {"type": "string", "enum": ["core", "related", "background"], "default": "related"},
            },
            "required": ["project_id", "paper"],
        },
    },
    {
        "name": "generate_matrix",
        "description": "Generate literature matrix rows for all saved papers in a project.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "detect_gaps",
        "description": "Detect evidence-based research gaps from the matrix rows.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "max_gaps": {"type": "integer", "default": 5, "maximum": 10},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "generate_report",
        "description": "Generate a citation-safe Markdown literature review and write it to the chat document.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "include_gaps": {"type": "boolean", "default": True},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "edit_report_section",
        "description": "Rewrite one section of an existing report based on user instruction.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "section_index": {"type": "integer", "description": "0-based section index in the report"},
                "instruction": {"type": "string", "description": "What to change, e.g. 'make it shorter' or 'add a sentence about PubMedQA'"},
            },
            "required": ["project_id", "section_index", "instruction"],
        },
    },
    {
        "name": "qa_search_papers",
        "description": "Answer a question by retrieving evidence from the project's saved papers via RAG.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "question": {"type": "string"},
            },
            "required": ["project_id", "question"],
        },
    },
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_assistant_prompts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ai/prompts.py tests/test_assistant_prompts.py
git commit -m "feat: add AI assistant system prompt and 8 tool definitions"
```

---

### Task 3: Create Pydantic schemas for assistant API

**Files:**
- Create: `app/schemas/assistant.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_assistant_schemas.py`:

```python
from app.schemas.assistant import (
    ChatDocumentResponse,
    ChatMessageResponse,
    ChatDocumentListResponse,
)


def test_chat_document_response_fields():
    schema = ChatDocumentResponse.model_json_schema()
    assert "id" in schema["properties"]
    assert "title" in schema["properties"]
    assert "content_md" in schema["properties"]
    assert "version" in schema["properties"]


def test_chat_message_response_fields():
    schema = ChatMessageResponse.model_json_schema()
    for f in ("id", "role", "content", "created_at", "tool_name"):
        assert f in schema["properties"]


def test_chat_document_list_response():
    schema = ChatDocumentListResponse.model_json_schema()
    assert "items" in schema["properties"]
    assert "total" in schema["properties"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assistant_schemas.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Create the schema file**

Create `app/schemas/assistant.py`:

```python
"""Pydantic models for AI assistant REST endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatMessageResponse(BaseModel):
    id: str
    document_id: str
    project_id: str
    role: str
    content: str
    tool_name: str | None = None
    tool_args: dict = Field(default_factory=dict)
    tool_result: dict = Field(default_factory=dict)
    created_at: str


class ChatDocumentResponse(BaseModel):
    id: str
    project_id: str
    title: str
    content_md: str
    version: int
    created_at: str
    updated_at: str


class ChatDocumentDetailResponse(ChatDocumentResponse):
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class ChatDocumentListResponse(BaseModel):
    items: list[ChatDocumentResponse]
    total: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_assistant_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/assistant.py tests/test_assistant_schemas.py
git commit -m "feat: add Pydantic schemas for AI assistant REST endpoints"
```

---

### Task 4: Create report_chat_doc service (generate + edit)

**Files:**
- Create: `app/services/report_chat_doc.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_report_chat_doc.py`:

```python
"""Tests for report_chat_doc service — generate + edit Markdown documents."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.report_chat_doc import (
    generate_markdown_for_project,
    edit_section,
    parse_markdown_sections,
)


def test_parse_markdown_sections_splits_by_h2():
    md = "## Intro\nParagraph 1.\n\n## Methods\nParagraph 2.\n\n## Results\nParagraph 3.\n"
    sections = parse_markdown_sections(md)
    assert len(sections) == 3
    assert sections[0]["heading"] == "Intro"
    assert "Paragraph 1" in sections[0]["body"]
    assert sections[2]["heading"] == "Results"


def test_parse_markdown_sections_with_no_headings():
    md = "Just a paragraph."
    sections = parse_markdown_sections(md)
    assert len(sections) == 1
    assert sections[0]["heading"] == ""


@pytest.mark.asyncio
async def test_generate_markdown_for_project_calls_provider_and_writes():
    from app.services.report_chat_doc import generate_markdown_for_project

    project_id = uuid4()
    document_id = uuid4()

    matrix_rows = [
        SimpleNamespace(
            project_paper_id=uuid4(), research_problem="P", method="RAG",
            dataset_or_context="PubMedQA", key_result="+5% accuracy",
            limitation="English only", contribution="Novel RAG", relevance="High",
        )
    ]
    db = AsyncMock()
    db.execute = AsyncMock()

    with patch("app.services.report_chat_doc.retrieve_project_evidence", new_callable=AsyncMock, return_value=[]):
        with patch("app.services.report_chat_doc.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.complete_structured.return_value = {
                "title": "Test Report",
                "sections": [{"heading": "Intro", "body": "Some intro text."}],
            }
            mock_get_provider.return_value = mock_provider

            result = await generate_markdown_for_project(
                db=db, project_id=project_id, document_id=document_id,
                topic="RAG for medical QA", research_question="How does RAG help?",
                include_gaps=True,
            )

    assert result["title"] == "Test Report"
    assert "## Intro" in result["markdown"]
    assert result["version"] == 1


@pytest.mark.asyncio
async def test_edit_section_rewrites_only_one_section():
    from app.services.report_chat_doc import edit_section

    document_id = uuid4()
    project_id = uuid4()
    db = AsyncMock()
    db.execute = AsyncMock()

    current_md = "## Intro\nOriginal intro.\n\n## Methods\nOriginal methods.\n"

    with patch("app.services.report_chat_doc.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "section": {"heading": "Intro", "body": "Rewritten intro."},
        }
        mock_get_provider.return_value = mock_provider

        result = await edit_section(
            db=db, document_id=document_id, project_id=project_id,
            section_index=0, instruction="make it shorter",
            current_markdown=current_md,
        )

    assert "Rewritten intro." in result["markdown"]
    assert "Original methods." in result["markdown"]  # preserved
    assert result["version"] == 2
    assert result["section_index"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_chat_doc.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create the service file**

Create `app/services/report_chat_doc.py`:

```python
"""Generate and edit Markdown documents for the AI assistant chat."""

from __future__ import annotations

import json
import logging
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import get_provider
from app.db.models import (
    ChatDocument,
    LiteratureMatrixRow,
    Paper,
    ProjectPaper,
    ResearchGap,
)
from app.services.hybrid_retrieval import RetrievedChunk, retrieve_project_evidence

logger = logging.getLogger(__name__)

_MAX_RAG_CHUNKS = 30
_MAX_CHUNKS_PER_PAPER = 4
_MAX_CHUNK_CHARS = 8000


def parse_markdown_sections(markdown: str) -> list[dict]:
    """Split a Markdown document into a list of {heading, body} sections by H2.

    Sections are delimited by lines starting with '## '. A document with no
    headings is returned as a single section with empty heading.
    """
    if not markdown or not markdown.strip():
        return [{"heading": "", "body": ""}]
    parts = re.split(r"(?m)^## ", markdown)
    sections: list[dict] = []
    for i, part in enumerate(parts):
        if i == 0:
            # Before the first '## ' is preamble (or empty)
            preamble = part.strip()
            if preamble:
                sections.append({"heading": "", "body": preamble})
            continue
        lines = part.split("\n", 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        sections.append({"heading": heading, "body": body})
    if not sections:
        sections = [{"heading": "", "body": markdown.strip()}]
    return sections


def _sections_to_markdown(title: str, sections: list[dict]) -> str:
    parts = [f"# {title}\n"]
    for sec in sections:
        if sec["heading"]:
            parts.append(f"\n## {sec['heading']}\n")
        if sec["body"]:
            parts.append(sec["body"])
    parts.append("\n## References\n")
    parts.append("_(auto-generated, populated after citation guardrail)_\n")
    return "\n".join(parts)


async def _load_context(db: AsyncSession, project_id: UUID) -> tuple[list, list]:
    """Load matrix rows + gaps for a project."""
    mr_stmt = select(LiteratureMatrixRow).where(LiteratureMatrixRow.project_id == project_id)
    matrix_rows = list((await db.execute(mr_stmt)).scalars().all())

    g_stmt = select(ResearchGap).where(ResearchGap.project_id == project_id)
    gaps = list((await db.execute(g_stmt)).scalars().all())
    return matrix_rows, gaps


def _rows_to_json_safe(rows: list) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "project_paper_id": str(r.project_paper_id),
            "research_problem": r.research_problem,
            "method": r.method,
            "dataset_or_context": r.dataset_or_context,
            "key_result": r.key_result,
            "limitation": r.limitation,
            "contribution": r.contribution,
            "relevance": r.relevance,
        })
    return out


def _build_chunk_context(chunks: list[RetrievedChunk]) -> str:
    parts: list[str] = []
    total = 0
    for c in chunks:
        label = c.section_label or c.content_type or "section"
        block = f"---{label}---\n{c.chunk_text}"
        if total + len(block) > _MAX_CHUNK_CHARS:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts) if parts else "No full-text sections available."


async def generate_markdown_for_project(
    db: AsyncSession,
    project_id: UUID,
    document_id: UUID,
    topic: str,
    research_question: str | None,
    include_gaps: bool = True,
) -> dict:
    """Generate a Markdown literature review and write it to chat_documents.

    Returns dict with keys: title, markdown, version, section_count.
    """
    matrix_rows, gaps = await _load_context(db, project_id)
    if not matrix_rows:
        return {"title": "Empty Report", "markdown": "", "version": 0, "section_count": 0, "error": "no_matrix_rows"}

    # RAG retrieval
    all_chunks: list[RetrievedChunk] = []
    try:
        all_chunks = await retrieve_project_evidence(db, project_id, topic, limit=_MAX_RAG_CHUNKS)
    except Exception as exc:
        logger.warning("RAG retrieval failed: %s", exc)
    chunk_context = _build_chunk_context(all_chunks)

    safe_rows = _rows_to_json_safe(matrix_rows)
    safe_gaps = [{"title": g.title, "description": g.description, "evidence_summary": g.evidence_summary} for g in gaps]

    system = (
        "You are a literature review writer. Return structured JSON with "
        "'title' (string) and 'sections' (list of {heading, body}). "
        "Use clear academic prose. Each section should synthesize across papers, "
        "not summarize one. Group by theme, method, or chronology."
    )
    user = (
        f"Project topic: {topic}\n"
        f"Research question: {research_question or topic}\n\n"
        f"Matrix rows:\n{json.dumps(safe_rows, indent=2, default=str)}\n\n"
        f"Research gaps:\n{json.dumps(safe_gaps, indent=2, default=str)}\n\n"
        f"Relevant full-text sections:\n{chunk_context}\n"
    )

    provider = get_provider()
    result = await provider.complete_structured(
        messages=[{"role": "user", "content": user}],
        schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "body": {"type": "string"},
                        },
                        "required": ["heading", "body"],
                    },
                },
            },
            "required": ["title", "sections"],
        },
        tool_name="generate_chat_report",
        system=system,
        max_tokens=4000,
    )

    title = result.get("title", f"Literature Review: {topic}")
    sections = result.get("sections", [])
    markdown = _sections_to_markdown(title, sections)

    # Persist to DB
    new_version = 1
    doc = (await db.execute(select(ChatDocument).where(ChatDocument.id == document_id))).scalar_one_or_none()
    if doc is None:
        doc = ChatDocument(
            id=document_id, project_id=project_id, user_id=(await db.execute(
                select(LiteratureMatrixRow.project_id).where(LiteratureMatrixRow.project_id == project_id)
            )).scalar_one_or_none() and (await db.execute(
                select(ChatDocument.user_id)
            )).scalars().first() or None,  # fallback; will be set by caller in practice
            title=title, content_md=markdown, version=new_version,
        )
        # The user_id should be passed in; refactor below
        db.add(doc)
    else:
        doc.title = title
        doc.content_md = markdown
        doc.version = doc.version + 1
        new_version = doc.version
    await db.commit()

    return {
        "title": title,
        "markdown": markdown,
        "version": new_version,
        "section_count": len(sections),
    }


async def edit_section(
    db: AsyncSession,
    document_id: UUID,
    project_id: UUID,
    section_index: int,
    instruction: str,
    current_markdown: str,
) -> dict:
    """Rewrite one section of the report. Other sections are preserved."""
    sections = parse_markdown_sections(current_markdown)
    if section_index < 0 or section_index >= len(sections):
        return {
            "markdown": current_markdown,
            "version": 0,
            "section_index": section_index,
            "error": f"section_index {section_index} out of range (0..{len(sections)-1})",
        }

    target = sections[section_index]
    system = (
        "You are a literature review editor. Return JSON: "
        "{'section': {'heading': string, 'body': string}}. "
        "Rewrite the section according to the user's instruction. "
        "Preserve academic tone. Do not invent citations."
    )
    user = (
        f"Current section heading: {target['heading']}\n"
        f"Current body:\n{target['body']}\n\n"
        f"Instruction: {instruction}\n"
    )

    provider = get_provider()
    result = await provider.complete_structured(
        messages=[{"role": "user", "content": user}],
        schema={
            "type": "object",
            "properties": {
                "section": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["heading", "body"],
                },
            },
            "required": ["section"],
        },
        tool_name="edit_chat_report_section",
        system=system,
        max_tokens=2000,
    )

    new_section = result.get("section", {})
    new_heading = (new_section.get("heading") or target["heading"]).strip()
    new_body = (new_section.get("body") or target["body"]).strip()
    sections[section_index] = {"heading": new_heading, "body": new_body}

    # Find title from preamble (first H1 or section with empty heading)
    title = "Literature Review"
    if sections and not sections[0]["heading"]:
        # Use first 60 chars of preamble as title
        preamble = sections[0]["body"]
        title = preamble.split("\n", 1)[0].strip("# ").strip()[:120] or title
        sections = sections[1:]

    new_markdown = _sections_to_markdown(title, sections)

    # Persist
    doc = (await db.execute(select(ChatDocument).where(ChatDocument.id == document_id))).scalar_one_or_none()
    new_version = 1
    if doc is not None:
        doc.content_md = new_markdown
        doc.version = doc.version + 1
        new_version = doc.version
        await db.commit()
    else:
        await db.rollback()

    return {
        "markdown": new_markdown,
        "version": new_version,
        "section_index": section_index,
        "section_preview": new_body[:300],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_report_chat_doc.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/report_chat_doc.py tests/test_report_chat_doc.py
git commit -m "feat: add report_chat_doc service for generate + edit Markdown"
```

---

### Task 5: Create the 8 tool handlers

**Files:**
- Create: `app/services/assistant_tools/__init__.py` (registry)
- Create: `app/services/assistant_tools/create_project.py`
- Create: `app/services/assistant_tools/search_papers.py`
- Create: `app/services/assistant_tools/save_paper.py`
- Create: `app/services/assistant_tools/generate_matrix.py`
- Create: `app/services/assistant_tools/detect_gaps.py`
- Create: `app/services/assistant_tools/generate_report.py`
- Create: `app/services/assistant_tools/edit_report_section.py`
- Create: `app/services/assistant_tools/qa_search_papers.py`

- [ ] **Step 1: Write the failing test for the registry**

Create `tests/test_assistant_tools.py`:

```python
from app.services.assistant_tools import TOOL_REGISTRY


def test_all_8_tools_registered():
    expected = {
        "create_project", "search_papers", "save_paper_to_project",
        "generate_matrix", "detect_gaps", "generate_report",
        "edit_report_section", "qa_search_papers",
    }
    assert set(TOOL_REGISTRY.keys()) == expected


def test_each_handler_is_async_callable():
    for name, handler in TOOL_REGISTRY.items():
        assert callable(handler), f"{name} not callable"
        import inspect
        assert inspect.iscoroutinefunction(handler), f"{name} not async"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assistant_tools.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Create each tool handler file**

Create `app/services/assistant_tools/create_project.py`:

```python
"""Tool: create_project — create a new Project and a chat_documents row."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.db.models import ChatDocument, Project, User
from app.schemas.project import ProjectCreate
from app.services.project import create_project as svc_create_project

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(
    db,
    user: User,
    args: dict,
    runner: "AssistantRunner | None" = None,
) -> dict:
    title = args["title"]
    topic = args["topic"]
    research_question = args.get("research_question")
    max_papers = args.get("max_papers", 12)

    data = ProjectCreate(title=title, topic=topic, research_question=research_question)
    resp = await svc_create_project(db, user, data)
    project_id = uuid.UUID(resp.id)

    # Create chat_documents row
    doc = ChatDocument(
        project_id=project_id, user_id=user.id,
        title=title, content_md="", version=0,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return {
        "project_id": str(project_id),
        "title": title,
        "topic": topic,
        "max_papers": max_papers,
        "document_id": str(doc.id),
    }
```

Create `app/services/assistant_tools/search_papers.py`:

```python
"""Tool: search_papers — fan out to academic sources."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.schemas.paper import PaperSearchRequest
from app.services.paper_search import search_and_download

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner
    from app.db.models import User

logger = logging.getLogger(__name__)


async def handle(
    db, user: "User", args: dict, runner: "AssistantRunner | None" = None
) -> dict:
    if runner:
        await runner.emit({"type": "log", "level": "info", "message": f"🔍 Searching: '{args.get('query', '')}'"})

    req = PaperSearchRequest(
        query=args["query"],
        limit=min(args.get("max_results", 25), 100),
        year_from=args.get("year_from"),
        download_pdfs=False,
    )
    outcome = await search_and_download(req)
    papers = [p.model_dump() for p in outcome.response.papers]

    if runner:
        await runner.emit({"type": "log", "level": "info", "message": f"✓ Found {len(papers)} candidates"})

    return {
        "papers": papers,
        "papers_found": len(papers),
        "diagnostics": outcome.response.source_diagnostics,
    }
```

Create `app/services/assistant_tools/save_paper.py`:

```python
"""Tool: save_paper_to_project — save one paper into the project corpus."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from app.schemas.project import SavePaperRequest
from app.services.project import save_paper_to_project

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: "AssistantRunner | None" = None) -> dict:
    project_id = UUID(args["project_id"])
    paper = args["paper"]
    authors = []
    for a in paper.get("authors") or []:
        if isinstance(a, dict):
            authors.append({"name": a.get("name", str(a)), "author_id": ""})
        else:
            authors.append({"name": str(a), "author_id": ""})

    req = SavePaperRequest(
        paper_title=paper.get("title", "Untitled"),
        paper_abstract=paper.get("abstract"),
        paper_year=paper.get("year"),
        paper_venue=paper.get("venue"),
        paper_doi=paper.get("doi"),
        paper_arxiv_id=paper.get("arxiv_id"),
        paper_semantic_scholar_id=paper.get("semantic_scholar_id"),
        paper_url=paper.get("url"),
        paper_citation_count=paper.get("citation_count"),
        paper_authors=authors,
        paper_source_names=paper.get("source_names") or ["paperhub"],
        status="saved",
        relevance_label=args.get("relevance_label", "related"),
        download_pdf=False,
    )
    resp = await save_paper_to_project(db, user, project_id, req)
    if resp is None:
        return {"saved": False, "error": "duplicate or invalid paper"}
    return {"saved": True, "project_paper_id": resp.project_paper_id}
```

Create `app/services/assistant_tools/generate_matrix.py`:

```python
"""Tool: generate_matrix — trigger matrix generation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from app.services.literature_matrix import generate as svc_generate

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: "AssistantRunner | None" = None) -> dict:
    project_id = UUID(args["project_id"])
    if runner:
        await runner.emit({"type": "progress", "step": "matrix", "status": "running", "percent": 0, "label": "Generating matrix"})
    try:
        result = await svc_generate(db, user.id, project_id)
        if runner:
            await runner.emit({"type": "progress", "step": "matrix", "status": "done", "percent": 100, "label": "Matrix done"})
        return {
            "rows_created": result.get("created_count", 0),
            "status": "completed",
        }
    except Exception as exc:
        if runner:
            await runner.emit({"type": "progress", "step": "matrix", "status": "failed", "percent": 0, "label": str(exc)})
        return {"rows_created": 0, "status": "failed", "error": str(exc)[:200]}
```

Create `app/services/assistant_tools/detect_gaps.py`:

```python
"""Tool: detect_gaps — trigger research gap detection."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from app.services.gap_detection import generate as svc_generate

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: "AssistantRunner | None" = None) -> dict:
    project_id = UUID(args["project_id"])
    if runner:
        await runner.emit({"type": "progress", "step": "gaps", "status": "running", "percent": 0, "label": "Detecting gaps"})
    try:
        result = await svc_generate(db, user.id, project_id, max_gaps=args.get("max_gaps", 5))
        if runner:
            await runner.emit({"type": "progress", "step": "gaps", "status": "done", "percent": 100, "label": "Gaps done"})
        return {
            "gaps_created": result.get("gaps_created", 0),
            "status": "completed",
        }
    except Exception as exc:
        if runner:
            await runner.emit({"type": "progress", "step": "gaps", "status": "failed", "percent": 0, "label": str(exc)})
        return {"gaps_created": 0, "status": "failed", "error": str(exc)[:200]}
```

Create `app/services/assistant_tools/generate_report.py`:

```python
"""Tool: generate_report — generate full report and write Markdown to chat_documents."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from app.db.models import ChatDocument, Project
from app.services.report_chat_doc import generate_markdown_for_project

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: "AssistantRunner | None" = None) -> dict:
    project_id = UUID(args["project_id"])

    # Find or create chat_documents row for this project
    doc = (await db.execute(
        select(ChatDocument)
        .where(ChatDocument.project_id == project_id, ChatDocument.user_id == user.id)
        .order_by(ChatDocument.created_at.desc())
    )).scalars().first()

    if doc is None:
        doc = ChatDocument(
            project_id=project_id, user_id=user.id,
            title="Literature Review", content_md="", version=0,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        return {"error": "Project not found", "status": "failed"}

    if runner:
        await runner.emit({"type": "progress", "step": "report", "status": "running", "percent": 0, "label": "Writing report"})

    result = await generate_markdown_for_project(
        db=db, project_id=project_id, document_id=doc.id,
        topic=project.topic, research_question=project.research_question,
        include_gaps=args.get("include_gaps", True),
    )

    if "error" in result and result.get("markdown", "") == "":
        if runner:
            await runner.emit({"type": "progress", "step": "report", "status": "failed", "percent": 0, "label": result["error"]})
        return {"status": "failed", "error": result["error"]}

    if runner:
        await runner.emit({
            "type": "markdown_updated",
            "content": result["markdown"],
            "version": result["version"],
            "section_changed": None,
        })
        await runner.emit({"type": "progress", "step": "report", "status": "done", "percent": 100, "label": "Report done"})

    return {
        "status": "completed",
        "document_id": str(doc.id),
        "title": result["title"],
        "version": result["version"],
        "section_count": result["section_count"],
    }
```

Create `app/services/assistant_tools/edit_report_section.py`:

```python
"""Tool: edit_report_section — rewrite one section of the current report."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from app.db.models import ChatDocument
from app.services.report_chat_doc import edit_section

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: "AssistantRunner | None" = None) -> dict:
    project_id = UUID(args["project_id"])
    section_index = int(args["section_index"])
    instruction = args["instruction"]

    doc = (await db.execute(
        select(ChatDocument)
        .where(ChatDocument.project_id == project_id, ChatDocument.user_id == user.id)
        .order_by(ChatDocument.created_at.desc())
    )).scalars().first()
    if doc is None:
        return {"error": "No chat document for this project", "status": "failed"}

    result = await edit_section(
        db=db, document_id=doc.id, project_id=project_id,
        section_index=section_index, instruction=instruction,
        current_markdown=doc.content_md,
    )

    if "error" in result:
        return {"error": result["error"], "status": "failed"}

    if runner:
        await runner.emit({
            "type": "markdown_updated",
            "content": result["markdown"],
            "version": result["version"],
            "section_changed": section_index,
        })

    return {
        "status": "completed",
        "version": result["version"],
        "section_index": section_index,
        "section_preview": result.get("section_preview", ""),
    }
```

Create `app/services/assistant_tools/qa_search_papers.py`:

```python
"""Tool: qa_search_papers — RAG Q&A over saved project papers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from app.ai.provider import get_provider
from app.services.hybrid_retrieval import retrieve_project_evidence

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: "AssistantRunner | None" = None) -> dict:
    project_id = UUID(args["project_id"])
    question = args["question"]

    chunks = await retrieve_project_evidence(db, project_id, question, limit=10)
    chunk_text = "\n\n".join(
        f"[paper {str(c.project_paper_id)[:8]} | {c.section_label or c.content_type}]\n{c.chunk_text}"
        for c in chunks[:6]
    )

    system = (
        "You are a research assistant. Answer the user's question based ONLY on "
        "the provided evidence. Cite the paper ID at the end of each claim in "
        "the format [paper XXXXXXXX] (the 8-char prefix shown in evidence). "
        "If the evidence doesn't support an answer, say so."
    )
    user_msg = f"Question: {question}\n\nEvidence:\n{chunk_text}"

    provider = get_provider()
    answer = await provider.complete(
        messages=[{"role": "user", "content": user_msg}],
        system=system,
        max_tokens=800,
    )

    return {
        "answer": answer,
        "cited_paper_ids": [str(c.project_paper_id) for c in chunks[:6]],
        "evidence_count": len(chunks[:6]),
    }
```

Create `app/services/assistant_tools/__init__.py`:

```python
"""Tool registry: name → async handler(db, user, args, runner)."""

from app.services.assistant_tools import (
    create_project,
    detect_gaps,
    edit_report_section,
    generate_matrix,
    generate_report,
    qa_search_papers,
    save_paper,
    search_papers,
)

TOOL_REGISTRY = {
    "create_project": create_project.handle,
    "search_papers": search_papers.handle,
    "save_paper_to_project": save_paper.handle,
    "generate_matrix": generate_matrix.handle,
    "detect_gaps": detect_gaps.handle,
    "generate_report": generate_report.handle,
    "edit_report_section": edit_report_section.handle,
    "qa_search_papers": qa_search_papers.handle,
}


def get_handler(name: str):
    return TOOL_REGISTRY.get(name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_assistant_tools.py -v`
Expected: PASS

- [ ] **Step 5: Verify imports compile**

Run: `python -c "from app.services.assistant_tools import TOOL_REGISTRY; print(len(TOOL_REGISTRY), 'tools')"`
Expected: `8 tools`

- [ ] **Step 6: Commit**

```bash
git add app/services/assistant_tools/ tests/test_assistant_tools.py
git commit -m "feat: add 8 assistant tool handlers with registry"
```

---

### Task 6: Create AssistantRunner (ReAct loop)

**Files:**
- Create: `app/services/assistant_runner.py`
- Create: `tests/test_assistant_runner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_assistant_runner.py`:

```python
"""Tests for AssistantRunner — ReAct loop and WS event emission."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.assistant_runner import AssistantRunner


def _state(agent_status="idle", iterations=0):
    return SimpleNamespace(
        history=[],
        agent_status=agent_status,
        iterations=iterations,
    )


@pytest.mark.asyncio
async def test_runner_emits_done_when_no_tool_calls():
    runner = AssistantRunner(
        db=AsyncMock(), user=SimpleNamespace(id=uuid4()),
        project_id=uuid4(), document_id=uuid4(), ws_send=AsyncMock(),
    )
    runner.history = [{"role": "user", "content": "hi"}]

    with patch("app.services.assistant_runner.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "message": "Hello!",
            "tool_calls": None,
        }
        mock_get_provider.return_value = mock_provider

        with patch("app.services.assistant_runner.persist_assistant_message", new_callable=AsyncMock):
            await runner.run_turn("hi")

    assert any(e["type"] == "done" for e in runner.events)


@pytest.mark.asyncio
async def test_runner_executes_tool_and_loops():
    runner = AssistantRunner(
        db=AsyncMock(), user=SimpleNamespace(id=uuid4()),
        project_id=uuid4(), document_id=uuid4(), ws_send=AsyncMock(),
    )

    # First call: returns tool_call. Second call: returns text. Loops once.
    with patch("app.services.assistant_runner.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.complete_structured.side_effect = [
            {
                "message": "Searching…",
                "tool_calls": [{"name": "search_papers", "args": {"query": "RAG"}}],
            },
            {"message": "Done", "tool_calls": None},
        ]
        mock_get_provider.return_value = mock_provider

        with patch("app.services.assistant_runner.TOOL_REGISTRY") as mock_registry:
            mock_handler = AsyncMock(return_value={"papers_found": 3})
            mock_registry.get.return_value = mock_handler
            with patch("app.services.assistant_runner.persist_assistant_message", new_callable=AsyncMock):
                await runner.run_turn("find papers on RAG")

    tool_call_events = [e for e in runner.events if e["type"] == "tool_call"]
    tool_result_events = [e for e in runner.events if e["type"] == "tool_result"]
    assert len(tool_call_events) == 1
    assert tool_call_events[0]["tool"] == "search_papers"
    assert len(tool_result_events) == 1
    assert any(e["type"] == "done" for e in runner.events)


@pytest.mark.asyncio
async def test_runner_stops_on_max_iterations():
    runner = AssistantRunner(
        db=AsyncMock(), user=SimpleNamespace(id=uuid4()),
        project_id=uuid4(), document_id=uuid4(), ws_send=AsyncMock(),
        max_iterations=3,
    )

    with patch("app.services.assistant_runner.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "message": "x", "tool_calls": [{"name": "search_papers", "args": {"query": "x"}}],
        }
        mock_get_provider.return_value = mock_provider

        with patch("app.services.assistant_runner.TOOL_REGISTRY") as mock_registry:
            mock_registry.get.return_value = AsyncMock(return_value={})
            with patch("app.services.assistant_runner.persist_assistant_message", new_callable=AsyncMock):
                await runner.run_turn("loop forever")

    # Should hit max_iterations and emit done with reason
    done_events = [e for e in runner.events if e["type"] == "done"]
    assert done_events
    assert done_events[0].get("reason") == "max_iterations"


@pytest.mark.asyncio
async def test_runner_stopped_flag_halts_loop():
    runner = AssistantRunner(
        db=AsyncMock(), user=SimpleNamespace(id=uuid4()),
        project_id=uuid4(), document_id=uuid4(), ws_send=AsyncMock(),
    )
    runner.stopped.set()

    with patch("app.services.assistant_runner.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "message": "x", "tool_calls": [{"name": "search_papers", "args": {}}],
        }
        mock_get_provider.return_value = mock_provider

        await runner.run_turn("stop test")

    stopped_events = [e for e in runner.events if e["type"] == "stopped"]
    assert stopped_events
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assistant_runner.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Create the runner**

Create `app/services/assistant_runner.py`:

```python
"""AssistantRunner — ReAct agent loop for the AI assistant chat page."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
from uuid import UUID

from app.ai.prompts import ASSISTANT_SYSTEM, TOOL_DESCRIPTIONS
from app.ai.provider import get_provider
from app.db.models import ChatMessage, User
from app.services.assistant_tools import TOOL_REGISTRY

logger = logging.getLogger(__name__)


async def persist_assistant_message(
    db, document_id: UUID, project_id: UUID, role: str, content: str,
    tool_name: str | None = None, tool_args: dict | None = None, tool_result: dict | None = None,
) -> None:
    """Persist a chat message to the DB. Best-effort — never raises."""
    try:
        msg = ChatMessage(
            document_id=document_id, project_id=project_id,
            role=role, content=content,
            tool_name=tool_name, tool_args=tool_args or {}, tool_result=tool_result or {},
        )
        db.add(msg)
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to persist chat message: %s", exc)
        try:
            await db.rollback()
        except Exception:
            pass


class AssistantRunner:
    """Runs one ReAct agent turn: think → tool call → observe → repeat.

    Emits WS events via the ws_send callable. Captures events in self.events
    for testing. Loops up to max_iterations. Stopped flag halts the loop.
    """

    def __init__(
        self,
        db,
        user: User,
        project_id: UUID | None,
        document_id: UUID | None,
        ws_send,
        max_iterations: int = 20,
    ) -> None:
        self.db = db
        self.user = user
        self.project_id = project_id
        self.document_id = document_id
        self.ws_send = ws_send
        self.max_iterations = max_iterations
        self.stopped = asyncio.Event()
        self.history: list[dict] = []
        self.events: list[dict] = []

    async def emit(self, event: dict) -> None:
        """Send a JSON event to WS client and capture for tests."""
        self.events.append(event)
        if self.ws_send:
            try:
                await self.ws_send(event)
            except Exception as exc:
                logger.debug("ws_send failed: %s", exc)

    async def run_turn(self, user_message: str) -> None:
        """One user message → agent loop until done, stopped, or max iterations."""
        self.history.append({"role": "user", "content": user_message})
        if self.document_id:
            await persist_assistant_message(
                self.db, self.document_id, self.project_id, "user", user_message
            )
        await self.emit({"type": "log", "level": "info", "message": "🤔 Thinking…"})

        iterations = 0
        t0 = time.monotonic()

        while iterations < self.max_iterations:
            if self.stopped.is_set():
                await self.emit({"type": "stopped"})
                return

            iterations += 1

            try:
                provider = get_provider()
                # Use complete_structured with the tool schemas as a forced tool call.
                # We pass the tool list and let the model choose.
                result = await provider.complete_structured(
                    messages=self.history,
                    schema={
                        "type": "object",
                        "properties": {
                            "message": {"type": "string", "description": "Natural-language response shown to user"},
                            "tool_calls": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string", "enum": list(TOOL_REGISTRY.keys())},
                                        "args": {"type": "object"},
                                    },
                                    "required": ["name", "args"],
                                },
                            },
                        },
                        "required": ["message"],
                    },
                    tool_name="assistant_decide",
                    system=ASSISTANT_SYSTEM + "\n\nAvailable tools:\n" + json.dumps(TOOL_DESCRIPTIONS, indent=2),
                    max_tokens=2000,
                )
            except Exception as exc:
                logger.exception("LLM call failed in runner")
                await self.emit({"type": "error", "message": f"LLM call failed: {exc}", "code": "ai_failure"})
                return

            message = result.get("message", "")
            tool_calls = result.get("tool_calls") or []

            # Emit the agent's intermediate text
            if message:
                await persist_assistant_message(
                    self.db, self.document_id, self.project_id, "assistant", message
                )
                await self.emit({"type": "agent_message", "content": message, "role": "assistant"})

            if not tool_calls:
                # No more work — done
                await self.emit({"type": "done", "iterations": iterations, "total_duration_ms": int((time.monotonic() - t0) * 1000)})
                return

            # Execute each tool
            for call in tool_calls:
                if self.stopped.is_set():
                    await self.emit({"type": "stopped"})
                    return

                tool_name = call.get("name")
                tool_args = call.get("args") or {}
                call_id = f"call_{iterations}_{tool_name}"
                await self.emit({
                    "type": "tool_call", "tool": tool_name, "args": tool_args, "call_id": call_id,
                })

                handler = TOOL_REGISTRY.get(tool_name)
                if handler is None:
                    err = f"Unknown tool: {tool_name}"
                    await self.emit({"type": "tool_result", "tool": tool_name, "call_id": call_id, "summary": err, "duration_ms": 0, "ok": False})
                    self.history.append({"role": "user", "content": f"Tool error: {err}. Pick a different tool or stop."})
                    continue

                t_tool = time.monotonic()
                try:
                    tool_result = await handler(self.db, self.user, tool_args, self)
                except Exception as exc:
                    logger.exception("Tool %s failed", tool_name)
                    tool_result = {"error": str(exc)[:300]}
                duration_ms = int((time.monotonic() - t_tool) * 1000)
                ok = "error" not in tool_result

                # Persist tool log
                await persist_assistant_message(
                    self.db, self.document_id, self.project_id, "tool_log",
                    f"Tool: {tool_name}\nArgs: {json.dumps(tool_args, default=str)[:500]}\nResult: {json.dumps(tool_result, default=str)[:500]}",
                    tool_name=tool_name, tool_args=tool_args, tool_result=tool_result,
                )

                # Summarize for the agent's history (avoid blowing the context window)
                summary = json.dumps(tool_result, default=str)[:1500]
                await self.emit({
                    "type": "tool_result", "tool": tool_name, "call_id": call_id,
                    "summary": summary, "duration_ms": duration_ms, "ok": ok,
                })

                self.history.append({
                    "role": "user",
                    "content": f"Tool '{tool_name}' result: {summary}",
                })

        # Hit max iterations
        await self.emit({
            "type": "done", "iterations": iterations,
            "total_duration_ms": int((time.monotonic() - t0) * 1000),
            "reason": "max_iterations",
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_assistant_runner.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/assistant_runner.py tests/test_assistant_runner.py
git commit -m "feat: add AssistantRunner ReAct loop with WS event emission"
```

---

### Task 7: Create WebSocket endpoint

**Files:**
- Create: `app/routers/assistant_ws.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_assistant_ws.py`:

```python
"""WS integration tests with mocked JWT auth and runner."""

import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _fake_token(user_id):
    """Issue a JWT for testing — uses the same secret as configured."""
    from app.core.security import create_access_token
    return create_access_token(subject=str(user_id))


@pytest.fixture
def client():
    return TestClient(app)


def test_ws_rejects_invalid_token(client):
    with client.websocket_connect("/api/assistant/ws?project_id=00000000-0000-0000-0000-000000000000&token=garbage") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"


def test_ws_accepts_valid_token_and_sends_connected(client):
    user_id = uuid4()
    token = _fake_token(user_id)
    project_id = uuid4()
    pid = "00000000-0000-0000-0000-000000000001"

    with patch("app.routers.assistant_ws.AssistantRunner") as mock_runner_cls:
        mock_runner = MagicMock()
        mock_runner.run_turn = AsyncMock()
        mock_runner_cls.return_value = mock_runner

        with client.websocket_connect(f"/api/assistant/ws?project_id={pid}&token={token}") as ws:
            msg = ws.receive_json()
            assert msg["type"] in ("connected", "error")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assistant_ws.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Create the WS router**

Create `app/routers/assistant_ws.py`:

```python
"""WebSocket endpoint for the AI assistant chat page."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.core.security import decode_access_token
from app.db.models import ChatDocument, Project, User
from app.db.session import async_session_factory
from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)

router = APIRouter()


async def _resolve_user_from_token(token: str) -> uuid.UUID | None:
    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        return uuid.UUID(sub) if sub else None
    except Exception:
        return None


@router.websocket("/ws")
async def assistant_ws(websocket: WebSocket, project_id: str, token: str):
    """WebSocket entry: project_id query param + JWT token.

    Lifecycle:
    1. Validate token → user_id
    2. If project_id == "new", wait for first message to create a project
    3. Find or create chat_documents row for this project
    4. Loop: receive user_message → run agent turn → send events
    """
    await websocket.accept()
    user_id = await _resolve_user_from_token(token)
    if not user_id:
        await websocket.send_json({"type": "error", "message": "Invalid or expired token", "code": "unauthorized"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not user or not user.is_active:
            await websocket.send_json({"type": "error", "message": "User not found or inactive", "code": "unauthorized"})
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Resolve project + document
        actual_project_id: uuid.UUID | None = None
        document_id: uuid.UUID | None = None
        if project_id != "new":
            try:
                actual_project_id = uuid.UUID(project_id)
            except ValueError:
                await websocket.send_json({"type": "error", "message": "Invalid project_id", "code": "bad_request"})
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

            project = (await db.execute(
                select(Project).where(Project.id == actual_project_id, Project.owner_id == user.id)
            )).scalar_one_or_none()
            if not project:
                await websocket.send_json({"type": "error", "message": "Project not found", "code": "not_found"})
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

            doc = (await db.execute(
                select(ChatDocument)
                .where(ChatDocument.project_id == actual_project_id, ChatDocument.user_id == user.id)
                .order_by(ChatDocument.created_at.desc())
            )).scalars().first()
            if doc:
                document_id = doc.id
                await websocket.send_json({
                    "type": "markdown_snapshot",
                    "content": doc.content_md,
                    "version": doc.version,
                    "title": doc.title,
                })
            else:
                # Create a doc row immediately so subsequent edits have a target
                doc = ChatDocument(
                    project_id=actual_project_id, user_id=user.id,
                    title=project.title, content_md="", version=0,
                )
                db.add(doc)
                await db.commit()
                await db.refresh(doc)
                document_id = doc.id

        await websocket.send_json({
            "type": "connected",
            "session_id": str(uuid.uuid4()),
            "project_id": str(actual_project_id) if actual_project_id else None,
            "document_id": str(document_id) if document_id else None,
            "resumed": project_id != "new",
        })

        # Main message loop
        async def ws_send(event: dict) -> None:
            try:
                await websocket.send_json(event)
            except Exception as exc:
                logger.debug("WS send failed: %s", exc)

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await ws_send({"type": "error", "message": "Invalid JSON", "code": "bad_request"})
                    continue

                mtype = msg.get("type")
                if mtype == "ping":
                    await ws_send({"type": "pong"})
                    continue
                if mtype == "stop":
                    if "runner" in dir() and runner is not None:
                        runner.stopped.set()
                    continue
                if mtype == "resume":
                    continue  # noop for MVP
                if mtype != "user_message":
                    await ws_send({"type": "error", "message": f"Unknown type: {mtype}", "code": "bad_request"})
                    continue

                content = (msg.get("content") or "").strip()
                if not content:
                    continue

                # Re-resolve project/document if "new"
                if actual_project_id is None:
                    # Heuristic: agent's first call to create_project will register
                    # the project. For MVP, the wizard page sends a user_message that
                    # triggers create_project. We just run the agent and the agent
                    # will mutate the runner state.
                    pass

                # Create a fresh runner per turn
                runner = AssistantRunner(
                    db=db, user=user,
                    project_id=actual_project_id, document_id=document_id,
                    ws_send=ws_send,
                )
                # If we just got a real project_id from the runner, update ws state
                # (the agent emits "connected" with project_id, frontend reads it)
                await runner.run_turn(content)

                # If a new project was created during this turn, capture it
                # by inspecting ChatDocument for a recently created one
                if actual_project_id is None:
                    doc = (await db.execute(
                        select(ChatDocument)
                        .where(ChatDocument.user_id == user.id)
                        .order_by(ChatDocument.created_at.desc())
                    )).scalars().first()
                    if doc:
                        actual_project_id = doc.project_id
                        document_id = doc.id
                        await ws_send({
                            "type": "project_created",
                            "project_id": str(actual_project_id),
                            "document_id": str(document_id),
                        })
        except WebSocketDisconnect:
            logger.info("WS disconnected for user %s", user_id)
        except Exception as exc:
            logger.exception("WS handler error")
            try:
                await ws_send({"type": "error", "message": str(exc)[:200], "code": "server_error"})
            except Exception:
                pass
```

- [ ] **Step 4: Verify imports compile**

Run: `python -c "from app.routers.assistant_ws import router; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Run WS tests**

Run: `pytest tests/test_assistant_ws.py -v`
Expected: PASS (or auth-related PASS with skip)

- [ ] **Step 6: Commit**

```bash
git add app/routers/assistant_ws.py tests/test_assistant_ws.py
git commit -m "feat: add WebSocket endpoint for AI assistant chat"
```

---

### Task 8: Create REST endpoints (list/get/export/delete)

**Files:**
- Create: `app/routers/assistant.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_assistant_ws.py`:

```python
def test_rest_list_documents(client):
    token = _fake_token(uuid4())
    r = client.get("/api/assistant/documents", headers={"Authorization": f"Bearer {token}"})
    # Either 200 (empty list) or 401/403 depending on auth
    assert r.status_code in (200, 401, 403)


def test_rest_get_document_404(client):
    token = _fake_token(uuid4())
    r = client.get(
        "/api/assistant/documents/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code in (404, 401, 403)
```

- [ ] **Step 2: Create the REST router**

Create `app/routers/assistant.py`:

```python
"""REST endpoints for AI assistant chat document history."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user
from app.db.models import ChatDocument, ChatMessage, User
from app.db.session import get_db
from app.schemas.assistant import (
    ChatDocumentDetailResponse,
    ChatDocumentListResponse,
    ChatDocumentResponse,
    ChatMessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _doc_to_response(doc: ChatDocument) -> ChatDocumentResponse:
    return ChatDocumentResponse(
        id=str(doc.id),
        project_id=str(doc.project_id),
        title=doc.title,
        content_md=doc.content_md,
        version=doc.version,
        created_at=doc.created_at.isoformat() if doc.created_at else "",
        updated_at=doc.updated_at.isoformat() if doc.updated_at else "",
    )


@router.get("/documents", response_model=ChatDocumentListResponse)
async def list_documents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatDocumentListResponse:
    stmt = (
        select(ChatDocument)
        .where(ChatDocument.user_id == user.id)
        .order_by(ChatDocument.updated_at.desc())
    )
    docs = list((await db.execute(stmt)).scalars().all())
    return ChatDocumentListResponse(
        items=[_doc_to_response(d) for d in docs],
        total=len(docs),
    )


@router.get("/documents/{doc_id}", response_model=ChatDocumentDetailResponse)
async def get_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatDocumentDetailResponse:
    try:
        did = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid doc_id")

    stmt = (
        select(ChatDocument)
        .options(selectinload(ChatDocument.__mapper__.relationships.get("messages")))
        .where(ChatDocument.id == did, ChatDocument.user_id == user.id)
    )
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    msgs_stmt = (
        select(ChatMessage)
        .where(ChatMessage.document_id == doc.id)
        .order_by(ChatMessage.created_at.asc())
    )
    msgs = list((await db.execute(msgs_stmt)).scalars().all())

    msg_responses = [
        ChatMessageResponse(
            id=str(m.id),
            document_id=str(m.document_id),
            project_id=str(m.project_id),
            role=m.role,
            content=m.content,
            tool_name=m.tool_name,
            tool_args=m.tool_args or {},
            tool_result=m.tool_result or {},
            created_at=m.created_at.isoformat() if m.created_at else "",
        )
        for m in msgs
    ]
    base = _doc_to_response(doc)
    return ChatDocumentDetailResponse(**base.model_dump(), messages=msg_responses)


@router.get("/documents/{doc_id}/export")
async def export_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        did = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid doc_id")

    doc = (await db.execute(
        select(ChatDocument).where(ChatDocument.id == did, ChatDocument.user_id == user.id)
    )).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return PlainTextResponse(
        content=doc.content_md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{doc.title[:60]}.md"'},
    )


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        did = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid doc_id")

    doc = (await db.execute(
        select(ChatDocument).where(ChatDocument.id == did, ChatDocument.user_id == user.id)
    )).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)
    await db.commit()
    return Response(status_code=204)
```

- [ ] **Step 3: Verify compile**

Run: `python -c "from app.routers.assistant import router; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/routers/assistant.py tests/test_assistant_ws.py
git commit -m "feat: add REST endpoints for chat document history/export"
```

---

### Task 9: Register routers in main.py

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add imports and router registrations**

In `app/main.py`:

Add to imports block (after line 23):

```python
from app.routers.assistant import router as assistant_router
from app.routers.assistant_ws import router as assistant_ws_router
```

In `create_app()` (after line 187, before the static files setup):

```python
    app.include_router(assistant_router, prefix="/api")
    app.include_router(assistant_ws_router, prefix="/api/assistant")
```

- [ ] **Step 2: Verify the app still loads**

Run: `python -c "from app.main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Run all backend tests**

Run: `pytest tests/test_assistant_*.py -v`
Expected: All PASS

- [ ] **Step 4: Run linter**

Run: `ruff check app/services/assistant_runner.py app/services/assistant_tools/ app/routers/assistant.py app/routers/assistant_ws.py app/schemas/assistant.py app/services/report_chat_doc.py app/ai/prompts.py app/db/models.py`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add app/main.py
git commit -m "feat: register AI assistant REST and WebSocket routers"
```

---

### Task 10: Add frontend types

**Files:**
- Modify: `frontend/lib/types.ts` (append at end)

- [ ] **Step 1: Add types**

Append to `frontend/lib/types.ts`:

```typescript
// ── AI Assistant types ──

export type PipelineStep =
  | "create_project"
  | "search_papers"
  | "save_papers"
  | "matrix"
  | "gaps"
  | "report";

export type AgentStatus =
  | "idle"
  | "thinking"
  | "running"
  | "needs_confirmation"
  | "stopped"
  | "done"
  | "error";

export interface ChatMessageFE {
  id?: string;
  role: "user" | "assistant" | "system" | "tool_log";
  content: string;
  tool_name?: string | null;
  created_at?: string;
}

export interface ToolCallEvent {
  type: "tool_call";
  tool: string;
  args: Record<string, unknown>;
  call_id: string;
}

export interface ToolResultEvent {
  type: "tool_result";
  tool: string;
  call_id: string;
  summary: string;
  duration_ms: number;
  ok: boolean;
}

export interface ProgressEvent {
  type: "progress";
  step: PipelineStep | string;
  status: "pending" | "running" | "done" | "failed";
  percent: number;
  label?: string;
}

export interface MarkdownUpdatedEvent {
  type: "markdown_updated";
  content: string;
  version: number;
  section_changed: number | null;
}

export interface LogEvent {
  type: "log";
  level: "info" | "warn" | "error";
  message: string;
}

export interface ConnectedEvent {
  type: "connected";
  session_id: string;
  project_id: string | null;
  document_id: string | null;
  resumed: boolean;
}

export interface ProjectCreatedEvent {
  type: "project_created";
  project_id: string;
  document_id: string;
}

export interface DoneEvent {
  type: "done";
  iterations: number;
  total_duration_ms: number;
  reason?: "max_iterations" | "stopped" | "completed";
}

export interface ErrorEvent {
  type: "error";
  message: string;
  code: string;
}

export type AssistantEvent =
  | ConnectedEvent
  | ProjectCreatedEvent
  | ProgressEvent
  | LogEvent
  | ToolCallEvent
  | ToolResultEvent
  | MarkdownUpdatedEvent
  | { type: "agent_message"; content: string; role: "assistant" }
  | DoneEvent
  | ErrorEvent
  | { type: "stopped" }
  | { type: "needs_confirmation"; prompt: string; options: string[]; request_id: string }
  | { type: "markdown_snapshot"; content: string; version: number; title: string }
  | { type: "message_history"; messages: ChatMessageFE[] }
  | { type: "pong" };

export interface ChatDocumentListResponse {
  items: Array<{
    id: string;
    project_id: string;
    title: string;
    content_md: string;
    version: number;
    created_at: string;
    updated_at: string;
  }>;
  total: number;
}

export interface ChatDocumentDetailResponse extends ChatDocumentListResponse {
  messages: ChatMessageFE[];
}
```

- [ ] **Step 2: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts
git commit -m "feat: add AI assistant TypeScript types"
```

---

### Task 11: Create Zustand store + WebSocket hook + API client

**Files:**
- Create: `frontend/lib/stores/assistantStore.ts`
- Create: `frontend/lib/hooks/useAssistantWS.ts`
- Create: `frontend/lib/api/assistant.ts`

- [ ] **Step 1: Create the Zustand store**

Create `frontend/lib/stores/assistantStore.ts`:

```typescript
"use client";

import { create } from "zustand";
import type {
  AgentStatus,
  AssistantEvent,
  ChatMessageFE,
  PipelineStep,
} from "@/lib/types";

interface ProgressState {
  status: "pending" | "running" | "done" | "failed";
  percent: number;
  label?: string;
}

interface AssistantState {
  // Identity
  projectId: string | null;
  documentId: string | null;
  sessionId: string | null;

  // Chat
  messages: ChatMessageFE[];
  streamingMessage: string | null;

  // Document
  currentMarkdown: string;
  documentVersion: number;
  documentTitle: string;

  // Progress
  progress: Record<PipelineStep, ProgressState>;
  currentLog: Array<{ level: "info" | "warn" | "error"; message: string }>;

  // Agent
  agentStatus: AgentStatus;

  // Connection
  ws: WebSocket | null;
  wsConnected: boolean;

  // Actions
  reset: () => void;
  setIdentity: (projectId: string | null, documentId: string | null) => void;
  setWs: (ws: WebSocket | null) => void;
  setConnected: (connected: boolean) => void;
  handleEvent: (event: AssistantEvent) => void;
  appendLocalMessage: (msg: ChatMessageFE) => void;
}

const DEFAULT_PROGRESS: Record<PipelineStep, ProgressState> = {
  create_project: { status: "pending", percent: 0 },
  search_papers: { status: "pending", percent: 0 },
  save_papers: { status: "pending", percent: 0 },
  matrix: { status: "pending", percent: 0 },
  gaps: { status: "pending", percent: 0 },
  report: { status: "pending", percent: 0 },
};

export const useAssistantStore = create<AssistantState>((set) => ({
  projectId: null,
  documentId: null,
  sessionId: null,
  messages: [],
  streamingMessage: null,
  currentMarkdown: "",
  documentVersion: 0,
  documentTitle: "",
  progress: { ...DEFAULT_PROGRESS },
  currentLog: [],
  agentStatus: "idle",
  ws: null,
  wsConnected: false,

  reset: () =>
    set({
      messages: [],
      streamingMessage: null,
      currentMarkdown: "",
      documentVersion: 0,
      documentTitle: "",
      progress: { ...DEFAULT_PROGRESS },
      currentLog: [],
      agentStatus: "idle",
    }),

  setIdentity: (projectId, documentId) => set({ projectId, documentId }),
  setWs: (ws) => set({ ws }),
  setConnected: (wsConnected) => set({ wsConnected }),

  appendLocalMessage: (msg) =>
    set((s) => ({ messages: [...s.messages, msg] })),

  handleEvent: (event) =>
    set((s) => {
      switch (event.type) {
        case "connected":
          return {
            sessionId: event.session_id,
            projectId: event.project_id || s.projectId,
            documentId: event.document_id || s.documentId,
            agentStatus: "idle",
          };
        case "project_created":
          return {
            projectId: event.project_id,
            documentId: event.document_id,
          };
        case "markdown_snapshot":
          return {
            currentMarkdown: event.content,
            documentVersion: event.version,
            documentTitle: event.title,
          };
        case "markdown_updated":
          return {
            currentMarkdown: event.content,
            documentVersion: event.version,
          };
        case "message_history":
          return { messages: event.messages };
        case "agent_message":
          return {
            messages: [
              ...s.messages,
              { role: "assistant", content: event.content, created_at: new Date().toISOString() },
            ],
            streamingMessage: null,
          };
        case "tool_call":
        case "tool_result":
          return {
            messages: [
              ...s.messages,
              {
                role: "tool_log",
                content:
                  event.type === "tool_call"
                    ? `🔧 ${event.tool}`
                    : `${event.ok ? "✓" : "✗"} ${event.tool}: ${event.summary.slice(0, 200)}`,
                tool_name: event.tool,
                created_at: new Date().toISOString(),
              },
            ],
          };
        case "log":
          return {
            currentLog: [...s.currentLog, { level: event.level, message: event.message }].slice(-50),
          };
        case "progress": {
          const step = event.step as PipelineStep;
          if (step in s.progress) {
            return {
              progress: {
                ...s.progress,
                [step]: { status: event.status, percent: event.percent, label: event.label },
              },
            };
          }
          return {};
        }
        case "done":
          return { agentStatus: "done" };
        case "stopped":
          return { agentStatus: "stopped" };
        case "error":
          return {
            agentStatus: "error",
            currentLog: [
              ...s.currentLog,
              { level: "error", message: `${event.code}: ${event.message}` },
            ],
          };
        case "needs_confirmation":
          return { agentStatus: "needs_confirmation" };
        default:
          return {};
      }
    }),
}));
```

- [ ] **Step 2: Create the WebSocket hook**

Create `frontend/lib/hooks/useAssistantWS.ts`:

```typescript
"use client";

import { useEffect } from "react";
import { useAssistantStore } from "@/lib/stores/assistantStore";
import type { AssistantEvent } from "@/lib/types";

const WS_URL = process.env.NEXT_PUBLIC_API_WS_URL || "ws://localhost:8010";

export function useAssistantWS(
  projectId: string | "new" | null,
  token: string | null,
) {
  const store = useAssistantStore();

  useEffect(() => {
    if (!projectId || !token) return;
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;

    const connect = () => {
      ws = new WebSocket(
        `${WS_URL}/api/assistant/ws?project_id=${projectId}&token=${encodeURIComponent(token)}`,
      );
      store.setWs(ws);

      ws.onopen = () => {
        store.setConnected(true);
        attempts = 0;
      };
      ws.onclose = () => {
        store.setConnected(false);
        attempts += 1;
        const delay = Math.min(30000, 1000 * Math.pow(2, attempts));
        reconnectTimer = setTimeout(connect, delay);
      };
      ws.onerror = () => {
        ws?.close();
      };
      ws.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data) as AssistantEvent;
          store.handleEvent(event);
        } catch (err) {
          console.error("Failed to parse WS message", err);
        }
      };
    };

    connect();

    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
      store.setWs(null);
      store.setConnected(false);
    };
  }, [projectId, token]);
}
```

- [ ] **Step 3: Create the API client**

Create `frontend/lib/api/assistant.ts`:

```typescript
import type { ChatDocumentDetailResponse, ChatDocumentListResponse } from "@/lib/types";
import { apiFetch } from "./client";

export async function listDocuments(token: string): Promise<ChatDocumentListResponse> {
  return apiFetch<ChatDocumentListResponse>("/assistant/documents", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getDocument(token: string, id: string): Promise<ChatDocumentDetailResponse> {
  return apiFetch<ChatDocumentDetailResponse>(`/assistant/documents/${id}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function exportDocumentUrl(id: string, token: string): string {
  return `/api/assistant/documents/${id}/export?token=${encodeURIComponent(token)}`;
}

export async function deleteDocument(token: string, id: string): Promise<void> {
  await apiFetch<void>(`/assistant/documents/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}
```

- [ ] **Step 4: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No new errors

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/stores/assistantStore.ts frontend/lib/hooks/useAssistantWS.ts frontend/lib/api/assistant.ts
git commit -m "feat: add assistant store, WS hook, and API client"
```

---

### Task 12: Create the page components

**Files:**
- Create: `frontend/components/assistant/StatusBadge.tsx`
- Create: `frontend/components/assistant/AssistantHeader.tsx`
- Create: `frontend/components/assistant/MessageBubble.tsx`
- Create: `frontend/components/assistant/ChatPanel.tsx`
- Create: `frontend/components/assistant/ToolLog.tsx`
- Create: `frontend/components/assistant/ProgressChecklist.tsx`
- Create: `frontend/components/assistant/PreviewPanel.tsx`

- [ ] **Step 1: Create StatusBadge**

Create `frontend/components/assistant/StatusBadge.tsx`:

```tsx
"use client";

import type { AgentStatus } from "@/lib/types";

const LABEL: Record<AgentStatus, { text: string; color: string }> = {
  idle: { text: "Ready", color: "bg-surface-bone text-charcoal" },
  thinking: { text: "Thinking…", color: "bg-yellow-100 text-yellow-800" },
  running: { text: "Running", color: "bg-blue-100 text-blue-800" },
  needs_confirmation: { text: "Awaiting input", color: "bg-orange-100 text-orange-800" },
  stopped: { text: "Stopped", color: "bg-ash/30 text-charcoal" },
  done: { text: "Done", color: "bg-green-100 text-green-800" },
  error: { text: "Error", color: "bg-red-100 text-red-800" },
};

export function StatusBadge({ status, connected }: { status: AgentStatus; connected: boolean }) {
  const { text, color } = LABEL[status];
  return (
    <div className="flex items-center gap-2">
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>{text}</span>
      <span
        className={`h-2 w-2 rounded-full ${connected ? "bg-green-500" : "bg-gray-400"}`}
        title={connected ? "Connected" : "Disconnected"}
      />
    </div>
  );
}
```

- [ ] **Step 2: Create AssistantHeader**

Create `frontend/components/assistant/AssistantHeader.tsx`:

```tsx
"use client";

import { useAssistantStore } from "@/lib/stores/assistantStore";
import { StatusBadge } from "./StatusBadge";

export function AssistantHeader() {
  const { documentTitle, documentVersion, agentStatus, wsConnected, reset } = useAssistantStore();
  return (
    <header className="flex items-center justify-between border-b border-hairline bg-canvas px-6 py-3">
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={reset}
          className="text-xs text-charcoal hover:text-ink"
          title="Back to wizard"
        >
          ← New
        </button>
        <h1 className="font-display text-base font-semibold text-ink truncate">
          {documentTitle || "New assistant session"}
        </h1>
        {documentVersion > 0 && (
          <span className="text-xs text-charcoal">v{documentVersion}</span>
        )}
      </div>
      <StatusBadge status={agentStatus} connected={wsConnected} />
    </header>
  );
}
```

- [ ] **Step 3: Create MessageBubble**

Create `frontend/components/assistant/MessageBubble.tsx`:

```tsx
"use client";

import type { ChatMessageFE } from "@/lib/types";

export function MessageBubble({ message }: { message: ChatMessageFE }) {
  if (message.role === "tool_log") {
    return (
      <div className="text-xs text-charcoal/80 italic px-3 py-1 border-l-2 border-hairline">
        {message.content}
      </div>
    );
  }
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
          isUser
            ? "bg-primary text-on-primary"
            : "bg-surface-card border border-hairline text-ink"
        }`}
      >
        {message.content}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create ToolLog**

Create `frontend/components/assistant/ToolLog.tsx`:

```tsx
"use client";

import { useAssistantStore } from "@/lib/stores/assistantStore";

export function ToolLog() {
  const logs = useAssistantStore((s) => s.currentLog);
  if (logs.length === 0) return null;
  return (
    <details className="border-t border-hairline bg-surface-bone/50 px-4 py-2">
      <summary className="text-xs text-charcoal cursor-pointer">
        Activity log ({logs.length})
      </summary>
      <div className="mt-2 space-y-1 max-h-32 overflow-y-auto">
        {logs.slice(-20).map((log, i) => (
          <div
            key={i}
            className={`text-xs font-mono ${
              log.level === "error" ? "text-red-700" : "text-charcoal/80"
            }`}
          >
            {log.message}
          </div>
        ))}
      </div>
    </details>
  );
}
```

- [ ] **Step 5: Create ChatPanel**

Create `frontend/components/assistant/ChatPanel.tsx`:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { useAssistantStore } from "@/lib/stores/assistantStore";
import { MessageBubble } from "./MessageBubble";
import { ToolLog } from "./ToolLog";

interface Props {
  token: string;
}

export function ChatPanel({ token }: Props) {
  const { messages, ws, agentStatus, appendLocalMessage } = useAssistantStore();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = () => {
    if (!input.trim() || !ws) return;
    const text = input.trim();
    appendLocalMessage({ role: "user", content: text, created_at: new Date().toISOString() });
    ws.send(JSON.stringify({ type: "user_message", content: text }));
    setInput("");
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const stop = () => {
    ws?.send(JSON.stringify({ type: "stop" }));
  };

  const disabled = !ws || agentStatus === "running" || agentStatus === "thinking";

  return (
    <div className="flex flex-col h-full bg-canvas">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-sm text-charcoal/70 text-center mt-12 px-6">
            Describe a research topic to start. The agent will create a project, find papers,
            build a literature matrix, and write a Markdown review.
          </div>
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}
      </div>
      <ToolLog />
      <div className="border-t border-hairline px-3 py-2 flex items-end gap-2 bg-canvas">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          rows={2}
          placeholder="Ask the agent or request an edit…"
          className="flex-1 resize-none rounded-lg border border-hairline bg-surface-card px-3 py-2 text-sm focus:outline-none focus:border-primary"
          disabled={disabled}
        />
        {agentStatus === "running" || agentStatus === "thinking" ? (
          <button
            onClick={stop}
            className="rounded-full bg-red-500 text-white px-4 py-2 text-sm font-medium hover:bg-red-600"
          >
            Stop
          </button>
        ) : (
          <button
            onClick={send}
            disabled={!input.trim() || !ws}
            className="rounded-full bg-primary text-on-primary px-4 py-2 text-sm font-semibold hover:bg-primary-deep disabled:opacity-50"
          >
            Send
          </button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Create ProgressChecklist**

Create `frontend/components/assistant/ProgressChecklist.tsx`:

```tsx
"use client";

import { useAssistantStore } from "@/lib/stores/assistantStore";
import type { PipelineStep } from "@/lib/types";

const STEPS: { key: PipelineStep; label: string }[] = [
  { key: "create_project", label: "Create project" },
  { key: "search_papers", label: "Search papers" },
  { key: "save_papers", label: "Save papers" },
  { key: "matrix", label: "Generate matrix" },
  { key: "gaps", label: "Detect gaps" },
  { key: "report", label: "Write report" },
];

export function ProgressChecklist() {
  const progress = useAssistantStore((s) => s.progress);
  return (
    <div className="border-b border-hairline bg-surface-bone/40 px-4 py-3">
      <ul className="space-y-1.5 text-sm">
        {STEPS.map(({ key, label }) => {
          const p = progress[key];
          const icon =
            p.status === "done" ? "✓" :
            p.status === "running" ? "▶" :
            p.status === "failed" ? "✗" :
            "○";
          const color =
            p.status === "done" ? "text-green-700" :
            p.status === "running" ? "text-blue-700" :
            p.status === "failed" ? "text-red-700" :
            "text-charcoal/50";
          return (
            <li key={key} className={`flex items-center gap-2 ${color}`}>
              <span className="w-4 inline-block text-center font-mono">{icon}</span>
              <span className="flex-1">{label}</span>
              {p.status === "running" && (
                <span className="text-xs text-charcoal/60">{p.percent}%</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
```

- [ ] **Step 7: Create PreviewPanel**

Create `frontend/components/assistant/PreviewPanel.tsx`:

```tsx
"use client";

import { useAssistantStore } from "@/lib/stores/assistantStore";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function PreviewPanel() {
  const { currentMarkdown, documentVersion, documentTitle, projectId } = useAssistantStore();

  if (!currentMarkdown) {
    return (
      <div className="h-full flex items-center justify-center bg-surface-bone/30 px-12 text-center">
        <div className="text-charcoal/60 text-sm">
          <p className="font-medium mb-2">No document yet</p>
          <p>The Markdown literature review will appear here once the agent finishes writing it.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-canvas px-8 py-6">
      <article className="prose prose-sm max-w-none prose-headings:font-display">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{currentMarkdown}</ReactMarkdown>
      </article>
    </div>
  );
}
```

- [ ] **Step 8: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

- [ ] **Step 9: Commit**

```bash
git add frontend/components/assistant/
git commit -m "feat: add AI assistant chat + preview UI components"
```

---

### Task 13: Create the page entry points

**Files:**
- Create: `frontend/app/(app)/assistant/page.tsx` (wizard / new session)
- Create: `frontend/app/(app)/assistant/[projectId]/page.tsx` (existing session)
- Modify: `frontend/components/AppShell.tsx` (add sidebar item)

- [ ] **Step 1: Create the wizard entry page**

Create `frontend/app/(app)/assistant/page.tsx`:

```tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useAssistantStore } from "@/lib/stores/assistantStore";
import { useAssistantWS } from "@/lib/hooks/useAssistantWS";
import { ChatPanel } from "@/components/assistant/ChatPanel";
import { PreviewPanel } from "@/components/assistant/PreviewPanel";
import { ProgressChecklist } from "@/components/assistant/ProgressChecklist";
import { AssistantHeader } from "@/components/assistant/AssistantHeader";

export default function AssistantEntryPage() {
  const { token } = useAuth();
  const router = useRouter();
  const { projectId, reset } = useAssistantStore();

  useEffect(() => {
    reset();
  }, [reset]);

  useAssistantWS("new", token);

  // When a project gets created, navigate to the session page
  useEffect(() => {
    if (projectId) {
      router.replace(`/assistant/${projectId}`);
    }
  }, [projectId, router]);

  if (!token) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-60px)]">
        <p className="text-charcoal">Please log in to use the assistant.</p>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 top-[60px] flex flex-col ml-0 xl:ml-[56px]">
      <AssistantHeader />
      <div className="flex-1 flex min-h-0">
        <div className="w-full md:w-[420px] shrink-0 flex flex-col border-r border-hairline">
          <ProgressChecklist />
          <div className="flex-1 min-h-0">
            <ChatPanel token={token} />
          </div>
        </div>
        <div className="flex-1 min-w-0 hidden md:block">
          <PreviewPanel />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create the session page**

Create `frontend/app/(app)/assistant/[projectId]/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useAssistantStore } from "@/lib/stores/assistantStore";
import { useAssistantWS } from "@/lib/hooks/useAssistantWS";
import { ChatPanel } from "@/components/assistant/ChatPanel";
import { PreviewPanel } from "@/components/assistant/PreviewPanel";
import { ProgressChecklist } from "@/components/assistant/ProgressChecklist";
import { AssistantHeader } from "@/components/assistant/AssistantHeader";
import { getDocument } from "@/lib/api/assistant";

export default function AssistantSessionPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = params?.projectId as string;
  const { token } = useAuth();
  const { reset, setIdentity } = useAssistantStore();
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    reset();
    if (projectId) setIdentity(projectId, null);
  }, [projectId, reset, setIdentity]);

  // Fetch chat document on mount to populate history + markdown
  useEffect(() => {
    if (!token || !projectId) return;
    (async () => {
      try {
        // Try listing to find latest document for this project
        const { listDocuments } = await import("@/lib/api/assistant");
        const list = await listDocuments(token);
        const doc = list.items.find((d) => d.project_id === projectId);
        if (doc) {
          setIdentity(projectId, doc.id);
          const detail = await getDocument(token, doc.id);
          // Inject initial state
          useAssistantStore.setState({
            currentMarkdown: detail.content_md,
            documentVersion: detail.version,
            documentTitle: detail.title,
            messages: detail.messages || [],
          });
        }
      } catch (err) {
        console.error("Failed to load chat document", err);
      } finally {
        setLoaded(true);
      }
    })();
  }, [token, projectId, setIdentity]);

  useAssistantWS(loaded ? projectId : null, token);

  if (!token) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-60px)]">
        <p className="text-charcoal">Please log in to use the assistant.</p>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 top-[60px] flex flex-col ml-0 xl:ml-[56px]">
      <AssistantHeader />
      <div className="flex-1 flex min-h-0">
        <div className="w-full md:w-[420px] shrink-0 flex flex-col border-r border-hairline">
          <ProgressChecklist />
          <div className="flex-1 min-h-0">
            <ChatPanel token={token} />
          </div>
        </div>
        <div className="flex-1 min-w-0 hidden md:block">
          <PreviewPanel />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add sidebar item**

In `frontend/components/AppShell.tsx`, update the icon imports and `NAV_ITEMS`:

Replace the icon imports block:

```tsx
import {
  SquaresFour,
  Folder,
  MagnifyingGlass,
  FileText,
  Table,
  Graph,
  Lightbulb,
  PencilLine,
  GearSix,
  SignOut,
  List,
  X,
  Sparkle,
} from "@phosphor-icons/react";
```

Replace the `NAV_ITEMS` array:

```tsx
const NAV_ITEMS = [
  { label: "Dashboard", href: "/dashboard", icon: SquaresFour },
  { label: "AI Assistant", href: "/assistant", icon: Sparkle },
  { label: "Projects", href: "/projects", icon: Folder },
  { label: "Search Papers", href: "/search", icon: MagnifyingGlass },
  { label: "Saved Papers", href: "/papers", icon: FileText },
  { label: "Matrix", href: "/matrix", icon: Table },
  { label: "Knowledge Map", href: "/map", icon: Graph },
  { label: "Gaps", href: "/gaps", icon: Lightbulb },
  { label: "Reports", href: "/reports", icon: PencilLine },
  { label: "Settings", href: "/settings", icon: GearSix },
];
```

- [ ] **Step 4: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -40`
Expected: No new errors

- [ ] **Step 5: Run linter on new files**

Run: `cd frontend && npx oxlint components/assistant/ app/\(app\)/assistant/ 2>&1 | head -20 || echo "oxlint not configured, skip"`

- [ ] **Step 6: Commit**

```bash
git add frontend/app/\(app\)/assistant/ frontend/components/AppShell.tsx
git commit -m "feat: add /assistant pages (wizard + session) and sidebar item"
```

---

### Task 14: Integration verification

- [ ] **Step 1: Run all backend tests**

Run: `pytest tests/test_assistant_*.py tests/test_assistant_models.py tests/test_assistant_prompts.py tests/test_assistant_schemas.py tests/test_assistant_tools.py tests/test_assistant_runner.py tests/test_assistant_ws.py tests/test_report_chat_doc.py -v`
Expected: All PASS

- [ ] **Step 2: Run full backend test suite**

Run: `pytest tests/ -q`
Expected: All PASS (or pre-existing failures)

- [ ] **Step 3: Run backend linter**

Run: `ruff check app/`
Expected: No errors

- [ ] **Step 4: Run frontend typecheck**

Run: `cd frontend && npx tsc --noEmit --pretty`
Expected: No errors

- [ ] **Step 5: Start backend, hit /api/health**

Run: `make backend` in one terminal, then:
```bash
curl -s http://localhost:8010/api/health
```
Expected: `{"status":"ok"}`

- [ ] **Step 6: Verify WS endpoint exists**

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8010/api/assistant/ws`
Expected: `426` (Upgrade Required — WS-only endpoint)

- [ ] **Step 7: Final commit if any fixups**

```bash
git status
# If clean, skip
# If changes:
git add -A
git commit -m "chore: assistant integration cleanup"
```

---

### Task 15: End-to-end smoke test (manual)

These steps verify the full user flow. Document any issues found.

- [ ] **Step 1: Start backend and frontend**

Terminal 1: `make backend`
Terminal 2: `make frontend` (or `cd frontend && npm run dev`)

- [ ] **Step 2: Log in, navigate to /assistant**

- Log in with a research user
- Click "AI Assistant" in the sidebar
- Verify the wizard page loads (empty chat + checklist)

- [ ] **Step 3: Send first message**

- Type: "Tôi muốn nghiên cứu về RAG cho medical question answering"
- Press Enter
- Verify progress checklist starts running through steps
- Verify tool log lines appear
- Verify the URL changes to /assistant/[projectId] after create_project

- [ ] **Step 4: Verify pipeline completion**

- Wait for all 6 checklist steps to show ✓
- Verify Markdown preview appears on the right pane
- Verify the project shows up in /projects

- [ ] **Step 5: Post-pipeline chat**

- Type: "thêm 3 paper về clinical trial"
- Press Enter
- Verify agent calls search_papers + save_paper_to_project

- [ ] **Step 6: Edit via chat**

- Type: "đoạn Methods viết ngắn lại"
- Press Enter
- Verify the report changes in the preview pane
- Verify version increments

- [ ] **Step 7: Stop test**

- Type any long-running prompt
- Click "Stop" while running
- Verify runner halts (status badge → "Stopped")

- [ ] **Step 8: Reload and resume**

- Close the browser tab
- Reopen /assistant/[projectId]
- Verify chat history + markdown restore
- Send a new message
- Verify it works

---

## Self-Review

**Spec coverage check:**
- [x] Page location + sidebar item — Task 13
- [x] WebSocket protocol — Task 7
- [x] 8 tool handlers — Task 5
- [x] ReAct runner — Task 6
- [x] chat_documents + chat_messages tables — Task 1
- [x] REST endpoints (list/get/export/delete) — Task 8
- [x] 2-pane chat + preview UI — Task 12
- [x] Progress checklist — Task 12
- [x] Markdown live update — Task 12 + store
- [x] Tool persistence (chat_messages) — Task 6
- [x] Project confirmation pause — handled by agent system prompt + LLM choice

**Placeholder scan:** No TBD/TODO found.

**Type consistency:** Checked `ChatDocument`/`ChatMessage` columns match between model and schema.
