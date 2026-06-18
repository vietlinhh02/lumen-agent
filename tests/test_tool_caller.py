"""Tests for the ToolCaller module."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class MockPydanticModel:
    """Mock Pydantic model with model_fields for testing."""

    def __init__(self, fields: dict):
        self._fields = fields

    @property
    def model_fields(self):
        return self._fields


class MockField:
    """Mock Pydantic field."""

    def __init__(self, annotation, description: str = "", required: bool = True):
        self.annotation = annotation
        self.description = description
        self._required = required

    def is_required(self) -> bool:
        return self._required


class TestConvertToOpenAIFormat:
    """Test tool format conversion to OpenAI format."""

    @pytest.fixture
    def caller(self):
        from app.agents.assistant.react.tool_caller import ToolCaller
        return ToolCaller()

    def test_empty_tools_list(self, caller) -> None:
        """Empty tools list returns empty."""
        result = caller.convert_to_openai_format([])
        assert result == []

    def test_single_tool_basic(self, caller) -> None:
        """Single tool converted correctly."""
        mock_tool = MagicMock()
        mock_tool.name = "search_papers"
        mock_tool.description = "Search for academic papers"
        mock_tool.args_schema = None

        result = caller.convert_to_openai_format([mock_tool])

        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "search_papers"
        assert result[0]["function"]["description"] == "Search for academic papers"
        assert result[0]["function"]["parameters"] == {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def test_tool_with_schema(self, caller) -> None:
        """Tool with args_schema converted correctly."""
        mock_tool = MagicMock()
        mock_tool.name = "search_papers"
        mock_tool.description = "Search for papers"
        mock_tool.args_schema = MockPydanticModel({
            "query": MockField(str, "Search query", True),
            "max_results": MockField(int, "Max results", False),
        })

        result = caller.convert_to_openai_format([mock_tool])

        func = result[0]["function"]
        assert func["name"] == "search_papers"
        assert "query" in func["parameters"]["properties"]
        assert "max_results" in func["parameters"]["properties"]
        assert func["parameters"]["properties"]["query"]["type"] == "string"
        assert func["parameters"]["properties"]["max_results"]["type"] == "integer"
        assert "query" in func["parameters"]["required"]

    def test_infers_boolean_type(self, caller) -> None:
        """Boolean types inferred correctly."""
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "Test"
        mock_tool.args_schema = MockPydanticModel({
            "flag": MockField(bool, "A flag"),
        })

        result = caller.convert_to_openai_format([mock_tool])
        assert result[0]["function"]["parameters"]["properties"]["flag"]["type"] == "boolean"

    def test_infers_integer_type(self, caller) -> None:
        """Integer types inferred correctly."""
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "Test"
        mock_tool.args_schema = MockPydanticModel({
            "count": MockField(int, "Count"),
        })

        result = caller.convert_to_openai_format([mock_tool])
        assert result[0]["function"]["parameters"]["properties"]["count"]["type"] == "integer"


class TestConvertToAnthropicFormat:
    """Test tool format conversion to Anthropic format."""

    @pytest.fixture
    def caller(self):
        from app.agents.assistant.react.tool_caller import ToolCaller
        return ToolCaller()

    def test_single_tool(self, caller) -> None:
        """Single tool converted to Anthropic format."""
        mock_tool = MagicMock()
        mock_tool.name = "search_papers"
        mock_tool.description = "Search for papers"
        mock_tool.args_schema = None

        result = caller.convert_to_anthropic_format([mock_tool])

        assert len(result) == 1
        assert result[0]["name"] == "search_papers"
        assert result[0]["description"] == "Search for papers"
        assert result[0]["input_schema"]["type"] == "object"


class TestToolCall:
    """Test the ToolCall dataclass."""

    def test_creates_with_generated_id(self) -> None:
        from app.agents.assistant.react.tool_caller import ToolCall

        call = ToolCall(name="test", arguments={"key": "value"})
        assert call.name == "test"
        assert call.arguments == {"key": "value"}
        assert call.call_id is not None
        assert len(call.call_id) > 0

    def test_creates_with_provided_id(self) -> None:
        from app.agents.assistant.react.tool_caller import ToolCall

        call = ToolCall(name="test", arguments={}, call_id="custom-id")
        assert call.call_id == "custom-id"


class TestExecute:
    """Test tool execution."""

    @pytest.fixture
    def caller(self):
        from app.agents.assistant.react.tool_caller import ToolCaller
        return ToolCaller()

    @pytest.mark.asyncio
    async def test_execute_async_tool(self, caller) -> None:
        """Async tool executed correctly."""
        mock_tool = MagicMock()
        mock_tool.name = "search_papers"
        mock_tool.ainvoke = AsyncMock(return_value={"ok": True, "papers": []})

        result, is_wait = await caller.execute(mock_tool, {"query": "AI"})

        assert is_wait is False
        assert result == {"ok": True, "papers": []}
        mock_tool.ainvoke.assert_called_once_with({"query": "AI"})

    @pytest.mark.asyncio
    async def test_execute_ask_user_clarification_returns_wait_sentinel(self, caller) -> None:
        """ask_user_clarification returns wait sentinel."""
        mock_tool = MagicMock()
        mock_tool.name = "ask_user_clarification"
        mock_tool.ainvoke = AsyncMock()

        result, is_wait = await caller.execute(mock_tool, {
            "question": "What topic?",
            "options": ["A", "B"],
        })

        assert is_wait is True
        assert result["_wait"] is True
        assert result["question"] == "What topic?"
        assert result["options"] == ["A", "B"]
        # Tool should NOT be invoked
        mock_tool.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_failure_returns_error(self, caller) -> None:
        """Tool failure returns error dict."""
        mock_tool = MagicMock()
        mock_tool.name = "search_papers"
        mock_tool.ainvoke = AsyncMock(side_effect=RuntimeError("API error"))

        result, is_wait = await caller.execute(mock_tool, {"query": "AI"})

        assert is_wait is False
        assert result["ok"] is False
        assert "API error" in result["error"]
        assert result["tool"] == "search_papers"


class TestExecuteParallel:
    """Test parallel tool execution."""

    @pytest.fixture
    def caller(self):
        from app.agents.assistant.react.tool_caller import ToolCaller
        return ToolCaller()

    @pytest.mark.asyncio
    async def test_parallel_empty_calls(self, caller) -> None:
        """Empty calls list returns empty."""
        tool_map = {}
        result = await caller.execute_parallel(tool_map, [])
        assert result == []

    @pytest.mark.asyncio
    async def test_parallel_single_call(self, caller) -> None:
        """Single call executed and returned."""
        mock_tool = MagicMock()
        mock_tool.name = "search_papers"
        mock_tool.ainvoke = AsyncMock(return_value={"ok": True})

        tool_map = {"search_papers": mock_tool}
        from app.agents.assistant.react.tool_caller import ToolCall

        calls = [ToolCall(name="search_papers", arguments={"query": "AI"})]
        result = await caller.execute_parallel(tool_map, calls)

        assert len(result) == 1
        call, tool_result, is_wait = result[0]
        assert call.name == "search_papers"
        assert tool_result == {"ok": True}
        assert is_wait is False

    @pytest.mark.asyncio
    async def test_parallel_multiple_calls(self, caller) -> None:
        """Multiple calls executed in parallel."""
        tool1 = MagicMock()
        tool1.name = "tool1"
        tool1.ainvoke = AsyncMock(return_value={"result": 1})

        tool2 = MagicMock()
        tool2.name = "tool2"
        tool2.ainvoke = AsyncMock(return_value={"result": 2})

        tool_map = {"tool1": tool1, "tool2": tool2}
        from app.agents.assistant.react.tool_caller import ToolCall

        calls = [
            ToolCall(name="tool1", arguments={}),
            ToolCall(name="tool2", arguments={}),
        ]

        result = await caller.execute_parallel(tool_map, calls)

        assert len(result) == 2
        # Both should complete
        results = [r[1] for r in result]
        assert {"result": 1} in results
        assert {"result": 2} in results

    @pytest.mark.asyncio
    async def test_parallel_unknown_tool_returns_error(self, caller) -> None:
        """Unknown tool returns error."""
        tool_map = {}
        from app.agents.assistant.react.tool_caller import ToolCall

        calls = [ToolCall(name="unknown_tool", arguments={})]
        result = await caller.execute_parallel(tool_map, calls)

        assert len(result) == 1
        _, tool_result, _ = result[0]
        assert tool_result["ok"] is False
        assert "Unknown tool" in tool_result["error"]


class TestParseToolCalls:
    """Test tool call extraction from LLM responses."""

    @pytest.fixture
    def caller(self):
        from app.agents.assistant.react.tool_caller import ToolCaller
        return ToolCaller()

    def test_empty_response(self, caller) -> None:
        """Empty response returns empty list."""
        response = MagicMock()
        response.tool_calls = []

        result = caller.parse_tool_calls(response)
        assert result == []

    def test_openai_style_tool_calls(self, caller) -> None:
        """OpenAI-style tool_calls parsed correctly."""
        mock_tc = MagicMock()
        mock_tc.name = "search_papers"
        mock_tc.arguments = '{"query": "AI"}'
        mock_tc.id = "call_123"

        response = MagicMock()
        response.tool_calls = [mock_tc]

        result = caller.parse_tool_calls(response)

        assert len(result) == 1
        assert result[0].name == "search_papers"
        assert result[0].arguments == {"query": "AI"}
        assert result[0].call_id == "call_123"

    def test_function_attribute_fallback(self, caller) -> None:
        """Falls back to function.name when name not set."""
        mock_tc = MagicMock()
        mock_tc.name = None
        mock_tc.function = MagicMock()
        mock_tc.function.name = "list_projects"
        mock_tc.arguments = "{}"
        mock_tc.id = None

        response = MagicMock()
        response.tool_calls = [mock_tc]

        result = caller.parse_tool_calls(response)

        assert len(result) == 1
        assert result[0].name == "list_projects"

    def test_invalid_json_arguments(self, caller) -> None:
        """Invalid JSON arguments handled gracefully."""
        mock_tc = MagicMock()
        mock_tc.name = "tool"
        mock_tc.arguments = "not valid json"
        mock_tc.id = "call_1"

        response = MagicMock()
        response.tool_calls = [mock_tc]

        result = caller.parse_tool_calls(response)

        assert len(result) == 1
        assert result[0].arguments == {}

    def test_no_tool_calls(self, caller) -> None:
        """Response without tool_calls attribute returns empty."""
        response = MagicMock(spec=[])  # No attributes

        result = caller.parse_tool_calls(response)
        assert result == []


class TestIsWaitResult:
    """Test wait sentinel detection."""

    @pytest.fixture
    def caller(self):
        from app.agents.assistant.react.tool_caller import ToolCaller
        return ToolCaller()

    def test_wait_sentinel_detected(self, caller) -> None:
        """_wait=True detected correctly."""
        assert caller.is_wait_result({"_wait": True}) is True

    def test_wait_sentinel_not_present(self, caller) -> None:
        """_wait not present returns False."""
        assert caller.is_wait_result({"ok": True}) is False

    def test_wait_false(self, caller) -> None:
        """_wait=False returns False."""
        assert caller.is_wait_result({"_wait": False}) is False

    def test_non_dict_returns_false(self, caller) -> None:
        """Non-dict returns False."""
        assert caller.is_wait_result("string") is False
        assert caller.is_wait_result(None) is False
        assert caller.is_wait_result([1, 2]) is False


class TestInferParamType:
    """Test parameter type inference."""

    @pytest.fixture
    def caller(self):
        from app.agents.assistant.react.tool_caller import ToolCaller
        return ToolCaller()

    def test_infers_bool(self, caller) -> None:
        assert caller._infer_param_type(bool) == "boolean"

    def test_infers_int(self, caller) -> None:
        assert caller._infer_param_type(int) == "integer"

    def test_infers_float(self, caller) -> None:
        assert caller._infer_param_type(float) == "number"

    def test_infers_list(self, caller) -> None:
        assert caller._infer_param_type(list) == "array"

    def test_infers_dict(self, caller) -> None:
        assert caller._infer_param_type(dict) == "object"

    def test_infers_string_by_default(self, caller) -> None:
        assert caller._infer_param_type(str) == "string"
        assert caller._infer_param_type("SomeUnknownType") == "string"
