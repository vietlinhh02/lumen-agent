import asyncio
import json
from openai import AsyncOpenAI

async def main():
    client = AsyncOpenAI(
        api_key="sk-sKzO2OhY8DGToftiFl1tCVrKFx5CqSZOz8vfLYBPKvGjRDZOzmnocIQ3abdMrFAv",
        base_url="https://opencode.ai/zen/go/v1"
    )
    schema = {
        "title": "Project Meta",
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "topic": {"type": "string"},
            "research_question": {"type": "string"}
        },
        "required": ["title", "topic"]
    }
    system = "You are a research project metadata extractor. Given a user's idea or description, produce a concise project title, a refined research topic, and an optional research question.\n\nRules:\n- Title: max 60 characters, academic style, no quotes.\n- Topic: 1-2 clear sentences describing the research area.\n- Research question: a focused, answerable question if possible, otherwise null.\n- ALL output MUST be in English. If the user's input is in another language (e.g. Vietnamese), translate and normalize it to English to optimize for paper searching.\n- Do NOT copy the raw user message verbatim."
    
    json_system = (
        f"You are a helpful assistant that ALWAYS responds with a single JSON object. "
        f"The JSON object MUST conform to this schema:\n{json.dumps(schema, indent=2)}\n"
        f"Do NOT include any text outside the JSON. Do NOT use markdown fences. "
        f"Output raw JSON only."
    )
    msgs = [
        {"role": "system", "content": json_system},
        {"role": "system", "content": system},
        {"role": "user", "content": "I want to research about AI agents in software engineering"}
    ]
    
    resp = await client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=msgs,
        response_format={"type": "json_object"}
    )
    print("RAW CONTENT:", repr(resp.choices[0].message.content))
    
    # Try parsing logic
    content = resp.choices[0].message.content or ""
    print("Content:", content)

asyncio.run(main())
