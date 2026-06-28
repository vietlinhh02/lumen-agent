import asyncio
import asyncpg

async def check():
    dsn = "postgresql://postgres:EQe7fjNPcGly9tWiombzf1TMJw1Vfcybl59OMxe8LH1paPqF4BCdPsf0LXYq1fj0@152.42.188.239:5432/postgres"
    conn = await asyncpg.connect(dsn)
    try:
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        tables = [t['table_name'] for t in tables]
        print("Tables:", tables)
        
        # check specific columns
        users_cols = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
        users_cols = [c['column_name'] for c in users_cols]
        print("Users columns:", users_cols)

        chunks_cols = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'paper_chunks'")
        chunks_cols = [c['column_name'] for c in chunks_cols]
        print("Paper chunks columns:", chunks_cols)
        
        events_cols = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'assistant_events'")
        events_cols = [c['column_name'] for c in events_cols]
        print("Assistant events columns:", events_cols)
    finally:
        await conn.close()

asyncio.run(check())
