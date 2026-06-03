"""Seed the database with an initial user.

Usage:
    uv run python scripts/seed_user.py [--username admin] [--password admin]
"""

import argparse
import asyncio

from sqlalchemy import select

from app.db.models import Base, User
from app.db.session import async_session_factory, engine
from app.services.auth import hash_password


async def seed(username: str, password: str) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.username == username))
        if result.scalar_one_or_none():
            print(f"User '{username}' already exists.")
            return

        user = User(username=username, hashed_password=hash_password(password))
        session.add(user)
        await session.commit()
        print(f"Created user '{username}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed initial user")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    args = parser.parse_args()
    asyncio.run(seed(args.username, args.password))
