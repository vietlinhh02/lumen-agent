#!/usr/bin/env python3
"""Database migration script for DeepResearchJob."""

import asyncio
import sys
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.core.config import get_settings

async def migrate():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=True)
    
    async with engine.begin() as conn:
        print("\nCreating deep_research_jobs table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS deep_research_jobs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id UUID NOT NULL REFERENCES assistant_sessions(id) ON DELETE CASCADE,
                project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                query TEXT NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                stage VARCHAR(50) NOT NULL DEFAULT 'init',
                progress FLOAT NOT NULL DEFAULT 0.0,
                message TEXT,
                progress_json JSONB NOT NULL DEFAULT '{}',
                report TEXT,
                papers_saved INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        print("\nMigration complete!")
        
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate())
