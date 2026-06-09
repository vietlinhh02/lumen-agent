import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    force=True,
)
from app.db.models import Base
from app.db.session import engine
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router
from app.routers.paper import router as paper_router
from app.routers.search_session import router as search_session_router
from app.routers.agent import router as agent_router
from app.routers.project import router as project_router
from app.routers.matrix import router as matrix_router
from app.routers.gaps import router as gaps_router
from app.routers.conflicts import router as conflicts_router
from app.routers.reports import router as reports_router
from app.routers.admin import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Update background_jobs constraint to include new job types
        await conn.execute(
            text("ALTER TABLE background_jobs DROP CONSTRAINT IF EXISTS ck_background_jobs_type")
        )
        await conn.execute(
            text(
                "ALTER TABLE background_jobs ADD CONSTRAINT ck_background_jobs_type "
                "CHECK (job_type IN ("
                "'auto_save', 'normalize', 'enrich', "
                "'matrix_generate', 'gap_generate', 'conflict_generate', "
                "'report_generate'"
                "))"
            )
        )
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(project_router, prefix="/api/projects")
    app.include_router(paper_router, prefix="/api/papers")
    app.include_router(search_session_router, prefix="/api/papers")
    app.include_router(agent_router, prefix="/api/agents")
    app.include_router(matrix_router, prefix="/api/projects")
    app.include_router(gaps_router, prefix="/api/projects")
    app.include_router(conflicts_router, prefix="/api/projects")
    app.include_router(reports_router, prefix="/api/projects")
    app.include_router(admin_router, prefix="/api/admin")

    # Serve PDF files statically
    from fastapi.staticfiles import StaticFiles
    import os

    os.makedirs(settings.paper_pdf_dir, exist_ok=True)
    app.mount("/api/pdf-files", StaticFiles(directory=settings.paper_pdf_dir), name="pdf-files")

    return app


app = create_app()
