"""Tool caller for the ReAct agent.

Handles tool execution with support for both sync and async tools,
parallel execution, and multiple provider formats (OpenAI, Anthropic).

Extracted from execution.py for use by the ReAct agent loop.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Sentinel value for ask_user_clarification
WAIT_SENTINEL = {"_wait": True}


class ToolCall:
    """Represents a single tool call."""

    def __init__(
        self,
        name: str,
        arguments: Dict[str, Any],
        call_id: Optional[str] = None,
    ) -> None:
        self.name = name
        self.arguments = arguments
        self.call_id = call_id or str(uuid.uuid4())


class ToolCaller:
    """Handles tool execution for the ReAct agent.

    Provides:
    - Tool format conversion (OpenAI, Anthropic)
    - Tool execution (sync/async)
    - Parallel execution of multiple tools
    - Detection of wait sentinel for ask_user_clarification
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    # ── Format conversion ─────────────────────────────────────────────────────

    def convert_to_openai_format(
        self,
        tools: List[Any],
    ) -> List[Dict[str, Any]]:
        """Convert LangChain tools to OpenAI function calling format.

        Args:
            tools: List of LangChain BaseTool instances.

        Returns:
            List of tool definitions in OpenAI format.
        """
        openai_tools = []
        for tool in tools:
            name = getattr(tool, "name", "unknown")
            desc = getattr(tool, "description", "No description")
            args_schema = getattr(tool, "args_schema", None)

            # Build parameters schema
            parameters = {
                "type": "object",
                "properties": {},
                "required": [],
            }

            if args_schema and hasattr(args_schema, "model_fields"):
                for field_name, field in args_schema.model_fields.items():
                    annotation = getattr(field, "annotation", str)
                    param_type = self._infer_param_type(annotation)

                    parameters["properties"][field_name] = {
                        "type": param_type,
                        "description": field.description or "",
                    }

                    if field.is_required():
                        parameters["required"].append(field_name)

            openai_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": parameters,
                },
            })

        return openai_tools

    def convert_to_anthropic_format(
        self,
        tools: List[Any],
    ) -> List[Dict[str, Any]]:
        """Convert LangChain tools to Anthropic tool format.

        Args:
            tools: List of LangChain BaseTool instances.

        Returns:
            List of tool definitions in Anthropic format.
        """
        anthropic_tools = []
        for tool in tools:
            name = getattr(tool, "name", "unknown")
            desc = getattr(tool, "description", "No description")
            args_schema = getattr(tool, "args_schema", None)

            # Build input schema
            input_schema: Dict[str, Any] = {
                "type": "object",
                "properties": {},
                "required": [],
            }

            if args_schema and hasattr(args_schema, "model_fields"):
                for field_name, field in args_schema.model_fields.items():
                    annotation = getattr(field, "annotation", str)
                    param_type = self._infer_param_type(annotation)

                    input_schema["properties"][field_name] = {
                        "type": param_type,
                        "description": field.description or "",
                    }

                    if field.is_required():
                        input_schema["required"].append(field_name)

            anthropic_tools.append({
                "name": name,
                "description": desc,
                "input_schema": input_schema,
            })

        return anthropic_tools

    @staticmethod
    def _infer_param_type(annotation: Any) -> str:
        """Infer JSON schema type from Python annotation."""
        annotation_str = str(annotation)

        if annotation is bool or annotation_str == "bool":
            return "boolean"
        if annotation is int or annotation_str == "int":
            return "integer"
        if annotation is float or annotation_str == "float":
            return "number"
        if annotation is list or annotation_str.startswith("list"):
            return "array"
        if annotation is dict or annotation_str.startswith("dict"):
            return "object"

        return "string"

    # ── Tool execution ────────────────────────────────────────────────────────

    async def execute(
        self,
        tool: Any,
        args: Dict[str, Any],
    ) -> Tuple[Any, bool]:
        """Execute a single tool.

        Detects ask_user_clarification and returns the wait sentinel.

        Args:
            tool: LangChain BaseTool instance.
            args: Tool arguments.

        Returns:
            Tuple of (result, is_wait). is_wait is True if this was ask_user_clarification.
        """
        tool_name = getattr(tool, "name", "unknown")

        # Check for ask_user_clarification sentinel
        if tool_name == "ask_user_clarification":
            question = args.get("question", "Please clarify")
            return {"_wait": True, "question": question, "options": args.get("options")}, True

        try:
            # Execute tool (async or sync)
            result = await self._invoke_tool(tool, args)
            return result, False
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            return {"ok": False, "error": str(exc), "tool": tool_name}, False

    async def execute_parallel(
        self,
        tool_map: Dict[str, Any],
        calls: List[ToolCall],
    ) -> List[Tuple[ToolCall, Any, bool]]:
        """Execute multiple tool calls in parallel.

        Args:
            tool_map: Map from tool name to tool instance.
            calls: List of ToolCall objects to execute.

        Returns:
            List of (ToolCall, result, is_wait) tuples.
        """
        if not calls:
            return []

        # Prepare call info and coroutines
        call_infos: List[Tuple[ToolCall, Optional[Any], Optional[asyncio.Task]]] = []
        coroutines: List[asyncio.Task] = []

        for call in calls:
            tool = tool_map.get(call.name)
            if tool is None:
                call_infos.append((call, {"ok": False, "error": f"Unknown tool: {call.name}"}, None))
            else:
                coro = asyncio.create_task(self.execute(tool, call.arguments))
                call_infos.append((call, None, coro))
                coroutines.append(coro)

        # Execute all in parallel
        if coroutines:
            results = await asyncio.gather(*coroutines, return_exceptions=True)

            # Map results back to call_infos
            result_idx = 0
            for i, (call, _, coro) in enumerate(call_infos):
                if coro is not None:
                    result = results[result_idx]
                    result_idx += 1
                    if isinstance(result, Exception):
                        call_infos[i] = (call, {"ok": False, "error": str(result)}, None)
                    else:
                        call_infos[i] = (call, result[0], None)  # (result, is_wait)

        # Convert to final format
        output = []
        for call, result, _ in call_infos:
            if result is None:
                result = {"ok": False, "error": "Execution failed"}
            is_wait = isinstance(result, dict) and result.get("_wait", False) is True
            output.append((call, result, is_wait))

        return output

    async def _execute_with_sentinel(
        self,
        tool: Any,
        call: ToolCall,
    ) -> Tuple[Any, bool]:
        """Execute a tool and return (result, is_wait)."""
        return await self.execute(tool, call.arguments)

    async def _invoke_tool(
        self,
        tool: Any,
        args: Dict[str, Any],
    ) -> Any:
        """Invoke a LangChain tool (async or sync)."""
        # Async tool
        if hasattr(tool, "ainvoke"):
            return await tool.ainvoke(args)

        # Sync tool - run in thread pool
        if hasattr(tool, "invoke"):
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return await loop.run_in_executor(
                    pool,
                    lambda: tool.invoke(args),
                )

        raise ValueError(f"Tool {getattr(tool, 'name', 'unknown')} has no invoke method")

    # ── Response parsing ───────────────────────────────────────────────────────

    @staticmethod
    def parse_tool_calls(response: Any) -> List[ToolCall]:
        """Extract tool calls from LLM response.

        Handles OpenAI and Anthropic response formats.

        Args:
            response: LLM response object.

        Returns:
            List of ToolCall objects.
        """
        tool_calls = []

        # OpenAI-style tool_calls
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                name = getattr(tc, "name", None)
                if name is None and hasattr(tc, "function"):
                    name = getattr(tc.function, "name", None)
                name = name or "unknown"

                args_raw = getattr(tc, "arguments", None)
                if args_raw is None and hasattr(tc, "function"):
                    args_raw = getattr(tc.function, "arguments", "{}")
                if args_raw is None:
                    args_raw = "{}"

                # Parse arguments
                if isinstance(args_raw, str):
                    try:
                        args = json.loads(args_raw)
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = args_raw or {}

                call_id = getattr(tc, "id", None) or str(uuid.uuid4())
                tool_calls.append(ToolCall(name=name, arguments=args, call_id=call_id))

        return tool_calls

    @staticmethod
    def extract_content(response: Any) -> str:
        """Extract text content from LLM response."""
        content = getattr(response, "content", None)
        if content:
            return content
        return ""

    @staticmethod
    def is_wait_result(result: Any) -> bool:
        """Check if a result is the wait sentinel."""
        if isinstance(result, dict):
            return result.get("_wait", False) is True
        return False
