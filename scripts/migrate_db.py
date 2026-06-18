#!/usr/bin/env python3
"""Database migration script for assistant tables.

This script creates all assistant-related tables:
- assistant_sessions
- assistant_messages
- assistant_events
- assistant_plans

Usage:
    python scripts/migrate_db.py [--dry-run]
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def migrate(database_url: str, dry_run: bool = False):
    """Run database migration for assistant tables."""
    
    engine = create_async_engine(database_url, echo=True)
    
    async with engine.begin() as conn:
        print("\n=== Phase 1: Create extension ===")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        
        print("\n=== Phase 2: Create assistant tables ===")
        
        # assistant_sessions
        print("\nCreating assistant_sessions table...")
        if not dry_run:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS assistant_sessions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
                    title TEXT,
                    status VARCHAR(16) NOT NULL DEFAULT 'active',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT ck_assistant_sessions_status 
                        CHECK (status IN ('active', 'completed', 'failed', 'cancelled', 'archived'))
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_assistant_sessions_user_updated 
                    ON assistant_sessions (user_id, updated_at)
            """))
        
        # assistant_messages
        print("\nCreating assistant_messages table...")
        if not dry_run:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS assistant_messages (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    session_id UUID NOT NULL REFERENCES assistant_sessions(id) ON DELETE CASCADE,
                    turn_id VARCHAR(64) NOT NULL,
                    role VARCHAR(16) NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    client_message_id VARCHAR(64),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT ck_assistant_messages_role 
                        CHECK (role IN ('user', 'assistant'))
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_assistant_messages_session_created 
                    ON assistant_messages (session_id, created_at)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_assistant_messages_session_turn 
                    ON assistant_messages (session_id, turn_id)
            """))
        
        # assistant_events
        print("\nCreating/altering assistant_events table...")
        if not dry_run:
            # Check if table exists
            table_exists = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'assistant_events'
                )
            """))
            table_exists = table_exists.scalar()
            
            if not table_exists:
                await conn.execute(text("""
                    CREATE TABLE assistant_events (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        session_id UUID NOT NULL REFERENCES assistant_sessions(id) ON DELETE CASCADE,
                        turn_id VARCHAR(64) NOT NULL DEFAULT 'initial',
                        event_type VARCHAR(32) NOT NULL,
                        payload JSONB NOT NULL DEFAULT '{}',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        CONSTRAINT ck_assistant_events_type 
                            CHECK (event_type IN ('title', 'tool', 'progress', 'done', 'error', 'wait', 'message_ack', 'message', 'thought', 'iteration', 'step', 'plan'))
                    )
                """))
            else:
                # Table exists, add turn_id column if missing
                col_exists = await conn.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'assistant_events' AND column_name = 'turn_id'
                    )
                """))
                if not col_exists.scalar():
                    print("  Adding turn_id column to assistant_events...")
                    await conn.execute(text("""
                        ALTER TABLE assistant_events 
                        ADD COLUMN turn_id VARCHAR(64) NOT NULL DEFAULT 'initial'
                    """))
                    await conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS ix_assistant_events_session_turn 
                            ON assistant_events (session_id, turn_id)
                    """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_assistant_events_session_created 
                    ON assistant_events (session_id, created_at)
            """))
        
        # assistant_plans
        print("\nCreating assistant_plans table...")
        if not dry_run:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS assistant_plans (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    session_id UUID NOT NULL UNIQUE REFERENCES assistant_sessions(id) ON DELETE CASCADE,
                    title TEXT,
                    language VARCHAR(16),
                    steps JSONB NOT NULL DEFAULT '[]',
                    current_step_index INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(16) NOT NULL DEFAULT 'in_progress',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT ck_assistant_plans_status 
                        CHECK (status IN ('in_progress', 'completed', 'failed', 'cancelled'))
                )
            """))
        
        print("\n=== Migration complete! ===")
        
        # Verify tables exist
        print("\nVerifying tables...")
        result = await conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'assistant%'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result.fetchall()]
        print(f"Tables found: {tables}")
        
    await engine.dispose()
    
    if dry_run:
        print("\n[Dry run] No changes were made.")
    
    return tables


def main():
    parser = argparse.ArgumentParser(description="Migrate assistant tables")
    parser.add_argument("--dry-run", action="store_true", help="Show SQL without executing")
    parser.add_argument("--database-url", help="Database URL (overrides env)")
    args = parser.parse_args()
    
    # Get database URL
    database_url = args.database_url or input("Database URL: ").strip()
    if not database_url:
        print("Error: Database URL required")
        sys.exit(1)
    
    asyncio.run(migrate(database_url, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
