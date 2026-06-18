import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings

async def migrate():
    import asyncpg
    settings = get_settings()
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("ALTER TABLE assistant_events DROP CONSTRAINT IF EXISTS ck_assistant_events_type")
        await conn.execute("ALTER TABLE assistant_events ADD CONSTRAINT ck_assistant_events_type CHECK (event_type IN ('title', 'tool', 'progress', 'done', 'error', 'wait', 'message_ack', 'message', 'thought', 'iteration', 'step', 'plan'))")
        print("Constraint updated successfully.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate())
