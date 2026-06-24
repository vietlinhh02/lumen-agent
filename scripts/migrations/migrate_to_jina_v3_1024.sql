-- ────────────────────────────────────────────────────────────────────────────
-- Migration: pgvector column → Jina v3 native 1024 dim
-- ────────────────────────────────────────────────────────────────────────────
--
-- Why:
--   `paper_chunks.embedding` is currently `vector(2000)`. We want to move to
--   `vector(1024)` so we can use jina-embeddings-v3 at its native dimension
--   (best MTEB score, no wasted storage, no zero-padded tail).
--
-- Pre-requisites:
--   1. Set in .env:
--        EMBEDDING_PROVIDER=jina
--        JINA_API_KEY=<your-key>
--        JINA_EMBEDDING_MODEL=jina-embeddings-v3
--        JINA_EMBEDDING_DIMENSION=1024
--        EMBEDDING_DIMENSION=1024
--   2. Run the re-embed job (see scripts/reembed_chunks_jina.py) BEFORE this
--      SQL script — the new column must contain 1024-d vectors.
--   3. Take a DB backup. This script drops the old vector column.
--
-- Estimated downtime:
--   - With re-embed pre-completed: ~1 minute (DDL only).
--   - If re-embedding in parallel: 0 (keep old column, dual-read in app).
--
-- Rollback strategy:
--   The old embedding data is NOT preserved by this script. If you need a
--   rollback window, run the "safe variant" at the bottom of this file first
--   to add the new column alongside the old one.

BEGIN;

-- 1. Lock the table to prevent concurrent writes during the column swap.
LOCK TABLE paper_chunks IN ACCESS EXCLUSIVE MODE;

-- 2. Drop the HNSW index that references the old column.
DROP INDEX IF EXISTS ix_paper_chunks_embedding_hnsw;

-- 3. Swap the old column for the new 1024-d one.
ALTER TABLE paper_chunks DROP COLUMN embedding;
ALTER TABLE paper_chunks ADD COLUMN embedding vector(1024);

-- 4. Recreate the HNSW index on the new column.
--    vector_cosine_ops matches the cosine_distance() call in
--    app/services/hybrid_retrieval.py.
CREATE INDEX ix_paper_chunks_embedding_hnsw
    ON paper_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 5. Record the dimension metadata so future re-embed jobs can verify it.
UPDATE paper_chunks
SET embedding_dimension = 1024
WHERE embedding IS NOT NULL
  AND (embedding_dimension IS NULL OR embedding_dimension != 1024);

-- 6. (Optional but recommended) Update the global embedding_model column too.
UPDATE paper_chunks
SET embedding_model = 'jina-embeddings-v3'
WHERE embedding IS NOT NULL
  AND (embedding_model IS NULL OR embedding_model != 'jina-embeddings-v3');

COMMIT;

-- ── Verify ──────────────────────────────────────────────────────────────────
SELECT
    COUNT(*) AS total_chunks,
    COUNT(embedding) AS embedded_chunks,
    COUNT(*) FILTER (WHERE embedding_dimension = 1024) AS dim_1024,
    COUNT(*) FILTER (WHERE embedding_model = 'jina-embeddings-v3') AS jina_model
FROM paper_chunks;

-- ────────────────────────────────────────────────────────────────────────────
-- SAFE VARIANT (zero-downtime): add new column alongside old one
-- ────────────────────────────────────────────────────────────────────────────
-- Run this INSTEAD of the ALTER above if you can't tolerate even 1 min
-- of downtime. Then the app code can dual-read for the cutover window,
-- and you drop the old column after verification:
--
--   BEGIN;
--   ALTER TABLE paper_chunks ADD COLUMN embedding_v3 vector(1024);
--   CREATE INDEX ix_paper_chunks_embedding_v3_hnsw
--       ON paper_chunks USING hnsw (embedding_v3 vector_cosine_ops);
--   COMMIT;
--
-- After re-embed job finishes, verify row counts match and then:
--   ALTER TABLE paper_chunks DROP COLUMN embedding;
--   ALTER TABLE paper_chunks RENAME COLUMN embedding_v3 TO embedding;
--   CREATE INDEX ix_paper_chunks_embedding_hnsw
--       ON paper_chunks USING hnsw (embedding vector_cosine_ops);
