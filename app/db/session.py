from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import socket
from urllib.parse import urlparse, urlunparse

from app.core.config import get_settings

settings = get_settings()

db_url = settings.database_url
try:
    parsed = urlparse(db_url)
    if parsed.hostname and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        # Force IPv4 resolution to prevent asyncpg from attempting IPv6
        # and hanging for 5s on misconfigured Docker/Coolify DNS networks
        ipv4 = socket.gethostbyname(parsed.hostname)
        netloc = parsed.netloc.replace(parsed.hostname, ipv4)
        parsed = parsed._replace(netloc=netloc)
        db_url = urlunparse(parsed)
except Exception:
    pass

engine = create_async_engine(
    db_url,
    echo=settings.debug,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=True,
    pool_recycle=3600,
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """Yield an async DB session per request."""
    async with async_session_factory() as session:
        yield session
