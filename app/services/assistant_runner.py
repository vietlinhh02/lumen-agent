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
                await persist_assistant_message(
                    self.db, self.document_id, self.project_id, "assistant", message
                )
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

                await persist_assistant_message(
                    self.db,
                    self.document_id,
                    self.project_id,
                    "tool_log",
                    f"Tool: {tool_name}\nArgs: {json.dumps(tool_args, default=str)[:500]}\nResult: {json.dumps(tool_result, default=str)[:500]}",
                    tool_name=tool_name,
                    tool_args=tool_args,
                    tool_result=tool_result,
                )

                summary = json.dumps(tool_result, default=str)[:1500]
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
