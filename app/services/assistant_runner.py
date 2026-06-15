"""AssistantRunner — ReAct agent loop for the AI assistant chat page."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import suppress
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.ai.prompts import ASSISTANT_SYSTEM, TOOL_DESCRIPTIONS
from app.ai.provider import get_provider
from app.db.models import ChatMessage, User
from app.services.assistant_tools import TOOL_REGISTRY

logger = logging.getLogger(__name__)
_CHUNK_SIZE = 80

# Max characters of a tool result that we feed back to the LLM as
# conversation history. Truncating prevents the agent's context from blowing
# up on large results (e.g. 50-paper search result with abstracts).
#
# Bumped from 1500 → 16000 because the previous limit was so small that only
# 2-3 papers from search_papers survived truncation, causing the LLM to save
# just 1 paper per turn and get stuck. 16K chars is ~4K tokens, well within
# the model's budget and enough to surface 100+ compact paper briefs.
_TOOL_RESULT_SUMMARY_CHARS = 16_000

# Tools whose results are sometimes structured into brief/full sections.
# The summary truncation must keep the LLM-facing brief field intact first;
# these tools emit their own compact view as the first key in the result.
_BRIEF_FIRST_TOOLS = {"search_papers", "qa_search_papers"}


# ── Per-project runner registry (for REST /stop) ──────────────────────────
# Maps project_id → AssistantRunner so the /stop endpoint can find the
# running agent without needing a WebSocket frame.
_RUNNER_REGISTRY: dict[UUID, "AssistantRunner"] = {}
_REGISTRY_LOCK = asyncio.Lock()


async def register_runner(project_id: UUID, runner: "AssistantRunner") -> None:
    async with _REGISTRY_LOCK:
        _RUNNER_REGISTRY[project_id] = runner


async def unregister_runner(project_id: UUID) -> None:
    async with _REGISTRY_LOCK:
        _RUNNER_REGISTRY.pop(project_id, None)


def get_runner(project_id: UUID) -> "AssistantRunner | None":
    """Return the currently running runner for *project_id* (synchronous lookup)."""
    return _RUNNER_REGISTRY.get(project_id)


async def persist_assistant_message(
    db,
    document_id: UUID | None,
    project_id: UUID | None,
    role: str,
    content: str,
    tool_name: str | None = None,
    tool_args: dict | None = None,
    tool_result: dict | None = None,
) -> None:
    """Persist a chat message to the DB. Best-effort — never raises."""
    if document_id is None or project_id is None:
        return
    try:
        msg = ChatMessage(
            document_id=document_id,
            project_id=project_id,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_args=tool_args or {},
            tool_result=tool_result or {},
        )
        db.add(msg)
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to persist chat message: %s", exc)
        with suppress(Exception):
            await db.rollback()


async def load_assistant_history(db, document_id: UUID | None) -> list[dict[str, str]]:
    """Load persisted chat context before each assistant turn."""
    if document_id is None:
        return []

    stmt = (
        select(ChatMessage)
        .where(ChatMessage.document_id == document_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = (await db.execute(stmt)).scalars().all()
    history: list[dict[str, str]] = []
    for message in messages:
        if message.role in {"user", "assistant"}:
            history.append({"role": message.role, "content": message.content})
        elif message.role == "tool_log":
            history.append({"role": "user", "content": f"Previous tool result: {message.content}"})
    return history[-30:]


def _message_chunks(message: str) -> list[str]:
    return [message[i : i + _CHUNK_SIZE] for i in range(0, len(message), _CHUNK_SIZE)]


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
        ws_send=None,
        max_iterations: int = 20,
        event_queue: asyncio.Queue | None = None,
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
        # If provided, every event is also pushed into this queue so the
        # SSE endpoint can stream it to the browser in real time.
        self.event_queue: asyncio.Queue | None = event_queue
        self._task: asyncio.Task | None = None

    async def emit(self, event: dict) -> None:
        """Send an event to all consumers (WS sink, queue, in-memory log)."""
        self.events.append(event)
        if self.event_queue is not None:
            try:
                self.event_queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("SSE event queue full, dropping event")
        if self.ws_send:
            try:
                await self.ws_send(event)
            except Exception as exc:
                logger.debug("ws_send failed: %s", exc)

    def start(self, user_message: str) -> asyncio.Task:
        """Launch run_turn as a background task. Returns the task handle."""
        if self._task is not None and not self._task.done():
            return self._task
        self._task = asyncio.create_task(self.run_turn(user_message))
        return self._task

    async def wait_done(self) -> None:
        """Wait for the background task (if any) to complete."""
        if self._task is None:
            return
        with suppress(asyncio.CancelledError):
            await self._task

    async def run_turn(self, user_message: str) -> None:
        """One user message → agent loop until done, stopped, or max iterations."""
        if not self.history:
            self.history = await load_assistant_history(self.db, self.document_id)
        self.history.append({"role": "user", "content": user_message})
        await persist_assistant_message(
            self.db, self.document_id, self.project_id, "user", user_message
        )
        await self.emit({"type": "log", "level": "info", "message": "AI đang thinking..."})

        # Register so /stop endpoint can find us
        if self.project_id is not None:
            await register_runner(self.project_id, self)

        iterations = 0
        t0 = time.monotonic()
        try:
            await self._run_loop(iterations, t0)
        finally:
            if self.project_id is not None:
                await unregister_runner(self.project_id)

    async def _run_loop(self, iterations: int, t0: float) -> None:
        while iterations < self.max_iterations:
            if self.stopped.is_set():
                await self.emit({"type": "stopped"})
                return

            iterations += 1

            try:
                provider = get_provider()
                result = await provider.complete_structured(
                    messages=self.history,
                    schema={
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "Natural-language response shown to user",
                            },
                            "tool_calls": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string",
                                            "enum": list(TOOL_REGISTRY.keys()),
                                        },
                                        "args": {"type": "object"},
                                    },
                                    "required": ["name", "args"],
                                },
                            },
                        },
                        "required": ["message"],
                    },
                    tool_name="assistant_decide",
                    system=ASSISTANT_SYSTEM
                    + "\n\nAvailable tools:\n"
                    + json.dumps(TOOL_DESCRIPTIONS, indent=2),
                    max_tokens=2000,
                )
            except Exception as exc:
                logger.exception("LLM call failed in runner")
                await self.emit(
                    {"type": "error", "message": f"LLM call failed: {exc}", "code": "ai_failure"}
                )
                return

            message = result.get("message", "")
            tool_calls = result.get("tool_calls") or []

            if message:
                for chunk in _message_chunks(message):
                    await self.emit(
                        {
                            "type": "agent_chunk",
                            "delta": chunk,
                            "call_id": f"turn_{iterations}",
                        }
                    )
                    await asyncio.sleep(0)
                await persist_assistant_message(
                    self.db, self.document_id, self.project_id, "assistant", message
                )
                self.history.append({"role": "assistant", "content": message})
                await self.emit({"type": "agent_message", "content": message, "role": "assistant"})

            if not tool_calls:
                await self.emit(
                    {
                        "type": "done",
                        "iterations": iterations,
                        "total_duration_ms": int((time.monotonic() - t0) * 1000),
                    }
                )
                return

            for call in tool_calls:
                if self.stopped.is_set():
                    await self.emit({"type": "stopped"})
                    return

                tool_name = call.get("name")
                tool_args = call.get("args") or {}
                call_id = f"call_{iterations}_{tool_name}"
                await self.emit(
                    {
                        "type": "tool_call",
                        "tool": tool_name,
                        "args": tool_args,
                        "call_id": call_id,
                    }
                )

                handler = TOOL_REGISTRY.get(tool_name)
                if handler is None:
                    err = f"Unknown tool: {tool_name}"
                    await self.emit(
                        {
                            "type": "tool_result",
                            "tool": tool_name,
                            "call_id": call_id,
                            "summary": err,
                            "duration_ms": 0,
                            "ok": False,
                        }
                    )
                    self.history.append(
                        {
                            "role": "user",
                            "content": f"Tool error: {err}. Pick a different tool or stop.",
                        }
                    )
                    continue

                t_tool = time.monotonic()
                try:
                    tool_result = await handler(self.db, self.user, tool_args, self)
                except Exception as exc:
                    logger.exception("Tool %s failed", tool_name)
                    tool_result = {"error": str(exc)[:300]}
                duration_ms = int((time.monotonic() - t_tool) * 1000)
                ok = "error" not in tool_result

                tool_content = (
                    f"Tool: {tool_name}\n"
                    f"Args: {json.dumps(tool_args, default=str)[:500]}\n"
                    f"Result: {json.dumps(tool_result, default=str)[:500]}"
                )
                await persist_assistant_message(
                    self.db,
                    self.document_id,
                    self.project_id,
                    "tool_log",
                    tool_content,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    tool_result=tool_result,
                )

                summary = json.dumps(tool_result, default=str)[:_TOOL_RESULT_SUMMARY_CHARS]
                await self.emit(
                    {
                        "type": "tool_result",
                        "tool": tool_name,
                        "call_id": call_id,
                        "summary": summary,
                        "duration_ms": duration_ms,
                        "ok": ok,
                    }
                )

                self.history.append(
                    {
                        "role": "user",
                        "content": f"Tool '{tool_name}' result: {summary}",
                    }
                )

        await self.emit(
            {
                "type": "done",
                "iterations": iterations,
                "total_duration_ms": int((time.monotonic() - t0) * 1000),
                "reason": "max_iterations",
            }
        )
