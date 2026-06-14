from app.services.assistant_tools import TOOL_REGISTRY


def test_all_8_tools_registered():
    expected = {
        "create_project",
        "search_papers",
        "save_paper_to_project",
        "generate_matrix",
        "detect_gaps",
        "generate_report",
        "edit_report_section",
        "qa_search_papers",
    }
    assert set(TOOL_REGISTRY.keys()) == expected


def test_each_handler_is_async_callable():
    for name, handler in TOOL_REGISTRY.items():
        assert callable(handler), f"{name} not callable"
        import inspect

        assert inspect.iscoroutinefunction(handler), f"{name} not async"
