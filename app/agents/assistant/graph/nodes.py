"""LangGraph nodes for the assistant agent.

Each node is a typed function that receives AssistantGraphState and returns
a dict of partial updates (LangGraph convention).

Nodes are designed to be:
1. Testable in isolation
2. Checkpointable (state changes are automatically persisted)
3. Composable into different graph topologies
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional, TYPE_CHECKING
from uuid import UUID, uuid4

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
from app.agents.assistant.react.intent_classifier import IntentClassifier
from app.agents.assistant.react.router import FastRouter, Intent
from app.agents.assistant.react.tool_caller import ToolCaller, ToolCall
from app.agents.assistant.graph.state import (
    AssistantGraphState,
    ScratchpadEntry,
    ToolCallPending,
    scratchpad_to_llm_messages,
    check_limits,
    get_scratchpad_context,
    get_last_user_message,
)

if TYPE_CHECKING:
    from app.ai.provider import AIProvider

logger = logging.getLogger(__name__)


# ── Node: Intent Classification ─────────────────────────────────────────────


async def classification_node(
    state: AssistantGraphState,
) -> Dict[str, Any]:
    """Classify user intent using FastRouter + IntentClassifier.

    This is the entry point for every user message.

    Args:
        state: Current graph state.

    Returns:
        Dict with current_intent and pending_events.
    """
    from app.agents.assistant.react.rag_injector import inject as rag_inject

    last_message = ""
    for msg in reversed(state.messages):
        # Handle both dicts and LangChain message objects
        if hasattr(msg, 'type') and hasattr(msg, 'content'):
            # LangChain HumanMessage has type='human', not role='user'
            msg_type = getattr(msg, 'type', None)
            msg_role = getattr(msg, 'role', None)
            if msg_type == 'human' or msg_role == 'user':
                last_message = msg.content if hasattr(msg, 'content') else str(msg)
                break
        elif isinstance(msg, dict):
            # Plain dict
            if msg.get("role") == "user":
                last_message = msg.get("content", "")
                break

    if not last_message:
        return {
            "current_intent": "chitchat",
            "pending_events": [],
        }

    # FastRouter for obvious intents (no LLM call)
    router = FastRouter()
    fast_intent = await router.classify(last_message)

    # Map Intent enum to string intents expected by the graph
    # COMPLEX is the fallback for unknown/ambiguous → needs LLM classification
    if fast_intent == Intent.COMPLEX:
        # Fall through to LLM classification for complex/ambiguous messages
        pass
    else:
        # Map FastRouter Intent to string intent
        intent_map = {
            Intent.DIRECT_LIST: "list_direct",
            Intent.ANALYZE: "analyze",
            Intent.SEARCH: "search",
            Intent.REPORT: "report",
            Intent.RAG_QA: "rag_qa",
        }
        intent_str = intent_map.get(fast_intent, fast_intent.value.lower())
        logger.info("FastRouter classified intent: %s", intent_str)
        return {
            "current_intent": intent_str,
            "pending_events": [IterationEvent(n=0, max=state.max_iterations, phase="reasoning")],
        }

    # Full LLM classification for complex/ambiguous cases
    from app.ai.provider import get_provider

    provider = get_provider()
    classifier = IntentClassifier(provider)

    try:
        classification = await classifier.classify(
            last_message,
            project_context=state.project_context,
        )

        logger.info(
            "Intent: %s (confidence=%.2f) | reasoning: %s",
            classification.intent,
            classification.confidence,
            classification.reasoning,
        )

        return {
            "current_intent": classification.intent,
            "pending_events": [
                IterationEvent(n=0, max=state.max_iterations, phase="reasoning"),
            ],
        }

    except Exception as exc:
        logger.error("Intent classification failed: %s", exc)
        return {
            "current_intent": "chitchat",  # Fallback
            "errors": [f"Classification failed: {exc}"],
            "pending_events": [],
        }


# ── Node: Simple Chat (chitchat, greetings) ─────────────────────────────────


async def simple_chat_node(
    state: AssistantGraphState,
) -> Dict[str, Any]:
    """Handle simple chat intents with a single LLM call.

    No tools, no ReAct loop. Just respond directly.

    Args:
        state: Current graph state.

    Returns:
        Dict with final assistant message and done event.
    """
    from app.ai.provider import get_provider
    from langgraph.config import get_stream_writer

    writer = get_stream_writer()

    def emit(event: BaseEvent) -> None:
        try:
            writer(event)
        except Exception as exc:
            pass

    last_message = ""
    for msg in reversed(state.messages):
        # Handle both dicts and LangChain message objects
        # LangChain HumanMessage has type='human', not role='user'
        if hasattr(msg, 'type') and hasattr(msg, 'content'):
            msg_type = getattr(msg, 'type', None)
            msg_role = getattr(msg, 'role', None)
            # Check for both type='human' (LangChain) and role='user' (dict-like)
            if msg_type == 'human' or msg_role == 'user':
                last_message = msg.content if hasattr(msg, 'content') else str(msg)
                break
        elif isinstance(msg, dict):
            if msg.get("role") == "user":
                last_message = msg.get("content", "")
                break

    provider = get_provider()

    system = (
        "You are a friendly research assistant. Keep your response brief and helpful. "
        "If the user greets you, greet them back and briefly mention what you can help with. "
        "If the user asks to search for papers or anything else, gently redirect them to use the advanced '/search' page (mục Tìm kiếm chuyên sâu trên menu) for the best search experience. "
        "IMPORTANT: Respond directly to the user. Do NOT include any internal reasoning, "
        "thinking process, or meta-commentary about the user's message in your response. "
        "Output only your actual reply to the user."
    )

    events: list = []
    streamed_text = ""

    try:
        async for token in provider.stream(
            messages=[{"role": "user", "content": last_message}],
            system=system,
            max_tokens=512,
        ):
            streamed_text += token
            emit(AssistantDeltaEvent(delta=token, is_final=False))

        emit(AssistantDeltaEvent(delta="", is_final=True))

    except Exception as exc:
        logger.error("Simple chat failed: %s", exc)
        emit(ErrorEvent(code="CHAT_ERROR", message=f"Chat failed: {exc}"))

    emit(DoneEvent())

    return {
        "pending_events": [],
        "messages": [{"role": "assistant", "content": streamed_text}],
    }


# ── Node: Direct Tool (list intents) ────────────────────────────────────────


async def direct_tool_node(
    state: AssistantGraphState,
) -> Dict[str, Any]:
    """Handle direct tool calls without ReAct loop.

    For intents like list_projects, list_papers, etc.

    Args:
        state: Current graph state.

    Returns:
        Dict with tool result and done event.
    """
    from app.ai.provider import get_provider
    from app.agents.assistant.react.tool_caller import ToolCaller
    from langgraph.config import get_stream_writer

    writer = get_stream_writer()

    def emit(event: BaseEvent) -> None:
        try:
            writer(event)
        except Exception as exc:
            pass

    intent = state.current_intent or ""
    tool_name = None

    if intent == "list_direct":
        from app.agents.assistant.graph.state import get_last_user_message
        msg = get_last_user_message(state) or ""
        msg_lower = msg.lower()
        if any(k in msg_lower for k in ["project", "dự án"]):
            tool_name = "list_projects"
        elif any(k in msg_lower for k in ["paper", "bài báo"]):
            tool_name = "list_project_papers"
        elif any(k in msg_lower for k in ["report", "báo cáo"]):
            tool_name = "list_reports"
        elif any(k in msg_lower for k in ["gap", "lỗ hổng"]):
            tool_name = "list_gaps"
        elif any(k in msg_lower for k in ["conflict", "xung đột"]):
            tool_name = "list_conflicts"
        else:
            tool_name = "list_projects" # Default to projects if ambiguous
    else:
        # Map other intents
        intent_to_tool = {
            "list_projects": "list_projects",
            "list_papers": "list_project_papers",
            "list_reports": "list_reports",
            "list_gaps": "list_gaps",
            "list_conflicts": "list_conflicts",
        }
        tool_name = intent_to_tool.get(intent)
    if not tool_name:
        emit(
            MessageEvent(
                role="assistant",
                content=f"Cannot handle intent '{intent}' directly.",
            )
        )
        emit(DoneEvent())
        return {"pending_events": []}

    # Get tool from provider's available tools
    provider = get_provider()
    tools = getattr(provider, "_tools", [])

    tool_map = {}
    for tool in tools:
        name = getattr(tool, "name", None)
        if name:
            tool_map[name] = tool

    tool = tool_map.get(tool_name)
    if not tool:
        emit(MessageEvent(role="assistant", content=f"Tool '{tool_name}' not available."))
        emit(DoneEvent())
        return {"pending_events": []}

    try:
        caller = ToolCaller()
        result, _ = await caller.execute(tool, {})

        # Format result as message
        if isinstance(result, dict):
            data = result.get("data", result)
            if "projects" in data:
                projects = data["projects"]
                if not projects:
                    content = "Bạn chưa có project nào."
                else:
                    lines = [f"Bạn có {len(projects)} project(s):"]
                    for p in projects[:10]:
                        lines.append(f"• {p.get('name', 'Unnamed')}")
                    content = "\n".join(lines)
            elif "papers" in data:
                papers = data["papers"]
                if not papers:
                    content = "Không có paper nào."
                else:
                    lines = [f"Tìm thấy {len(papers)} paper(s):"]
                    for paper in papers[:10]:
                        lines.append(f"• {paper.get('title', 'Untitled')}")
                    content = "\n".join(lines)
            else:
                content = str(result)
        else:
            content = str(result)

        emit(MessageEvent(role="assistant", content=content))
        emit(DoneEvent())

    except Exception as exc:
        logger.error("Direct tool '%s' failed: %s", tool_name, exc)
        emit(ErrorEvent(code="TOOL_ERROR", message=f"Tool failed: {exc}"))
        emit(DoneEvent())

    return {"pending_events": []}


# ── Node: ReAct Loop (single iteration) ─────────────────────────────────────


async def react_loop_node(
    state: AssistantGraphState,
) -> Dict[str, Any]:
    """Single ReAct iteration node.

    This node performs one iteration of the ReAct loop:
    1. Build messages with scratchpad context
    2. Stream LLM response
    3. Parse tool calls
    4. Update scratchpad entries

    Args:
        state: Current graph state.

    Returns:
        Dict with updated iteration, scratchpad, pending_events.
    """
    from app.ai.provider import get_provider, TextChunk, ToolCallStart, ToolCallArgsDelta, ToolCallDone, StreamDone
    from langgraph.config import get_stream_writer

    writer = get_stream_writer()

    def emit(event: BaseEvent) -> None:
        try:
            writer(event)
        except Exception as exc:
            pass

    # Check limits
    limit_error = check_limits(state)
    if limit_error:
        return {
            "errors": [limit_error],
            "pending_events": [
                ErrorEvent(code=limit_error.split(":")[0], message=limit_error),
                DoneEvent(),
            ],
        }

    from app.agents.assistant.graph.config import DEFAULT_MAX_ITERATIONS

    iteration = state.iteration

    # Build messages for LLM
    messages = _build_react_messages(state)

    # Emit iteration event
    emit(IterationEvent(n=iteration, max=state.max_iterations, phase="reasoning"))

    provider = get_provider()

    # Stream LLM response
    response_text = ""
    tool_calls_found: List[ToolCall] = []
    tool_call_args: Dict[str, Dict[str, Any]] = {}

    try:
        async for chunk in provider.stream_with_tools(
            messages=messages,
            system=None,
            max_tokens=4096,  # Increased to allow for thinking + tool calls
            tools=_get_tool_definitions(state),
        ):
            if isinstance(chunk, TextChunk):
                response_text += chunk.delta
                emit(AssistantDeltaEvent(delta=chunk.delta, is_final=False))

            elif isinstance(chunk, ToolCallStart):
                tool_call_args[chunk.call_id] = {"name": chunk.name, "args_str": ""}
                emit(
                    ToolEvent(
                        tool_call_id=chunk.call_id,
                        name=chunk.name,
                        status="calling",
                        function=chunk.name,
                        args={},
                    )
                )

            elif isinstance(chunk, ToolCallArgsDelta):
                if chunk.call_id in tool_call_args:
                    tool_call_args[chunk.call_id]["args_str"] += chunk.delta

            elif isinstance(chunk, ToolCallDone):
                name = chunk.name or tool_call_args.get(chunk.call_id, {}).get("name", "unknown")
                args = chunk.arguments or {}
                if not args and tool_call_args.get(chunk.call_id, {}).get("args_str"):
                    try:
                        args = json.loads(tool_call_args[chunk.call_id]["args_str"])
                    except json.JSONDecodeError:
                        args = {}

                tool_calls_found.append(
                    ToolCall(name=name, arguments=args, call_id=chunk.call_id)
                )

            elif isinstance(chunk, StreamDone):
                # Tool calls are already accumulated via ToolCallDone, no need to duplicate them here
                pass

    except Exception as exc:
        logger.error("stream_with_tools failed: %s", exc)
        emit(ErrorEvent(code="PROVIDER_ERROR", message=f"Provider stream failed: {exc}"))

    if response_text:
        emit(AssistantDeltaEvent(delta="", is_final=True))

    # Check for tool calls
    if not tool_calls_found:
        # No tools - graph will proceed to final_answer_node
        return {
            "iteration": iteration + 1,
            "pending_events": [],
            "messages": [{"role": "assistant", "content": response_text}],
        }

    # Emit acting phase
    emit(IterationEvent(n=iteration, max=state.max_iterations, phase="acting"))

    # Execute tools
    from app.agents.assistant.react.tool_caller import ToolCaller
    from app.agents.assistant.tools.context import get_tools

    caller = ToolCaller()
    scratchpad_updates: List[ScratchpadEntry] = list(state.scratchpad_entries)
    
    # Format tool calls for LangChain AIMessage
    formatted_tool_calls = [
        {
            "name": tc.name,
            "args": tc.arguments,
            "id": tc.call_id,
        }
        for tc in tool_calls_found
    ]
    
    new_messages: List[dict] = [{
        "role": "assistant", 
        "content": response_text,
        "tool_calls": formatted_tool_calls,
    }]

    # Build tool map from context (set in session_service.chat_with_graph)
    tools_list = get_tools() or []
    tool_map = {getattr(t, "name", ""): t for t in tools_list}

    for tool_call in tool_calls_found:
        tool = tool_map.get(tool_call.name)
        if tool is None:
            result, is_wait = {"ok": False, "error": f"Unknown tool: {tool_call.name}"}, False
        else:
            result, is_wait = await caller.execute(tool, tool_call.arguments)

        if is_wait:
            emit(
                WaitEvent(
                    question=result.get("question", "Bạn có thể cho tôi biết thêm chi tiết?"),
                    options=result.get("options"),
                    placeholder=result.get("question"),
                )
            )
            # Graph will go to final_answer_node which emits DoneEvent
            return {
                "is_waiting": True,
                "waiting_question": result.get("question"),
                "waiting_options": result.get("options"),
                "pending_events": [],
            }

        status = "failed" if result.get("ok") is False else "called"

        emit(
            ToolEvent(
                tool_call_id=tool_call.call_id,
                name=tool_call.name,
                status=status,
                function=tool_call.name,
                args=tool_call.arguments,
                result=result if status == "called" else None,
                error=result.get("error") if status == "failed" else None,
            )
        )

        if status == "called" or status == "failed":
            if status == "called":
                scratchpad_updates.append(
                    ScratchpadEntry(
                        tool_name=tool_call.name,
                        args=tool_call.arguments,
                        result=result,
                    )
                )
            # Always append the tool message to satisfy LangChain's requirement
            # that every tool call in AIMessage has a corresponding ToolMessage
            new_messages.append({
                "role": "tool",
                "name": tool_call.name,
                "tool_call_id": tool_call.call_id,
                "content": json.dumps(result, default=str, ensure_ascii=False),
            })

    return {
        "iteration": iteration + 1,
        "scratchpad_entries": scratchpad_updates,
        "messages": new_messages,  # add_messages reducer will append
        "pending_events": [],
    }


# ── Node: Research Pipeline (deterministic orchestration) ────────────────────


async def research_pipeline_node(
    state: AssistantGraphState,
) -> Dict[str, Any]:
    """Run the deterministic research pipeline.

    End-to-end flow: search → screen → save → matrix → gap → report. Each
    stage emits a ProgressEvent so the UI can show real-time updates. The
    LLM is not used to control the workflow; it is only invoked inside
    individual stages (e.g. paper relevance screening). This matches the
    orchestration pattern in docs/assistant-direction.md §2 and the
    decision record in docs/architecture/react-agent-migration.md §8.

    Events are streamed to the FE in real time via
    ``get_stream_writer()`` so the user sees progress within seconds
    instead of waiting 1-5 minutes for the whole pipeline to finish.
    They are also returned in ``pending_events`` so they are still
    available for event-replay and persistence.

    If no project is pinned to the session, the node emits a visible
    assistant MessageEvent (so the user sees feedback in the chat) plus
    a WaitEvent, mirroring the legacy ReAct agent's behavior in
    react/agent.py.

    Returns:
        Dict with ``pending_events`` containing all pipeline events.
    """
    from langgraph.config import get_stream_writer

    from app.agents.assistant.pipelines.research_pipeline import (
        ResearchPipeline,
        ResearchPipelineConfig,
    )
    from app.agents.assistant.tools.context import get_project_id

    writer = get_stream_writer()
    streamed_done = False

    def emit(event: BaseEvent) -> None:
        """Push event to the custom stream for real-time SSE delivery.

        We do NOT also push to ``pending_events`` because that would
        duplicate the event (it would arrive once via the custom stream
        and again at the end of the node via the updates stream). The
        session_service persists every yielded event to the DB, so we
        don't lose them for resume/replay.
        """
        nonlocal streamed_done
        if isinstance(event, DoneEvent):
            streamed_done = True
        try:
            writer(event.model_dump(mode="json"))
        except Exception as exc:
            logger.warning("Failed to write event to stream: %s", exc)

    project_id = get_project_id()
    query = get_last_user_message(state) or ""

    if not project_id:
        emit(
            MessageEvent(
                role="assistant",
                content=(
                    "Để chạy research pipeline, em cần anh mở hoặc tạo một project trước. "
                    "Vào trang **Projects** → **New Project**, đặt tên và chủ đề, "
                    "rồi quay lại đây chạy lại nhé."
                ),
            )
        )
        emit(
            WaitEvent(
                question="Which project should I use for the research?",
                options=None,
                placeholder="Open or create a project to continue.",
            )
        )
        emit(DoneEvent(summary="Awaiting project selection."))
        return {"pending_events": []}

    if not query:
        emit(
            ErrorEvent(
                code="EMPTY_QUERY",
                message="Cannot start research pipeline: empty user message.",
            )
        )
        emit(DoneEvent(summary="Research pipeline aborted."))
        return {"pending_events": []}

    config = ResearchPipelineConfig(
        project_id=project_id,
        query=query,
        max_papers_to_save=10,
        relevance_threshold="medium",
        include_gap_section=True,
        auto_generate_report=True,
    )

    pipeline = ResearchPipeline(config)

    try:
        async for event in pipeline.run():
            emit(event)
    except asyncio.CancelledError:
        # Pipeline already yielded its own ErrorEvent + DoneEvent before
        # re-raising. Re-raise so the parent generator can stop cleanly.
        raise

    if not streamed_done:
        emit(DoneEvent(summary="Research pipeline complete."))

    return {"pending_events": []}


# ── Node: Check More Iterations ──────────────────────────────────────────────


def should_continue_react(state: AssistantGraphState) -> Literal["react_loop", "final_answer"]:
    """Conditional edge: check if more ReAct iterations are needed.

    Args:
        state: Current graph state.

    Returns:
        "react_loop" to continue, "final_answer" to finish.
    """
    if state.is_waiting:
        return "final_answer"

    if state.iteration >= state.max_iterations:
        return "final_answer"

    # Check if the last message was a tool result
    if state.messages:
        last_msg = state.messages[-1]
        role = last_msg.get("role") if isinstance(last_msg, dict) else getattr(last_msg, "type", getattr(last_msg, "role", None))
        if role == "tool":
            return "react_loop"

    return "final_answer"


# ── Node: Final Answer ───────────────────────────────────────────────────────


async def final_answer_node(
    state: AssistantGraphState,
) -> Dict[str, Any]:
    """Emit final answer and done event.

    This node is called when the ReAct loop is complete.

    Args:
        state: Current graph state.

    Returns:
        Dict with done event.
    """
    from langgraph.config import get_stream_writer

    writer = get_stream_writer()

    def emit(event: BaseEvent) -> None:
        try:
            writer(event)
        except Exception as exc:
            pass

    # Check if we have errors
    if state.errors:
        error_msg = state.errors[-1]
        emit(ErrorEvent(code="RUN_ERROR", message=error_msg))
    elif state.is_waiting:
        emit(WaitEvent(
            question=state.waiting_question or "Awaiting your response.",
            options=state.waiting_options,
            placeholder=state.waiting_placeholder,
        ))
    elif state.iteration >= state.max_iterations:
        emit(
            ErrorEvent(
                code="MAX_ITERATIONS",
                message=f"Exceeded maximum iterations ({state.max_iterations})",
            )
        )

    emit(DoneEvent())

    return {"pending_events": []}


# ── Helper Functions ──────────────────────────────────────────────────────────


def _message_to_dict(msg: Any) -> Dict[str, Any]:
    """Convert a message to dict format (handles both dicts and LangChain objects).

    Faithfully preserves tool_calls and tool_call_id for OpenAI API compatibility.

    Args:
        msg: A message dict or LangChain message object.

    Returns:
        A message dict.
    """
    import json
    
    # Handle LangChain message objects
    if hasattr(msg, 'type') and hasattr(msg, 'content'):
        msg_type = getattr(msg, 'type', None)
        
        # Map LangChain types to OpenAI-compatible roles
        role_map = {
            'human': 'user',
            'ai': 'assistant',
            'system': 'system',
            'tool': 'tool',
            'function': 'tool',
        }
        role = role_map.get(msg_type, 'user')
        result = {"role": role, "content": msg.content or ""}
        
        if role == "assistant" and getattr(msg, "tool_calls", None):
            # Convert LangChain tool_calls to OpenAI API format
            openai_tool_calls = []
            for tc in msg.tool_calls:
                # LangChain format: {'name': 'foo', 'args': {}, 'id': 'call_123', 'type': 'tool_call'}
                # OpenAI format: {'id': 'call_123', 'type': 'function', 'function': {'name': 'foo', 'arguments': '{}'}}
                args_str = json.dumps(tc.get("args", {}), ensure_ascii=False) if isinstance(tc.get("args"), dict) else (tc.get("args") or "{}")
                
                openai_tool_calls.append({
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": args_str
                    }
                })
            result["tool_calls"] = openai_tool_calls
            
        if role == "tool":
            if getattr(msg, "tool_call_id", None):
                result["tool_call_id"] = msg.tool_call_id
            if getattr(msg, "name", None):
                result["name"] = msg.name
            
            # Truncate tool content to prevent context overflow
            if isinstance(result["content"], str) and len(result["content"]) > 50000:
                result["content"] = result["content"][:50000] + "...[truncated]"
                
        return result

    # Handle plain dicts
    elif isinstance(msg, dict):
        result = dict(msg)
        # Ensure content is never None if required
        if result.get("content") is None:
            result["content"] = ""
            
        if result.get("role") == "assistant" and result.get("tool_calls"):
            # Ensure they are in OpenAI format
            openai_tool_calls = []
            for tc in result["tool_calls"]:
                # If already OpenAI format
                if "function" in tc and "arguments" in tc["function"]:
                    openai_tool_calls.append(tc)
                # If LangChain dict format
                elif "args" in tc:
                    args_str = json.dumps(tc.get("args", {}), ensure_ascii=False) if isinstance(tc.get("args"), dict) else (tc.get("args") or "{}")
                    openai_tool_calls.append({
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": args_str
                        }
                    })
                else:
                    openai_tool_calls.append(tc)
            result["tool_calls"] = openai_tool_calls
            
        if result.get("role") == "tool" and isinstance(result.get("content"), str) and len(result["content"]) > 50000:
            result["content"] = result["content"][:50000] + "...[truncated]"
        return result
    else:
        return {"role": "user", "content": str(msg)}


def _build_react_messages(state: AssistantGraphState) -> List[Dict[str, Any]]:
    """Build messages for the ReAct LLM call.

    Includes:
    - System prompt with tools
    - Conversation history (which includes AI tool_calls and ToolMessages)

    Args:
        state: Current graph state.

    Returns:
        List of message dicts.
    """
    messages: List[Dict[str, Any]] = []

    # System prompt based on project context (Direction A vs Direction B)
    tools_desc = _format_tools_description(state)
    
    if getattr(state, "project_context", None) and state.project_context.get("project_name"):
        ctx = state.project_context
        system_content = (
            "You are a research assistant currently working on an ACTIVE PROJECT.\n"
            "Your main goal is to assist the user with tasks related to this specific project.\n\n"
            "**Current Project Context**:\n"
            f"- Project Name: {ctx.get('project_name')}\n"
            f"- Topic: {ctx.get('topic', 'None')}\n"
            f"- Research Question: {ctx.get('research_question', 'None')}\n\n"
            f"Available tools:\n{tools_desc}\n\n"
            "Rules:\n"
            "1. Call exactly ONE tool per turn.\n"
            "2. When calling a tool, output ONLY the tool call, no preamble.\n"
            "3. If you have the information needed, answer the user directly in text.\n"
            "4. Do not ask for the project name; you are already working within the context of the project listed above."
        )
    else:
        system_content = (
            "You are a research assistant. The user has NOT selected an active project yet.\n"
            "Your main goal is to help the user find an existing project or create a new one to get started.\n\n"
            "**Current Project Context**: None currently selected.\n\n"
            f"Available tools:\n{tools_desc}\n\n"
            "Rules:\n"
            "1. Call exactly ONE tool per turn.\n"
            "2. CRITICAL: If the user asks about 'this project', 'the project', or existing projects, YOU MUST use the 'list_projects' tool to find available projects. DO NOT say you don't know or ask the user for the project name first.\n"
            "3. For 'create_project': pass name, topic, research_question based on user input.\n"
            "4. For 'list_projects': call with no args.\n"
            "5. When calling a tool, output ONLY the tool call, no preamble. If you have the information needed, answer the user directly in text."
        )
    messages.append({"role": "system", "content": system_content})

    # Conversation history (converting LangChain messages to dicts)
    # The history contains the exact sequence of user -> assistant (tool_calls) -> tool (tool_call_id) -> ...
    for msg in state.messages:
        msg_dict = _message_to_dict(msg)
        if msg_dict is not None:
            messages.append(msg_dict)

    return messages


def _format_tools_description(state: AssistantGraphState) -> str:
    """Format available tools for the system prompt.

    Tools are stored in the request context (set via set_user_context).

    Args:
        state: Current graph state.

    Returns:
        Formatted tools description string.
    """
    from app.agents.assistant.tools.context import get_tools

    tools = get_tools() or []

    if not tools:
        return "(No tools available)"

    lines = []
    for tool in tools:
        name = getattr(tool, "name", "unknown")
        desc = getattr(tool, "description", "No description")
        lines.append(f"- {name}: {desc}")

    return "\n".join(lines)


def _get_tool_definitions(state: AssistantGraphState) -> List[Dict[str, Any]]:
    """Get tool definitions in OpenAI function calling format.

    Tools are stored in the request context (set via set_user_context).
    This avoids serializing tools into checkpointed state.

    Args:
        state: Current graph state.

    Returns:
        List of tool definitions.
    """
    from app.agents.assistant.react.tool_caller import ToolCaller
    from app.agents.assistant.tools.context import get_tools

    tools = get_tools() or []
    if not tools:
        logger.warning("No tools available in context for tool definitions")

    caller = ToolCaller()
    return caller.convert_to_openai_format(tools)
