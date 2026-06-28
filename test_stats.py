import asyncio
from httpx import AsyncClient

async def run():
    async with AsyncClient() as client:
        r1, r2 = await asyncio.gather(
            client.get("http://127.0.0.1:8000/api/projects"),
            client.get("http://127.0.0.1:8000/api/stats")
        )
        print(r1.status_code, r2.status_code)

asyncio.run(run())
