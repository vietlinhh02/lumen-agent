import asyncio
from openai import AsyncOpenAI

async def main():
    client = AsyncOpenAI(
        api_key="sk-sKzO2OhY8DGToftiFl1tCVrKFx5CqSZOz8vfLYBPKvGjRDZOzmnocIQ3abdMrFAv",
        base_url="https://opencode.ai/zen/go/v1"
    )
    resp = await client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "Hello. Output JSON {\"a\": 1}"}],
        response_format={"type": "json_object"}
    )
    print("Response Format True:", repr(resp.choices[0].message.content))

    resp2 = await client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "Hello. Output JSON {\"a\": 1}"}],
    )
    print("Response Format False:", repr(resp2.choices[0].message.content))

asyncio.run(main())
