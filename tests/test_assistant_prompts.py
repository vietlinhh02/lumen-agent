from app.ai.prompts import ASSISTANT_SYSTEM, TOOL_DESCRIPTIONS


def test_assistant_system_prompt_mentions_all_10_tools():
    """Verify all 10 production tools are mentioned in the system prompt."""
    for tool in [
        "create_project",
        "search_papers",
        "save_paper_to_project",
        "trigger_normalization",
        "generate_matrix",
        "detect_gaps",
        "detect_conflicts",
        "generate_report",
        "edit_report_section",
        "qa_search_papers",
    ]:
        assert tool in ASSISTANT_SYSTEM, f"Missing tool: {tool}"

    # Should mention the standard pipeline
    assert "trigger_normalization" in ASSISTANT_SYSTEM
    assert "detect_conflicts" in ASSISTANT_SYSTEM


def test_assistant_system_includes_pipeline_guidance():
    """System prompt should guide the LLM through the production pipeline."""
    assert "trigger_normalization" in ASSISTANT_SYSTEM
    assert "Standard research pipeline" in ASSISTANT_SYSTEM
    assert "full-text chunks" in ASSISTANT_SYSTEM.lower()


def test_tool_descriptions_is_list_of_dicts():
    assert isinstance(TOOL_DESCRIPTIONS, list)
    assert len(TOOL_DESCRIPTIONS) == 11
    for td in TOOL_DESCRIPTIONS:
        assert "name" in td
        assert "description" in td
        assert "parameters" in td
        assert td["parameters"]["type"] == "object"

    # Verify all 11 tools have descriptions
    names = {td["name"] for td in TOOL_DESCRIPTIONS}
    assert names == {
        "create_project",
        "search_papers",
        "save_paper_to_project",
        "save_papers_batch",
        "generate_matrix",
        "trigger_normalization",
        "detect_gaps",
        "detect_conflicts",
        "generate_report",
        "edit_report_section",
        "qa_search_papers",
    }
