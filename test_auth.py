import asyncio
from sqlalchemy import select
from app.db.session import async_session_factory
from app.db.models import User

async def run():
    async with async_session_factory() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one_or_none()
        if user:
            print(user.id)
        else:
            print("No user")

asyncio.run(run())
