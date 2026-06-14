from app.ai.prompts import ASSISTANT_SYSTEM, TOOL_DESCRIPTIONS


def test_assistant_system_prompt_mentions_8_tools():
    for tool in [
        "create_project",
        "search_papers",
        "save_paper_to_project",
        "generate_matrix",
        "detect_gaps",
        "generate_report",
        "edit_report_section",
        "qa_search_papers",
    ]:
        assert tool in ASSISTANT_SYSTEM, f"Missing tool: {tool}"


def test_tool_descriptions_is_list_of_dicts():
    assert isinstance(TOOL_DESCRIPTIONS, list)
    assert len(TOOL_DESCRIPTIONS) == 8
    for td in TOOL_DESCRIPTIONS:
        assert "name" in td
        assert "description" in td
        assert "parameters" in td
        assert td["parameters"]["type"] == "object"
