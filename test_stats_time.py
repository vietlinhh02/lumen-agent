import asyncio
import time
from httpx import AsyncClient

async def run():
    t0 = time.time()
    async with AsyncClient() as client:
        r1, r2 = await asyncio.gather(
            client.get("http://127.0.0.1:8000/api/projects"),
            client.get("http://127.0.0.1:8000/api/stats")
        )
        t1 = time.time()
        print(f"Latency: {t1 - t0:.2f}s")

asyncio.run(run())
