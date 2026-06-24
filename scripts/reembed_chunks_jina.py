"""Re-embed all paper_chunks using Jina AI.

Why:
    After switching EMBEDDING_PROVIDER to ``jina``, existing chunks have
    embeddings from the previous provider (Gemini/OpenRouter) and are not
    directly comparable. This script walks the ``paper_chunks`` table,
    re-embeds each row in batches via Jina, and writes the new vector back.

Usage:
    # Dry-run first to see counts
    python scripts/reembed_chunks_jina.py --dry-run

    # Re-embed everything (default batch size 32)
    python scripts/reembed_chunks_jina.py

    # Only re-embed rows where the embedding model is NOT already Jina
    python scripts/reembed_chunks_jina.py --skip-if-jina

    # Custom batch size (respect Jina's 100 RPM free tier; smaller=fewer
    # retries on transient errors)
    python scripts/reembed_chunks_jina.py --batch-size 16

Idempotency:
    - ``--skip-if-jina`` reuses existing Jina embeddings.
    - The script writes ``embedding_model`` and ``embedding_dimension`` so
      you can re-run safely; only rows that differ are touched in default
      mode.

Prerequisites:
    1. .env has ``JINA_API_KEY`` set.
    2. ``EMBEDDING_PROVIDER=jina``.
    3. DB is reachable.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.embeddings import (  # noqa: E402
    encode_batch,
    get_embedding_dimension,
    get_embedding_model_name,
)
from app.db.session import async_session_factory  # noqa: E402
from app.db.models import PaperChunk  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("reembed_jina")


async def count_chunks(
    db,
    *,
    skip_if_jina: bool,
    only_missing: bool,
) -> int:
    """Count chunks that need re-embedding."""
    stmt = select(PaperChunk.id).where(PaperChunk.embedding.isnot(None))
    if skip_if_jina:
        stmt = stmt.where(PaperChunk.embedding_model != "jina-embeddings-v3")
    if only_missing:
        stmt = stmt.where(PaperChunk.embedding.is_(None))
    rows = (await db.execute(stmt)).all()
    return len(rows)


async def reembed_all(
    *,
    batch_size: int,
    skip_if_jina: bool,
    dry_run: bool,
    only_missing: bool,
) -> None:
    """Walk all paper_chunks and re-embed them in batches."""
    target_model = get_embedding_model_name()
    target_dim = get_embedding_dimension()

    logger.info(
        "Re-embed target: model=%s, dim=%d, batch=%d, skip_if_jina=%s, "
        "dry_run=%s, only_missing=%s",
        target_model, target_dim, batch_size, skip_if_jina, dry_run, only_missing,
    )

    async with async_session_factory() as db:
        total = await count_chunks(
            db,
            skip_if_jina=skip_if_jina,
            only_missing=only_missing,
        )
        logger.info("Found %d chunks to process", total)
        if dry_run:
            logger.info("Dry-run: not modifying any rows")
            return

        if total == 0:
            return

        # Stream in batches ordered by id for stable resume
        last_id = None
        processed = 0
        failed_batches = 0
        started = time.monotonic()

        while True:
            stmt = (
                select(PaperChunk)
                .where(PaperChunk.embedding.isnot(None))
                .order_by(PaperChunk.id)
                .limit(batch_size)
            )
            if skip_if_jina:
                stmt = stmt.where(PaperChunk.embedding_model != "jina-embeddings-v3")
            if last_id is not None:
                stmt = stmt.where(PaperChunk.id > last_id)

            chunks = (await db.execute(stmt)).scalars().all()
            if not chunks:
                break

            texts = [c.chunk_text for c in chunks]
            try:
                vectors = await encode_batch(texts, batch_size=batch_size)
            except Exception as exc:
                failed_batches += 1
                logger.exception(
                    "Batch starting at id=%s failed (failure %d): %s",
                    chunks[0].id, failed_batches, exc,
                )
                if failed_batches >= 5:
                    logger.error("Too many batch failures; aborting")
                    raise
                # Skip these chunks so we don't loop forever
                last_id = chunks[-1].id
                await asyncio.sleep(2.0)
                continue

            # Write each row's new embedding + metadata
            for chunk, vec in zip(chunks, vectors, strict=True):
                chunk.embedding = vec
                chunk.embedding_model = target_model
                chunk.embedding_dimension = target_dim

            await db.commit()
            processed += len(chunks)
            last_id = chunks[-1].id

            elapsed = time.monotonic() - started
            rate = processed / max(elapsed, 0.001)
            logger.info(
                "Progress: %d/%d chunks (%.1f/s, %.1fs elapsed)",
                processed, total, rate, elapsed,
            )

        logger.info(
            "Done. Re-embedded %d/%d chunks in %.1fs (failed_batches=%d)",
            processed, total, time.monotonic() - started, failed_batches,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--skip-if-jina",
        action="store_true",
        help="Skip chunks already embedded with jina-embeddings-v3 (idempotent)",
    )
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Only process chunks with NULL embeddings",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts but don't write anything",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        reembed_all(
            batch_size=args.batch_size,
            skip_if_jina=args.skip_if_jina,
            dry_run=args.dry_run,
            only_missing=args.only_missing,
        )
    )
