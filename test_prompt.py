import asyncio
from app.agents.assistant.graph.state import AssistantGraphState
from app.agents.assistant.graph.nodes import _build_react_messages
from langchain_core.messages import HumanMessage

state = AssistantGraphState(messages=[HumanMessage(content="bạn biết gì về project này")])
msgs = _build_react_messages(state)
for m in msgs:
    print(m)
