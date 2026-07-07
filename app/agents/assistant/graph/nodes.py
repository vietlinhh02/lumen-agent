"""LangGraph nodes for the assistant agent.

Each node is a typed function that receives AssistantGraphState and returns
a dict of partial updates (LangGraph convention).

Nodes are designed to be:
1. Testable in isolation
2. Checkpointable (state changes are automatically persisted)
3. Composable into different graph topologies
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import TYPE_CHECKING, Any, Literal

from app.agents.assistant.events import (
    AssistantDeltaEvent,
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    IterationEvent,
    MessageEvent,
    ToolEvent,
    WaitEvent,
)
from app.agents.assistant.graph.state import (
    AssistantGraphState,
    ScratchpadEntry,
    check_limits,
)
from app.agents.assistant.react.intent_classifier import IntentClassifier
from app.agents.assistant.react.router import FastRouter, Intent
from app.agents.assistant.react.tool_caller import ToolCall, ToolCaller

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ── Node: Intent Classification ─────────────────────────────────────────────


async def classification_node(
    state: AssistantGraphState,
) -> dict[str, Any]:
    """Classify user intent using FastRouter + IntentClassifier.

    This is the entry point for every user message.

    Args:
        state: Current graph state.

    Returns:
        Dict with current_intent and pending_events.
    """
    if state.current_intent is not None and state.current_intent != "unknown":
        return {
            "current_intent": state.current_intent,
            "pending_events": [IterationEvent(n=0, max=state.max_iterations, phase="reasoning")] if state.current_intent != "chitchat" else [],
        }

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
) -> dict[str, Any]:
    """Handle simple chat intents with a single LLM call.

    No tools, no ReAct loop. Just respond directly.

    Args:
        state: Current graph state.

    Returns:
        Dict with final assistant message and done event.
    """
    from langgraph.config import get_stream_writer

    from app.ai.provider import get_provider

    writer = get_stream_writer()

    def emit(event: BaseEvent) -> None:
        with contextlib.suppress(Exception):
            writer(event)

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
        "IMPORTANT: Respond directly to the user. Do NOT include any internal reasoning, "
        "thinking process, or meta-commentary about the user's message in your response. "
        "Output only your actual reply to the user. Do NOT use emoji, pictograms, "
        "decorative icons, or emoticons."
    )

    streamed_text = ""

    try:
        async for token in provider.stream(
            messages=[{"role": "user", "content": last_message}],
            system=system,
            max_tokens=32768,
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
) -> dict[str, Any]:
    """Handle direct tool calls without ReAct loop.

    For intents like list_projects, list_papers, etc.

    Args:
        state: Current graph state.

    Returns:
        Dict with tool result and done event.
    """
    from langgraph.config import get_stream_writer

    from app.ai.provider import get_provider

    writer = get_stream_writer()

    def emit(event: BaseEvent) -> None:
        with contextlib.suppress(Exception):
            writer(event)

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
                        lines.append(f"- {p.get('name', 'Unnamed')}")
                    content = "\n".join(lines)
            elif "papers" in data:
                papers = data["papers"]
                if not papers:
                    content = "Không có paper nào."
                else:
                    lines = [f"Tìm thấy {len(papers)} paper(s):"]
                    for paper in papers[:10]:
                        lines.append(f"- {paper.get('title', 'Untitled')}")
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
) -> dict[str, Any]:
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
    from langgraph.config import get_stream_writer

    from app.ai.provider import (
        StreamDone,
        TextChunk,
        ToolCallArgsDelta,
        ToolCallDone,
        ToolCallStart,
        get_provider,
    )

    writer = get_stream_writer()

    def emit(event: BaseEvent) -> None:
        with contextlib.suppress(Exception):
            writer(event)

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


    iteration = state.iteration

    # Build messages for LLM
    messages = _build_react_messages(state)

    # Emit iteration event
    emit(IterationEvent(n=iteration, max=state.max_iterations, phase="reasoning"))

    provider = get_provider()

    # Stream LLM response
    response_text = ""
    tool_calls_found: list[ToolCall] = []
    tool_call_args: dict[str, dict[str, Any]] = {}

    try:
        async for chunk in provider.stream_with_tools(
            messages=messages,
            system=None,
            max_tokens=32768,  # Increased to allow for thinking + tool calls
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
    from app.agents.assistant.tools.context import get_tools

    caller = ToolCaller()
    scratchpad_updates: list[ScratchpadEntry] = list(state.scratchpad_entries)
    
    # Format tool calls for LangChain AIMessage
    formatted_tool_calls = [
        {
            "name": tc.name,
            "args": tc.arguments,
            "id": tc.call_id,
        }
        for tc in tool_calls_found
    ]
    
    new_messages: list[dict] = [{
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
) -> dict[str, Any]:
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
        with contextlib.suppress(Exception):
            writer(event)

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


def _message_to_dict(msg: Any) -> dict[str, Any]:
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


def _build_react_messages(state: AssistantGraphState) -> list[dict[str, Any]]:
    """Build messages for the ReAct LLM call.

    Includes:
    - System prompt with tools
    - Conversation history (which includes AI tool_calls and ToolMessages)

    Args:
        state: Current graph state.

    Returns:
        List of message dicts.
    """
    messages: list[dict[str, Any]] = []

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
            "2. CRITICAL: When using a tool, you MUST NOT output any conversational text or preamble before the tool call. Your response must ONLY contain the tool call.\n"
            "3. If you have all the information needed and do NOT need a tool, answer the user directly in plain text.\n"
            "4. Do not ask for the project name; you are already working within the context of the project listed above.\n"
            "5. Do not use emoji, pictograms, decorative icons, emoticons, or Unicode symbol bullets in final answers.\n"
            "6. Use clean markdown with ASCII bullets (-) and plain text headings."
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
            "5. CRITICAL: When using a tool, you MUST NOT output any conversational text or preamble before the tool call. Your response must ONLY contain the tool call. If you have the information needed, answer the user directly in text.\n"
            "6. Do not use emoji, pictograms, decorative icons, emoticons, or Unicode symbol bullets in final answers.\n"
            "7. Use clean markdown with ASCII bullets (-) and plain text headings."
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


def _get_tool_definitions(state: AssistantGraphState) -> list[dict[str, Any]]:
    """Get tool definitions in OpenAI function calling format.

    Tools are stored in the request context (set via set_user_context).
    This avoids serializing tools into checkpointed state.

    Args:
        state: Current graph state.

    Returns:
        List of tool definitions.
    """
    from app.agents.assistant.tools.context import get_tools

    tools = get_tools() or []
    if not tools:
        logger.warning("No tools available in context for tool definitions")

    caller = ToolCaller()
    return caller.convert_to_openai_format(tools)


async def _generate_search_query(
    user_message: str,
    project_name: str,
    project_topic: str,
) -> str:
    """Use LLM to generate a concise academic search query from user's request + project context.

    Falls back to a cleaned-up version of the user message if LLM call fails.
    """
    from app.ai.provider import get_provider

    provider = get_provider()

    context_parts = []
    if project_name:
        context_parts.append(f"Project: {project_name}")
    if project_topic:
        context_parts.append(f"Topic: {project_topic}")
    context_str = "\n".join(context_parts) if context_parts else "(no project context)"

    system = (
        "You are a research assistant helping formulate academic search queries. "
        "Given the user's request and project context, output a single concise academic search query "
        "suitable for Semantic Scholar / Google Scholar. "
        "The query should be in English, 5-15 words, using academic terminology. "
        "Output ONLY the query string, no explanation, no quotes, no punctuation at the end."
    )

    prompt = (
        f"Project context:\n{context_str}\n\n"
        f"User request: {user_message}\n\n"
        "Generate the academic search query:"
    )

    try:
        result = ""
        async for token in provider.stream(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            max_tokens=32768,
        ):
            result += token
        query = result.strip().strip('"').strip("'").strip()
        if query and len(query) >= 3:
            return query[:500]
    except Exception as exc:
        logger.warning("Query generation LLM call failed: %s", exc)

    # Fallback: strip conversational phrases and use first 500 chars
    fallback = user_message.strip()
    for phrase in ["tìm các paper", "tìm paper", "tóm tắt cho tôi", "liên quan", "tìm hiểu", "giúp tôi", "hãy", "please", "can you", "find papers about"]:
        fallback = fallback.replace(phrase, "").strip()
    fallback = " ".join(fallback.split())[:500] or user_message[:500]
    return fallback
