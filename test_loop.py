import asyncio
from httpx import AsyncClient

async def run():
    async with AsyncClient() as client:
        await asyncio.gather(*[client.get("http://127.0.0.1:8000/api/projects") for _ in range(10)])

asyncio.run(run())
