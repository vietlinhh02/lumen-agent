"""Tests for the ReActAgent."""

from unittest.mock import MagicMock


class MockProvider:
    """Mock AI provider."""

    def __init__(self, response: str = "Final Answer: Test response"):
        self.response = response

    async def complete(self, messages, system=None, max_tokens=2048):
        return self.response


class TestReActAgentInit:
    """Test ReActAgent initialization."""

    def test_creates_with_defaults(self) -> None:
        """Agent creates with default values."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        tools = []

        agent = ReActAgent(provider=provider, tools=tools)

        assert agent.provider is provider
        assert agent._tools == []
        assert agent.max_iterations == 15
        assert agent.max_wall_time == 600

    def test_creates_with_custom_values(self) -> None:
        """Agent creates with custom values."""
        from app.agents.assistant.react.agent import ProjectContext, ReActAgent

        provider = MockProvider()
        tools = []
        ctx = ProjectContext(project_id="test-project", user_id="user-1")

        agent = ReActAgent(
            provider=provider,
            tools=tools,
            project_context=ctx,
            max_iterations=5,
            max_wall_time=300,
        )

        assert agent.max_iterations == 5
        assert agent.max_wall_time == 300
        assert agent.project_context.project_id == "test-project"
        assert agent.project_context.user_id == "user-1"

    def test_builds_tool_map(self) -> None:
        """Agent builds tool map from tools list."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        mock_tool = MagicMock()
        mock_tool.name = "search_papers"
        tools = [mock_tool]

        agent = ReActAgent(provider=provider, tools=tools)

        assert "search_papers" in agent._tool_map
        assert agent._tool_map["search_papers"] is mock_tool


class TestProjectContext:
    """Test ProjectContext class."""

    def test_has_project_true(self) -> None:
        """has_project returns True when project_id is set."""
        from app.agents.assistant.react.agent import ProjectContext

        ctx = ProjectContext(project_id="test-id")
        assert ctx.has_project is True

    def test_has_project_false(self) -> None:
        """has_project returns False when project_id is None."""
        from app.agents.assistant.react.agent import ProjectContext

        ctx = ProjectContext(project_id=None)
        assert ctx.has_project is False

    def test_defaults_to_none(self) -> None:
        """Defaults to None for project_id and user_id."""
        from app.agents.assistant.react.agent import ProjectContext

        ctx = ProjectContext()
        assert ctx.project_id is None
        assert ctx.user_id is None


class TestInferDirectTool:
    """Test direct tool inference."""

    def test_infers_list_projects(self) -> None:
        """Infers list_projects for project requests."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        assert agent._infer_direct_tool("list my projects") == "list_projects"
        assert agent._infer_direct_tool("show projects") == "list_projects"
        assert agent._infer_direct_tool("hiển thị các dự án") == "list_projects"

    def test_infers_list_papers(self) -> None:
        """Infers list_project_papers for paper requests."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        assert agent._infer_direct_tool("list my papers") == "list_project_papers"
        assert agent._infer_direct_tool("show papers") == "list_project_papers"

    def test_infers_list_reports(self) -> None:
        """Infers list_reports for report requests."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        assert agent._infer_direct_tool("list reports") == "list_reports"
        assert agent._infer_direct_tool("show my reports") == "list_reports"

    def test_infers_list_gaps(self) -> None:
        """Infers list_gaps for gap requests."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        assert agent._infer_direct_tool("list gaps") == "list_gaps"
        assert agent._infer_direct_tool("show research gaps") == "list_gaps"

    def test_infers_list_conflicts(self) -> None:
        """Infers list_conflicts for conflict requests."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        assert agent._infer_direct_tool("list conflicts") == "list_conflicts"
        assert agent._infer_direct_tool("show conflicts") == "list_conflicts"

    def test_returns_none_for_unknown(self) -> None:
        """Returns None for unrecognized requests."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        assert agent._infer_direct_tool("do something complex") is None


class TestParseToolCallsFromText:
    """Test tool call parsing from LLM text."""

    def test_parses_single_tool_call(self) -> None:
        """Parses single tool call."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        text = '''
        Thought: I need to search for papers about AI.
        Action: search_papers
        Action Input: {"query": "AI in healthcare", "max_results": 10}
        '''

        calls = agent._parse_tool_calls_from_text(text)

        assert len(calls) == 1
        assert calls[0].name == "search_papers"
        assert calls[0].arguments == {"query": "AI in healthcare", "max_results": 10}

    def test_parses_multiple_tool_calls(self) -> None:
        """Parses multiple tool calls."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        text = '''
        Action: search_papers
        Action Input: {"query": "AI"}

        Action: generate_matrix
        Action Input: {"project_id": "abc123"}
        '''

        calls = agent._parse_tool_calls_from_text(text)

        assert len(calls) == 2
        assert calls[0].name == "search_papers"
        assert calls[1].name == "generate_matrix"

    def test_handles_invalid_json(self) -> None:
        """Handles invalid JSON gracefully."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        text = '''
        Action: search_papers
        Action Input: {invalid json}
        '''

        calls = agent._parse_tool_calls_from_text(text)

        assert len(calls) == 1
        assert calls[0].arguments == {}

    def test_returns_empty_for_no_calls(self) -> None:
        """Returns empty list when no tool calls found."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        text = "This is just a regular response without any tool calls."

        calls = agent._parse_tool_calls_from_text(text)

        assert calls == []


class TestExtractFinalAnswer:
    """Test final answer extraction."""

    def test_extracts_from_final_answer_pattern(self) -> None:
        """Extracts from Final Answer: pattern."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        text = '''
        Thought: Let me answer this question.
        Final Answer: The answer is 42.
        '''

        answer = agent._extract_final_answer(text)

        assert answer == "The answer is 42."

    def test_extracts_from_answer_pattern(self) -> None:
        """Extracts from Answer: pattern."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        text = "Answer: Here is the answer."

        answer = agent._extract_final_answer(text)

        assert answer == "Here is the answer."

    def test_returns_cleaned_text(self) -> None:
        """Returns cleaned text when no pattern found."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        text = "Just a simple response without any special markers."

        answer = agent._extract_final_answer(text)

        assert answer == "Just a simple response without any special markers."


class TestFormatToolsForPrompt:
    """Test tool formatting for prompt."""

    def test_formats_single_tool(self) -> None:
        """Formats single tool correctly."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        mock_tool = MagicMock()
        mock_tool.name = "search_papers"
        mock_tool.description = "Search for papers"
        tools = [mock_tool]

        agent = ReActAgent(provider=provider, tools=tools)

        formatted = agent._format_tools_for_prompt()

        assert "- search_papers: Search for papers" in formatted

    def test_formats_multiple_tools(self) -> None:
        """Formats multiple tools."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        tool1 = MagicMock()
        tool1.name = "search_papers"
        tool1.description = "Search for papers"
        tool2 = MagicMock()
        tool2.name = "list_projects"
        tool2.description = "List projects"
        tools = [tool1, tool2]

        agent = ReActAgent(provider=provider, tools=tools)

        formatted = agent._format_tools_for_prompt()

        assert "search_papers" in formatted
        assert "list_projects" in formatted

    def test_handles_empty_tools(self) -> None:
        """Handles empty tools list."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        formatted = agent._format_tools_for_prompt()

        assert "(No tools available)" in formatted


class TestScratchpadProperty:
    """Test scratchpad property."""

    def test_returns_scratchpad(self) -> None:
        """Returns the scratchpad instance."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        assert agent.scratchpad is agent._scratchpad

    def test_scratchpad_is_shared(self) -> None:
        """Same scratchpad instance returned on multiple calls."""
        from app.agents.assistant.react.agent import ReActAgent

        provider = MockProvider()
        agent = ReActAgent(provider=provider, tools=[])

        sp1 = agent.scratchpad
        sp2 = agent.scratchpad

        assert sp1 is sp2
