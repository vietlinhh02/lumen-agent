"""
Execution Agent for the Assistant.

Executes one plan step at a time using the registered tools.
Drives the LLM tool-calling loop and yields ToolEvent and MessageEvent events.

Usage:
    executor = ExecutionAgent(provider=provider, tools=tools)
    async for event in executor.execute_step(plan, step, message):
        yield event
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from app.agents.assistant.events import (
    BaseEvent,
    ErrorEvent,
    MessageEvent,
    PlanEvent,
    PlanStep,
    StepEvent,
    ToolEvent,
    WaitEvent,
)
from app.ai.prompts import (
    EXECUTION_PROMPT,
    EXECUTION_SYSTEM_PROMPT,
    SUMMARIZE_PROMPT,
)

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from app.ai.provider import AIProvider

logger = logging.getLogger(__name__)

# Maximum tool calls per step to prevent infinite loops
MAX_TOOL_CALLS_PER_STEP = 10


class ExecutionAgent:
    """
    Execution agent that drives tool calling for a single plan step.

    The executor takes a plan step and drives the LLM through a tool-calling
    loop until either:
    1. The LLM stops calling tools (returns a final message)
    2. A maximum number of tool calls is reached
    3. The ask_user_clarification tool is called (yields WaitEvent)
    4. An unknown tool is called (yields ErrorEvent)

    Attributes:
        provider: LLM provider for making AI calls.
        tools: List of LangChain BaseTool instances available to the executor.
    """

    def __init__(
        self,
        provider: "AIProvider",
        tools: Optional[List["BaseTool"]] = None,
    ) -> None:
        """
        Initialize the execution agent.

        Args:
            provider: LLM provider for making AI calls.
            tools: List of LangChain BaseTool instances.
        """
        self.provider = provider
        self._tools = tools or []
        self._tool_map = self._build_tool_map()

    def _build_tool_map(self) -> Dict[str, "BaseTool"]:
        """Build a mapping from tool name to tool instance."""
        tool_map: Dict[str, "BaseTool"] = {}
        for tool in self._tools:
            if hasattr(tool, "name") and tool.name:
                tool_map[tool.name] = tool
        return tool_map

    def _format_tools_for_prompt(self) -> str:
        """Format tools for the LLM prompt."""
        if not self._tools:
            return "(No tools available)"
        
        lines = []
        for tool in self._tools:
            name = getattr(tool, "name", "unknown")
            desc = getattr(tool, "description", "No description")
            args_schema = getattr(tool, "args_schema", None)
            
            # Get parameter info
            params = ""
            if args_schema and hasattr(args_schema, "model_fields"):
                param_parts = []
                for field_name, field in args_schema.model_fields.items():
                    field_desc = field.description or ""
                    field_type = "string"
                    if hasattr(field, "annotation") and field.annotation:
                        field_type = str(field.annotation)
                    param_parts.append(f"  - {field_name}: {field_type} ({field_desc})")
                params = "\n".join(param_parts)
            
            lines.append(f"- {name}: {desc}\n{params}")
        
        return "\n\n".join(lines)

    def _convert_langchain_tools_to_openai_format(self) -> List[Dict[str, Any]]:
        """
        Convert LangChain tools to OpenAI function calling format.
        
        Returns:
            List of tool definitions in OpenAI format.
        """
        tools = []
        for tool in self._tools:
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
                    # Determine field type from annotation
                    annotation = getattr(field, "annotation", str)
                    if annotation is bool or str(annotation) == "bool":
                        param_type = "boolean"
                    elif annotation is int or str(annotation) == "int":
                        param_type = "integer"
                    elif annotation is float or str(annotation) == "float":
                        param_type = "number"
                    elif annotation is list or str(annotation).startswith("list"):
                        param_type = "array"
                    else:
                        param_type = "string"
                    
                    parameters["properties"][field_name] = {
                        "type": param_type,
                        "description": field.description or "",
                    }
                    
                    # Check if required
                    if field.is_required():
                        parameters["required"].append(field_name)
            
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": parameters,
                },
            })
        
        return tools

    async def execute_step(
        self,
        plan: PlanEvent,
        step: PlanStep,
        message: str,
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Execute a single plan step using the registered tools.

        Drives the LLM through a tool-calling loop until:
        - The LLM stops calling tools
        - Max tool calls reached (loop detected)
        - ask_user_clarification is called
        - Unknown tool is called

        Args:
            plan: The current plan event.
            step: The step to execute.
            message: Optional user message or context for this step.

        Yields:
            StepEvent with status "running"
            ToolEvent for each tool call (calling and called)
            MessageEvent for final summary or error
            WaitEvent if ask_user_clarification is called
            ErrorEvent if execution fails
        """
        step_id = step.id

        # Yield step started event
        yield StepEvent(
            step_id=step_id,
            description=step.description,
            status="running",
        )

        # Build the execution context
        messages = self._build_messages(plan, step, message)
        tools = self._convert_langchain_tools_to_openai_format()

        tool_call_count = 0
        last_has_tool_call = True

        # Tool-calling loop
        while last_has_tool_call and tool_call_count < MAX_TOOL_CALLS_PER_STEP:
            tool_call_count += 1

            try:
                # Make LLM call with tools
                response = await self._call_llm_with_tools(messages, tools)

                # Extract tool calls from response
                tool_calls = self._extract_tool_calls(response)
                final_content = self._extract_content(response)

                if tool_calls:
                    for tool_call in tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["arguments"]
                        tool_call_id = tool_call.get("id") or str(uuid.uuid4())

                        # Check for ask_user_clarification
                        if tool_name == "ask_user_clarification":
                            question = tool_args.get("question", "Please clarify")
                            options = tool_args.get("options")

                            # Yield tool calling event
                            yield ToolEvent(
                                tool_call_id=tool_call_id,
                                name=tool_name,
                                status="calling",
                                function=tool_name,
                                args=tool_args,
                            )

                            # Yield WaitEvent and return
                            yield WaitEvent(
                                question=question,
                                options=options,
                                placeholder=question,
                            )

                            # Mark step as waiting (not failed)
                            yield StepEvent(
                                step_id=step_id,
                                description=step.description,
                                status="running",  # Still running, waiting for user
                            )
                            return

                        # Check if tool exists
                        if tool_name not in self._tool_map:
                            # Unknown tool - yield error
                            yield ToolEvent(
                                tool_call_id=tool_call_id,
                                name=tool_name,
                                status="failed",
                                function=tool_name,
                                args=tool_args,
                                error=f"Unknown tool: {tool_name}",
                            )

                            yield ErrorEvent(
                                code="UNKNOWN_TOOL",
                                message=f"Tool '{tool_name}' is not available",
                                details={"tool_name": tool_name},
                            )

                            yield StepEvent(
                                step_id=step_id,
                                description=step.description,
                                status="failed",
                            )
                            return

                        # Execute the tool
                        langchain_tool = self._tool_map[tool_name]

                        # Yield tool calling event
                        yield ToolEvent(
                            tool_call_id=tool_call_id,
                            name=tool_name,
                            status="calling",
                            function=tool_name,
                            args=tool_args,
                        )

                        try:
                            # Execute tool (may be sync or async)
                            result = await self._execute_tool(langchain_tool, tool_args)

                            # Yield tool result event
                            yield ToolEvent(
                                tool_call_id=tool_call_id,
                                name=tool_name,
                                status="called",
                                function=tool_name,
                                args=tool_args,
                                result=result,
                            )

                            # Add tool result to messages (append to context exactly once)
                            messages.append({
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": tool_call_id,
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": json.dumps(tool_args),
                                        },
                                    }
                                ],
                            })
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": json.dumps(result),
                            })

                        except Exception as tool_exc:
                            # Tool execution failed
                            error_msg = str(tool_exc)
                            logger.error("Tool %s failed: %s", tool_name, tool_exc)

                            yield ToolEvent(
                                tool_call_id=tool_call_id,
                                name=tool_name,
                                status="failed",
                                function=tool_name,
                                args=tool_args,
                                error=error_msg,
                            )

                            # Add error to context
                            messages.append({
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": tool_call_id,
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": json.dumps(tool_args),
                                        },
                                    }
                                ],
                            })
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": json.dumps({"ok": False, "error": error_msg}),
                            })

                    last_has_tool_call = True
                else:
                    # No tool call - LLM provided a final response
                    last_has_tool_call = False

                    # Yield the final message
                    if final_content:
                        yield MessageEvent(
                            role="assistant",
                            content=final_content,
                        )
                    else:
                        # No content but no tools - step complete
                        yield MessageEvent(
                            role="assistant",
                            content=f"Step '{step.description}' completed.",
                        )

            except Exception as exc:
                logger.error("Execution error: %s", exc)
                yield ErrorEvent(
                    code="EXECUTION_ERROR",
                    message=str(exc),
                )

                yield StepEvent(
                    step_id=step_id,
                    description=step.description,
                    status="failed",
                )
                return

        # Check if we hit the max tool calls limit
        if tool_call_count >= MAX_TOOL_CALLS_PER_STEP:
            yield ErrorEvent(
                code="MAX_TOOL_CALLS_REACHED",
                message=f"Step exceeded maximum tool calls ({MAX_TOOL_CALLS_PER_STEP}). Possible infinite loop.",
            )

            yield StepEvent(
                step_id=step_id,
                description=step.description,
                status="failed",
            )
            return

        # Step completed successfully
        yield StepEvent(
            step_id=step_id,
            description=step.description,
            status="completed",
        )

    def _extract_tool_calls(self, response: Any) -> List[Dict[str, Any]]:
        """
        Extract tool calls from LLM response.

        Handles different response formats from OpenAI and Anthropic.

        Args:
            response: LLM response object.

        Returns:
            List of tool call dicts with name, arguments, and id.
        """
        tool_calls = []

        # Handle OpenAI-style tool_calls attribute
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                # Get name
                name = getattr(tc, "name", None)
                if name is None and hasattr(tc, "function"):
                    name = getattr(tc.function, "name", None)
                name = name or "unknown"

                # Get arguments
                args_str = getattr(tc, "arguments", None)
                if args_str is None and hasattr(tc, "function"):
                    args_str = getattr(tc.function, "arguments", "{}")
                if args_str is None:
                    args_str = "{}"

                # Parse arguments if string
                if isinstance(args_str, str):
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = args_str or {}

                # Get call id
                call_id = getattr(tc, "id", None) or str(uuid.uuid4())

                tool_calls.append({
                    "name": name,
                    "arguments": args,
                    "id": call_id,
                })

        return tool_calls

    def _extract_content(self, response: Any) -> str:
        """
        Extract text content from LLM response.

        Args:
            response: LLM response object.

        Returns:
            Text content string.
        """
        content = getattr(response, "content", None)
        if content:
            return content
        return ""

    def _build_messages(
        self,
        plan: PlanEvent,
        step: PlanStep,
        message: str,
    ) -> List[Dict[str, Any]]:
        """
        Build the message list for the LLM call.

        Args:
            plan: The current plan.
            step: The step to execute.
            message: Optional user message.

        Returns:
            List of messages for the LLM.
        """
        # Format plan steps for context
        steps_text = "\n".join(
            f"- [{s.id}] {s.description} -> {s.expected_tool} [{s.status}]"
            for s in plan.steps
        )
        
        # Build the system prompt
        system_prompt = EXECUTION_SYSTEM_PROMPT.format(
            plan_title=plan.title,
            plan_steps=steps_text,
            tools_description=self._format_tools_for_prompt(),
        )
        
        # Build user message
        user_message = EXECUTION_PROMPT.format(
            current_step_id=step.id,
            current_step_description=step.description,
            expected_tool=step.expected_tool,
            user_message=message or "(no additional context)",
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        
        return messages

    async def _call_llm_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Any:
        """
        Call the LLM with tool definitions.

        Args:
            messages: List of messages.
            tools: List of tool definitions in OpenAI format.

        Returns:
            LLM response with tool_calls attribute.
        """
        # Use the provider's completion method with tools
        # The OpenAI-compatible adapter supports tool_calls
        from openai import AsyncOpenAI
        from openai.types.chat import ChatCompletionMessageParam
        from app.core.config import get_settings
        
        settings = get_settings()
        
        # Get the model name from settings
        model = settings.default_model
        
        # Determine base URL and API key based on model
        if model.startswith(("deepseek", "mimo")):
            api_key = settings.deepseek_api_key
            base_url = settings.deepseek_base_url
        elif model.startswith("claude"):
            # Use Anthropic directly for Claude
            return await self._call_anthropic_with_tools(messages, tools, model)
        else:
            api_key = settings.openai_api_key
            base_url = None
        
        # Create client
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        
        client = AsyncOpenAI(**client_kwargs)
        
        # Build kwargs for chat completion
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,  # type: ignore
            "tools": tools,
            "max_tokens": 4096,
            "temperature": 0.0,
        }
        
        if model.startswith("deepseek"):
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        
        response = await client.chat.completions.create(**kwargs)
        return response.choices[0].message

    async def _call_anthropic_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        model: str,
    ) -> Any:
        """
        Call Anthropic Claude with tool definitions.

        Args:
            messages: List of messages.
            tools: List of tool definitions.
            model: Anthropic model name.

        Returns:
            LLM response with tool_calls attribute.
        """
        import anthropic
        from app.core.config import get_settings
        
        settings = get_settings()
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        
        # Convert OpenAI-style tools to Anthropic format
        anthropic_tools = []
        for tool in tools:
            func = tool.get("function", {})
            anthropic_tools.append({
                "name": func.get("name"),
                "description": func.get("description"),
                "input_schema": func.get("parameters", {}),
            })
        
        # Extract system message
        system_message = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_message += msg["content"] + "\n"
            else:
                user_messages.append(msg)
        
        # Make the call
        kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "messages": user_messages,  # type: ignore
            "tools": anthropic_tools,
        }
        
        if system_message:
            kwargs["system"] = system_message
        
        response = await client.messages.create(**kwargs)
        
        # Convert Anthropic response to OpenAI-like format
        class ToolCall:
            def __init__(self, name: str, arguments: str, id: str):
                self.function = type("obj", (object,), {"name": name, "arguments": arguments})()
                self.id = id
        
        class Response:
            def __init__(self, content: str, tool_calls: List[ToolCall]):
                self.content = content
                self.tool_calls = tool_calls
        
        tool_calls = []
        content_text = ""
        
        for block in response.content:
            if hasattr(block, "type"):
                if block.type == "text":
                    content_text = block.text
                elif block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        name=block.name,
                        arguments=json.dumps(block.input),
                        id=block.id,
                    ))
        
        return Response(content=content_text, tool_calls=tool_calls)

    async def _execute_tool(
        self,
        tool: "BaseTool",
        args: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a LangChain tool.

        Handles both sync and async tools.

        Args:
            tool: LangChain BaseTool instance.
            args: Tool arguments.

        Returns:
            Tool result dict.
        """
        # Check if tool has async invoke
        if hasattr(tool, "ainvoke"):
            return await tool.ainvoke(args)
        elif hasattr(tool, "invoke"):
            # Sync invoke - run in thread pool
            import asyncio
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(tool.invoke, args)
                return future.result()
        else:
            raise ValueError(f"Tool {tool.name} has no invoke or ainvoke method")

    async def summarize_step(
        self,
        step: PlanStep,
        tool_results: List[Dict[str, Any]],
    ) -> str:
        """
        Generate a summary of step execution results.

        Args:
            step: The step that was executed.
            tool_results: List of tool results.

        Returns:
            Summary string.
        """
        # Build summary prompt
        tool_results_text = "\n".join(
            f"- {r.get('name', 'unknown')}: {r.get('result', {})}"
            for r in tool_results
        )
        
        prompt = SUMMARIZE_PROMPT.format(
            step_description=step.description,
            expected_tool=step.expected_tool,
            tool_results=tool_results_text or "(no tool results)",
        )
        
        messages = [
            {"role": "user", "content": prompt},
        ]
        
        try:
            summary = await self.provider.complete(
                messages=messages,
                system="You are a helpful assistant that summarizes tool execution results.",
                max_tokens=512,
            )
            return summary
        except Exception as exc:
            logger.error("Summary generation failed: %s", exc)
            return f"Step completed with {len(tool_results)} tool call(s)."
