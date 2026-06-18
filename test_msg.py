import json
from langchain_core.messages import AIMessage, ToolMessage
from app.agents.assistant.graph.nodes import _message_to_dict

msg_ai = AIMessage(content="", tool_calls=[{'name': 'list_projects', 'args': {}, 'id': 'call_123', 'type': 'tool_call'}])
msg_tool = ToolMessage(content="foo", tool_call_id="call_123", name="list_projects")

print(json.dumps(_message_to_dict(msg_ai), indent=2))
print(json.dumps(_message_to_dict(msg_tool), indent=2))
