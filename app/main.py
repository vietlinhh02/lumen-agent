import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.db.models import Base
from app.db.session import engine
from app.routers.admin import router as admin_router
from app.routers.agent import router as agent_router
from app.routers.assistant import router as assistant_router
from app.routers.audit import router as audit_router
from app.routers.auth import router as auth_router
from app.routers.claims import router as claims_router
from app.routers.conflicts import router as conflicts_router
from app.routers.evidence_ratings import router as evidence_ratings_router
from app.routers.extraction_schema import router as extraction_schema_router
from app.routers.gaps import router as gaps_router
from app.routers.health import router as health_router
from app.routers.knowledge_graph import router as knowledge_graph_router
from app.routers.matrix import router as matrix_router
from app.routers.paper import router as paper_router
from app.routers.project import router as project_router
from app.routers.reports import router as reports_router
from app.routers.search_session import router as search_session_router
from app.routers.stats import router as stats_router

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    force=True,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup."""
    from sqlalchemy import text

    from app.core.embeddings import close_async_client, init_async_client
    from app.services.pdf_extraction import register_optional_fallback_engines
    from app.services.reranker import close_rerank_client, init_rerank_client

    # Phase 0: Init async HTTP clients
    await init_async_client()
    await init_rerank_client()

    # Phase 1: pgvector extension
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # Phase 2: Migrate embedding column to Vector(2000) for pgvector HNSW
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE paper_chunks DROP COLUMN IF EXISTS embedding_tmp"))
            await conn.execute(text("ALTER TABLE paper_chunks DROP COLUMN IF EXISTS embedding_new"))

            col_info = await conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'paper_chunks' AND column_name = 'embedding'"
                )
            )
            row = col_info.fetchone()
            if not row:
                pass  # table doesn't exist yet, create_all will handle it
            elif row[0] == "text":
                # Text/JSON column — migrate from scratch
                logger.info("Migrating paper_chunks.embedding from Text to Vector(2000)")
                await conn.execute(
                    text("ALTER TABLE paper_chunks ADD COLUMN embedding_tmp vector(2000)")
                )
                await conn.execute(
                    text(
                        "UPDATE paper_chunks SET embedding_tmp = "
                        "subvector(embedding::json::text::vector, 1, 2000) "
                        "WHERE embedding IS NOT NULL "
                        "AND json_array_length(embedding::json) >= 2000"
                    )
                )
                migrated = await conn.execute(
                    text("SELECT count(*) FROM paper_chunks WHERE embedding_tmp IS NOT NULL")
                )
                logger.info(
                    "Migrated %s rows with embeddings truncated to 2000 dims",
                    migrated.scalar(),
                )
                await conn.execute(text("ALTER TABLE paper_chunks DROP COLUMN embedding"))
                await conn.execute(
                    text("ALTER TABLE paper_chunks RENAME COLUMN embedding_tmp TO embedding")
                )
                logger.info("Column migration complete")
            elif row[0] != "text":
                # Already a vector column — check if it needs truncation
                dim_check = await conn.execute(
                    text(
                        "SELECT max(vector_dims(embedding)) "
                        "FROM paper_chunks WHERE embedding IS NOT NULL"
                    )
                )
                max_dim = dim_check.scalar()
                if max_dim and max_dim > 2000:
                    logger.info("Truncating embeddings from %s→2000 dims", max_dim)
                    # Need to alter column type — add new, copy truncated, swap
                    await conn.execute(
                        text("ALTER TABLE paper_chunks ADD COLUMN embedding_new vector(2000)")
                    )
                    await conn.execute(
                        text(
                            "UPDATE paper_chunks SET embedding_new = "
                            "subvector(embedding, 1, 2000) WHERE embedding IS NOT NULL"
                        )
                    )
                    await conn.execute(text("ALTER TABLE paper_chunks DROP COLUMN embedding"))
                    await conn.execute(
                        text("ALTER TABLE paper_chunks RENAME COLUMN embedding_new TO embedding")
                    )
                    logger.info("Column type changed to vector(2000)")
                else:
                    logger.info("Embedding column already vector(≤2000), no migration needed")
    except Exception as exc:
        logger.warning("Embedding column migration skipped: %s", exc)

    # Phase 3: Create tables + HNSW index
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_paper_chunks_embedding_hnsw "
                    "ON paper_chunks USING hnsw (embedding vector_cosine_ops) "
                    "WITH (m = 16, ef_construction = 64)"
                )
            )
        except Exception as exc:
            logger.warning("HNSW index skipped: %s", exc)
        await conn.execute(
            text(
                "ALTER TABLE literature_matrix_rows "
                "ADD COLUMN IF NOT EXISTS content_hash VARCHAR(16)"
            )
        )
        await conn.execute(
            text("ALTER TABLE papers ADD COLUMN IF NOT EXISTS content_sha256 VARCHAR(64)")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(80)")
        )
        await conn.execute(
            text(
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS "
                "review_protocol JSONB NOT NULL DEFAULT '{}'"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE project_papers ADD COLUMN IF NOT EXISTS "
                "exclusion_reason VARCHAR(64)"
            )
        )
        await conn.execute(
            text(
                "UPDATE users SET display_name = split_part(email, '@', 1) "
                "WHERE display_name IS NULL"
            )
        )

    # Phase 4: Constraint updates
    async with engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE paper_chunks DROP CONSTRAINT IF EXISTS ck_paper_chunks_content_type")
        )
        await conn.execute(
            text(
                "ALTER TABLE paper_chunks ADD CONSTRAINT ck_paper_chunks_content_type "
                "CHECK (content_type IS NULL OR content_type IN ("
                "'abstract', 'narrative', 'method', 'results', 'limitation', "
                "'equation', 'table', 'figure_caption', 'reference'"
                "))"
            )
        )
        await conn.execute(
            text("ALTER TABLE background_jobs DROP CONSTRAINT IF EXISTS ck_background_jobs_type")
        )
        await conn.execute(
            text(
                "ALTER TABLE background_jobs ADD CONSTRAINT ck_background_jobs_type "
                "CHECK (job_type IN ("
                "'auto_save', 'auto_search', 'normalize', 'enrich', "
                "'matrix_generate', 'gap_generate', 'conflict_generate', "
                "'report_generate', 'paper_search', 'claim_generate'"
                "))"
            )
        )
        # T4: Custom Extraction Schema — add the custom_fields JSONB column
        # to literature_matrix_rows. ``Base.metadata.create_all`` already
        # created the project_extraction_schemas table; we still defensively
        # ensure the column is present for hand-migrated databases.
        await conn.execute(
            text(
                "ALTER TABLE literature_matrix_rows "
                "ADD COLUMN IF NOT EXISTS custom_fields JSONB NOT NULL DEFAULT '{}'"
            )
        )
        # GIN index on (project_id, custom_fields) for project-scoped
        # filter/aggregate queries over typed custom-field values.
        try:
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_matrix_rows_custom_fields_gin "
                    "ON literature_matrix_rows USING gin (custom_fields jsonb_path_ops)"
                )
            )
        except Exception as exc:
            logger.warning("GIN index on custom_fields skipped: %s", exc)
        await conn.execute(
            text("ALTER TABLE background_jobs ADD COLUMN IF NOT EXISTS progress_json JSONB")
        )
        # Allow 'draft' status for papers awaiting upload confirmation.
        await conn.execute(
            text("ALTER TABLE project_papers DROP CONSTRAINT IF EXISTS ck_project_papers_status")
        )
        await conn.execute(
            text(
                "ALTER TABLE project_papers ADD CONSTRAINT ck_project_papers_status "
                "CHECK (status IN ('saved', 'rejected', 'uncertain', 'draft'))"
            )
        )

    # Phase 5: Assistant tables (Plan-Act chat surface).
    # `Base.metadata.create_all` above already created the tables and the
    # indexes declared in `__table_args__`; the explicit
    # `CREATE INDEX IF NOT EXISTS` below mirrors the HNSW index pattern and
    # guarantees the composite (session_id, created_at) index exists even on
    # hand-migrated databases that pre-date the model declaration.
    async with engine.begin() as conn:
        try:
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_assistant_events_session_created "
                    "ON assistant_events (session_id, created_at)"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_assistant_sessions_user_updated "
                    "ON assistant_sessions (user_id, updated_at)"
                )
            )
        except Exception as exc:
            logger.warning("Assistant index ensure skipped: %s", exc)

    # Phase 6: Register layout-aware / OCR fallback engines whose
    # optional dependencies are installed (e.g. Docling via
    # `uv sync --extra docling`). The fast pdf_oxide + pypdf pair runs
    # on every extraction; the fallback tier runs only when the fast
    # tier scores below the routing threshold.
    fallback_names = register_optional_fallback_engines()
    if fallback_names:
        logger.info(
            "PDF extraction fallback engines registered: %s",
            ", ".join(fallback_names),
        )

    yield

    # Cleanup: close async HTTP clients
    await close_async_client()
    await close_rerank_client()


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

    # ── Latency logging middleware ────────────────────────────────────────────
    import time as _time

    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request as _Request

    class LatencyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: _Request, call_next):
            _start = _time.monotonic()
            response = await call_next(request)
            _elapsed_ms = round((_time.monotonic() - _start) * 1000, 1)
            logger.info(
                "request",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": response.status_code,
                    "latency_ms": _elapsed_ms,
                },
            )
            return response

    app.add_middleware(LatencyMiddleware)
    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(project_router, prefix="/api/projects")
    app.include_router(audit_router, prefix="/api/projects")
    app.include_router(paper_router, prefix="/api/papers")
    app.include_router(search_session_router, prefix="/api/papers")
    app.include_router(agent_router, prefix="/api/agents")
    app.include_router(matrix_router, prefix="/api/projects")
    app.include_router(gaps_router, prefix="/api/projects")
    app.include_router(conflicts_router, prefix="/api/projects")
    app.include_router(evidence_ratings_router, prefix="/api/projects")
    app.include_router(extraction_schema_router, prefix="/api/projects")
    app.include_router(claims_router, prefix="/api/projects")
    app.include_router(reports_router, prefix="/api/projects")
    app.include_router(admin_router, prefix="/api/admin")
    app.include_router(knowledge_graph_router, prefix="/api/projects")
    app.include_router(stats_router, prefix="/api")
    app.include_router(assistant_router, prefix="/api/assistant")

    # Serve PDF files statically
    os.makedirs(settings.paper_pdf_dir, exist_ok=True)
    app.mount("/api/pdf-files", StaticFiles(directory=settings.paper_pdf_dir), name="pdf-files")

    return app


app = create_app()
