import json
import asyncio
from app.ai.provider import _build_provider_for_model

async def main():
    provider = _build_provider_for_model("mimo-v2.5")
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "", "tool_calls": [{'name': 'list_projects', 'args': {}, 'id': 'call_123', 'type': 'tool_call'}]},
        {"role": "tool", "tool_call_id": "call_123", "name": "list_projects", "content": "success"}
    ]
    try:
        res = await provider.complete(messages=messages, max_tokens=10)
        print("Success")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
