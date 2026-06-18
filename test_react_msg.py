import json
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from app.agents.assistant.graph.nodes import _message_to_dict

messages = [
    HumanMessage(content="bạn biết gì về project này"),
    AIMessage(content="", tool_calls=[{'name': 'list_projects', 'args': {}, 'id': 'call_123', 'type': 'tool_call'}]),
    ToolMessage(content='{"ok": true, "message": "Found 1 projects", "data": {"projects": [{"name": "AI Project"}]}}', tool_call_id="call_123", name="list_projects")
]

for m in messages:
    print(json.dumps(_message_to_dict(m), indent=2))
