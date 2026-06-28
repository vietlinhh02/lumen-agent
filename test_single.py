import asyncio
import time
from httpx import AsyncClient

async def run():
    t0 = time.time()
    async with AsyncClient() as client:
        r = await client.get("http://127.0.0.1:8000/api/projects")
        t1 = time.time()
        print(f"Latency: {t1 - t0:.2f}s")

asyncio.run(run())
