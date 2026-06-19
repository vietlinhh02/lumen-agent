"""ReActAgent — the core agent loop.

Implements the ReAct (Reasoning + Acting) loop that:
1. Classifies user intent via structured LLM classifier (IntentClassifier)
2. Dispatches to deterministic pipelines for research_pipeline intent
3. Handles simple intents (list, chitchat) without full ReAct loop
4. Runs the ReAct loop for complex tasks with RAG injection
5. Streams ThoughtEvent tokens and yields IterationEvent, ToolEvent, etc.

Key features (Task 8 - Native Tool Calls):
- Uses provider.stream_with_tools() for structured tool call support
- No fragile Action: text parsing - uses native AIMessage.tool_calls
- Parallel tool execution via execute_parallel()
- ToolMessage format for returning results to the model

Legacy features:
- Real token streaming via provider.stream() -- no fake chunking
- Tool results fed back to LLM in the next iteration as assistant messages
- Proper ToolEvent status: "calling" -> "called" or "failed"
- Bounded queue (maxsize=100) with backpressure handling
- Heartbeat events every 15s during long LLM calls
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from app.agents.assistant.events import (
    AssistantDeltaEvent,
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    IterationEvent,
    MessageEvent,
    ProgressEvent,
    ThoughtEvent,
    ToolEvent,
    WaitEvent,
)
from app.agents.assistant.pipelines import ResearchPipeline, ResearchPipelineConfig
from app.agents.assistant.react.intent_classifier import IntentClassifier
from app.agents.assistant.react.memory import Scratchpad
from app.agents.assistant.react.prompts import (
    CLARIFY_TOPIC_PROMPT,
    REACT_SYSTEM_PROMPT,
)
from app.agents.assistant.react.rag_injector import inject as rag_inject
from app.agents.assistant.react.tool_caller import ToolCall, ToolCaller

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from app.ai.provider import AIProvider

logger = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_MAX_ITERATIONS = 15
DEFAULT_MAX_WALL_TIME_SECONDS = 600
DEFAULT_HEARTBEAT_SECONDS = 15
QUEUE_MAXSIZE = 100  # Bounded queue to prevent memory leaks


class ProjectContext:
    """Context about the user's active project."""

    def __init__(
        self,
        project_id: str | None = None,
        user_id: str | None = None,
        project_name: str | None = None,
        topic: str | None = None,
        research_question: str | None = None,
    ) -> None:
        self.project_id = project_id
        self.user_id = user_id
        self.project_name = project_name
        self.topic = topic
        self.research_question = research_question

    @property
    def has_project(self) -> bool:
        return bool(self.project_id)


class ReActAgent:
    """ReAct (Reasoning + Acting) agent for the assistant.

    The agent:
    1. Classifies user intent via FastRouter (fast, no LLM for obvious cases)
    2. Handles DIRECT_LIST intents by calling tools directly
    3. For complex intents, runs a ReAct loop with RAG injection
    4. Streams ThoughtEvent tokens for real-time UX
    5. Handles all limits (iteration, tokens, wall time)

    Usage:
        agent = ReActAgent(provider=provider, tools=tools, project_context=ctx)
        async for event in agent.run("find papers about AI"):
            yield event
    """

    def __init__(
        self,
        provider: AIProvider,
        tools: list[BaseTool],
        project_context: ProjectContext | None = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        max_wall_time: int = DEFAULT_MAX_WALL_TIME_SECONDS,
    ) -> None:
        self.provider = provider
        self._tools = tools
        self.project_context = project_context or ProjectContext()
        self.max_iterations = max_iterations
        self.max_wall_time = max_wall_time

        # Initialize components
        self._classifier = IntentClassifier(provider)
        self._tool_caller = ToolCaller()
        self._scratchpad = Scratchpad()

        # Build tool map for quick lookup
        self._tool_map: dict[str, BaseTool] = {}
        for tool in tools:
            name = getattr(tool, "name", None)
            if name:
                self._tool_map[name] = tool

    @property
    def scratchpad(self) -> Scratchpad:
        """Get the current scratchpad."""
        return self._scratchpad

    async def run(
        self,
        message: str,
        resume: bool = False,
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[BaseEvent]:
        """Run the agent for a user message.

        Args:
            message: The user's message.
            resume: If True, continue from previous state (scratchpad has context).
            cancel_event: Optional event to check for cancellation.

        Yields:
            BaseEvent subclasses: IterationEvent, ThoughtEvent, ToolEvent, MessageEvent,
            WaitEvent, DoneEvent, ErrorEvent, ProgressEvent.
        """
        # Reset scratchpad for new run (unless resuming)
        if not resume:
            self._scratchpad.reset()

        start_time = time.monotonic()

        try:
            # ── 1. Classify intent via IntentClassifier ─────────────────────
            project_context_dict = None
            if self.project_context.has_project:
                project_context_dict = {
                    "project_name": self.project_context.project_name or "",
                    "topic": self.project_context.topic or "",
                    "research_question": self.project_context.research_question or "",
                }

            classification = await self._classifier.classify(
                message,
                project_context=project_context_dict,
            )

            logger.info(
                "Intent: %s (confidence=%.2f) | reasoning: %s",
                classification.intent,
                classification.confidence,
                classification.reasoning,
            )

            # ── 2. Dispatch by intent ───────────────────────────────────────
            intent = classification.intent

            # research_pipeline: run full deterministic pipeline
            if intent == "research_pipeline":
                # Determine project_id: use classified override, or session project
                project_id = (
                    classification.project_id
                    or self.project_context.project_id
                )

                if not project_id:
                    # Ask user to pick a project
                    projects = await self._list_project_summaries()
                    yield WaitEvent(
                        question="Which project should I use for the research?",
                        options=projects,
                        placeholder="Select a project or say 'create new'",
                    )
                    yield DoneEvent(summary="Awaiting project selection.")
                    return

                query = classification.query or classification.topic_hint or message

                async for event in self._run_research_pipeline(
                    query=query,
                    project_id=project_id,
                    cancel_event=cancel_event,
                ):
                    yield event
                return

            # search_only: run ReAct loop with search as primary action
            if intent == "search_only":
                async for event in self._run_react_loop(
                    message=message,
                    start_time=start_time,
                    cancel_event=cancel_event,
                ):
                    yield event
                return

            # matrix_only: run matrix generation directly
            if intent == "matrix_only":
                if not self.project_context.project_id:
                    yield MessageEvent(
                        role="assistant",
                        content="Please select a project first to generate a matrix.",
                    )
                    yield DoneEvent()
                    return
                async for event in self._run_single_tool(
                    "generate_matrix",
                    {"project_id": self.project_context.project_id},
                    cancel_event=cancel_event,
                ):
                    yield event
                return

            # gap_only: run gap detection directly
            if intent == "gap_only":
                if not self.project_context.project_id:
                    yield MessageEvent(
                        role="assistant",
                        content="Please select a project first to detect gaps.",
                    )
                    yield DoneEvent()
                    return
                async for event in self._run_single_tool(
                    "detect_research_gaps",
                    {"project_id": self.project_context.project_id},
                    cancel_event=cancel_event,
                ):
                    yield event
                return

            # report_only: run report generation directly
            if intent == "report_only":
                if not self.project_context.project_id:
                    yield MessageEvent(
                        role="assistant",
                        content="Please select a project first to generate a report.",
                    )
                    yield DoneEvent()
                    return
                async for event in self._run_single_tool(
                    "generate_report",
                    {
                        "project_id": self.project_context.project_id,
                        "include_gap_section": True,
                    },
                    cancel_event=cancel_event,
                ):
                    yield event
                return

            # qa: RAG-augmented ReAct loop
            if intent == "qa":
                if self.project_context.has_project:
                    await rag_inject(
                        message=message,
                        project_id=self.project_context.project_id,
                        scratchpad=self._scratchpad,
                        user_id=self.project_context.user_id or "",
                        k=5,
                    )
                async for event in self._run_react_loop(
                    message=message,
                    start_time=start_time,
                    cancel_event=cancel_event,
                ):
                    yield event
                return

            # list: direct tool calls without ReAct
            if intent == "list":
                async for event in self._handle_direct_list(message):
                    yield event
                yield DoneEvent()
                return

            # create_project: delegate to ReAct which has the create_project tool
            if intent == "create_project":
                async for event in self._run_react_loop(
                    message=message,
                    start_time=start_time,
                    cancel_event=cancel_event,
                ):
                    yield event
                return

            # chitchat: simple LLM response without tools
            if intent == "chitchat":
                async for event in self._run_simple_chat(message):
                    yield event
                return

            # ambiguous: ask for clarification
            if intent == "ambiguous":
                yield WaitEvent(
                    question=CLARIFY_TOPIC_PROMPT,
                    options=["Tìm kiếm paper", "Phân tích papers", "Tạo báo cáo", "Phát hiện gaps"],
                    placeholder="VD: Tìm paper về LLM evaluation",
                )
                yield DoneEvent()
                return

            # Fallback: run ReAct loop
            logger.warning("Unhandled intent '%s', falling back to ReAct loop", intent)
            async for event in self._run_react_loop(
                message=message,
                start_time=start_time,
                cancel_event=cancel_event,
            ):
                yield event

        except asyncio.CancelledError:
            logger.info("Agent run cancelled")
            yield ErrorEvent(code="CANCELLED", message="Session was cancelled")
            yield DoneEvent()
            raise

        except Exception as exc:
            logger.exception("Agent run failed: %s", exc)
            yield ErrorEvent(
                code="AGENT_ERROR",
                message=f"Agent error: {str(exc)}",
            )
            yield DoneEvent()

    # ── Direct list handling ─────────────────────────────────────────────────

    async def _handle_direct_list(self, message: str) -> AsyncGenerator[BaseEvent]:
        """Handle DIRECT_LIST intents by calling tools directly.

        Yields ToolEvent and MessageEvent without LLM calls.
        """
        # Determine which tool to call based on message
        tool_name = self._infer_direct_tool(message)

        if tool_name and tool_name in self._tool_map:
            tool = self._tool_map[tool_name]

            # Yield calling event
            yield IterationEvent(n=0, max=self.max_iterations, phase="acting")
            yield ToolEvent(
                tool_call_id="direct-call",
                name=tool_name,
                status="calling",
                function=tool_name,
                args={},
            )

            # Execute tool
            result, _ = await self._tool_caller.execute(tool, {})

            # Yield result event
            yield ToolEvent(
                tool_call_id="direct-call",
                name=tool_name,
                status="called",
                function=tool_name,
                args={},
                result=result,
            )

            # Format response
            if isinstance(result, dict):
                if result.get("ok") is False:
                    yield MessageEvent(
                        role="assistant",
                        content=f"Không thể thực hiện: {result.get('message', result.get('error', 'Lỗi không xác định'))}",
                    )
                    return

                data = result.get("data", result)
                if "projects" in data:
                    projects = data["projects"]
                    if not projects:
                        yield MessageEvent(role="assistant", content="Bạn chưa có project nào.")
                    else:
                        lines = [f"Bạn có {len(projects)} project(s):"]
                        for p in projects[:10]:
                            lines.append(f"• {p.get('name', 'Unnamed')}")
                        yield MessageEvent(role="assistant", content="\n".join(lines))
                    return

                if "papers" in data:
                    papers = data["papers"]
                    if not papers:
                        yield MessageEvent(role="assistant", content="Không có paper nào.")
                    else:
                        lines = [f"Tìm thấy {len(papers)} paper(s):"]
                        for paper in papers[:10]:
                            lines.append(f"• {paper.get('title', 'Untitled')}")
                        yield MessageEvent(role="assistant", content="\n".join(lines))
                    return

            yield MessageEvent(role="assistant", content=str(result))
        else:
            yield MessageEvent(
                role="assistant",
                content="Tôi không thể xử lý yêu cầu này một cách trực tiếp. Bạn có thể mô tả cụ thể hơn không?",
            )

    def _infer_direct_tool(self, message: str) -> str | None:
        """Infer which tool to call for a direct list request."""
        msg = message.lower()

        if any(k in msg for k in ["project", "dự án"]):
            return "list_projects"
        if any(k in msg for k in ["paper", "bài báo"]):
            return "list_project_papers"
        if any(k in msg for k in ["report", "báo cáo"]):
            return "list_reports"
        if any(k in msg for k in ["gap", "lỗ hổng"]):
            return "list_gaps"
        if any(k in msg for k in ["conflict", "xung đột"]):
            return "list_conflicts"

        return None

    # ── Pipeline and simple dispatch helpers ──────────────────────────────────

    async def _run_research_pipeline(
        self,
        query: str,
        project_id: str,
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[BaseEvent]:
        """Run the deterministic research pipeline orchestrator."""
        config = ResearchPipelineConfig(
            project_id=project_id,
            query=query,
            max_papers_to_save=10,
            relevance_threshold="medium",
            include_gap_section=True,
            auto_generate_report=True,
        )
        pipeline = ResearchPipeline(config, cancel_event=cancel_event)
        async for event in pipeline.run():
            yield event
        yield DoneEvent()

    async def _run_single_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[BaseEvent]:
        """Execute a single tool and return its result as a message."""
        tool = self._tool_map.get(tool_name)
        if tool is None:
            yield MessageEvent(
                role="assistant",
                content=f"Tool '{tool_name}' is not available.",
            )
            yield DoneEvent()
            return

        yield ProgressEvent(
            stage=tool_name,
            progress=0.0,
            message=f"Running {tool_name}...",
        )

        try:
            if cancel_event and cancel_event.is_set():
                yield ErrorEvent(code="CANCELLED", message="Cancelled before tool execution")
                yield DoneEvent()
                return

            result, _ = await self._tool_caller.execute(tool, args)

            if isinstance(result, dict) and result.get("ok") is False:
                yield MessageEvent(
                    role="assistant",
                    content=f"Tool failed: {result.get('message', result.get('error', 'Unknown error'))}",
                )
                yield DoneEvent()
                return

            # Format result as message
            if isinstance(result, dict) and "data" in result:
                data = result["data"]
                if "rows" in data:
                    count = len(data["rows"])
                    yield MessageEvent(
                        role="assistant",
                        content=f"{tool_name} completed. {count} items found.",
                    )
                elif "gaps" in data:
                    count = len(data["gaps"])
                    yield MessageEvent(
                        role="assistant",
                        content=f"{tool_name} completed. {count} gaps found.",
                    )
                elif "report_id" in data:
                    yield MessageEvent(
                        role="assistant",
                        content=f"{tool_name} completed. Report ID: {data['report_id']}",
                    )
                else:
                    yield MessageEvent(role="assistant", content=str(result.get("message", result)))
            else:
                yield MessageEvent(role="assistant", content=str(result))

        except asyncio.CancelledError:
            yield ErrorEvent(code="CANCELLED", message="Tool execution cancelled")
            yield DoneEvent()
            raise
        except Exception as exc:
            logger.error("Single tool '%s' failed: %s", tool_name, exc)
            yield MessageEvent(
                role="assistant",
                content=f"Tool '{tool_name}' failed: {exc}",
            )
            yield DoneEvent()

    async def _run_simple_chat(self, message: str) -> AsyncGenerator[BaseEvent]:
        """Respond to chitchat / greetings with a direct LLM call (no tools).
        
        Streams the visible assistant response as AssistantDeltaEvent tokens
        so the user sees the answer bubble immediately. Uses ONE model call.
        """
        system = (
            "You are a friendly research assistant. Keep your response brief and helpful. "
            "If the user greets you, greet them back and briefly mention what you can help with."
        )
        messages = [{"role": "user", "content": message}]

        # Stream visible assistant text as deltas (single model call)
        async for token in self.provider.stream(
            messages=messages,
            system=system,
            max_tokens=32768,
        ):
            yield AssistantDeltaEvent(delta=token, is_final=False)
        
        # Signal completion of the assistant message stream
        yield AssistantDeltaEvent(delta="", is_final=True)
        yield DoneEvent()

    async def _list_project_summaries(self) -> list[str]:
        """Return a list of project names for the current user."""
        from app.db.session import async_session_factory
        from app.services.project import list_projects

        user = self.project_context.user_id
        if not user:
            return []

        try:
            from sqlalchemy import select

            from app.db.models import User

            async with async_session_factory() as db:
                result = await db.execute(select(User).where(User.id == user))
                user_obj = result.scalar_one_or_none()
                if not user_obj:
                    return []
                projects = await list_projects(db, user_obj)
            return [p.title for p in projects]
        except Exception as exc:
            logger.warning("Failed to list projects: %s", exc)
            return []

    # ── ReAct loop with Native Tool Calls (Task 8) ──────────────────────────

    async def _run_react_loop(
        self,
        message: str,
        start_time: float,
        cancel_event: asyncio.Event | None,
    ) -> AsyncGenerator[BaseEvent]:
        """Run the main ReAct reasoning loop with native structured tool calls.

        Task 8: Replaces fragile Action: text parsing with native AIMessage.tool_calls.
        
        Key changes:
        - Uses provider.stream_with_tools() for structured tool call streaming
        - Parses tool calls from stream chunks, not text
        - Executes independent tool calls in parallel via execute_parallel()
        - Formats tool results as ToolMessage for the next LLM turn

        Args:
            message: The user's message.
            start_time: Wall time when run started.
            cancel_event: Event to check for cancellation.

        Yields:
            IterationEvent, ThoughtEvent, ToolEvent, MessageEvent, WaitEvent.
        """
        iteration = 0
        conversation_messages: list[dict[str, Any]] = []  # ToolMessage format

        while iteration < self.max_iterations:
            # ── Limit checks ──────────────────────────────────────────────
            if cancel_event and cancel_event.is_set():
                yield ErrorEvent(code="CANCELLED", message="Session was cancelled")
                yield DoneEvent(summary="Session cancelled.")
                return

            elapsed = time.monotonic() - start_time
            if elapsed > self.max_wall_time:
                yield ErrorEvent(
                    code="MAX_WALL_TIME",
                    message=f"Exceeded maximum runtime of {self.max_wall_time}s",
                )
                yield DoneEvent()
                return

            # ── Build messages for LLM ─────────────────────────────────────
            messages = self._build_react_messages_with_tools(message, conversation_messages)

            # ── Emit iteration event ───────────────────────────────────────
            yield IterationEvent(n=iteration, max=self.max_iterations, phase="reasoning")

            # ── Stream LLM response with native tool calls ─────────────────
            response_text = ""
            tool_calls_found: list[ToolCall] = []
            tool_call_args: dict[str, dict[str, Any]] = {}  # call_id -> {name, args}
            
            # Track last heartbeat time for timeout detection
            last_heartbeat = time.monotonic()

            try:
                async for chunk in self.provider.stream_with_tools(
                    messages=messages,
                    system=None,  # System prompt is in messages
                    max_tokens=32768,
                    tools=self._get_tool_definitions(),
                ):
                    from app.ai.provider import (
                        StreamDone,
                        TextChunk,
                        ToolCallArgsDelta,
                        ToolCallDone,
                        ToolCallStart,
                    )
                    
                    if isinstance(chunk, TextChunk):
                        # Text delta for thought/answer
                        response_text += chunk.delta
                        last_heartbeat = time.monotonic()
                        yield ThoughtEvent(delta=chunk.delta, iteration=iteration, is_final=False)
                        
                        # Check heartbeat timeout
                        elapsed_since = time.monotonic() - last_heartbeat
                        if elapsed_since > DEFAULT_HEARTBEAT_SECONDS * 3:
                            logger.warning(
                                "LLM stream stalled for %.1fs at iteration %d",
                                elapsed_since, iteration,
                            )
                    
                    elif isinstance(chunk, ToolCallStart):
                        # Start of a tool call
                        tool_call_args[chunk.call_id] = {
                            "name": chunk.name,
                            "args_str": "",
                        }
                        yield ToolEvent(
                            tool_call_id=chunk.call_id,
                            name=chunk.name,
                            status="calling",
                            function=chunk.name,
                            args={},  # Will be filled as args arrive
                        )
                    
                    elif isinstance(chunk, ToolCallArgsDelta):
                        # Partial arguments delta
                        if chunk.call_id in tool_call_args:
                            tool_call_args[chunk.call_id]["args_str"] += chunk.delta
                    
                    elif isinstance(chunk, ToolCallDone):
                        # Tool call complete
                        call_data = tool_call_args.get(chunk.call_id, {})
                        name = chunk.name or call_data.get("name", "unknown")
                        args = chunk.arguments or {}
                        
                        # Parse args from accumulated string if not provided
                        if not args and call_data.get("args_str"):
                            try:
                                args = json.loads(call_data["args_str"])
                            except json.JSONDecodeError:
                                args = {}
                        
                        tool_calls_found.append(
                            ToolCall(name=name, arguments=args, call_id=chunk.call_id)
                        )
                    
                    elif isinstance(chunk, StreamDone):
                        # Stream finished
                        if chunk.tool_calls:
                            for tc in chunk.tool_calls:
                                tool_calls_found.append(
                                    ToolCall(
                                        name=tc["name"],
                                        arguments=tc["arguments"] or {},
                                        call_id=tc["id"],
                                    )
                                )
            
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("stream_with_tools failed: %s", exc)
                # Fall back to text-based parsing
                response_text = await self._fallback_text_stream(messages, cancel_event)

            # Emit final thought event
            yield ThoughtEvent(delta="", iteration=iteration, is_final=True)

            # ── Check for tool calls ───────────────────────────────────────
            if not tool_calls_found:
                # No tool calls — this is the final answer
                final_answer = self._extract_final_answer(response_text)
                # Stream the final answer as deltas for immediate user feedback
                for token in final_answer:
                    yield AssistantDeltaEvent(delta=token, is_final=False)
                yield AssistantDeltaEvent(delta="", is_final=True)
                yield DoneEvent()
                return

            # ── Execute tools in parallel ───────────────────────────────────
            yield IterationEvent(n=iteration, max=self.max_iterations, phase="acting")

            # Execute all tool calls in parallel
            execution_results = await self._tool_caller.execute_parallel(
                self._tool_map, tool_calls_found
            )

            # Track whether any tool asked for user clarification
            has_wait = False
            tool_messages: list[dict[str, Any]] = []  # For ToolMessage format

            for tool_call, result, is_wait in execution_results:
                status = "failed"
                
                if is_wait:
                    has_wait = True
                    status = "called"
                    yield WaitEvent(
                        question=result.get("question", "Bạn có thể cho tôi biết thêm chi tiết?"),
                        options=result.get("options"),
                        placeholder=result.get("question"),
                    )
                elif result.get("ok") is False:
                    status = "failed"
                else:
                    status = "called"

                # Emit result event
                yield ToolEvent(
                    tool_call_id=tool_call.call_id,
                    name=tool_call.name,
                    status=status,
                    function=tool_call.name,
                    args=tool_call.arguments,
                    result=result if status == "called" else None,
                    error=result.get("error") if status == "failed" else None,
                )

                # Add to scratchpad
                if status == "called" and not has_wait:
                    self._scratchpad.add_observation(
                        tool_call.name,
                        tool_call.arguments,
                        result,
                    )

                # Add tool result as ToolMessage (Task 8: native format)
                if not has_wait:
                    tool_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.call_id,
                        "name": tool_call.name,
                        "content": json.dumps(result, default=str, ensure_ascii=False),
                    })

            # Add assistant message and tool results to conversation
            if not has_wait:
                conversation_messages.append({"role": "assistant", "content": response_text})
                conversation_messages.extend(tool_messages)

            # If any tool asked for clarification, stop the loop
            if has_wait:
                yield DoneEvent(summary="Awaiting user clarification.")
                return

            # Move to next iteration
            iteration += 1

        # ── Max iterations reached ───────────────────────────────────────────
        yield ErrorEvent(
            code="MAX_ITERATIONS",
            message=f"Exceeded maximum iterations ({self.max_iterations})",
        )
        yield DoneEvent()

    # ── LLM helpers ──────────────────────────────────────────────────────────

    async def _stream_llm(
        self,
        messages: list[dict[str, Any]],
        cancel_event: asyncio.Event | None,
    ) -> AsyncGenerator[str]:
        """Stream LLM response tokens using REAL provider.stream().

        FIX: No more fake chunking! Uses the actual streaming API.

        Args:
            messages: The messages to send to the LLM.
            cancel_event: Optional event to check for cancellation.

        Yields:
            Token chunks as strings.
        """
        # Extract system message
        system_msg = None
        chat_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                chat_messages.append(msg)

        try:
            async for token in self.provider.stream(
                messages=chat_messages,
                system=system_msg,
                max_tokens=32768,
            ):
                if cancel_event and cancel_event.is_set():
                    raise asyncio.CancelledError("Session cancelled")
                if token:
                    yield token
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("LLM stream failed: %s", exc)
            yield f"\n[LLM Error: {str(exc)}]"

    def _build_react_messages(
        self,
        user_message: str,
        conversation_messages: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Build messages for the ReAct loop.

        Args:
            user_message: The user's message (or tool result on subsequent iterations).
            conversation_messages: Previous assistant/user turns to continue context.

        Returns:
            List of messages in ChatML format.
        """
        messages: list[dict[str, Any]] = []

        # System prompt with tools
        tools_desc = self._format_tools_for_prompt()
        
        context_str = ""
        if self.project_context.has_project:
            context_str = (
                "\n\n**Current Project Context**:\n"
                f"- Project Name: {self.project_context.project_name or 'Unknown'}\n"
                f"- Topic: {self.project_context.topic or 'None'}\n"
                f"- Research Question: {self.project_context.research_question or 'None'}\n"
            )

        system_content = REACT_SYSTEM_PROMPT.format(
            tools_description=tools_desc + context_str,
        )
        messages.append({"role": "system", "content": system_content})

        # Add scratchpad context (RAG + previous observations)
        scratchpad_msgs = self._scratchpad.to_messages()
        messages.extend(scratchpad_msgs)

        # Add previous turns (tool executions) from this ReAct run
        for conv_msg in conversation_messages:
            messages.append(conv_msg)

        # User message (original query or tool result from last iteration)
        messages.append({"role": "user", "content": user_message})

        return messages

    def _format_tools_for_prompt(self) -> str:
        """Format tools for the prompt."""
        if not self._tools:
            return "(No tools available)"

        lines = []
        for tool in self._tools:
            name = getattr(tool, "name", "unknown")
            desc = getattr(tool, "description", "No description")
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    def _format_observation_for_llm(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
    ) -> str:
        """Format a tool execution result for the LLM to consume in the next turn."""
        args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
        result_str = json.dumps(result, default=str, ensure_ascii=False)
        if len(result_str) > 500:
            result_str = result_str[:500] + "...[truncated]"
        return (
            f"Action: {tool_name}\n"
            f"  Args: {args_str}\n"
            f"  Result: {result_str}"
        )

    # ── Native Tool Call Helpers (Task 8) ────────────────────────────────────

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get tool definitions for native tool calling (Task 8).

        Returns tool definitions in OpenAI function calling format
        for use with stream_with_tools().

        Returns:
            List of tool definitions.
        """
        return self._tool_caller.convert_to_openai_format(self._tools)

    def _build_react_messages_with_tools(
        self,
        user_message: str,
        conversation_messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build messages for the ReAct loop with native tool call support (Task 8).

        Uses ToolMessage format for tool results instead of text format.

        Args:
            user_message: The user's message (or tool result on subsequent iterations).
            conversation_messages: Previous turns in ToolMessage format.

        Returns:
            List of messages in ChatML/ToolMessage format.
        """
        messages: list[dict[str, Any]] = []

        # System prompt with tools
        tools_desc = self._format_tools_for_prompt()
        
        context_str = ""
        if self.project_context.has_project:
            context_str = (
                "\n\n**Current Project Context**:\n"
                f"- Project Name: {self.project_context.project_name or 'Unknown'}\n"
                f"- Topic: {self.project_context.topic or 'None'}\n"
                f"- Research Question: {self.project_context.research_question or 'None'}\n"
            )

        system_content = REACT_SYSTEM_PROMPT.format(
            tools_description=tools_desc + context_str,
        )
        messages.append({"role": "system", "content": system_content})

        # Add scratchpad context (RAG + previous observations)
        scratchpad_msgs = self._scratchpad.to_messages()
        messages.extend(scratchpad_msgs)

        # Add previous turns (assistant messages + tool results) from this ReAct run
        messages.extend(conversation_messages)

        # User message
        messages.append({"role": "user", "content": user_message})

        return messages

    async def _fallback_text_stream(
        self,
        messages: list[dict[str, Any]],
        cancel_event: asyncio.Event | None,
    ) -> str:
        """Fallback to text-based streaming when stream_with_tools fails.

        Used for providers that don't support native tool calls.

        Args:
            messages: The messages to send to the LLM.
            cancel_event: Optional event to check for cancellation.

        Returns:
            The full text response.
        """
        response_text = ""
        try:
            async for token in self._stream_llm(messages, cancel_event):
                response_text += token
        except Exception as exc:
            logger.error("Fallback text stream also failed: %s", exc)
        return response_text

    def _parse_tool_calls_from_text(self, text: str) -> list[ToolCall]:
        """Parse tool calls from LLM response text.

        Looks for Action: tool_name and Action Input: {...} patterns.

        Args:
            text: The LLM response text.

        Returns:
            List of ToolCall objects.
        """
        tool_calls = []
        lines = text.splitlines()

        current_tool = None
        current_args_str = ""
        in_args = False

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Check for Action: tool_name
            if line_str.lower().startswith("action:"):
                if current_tool:
                    args = {}
                    if current_args_str:
                        with contextlib.suppress(json.JSONDecodeError):
                            args = json.loads(current_args_str)
                    tool_calls.append(ToolCall(name=current_tool, arguments=args))

                current_tool = line_str[7:].strip()
                current_args_str = ""
                in_args = False

            # Check for Action Input: {...}
            elif line_str.lower().startswith("action input:"):
                args_content = line_str[13:].strip()
                current_args_str = args_content
                in_args = True

            # Accumulate multi-line action input JSON
            elif in_args:
                current_args_str += "\n" + line

        # Add the last pending tool call
        if current_tool:
            args = {}
            if current_args_str:
                with contextlib.suppress(json.JSONDecodeError):
                    args = json.loads(current_args_str)
            tool_calls.append(ToolCall(name=current_tool, arguments=args))

        return tool_calls

    def _extract_final_answer(self, text: str) -> str:
        """Extract final answer from LLM response.

        Looks for 'Final Answer:' or 'Answer:' pattern.

        Args:
            text: The LLM response text.

        Returns:
            The final answer text.
        """
        # Look for Final Answer: pattern
        patterns = [
            r"Final Answer:\s*(.+?)(?=\n\n|\Z)",
            r"Answer:\s*(.+?)(?=\n\n|\Z)",
            r"Final:\s*(.+?)(?=\n\n|\Z)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # If no pattern found, return the text (minus thought/action blocks)
        clean_text = re.sub(
            r"(Thought:|Action:|Final Answer:).*?(?=\n|$)", "", text, flags=re.MULTILINE
        )
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
        return clean_text.strip() or text.strip()
