"""User paper uploads (PDF / Markdown).

Mirrors the internet-paper path: an uploaded file is saved to the same
``paper_pdf_dir``, ingested through :func:`app.services.pdf_fulltext.process_pdf`
(which already handles ``.md``), LLM-enriched with metadata, then — after the
user confirms — promoted from ``draft`` to ``saved`` and fed into the existing
matrix-generation job.

Flow:

    upload   → save file + Paper(source=["upload"]) + ProjectPaper(status="draft")
             → background: process_pdf → LLM metadata onto Paper
    status   → frontend polls full_text_status + extracted metadata
    confirm  → update Paper, status="draft"→"saved", trigger matrix job
    discard  → delete draft ProjectPaper + canonical Paper + file
"""

from __future__ import annotations

import asyncio
import logging
import re
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import get_provider
from app.core.config import get_settings
from app.db.models import Paper, Project, ProjectPaper, User
from app.schemas.project import (
    ConfirmUploadItem,
    UploadDraftItem,
    UploadStatusItem,
)

logger = logging.getLogger(__name__)

MAX_FILES = 5
MAX_BYTES = 30 * 1024 * 1024  # 30 MB
ALLOWED_EXT = {".pdf", ".md"}
_METADATA_SAMPLE_CHARS = 8000

_METADATA_SYSTEM = (
    "You are a bibliographic metadata extractor. Given the beginning of an "
    "academic paper (extracted from a PDF or a markdown file), extract its "
    "title, author full names, publication year, venue, and abstract.\n"
    "Rules:\n"
    "- Always return a title (infer from the leading heading if needed).\n"
    "- authors: list of full names as plain strings (may be empty).\n"
    "- year: 4-digit integer or null.\n"
    "- venue/abstract: null if not present.\n"
    "- Do not invent facts that are not supported by the text."
)

_METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "authors": {"type": "array", "items": {"type": "string"}},
        "year": {"type": ["integer", "null"]},
        "venue": {"type": ["string", "null"]},
        "abstract": {"type": ["string", "null"]},
    },
    "required": ["title"],
    "additionalProperties": False,
}


def _safe_filename(name: str) -> str:
    """Sanitise an original filename for safe on-disk storage."""
    base = Path(name).name
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return base[:80] or "file"


async def _verify_owner(db: AsyncSession, user: User, project_id: UUID) -> Project | None:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    return result.scalar_one_or_none()


# ── Upload kickoff ──────────────────────────────────────────────────────────


async def handle_uploads(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    files: list[UploadFile],
) -> list[UploadDraftItem] | None:
    """Validate + persist uploaded files and launch background ingestion.

    Returns ``None`` if the project is not found/owned. Raises ``ValueError``
    for whole-request violations (e.g. too many files).
    """
    project = await _verify_owner(db, user, project_id)
    if project is None:
        return None
    if len(files) > MAX_FILES:
        raise ValueError(f"Tối đa {MAX_FILES} file mỗi lần.")
    if not files:
        raise ValueError("Chưa chọn file nào.")

    settings = get_settings()
    pdf_dir = Path(settings.paper_pdf_dir)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    drafts: list[UploadDraftItem] = []
    for f in files:
        name = f.filename or "upload"
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXT:
            drafts.append(
                UploadDraftItem(
                    filename=name, status="rejected", reason="Chỉ hỗ trợ .pdf và .md"
                )
            )
            continue

        data = await f.read()
        if len(data) == 0:
            drafts.append(UploadDraftItem(filename=name, status="rejected", reason="File rỗng"))
            continue
        if len(data) > MAX_BYTES:
            drafts.append(
                UploadDraftItem(filename=name, status="rejected", reason="File vượt 30MB")
            )
            continue

        digest = sha256(data).hexdigest()

        # Dedup within this project (same file already uploaded/saved here).
        dup = (
            await db.execute(
                select(ProjectPaper.id)
                .join(Paper, ProjectPaper.paper_id == Paper.id)
                .where(
                    ProjectPaper.project_id == project_id,
                    Paper.content_sha256 == digest,
                )
            )
        ).first()
        if dup is not None:
            drafts.append(
                UploadDraftItem(
                    filename=name, status="duplicate", reason="File đã có trong project"
                )
            )
            continue

        # Use the lowercased extension so process_pdf's markdown branch (which
        # matches ".md"/".txt" case-sensitively) handles uppercase ".MD" files.
        dest = pdf_dir / f"upload_{digest[:12]}_{_safe_filename(Path(name).stem)}{ext}"
        try:
            dest.write_bytes(data)
        except Exception as exc:  # pragma: no cover - disk failure
            logger.exception("Failed to save upload %s: %s", name, exc)
            drafts.append(UploadDraftItem(filename=name, status="rejected", reason="Lỗi lưu file"))
            continue

        paper = Paper(
            title=(Path(name).stem[:512] or "Untitled"),
            source_names=["upload"],
            content_sha256=digest,
        )
        db.add(paper)
        await db.flush()  # populate paper.id

        pp = ProjectPaper(
            project_id=project_id,
            paper_id=paper.id,
            status="draft",
            full_text_status="pending",
        )
        db.add(pp)
        await db.commit()
        await db.refresh(pp)
        await db.refresh(paper)

        asyncio.ensure_future(_ingest_and_extract_metadata_bg(pp.id, paper.id, str(dest)))
        drafts.append(
            UploadDraftItem(
                filename=name,
                status="pending",
                project_paper_id=pp.id,
                paper_id=paper.id,
            )
        )

    return drafts


# ── Background ingestion + metadata ─────────────────────────────────────────


def _read_text_for_metadata(path: Path) -> str | None:
    """Read ordered text for the metadata LLM (avoids unordered DB chunks)."""
    if path.suffix.lower() in (".md", ".txt"):
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None
    from app.services.pdf_fulltext import extract_text

    return extract_text(path)


async def _ingest_and_extract_metadata_bg(
    project_paper_id: UUID,
    paper_id: UUID,
    file_path: str,
) -> None:
    """Background task: ingest full text then fill metadata. Never raises."""
    from app.db.session import async_session_factory
    from app.services.pdf_fulltext import process_pdf

    path = Path(file_path)
    try:
        async with async_session_factory() as db:
            pp = await db.get(ProjectPaper, project_paper_id)
            if pp is None:
                return
            pp.full_text_status = "ingesting"
            await db.commit()

            result = await process_pdf(db, project_paper_id, path)

            # Hold the row NON-terminal until metadata is filled. process_pdf flips
            # it to "completed" as soon as chunks are stored — but the LLM metadata
            # pass runs afterwards, so if we left it terminal the confirm form would
            # snapshot empty metadata (race). Keep "ingesting" through that pass.
            pp = await db.get(ProjectPaper, project_paper_id)
            if pp is not None:
                pp.full_text_status = (
                    "ingesting" if result.status == "completed" else result.status
                )
                await db.commit()

        if result.status != "completed":
            logger.info("Upload ingest non-complete (%s): %s", result.status, path.name)
            return

        text = await asyncio.to_thread(_read_text_for_metadata, path)
        meta = await extract_metadata_from_text(text)

        async with async_session_factory() as db:
            paper = await db.get(Paper, paper_id)
            if paper is not None and meta:
                if meta.get("title"):
                    paper.title = meta["title"][:512]
                if meta.get("authors"):
                    paper.authors = meta["authors"]
                if meta.get("year"):
                    paper.year = meta["year"]
                if meta.get("venue"):
                    paper.venue = meta["venue"][:512]
                if meta.get("abstract"):
                    paper.abstract = meta["abstract"]
            # Only now mark terminal — the form will show the filled metadata.
            pp = await db.get(ProjectPaper, project_paper_id)
            if pp is not None:
                pp.full_text_status = "completed"
            await db.commit()
    except Exception as exc:
        logger.exception("Upload ingest failed for %s: %s", project_paper_id, exc)
        try:
            async with async_session_factory() as db:
                pp = await db.get(ProjectPaper, project_paper_id)
                if pp is not None and pp.full_text_status in (None, "pending", "ingesting"):
                    pp.full_text_status = "failed"
                    await db.commit()
        except Exception:
            pass


async def extract_metadata_from_text(text: str | None) -> dict:
    """LLM-extract bibliographic metadata from the start of a paper."""
    text = (text or "").strip()
    if not text:
        return {}
    sample = text[:_METADATA_SAMPLE_CHARS]
    provider = get_provider()
    try:
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": sample}],
            schema=_METADATA_SCHEMA,
            tool_name="extract_paper_metadata",
            system=_METADATA_SYSTEM,
            max_tokens=800,
        )
    except Exception as exc:
        logger.warning("Metadata extraction LLM failed: %s", exc)
        return {}

    authors = [
        {"name": a.strip()}
        for a in (result.get("authors") or [])
        if isinstance(a, str) and a.strip()
    ]
    return {
        "title": (result.get("title") or "").strip() or None,
        "authors": authors,
        "year": result.get("year"),
        "venue": (result.get("venue") or None),
        "abstract": (result.get("abstract") or None),
    }


# ── Status polling ──────────────────────────────────────────────────────────


async def get_upload_status(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    project_paper_ids: list[UUID],
) -> list[UploadStatusItem] | None:
    """Return ingest status + extracted metadata for draft uploads."""
    if await _verify_owner(db, user, project_id) is None:
        return None
    if not project_paper_ids:
        return []

    rows = (
        await db.execute(
            select(ProjectPaper, Paper)
            .join(Paper, ProjectPaper.paper_id == Paper.id)
            .where(
                ProjectPaper.project_id == project_id,
                ProjectPaper.id.in_(project_paper_ids),
            )
        )
    ).all()

    return [
        UploadStatusItem(
            project_paper_id=pp.id,
            filename="",  # frontend keeps its own filename map from the upload response
            full_text_status=pp.full_text_status,
            title=paper.title,
            authors=paper.authors if isinstance(paper.authors, list) else [],
            year=paper.year,
            venue=paper.venue,
            abstract=paper.abstract,
        )
        for pp, paper in rows
    ]


# ── Confirm ─────────────────────────────────────────────────────────────────


async def confirm_uploads(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    items: list[ConfirmUploadItem],
) -> bool | None:
    """Apply confirmed metadata, promote drafts to saved, trigger matrix."""
    project = await _verify_owner(db, user, project_id)
    if project is None:
        return None

    promoted = 0
    for item in items:
        row = (
            await db.execute(
                select(ProjectPaper, Paper)
                .join(Paper, ProjectPaper.paper_id == Paper.id)
                .where(
                    ProjectPaper.id == item.project_paper_id,
                    ProjectPaper.project_id == project_id,
                )
            )
        ).one_or_none()
        if row is None:
            continue
        pp, paper = row
        paper.title = item.title[:512]
        paper.authors = item.authors
        paper.year = item.year
        paper.venue = (item.venue or None)
        paper.abstract = (item.abstract or None)
        if pp.status == "draft":
            pp.status = "saved"
            promoted += 1
    await db.commit()

    if promoted:
        await _trigger_matrix(db, project_id, user.id, project.topic)
    return True


async def _trigger_matrix(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    topic: str,
) -> None:
    """Launch the existing matrix-generation job (skips unchanged papers)."""
    from app.db.models import BackgroundJob
    from app.routers.matrix import _run_matrix_job

    saved = (
        await db.execute(
            select(ProjectPaper).where(
                ProjectPaper.project_id == project_id,
                ProjectPaper.status == "saved",
            )
        )
    ).scalars().all()

    job = BackgroundJob(
        job_type="matrix_generate",
        project_id=project_id,
        user_id=user_id,
        status="pending",
        total=len(saved),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    asyncio.ensure_future(_run_matrix_job(job.id, project_id, user_id, topic))


# ── Discard (cancel) ────────────────────────────────────────────────────────


async def discard_uploads(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    project_paper_ids: list[UUID],
) -> bool | None:
    """Delete draft uploads: ProjectPaper + orphan Paper + stored file."""
    if await _verify_owner(db, user, project_id) is None:
        return None

    settings = get_settings()
    pdf_dir = Path(settings.paper_pdf_dir)

    for pp_id in project_paper_ids:
        row = (
            await db.execute(
                select(ProjectPaper, Paper)
                .join(Paper, ProjectPaper.paper_id == Paper.id)
                .where(
                    ProjectPaper.id == pp_id,
                    ProjectPaper.project_id == project_id,
                )
            )
        ).one_or_none()
        if row is None:
            continue
        pp, paper = row
        if pp.status != "draft":
            continue  # only cancel unconfirmed uploads

        paper_id = paper.id
        digest = paper.content_sha256
        is_upload = isinstance(paper.source_names, list) and "upload" in paper.source_names

        await db.delete(pp)
        await db.flush()

        if is_upload:
            others = (
                await db.execute(
                    select(ProjectPaper.id).where(ProjectPaper.paper_id == paper_id)
                )
            ).first()
            if others is None:
                orphan = await db.get(Paper, paper_id)
                if orphan is not None:
                    await db.delete(orphan)
        await db.commit()

        if digest:
            # Only remove the file when no other Paper (e.g. the same file in a
            # different project) still references this content.
            still_used = (
                await db.execute(select(Paper.id).where(Paper.content_sha256 == digest))
            ).first()
            if still_used is None:
                try:
                    for fp in pdf_dir.glob(f"upload_{digest[:12]}_*"):
                        fp.unlink(missing_ok=True)
                except Exception:  # pragma: no cover - best-effort cleanup
                    pass

    return True
