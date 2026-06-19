import asyncio
from sqlalchemy import select
from app.db.session import async_session_factory
from app.db.models import PaperChunk, ProjectPaper

async def main():
    async with async_session_factory() as db:
        # Find the paper by id bd991ee6-fa99-4f89-974f-9c43806b24d7
        result = await db.execute(select(PaperChunk).where(PaperChunk.project_paper_id == 'bd991ee6-fa99-4f89-974f-9c43806b24d7'))
        chunks = result.scalars().all()
        print(f"Found {len(chunks)} chunks.")
        
        sections = set(c.section_label for c in chunks if c.section_label)
        print(f"Distinct sections: {sections}")
        print(f"Pipeline versions: {set(c.pipeline_version for c in chunks)}")

if __name__ == "__main__":
    asyncio.run(main())
