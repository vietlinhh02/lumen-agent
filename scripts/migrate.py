"""Migration script: add columns for PDF Ingestion Pipeline.

Run:  python scripts/migrate.py

Idempotent — safe to run multiple times.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings

_MIGRATIONS = [
    # 1. Add full_text_status to project_papers
    "ALTER TABLE project_papers ADD COLUMN IF NOT EXISTS full_text_status VARCHAR(16)",
    # 1b. Add raw_text to paper_enrichments
    "ALTER TABLE paper_enrichments ADD COLUMN IF NOT EXISTS raw_text TEXT",
    # 2. Add section_label to paper_chunks
    "ALTER TABLE paper_chunks ADD COLUMN IF NOT EXISTS section_label VARCHAR(64)",
    # 3. Update paper_chunks default chunk_type
    "ALTER TABLE paper_chunks ALTER COLUMN chunk_type SET DEFAULT 'full_text'",
    # 3b. Add evidence chunk metadata for adaptive RAG
    "ALTER TABLE paper_chunks ADD COLUMN IF NOT EXISTS section_path TEXT",
    "ALTER TABLE paper_chunks ADD COLUMN IF NOT EXISTS chunk_index INTEGER",
    "ALTER TABLE paper_chunks ADD COLUMN IF NOT EXISTS page_start INTEGER",
    "ALTER TABLE paper_chunks ADD COLUMN IF NOT EXISTS page_end INTEGER",
    "ALTER TABLE paper_chunks ADD COLUMN IF NOT EXISTS content_type VARCHAR(32)",
    "ALTER TABLE paper_chunks ADD COLUMN IF NOT EXISTS pipeline_version VARCHAR(32)",
    "ALTER TABLE paper_chunks ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)",
    # 4. Drop old constraint, recreate with new values
    "ALTER TABLE paper_chunks DROP CONSTRAINT IF EXISTS ck_paper_chunks_type",
    "ALTER TABLE paper_chunks "
    "ADD CONSTRAINT ck_paper_chunks_type "
    "CHECK (chunk_type IN ('abstract', 'summary', 'matrix', 'full_text', 'section'))",
    "ALTER TABLE paper_chunks DROP CONSTRAINT IF EXISTS ck_paper_chunks_content_type",
    "ALTER TABLE paper_chunks "
    "ADD CONSTRAINT ck_paper_chunks_content_type "
    "CHECK (content_type IS NULL OR content_type IN ("
    "'abstract', 'narrative', 'method', 'results', 'limitation', "
    "'table', 'figure_caption', 'reference'"
    "))",
    "CREATE INDEX IF NOT EXISTS ix_paper_chunks_project_content "
    "ON paper_chunks (project_paper_id, content_type)",
    "CREATE INDEX IF NOT EXISTS ix_paper_chunks_project_section "
    "ON paper_chunks (project_paper_id, section_label)",
]


async def migrate() -> None:
    try:
        import asyncpg
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: asyncpg.\n"
            "Run this migration with the project environment:\n"
            "  .venv/bin/python scripts/migrate.py\n"
            "or:\n"
            "  uv run python scripts/migrate.py"
        ) from exc

    settings = get_settings()
    url = settings.database_url

    # Convert asyncpg DSN: postgresql+asyncpg:// -> postgresql://
    dsn = url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(dsn)
    try:
        for sql in _MIGRATIONS:
            try:
                await conn.execute(sql)
                print(f"  ✓ {sql.split()[1]} {sql.split()[2]}...")
            except asyncpg.exceptions.DuplicateObjectError:
                print(f"  ~ Already applied: {sql[:60]}...")
            except Exception as exc:
                print(f"  ✗ {sql[:60]}... → {exc}")
    finally:
        await conn.close()


if __name__ == "__main__":
    print("Running PDF Ingestion Pipeline migrations...")
    asyncio.run(migrate())
    print("Done.")
