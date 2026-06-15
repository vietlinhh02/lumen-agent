from app.ai.prompts import ASSISTANT_SYSTEM, TOOL_DESCRIPTIONS


def test_assistant_system_prompt_mentions_all_local_tools():
    """Verify all fast-path tools are mentioned in the system prompt."""
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


def test_assistant_system_mentions_sandbox_tools():
    """The system prompt should describe the 8 sandbox-backed tools."""
    for tool in [
        "run_python",
        "run_shell",
        "read_file",
        "write_file",
        "open_pdf_page",
        "grep_pdf",
        "install_packages",
    ]:
        assert tool in ASSISTANT_SYSTEM, f"Missing sandbox tool: {tool}"


def test_assistant_system_includes_pipeline_guidance():
    """System prompt should guide the LLM through the production pipeline."""
    assert "trigger_normalization" in ASSISTANT_SYSTEM
    assert "Standard research pipeline" in ASSISTANT_SYSTEM
    assert "full-text chunks" in ASSISTANT_SYSTEM.lower()


def test_assistant_system_mentions_sandbox_persistence():
    """The LLM should know that /workspace files persist across calls."""
    assert "/workspace" in ASSISTANT_SYSTEM
    assert "persist" in ASSISTANT_SYSTEM.lower()


def test_tool_descriptions_is_list_of_dicts():
    assert isinstance(TOOL_DESCRIPTIONS, list)
    assert len(TOOL_DESCRIPTIONS) == 19
    for td in TOOL_DESCRIPTIONS:
        assert "name" in td
        assert "description" in td
        assert "parameters" in td
        assert td["parameters"]["type"] == "object"

    # Verify all 19 tools have descriptions (11 local + 8 sandbox)
    names = {td["name"] for td in TOOL_DESCRIPTIONS}
    assert names == {
        # Local fast path
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
        # Sandbox path
        "run_python",
        "run_shell",
        "read_file",
        "write_file",
        "list_files",
        "open_pdf_page",
        "grep_pdf",
        "install_packages",
    }


def test_each_sandbox_tool_has_parameters():
    """Sandbox tool params must include the right fields so the LLM knows
    what to send."""
    name_to_required = {
        "run_python": ["code"],
        "run_shell": ["command"],
        "read_file": ["path"],
        "write_file": ["path", "content"],
        "open_pdf_page": ["path", "page"],
        "grep_pdf": ["path", "pattern"],
        "install_packages": ["packages"],
    }
    by_name = {td["name"]: td for td in TOOL_DESCRIPTIONS}
    for name, required in name_to_required.items():
        td = by_name[name]
        params = td["parameters"]
        assert params.get("required") == required, (
            f"{name} required params mismatch: {params.get('required')} vs {required}"
        )
