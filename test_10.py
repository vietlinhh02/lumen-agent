import asyncio
import time
from httpx import AsyncClient

async def run():
    t0 = time.time()
    async with AsyncClient() as client:
        reqs = [client.get("http://127.0.0.1:8000/api/projects") for _ in range(10)]
        await asyncio.gather(*reqs)
        t1 = time.time()
        print(f"Latency: {t1 - t0:.2f}s")

asyncio.run(run())
