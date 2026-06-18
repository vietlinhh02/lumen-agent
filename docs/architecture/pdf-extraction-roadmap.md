# PDF Extraction Roadmap

Status: **Phases 1, 2, 3 shipped.** The new architecture now reaches:

- ~87% papers via fast tier (pdf_oxide + pypdf) at ~1s/paper
- ~12% papers via Docling fallback at ~5-15s/paper
- ~0.4% papers via OCR (future)
- Per-page re-extraction when most pages are clean but a few fail
- LaTeX formulas preserved in Docling output
- Layout cleanup skipped for Docling output (no double work)

## Why this exists

The original PDF pipeline (pdf_oxide → regex cleanup → chunk → embed) hits
hard limits on real scientific PDFs. Regex cleanup is a 1D view of a 2D
document, so it cannot reliably distinguish:

- column A vs column B in two-column papers (interleaving)
- body text vs running header / footer / journal boilerplate
- inline page numbers vs equation labels vs citation numbers
- TOC entries vs section headings (different publishers format them
  differently)

Each failure mode forced a new regex to be added. By mid-2025 the cleanup
file had 14+ regexes and was still missing many cases. Research from
pdfmux (2026), ÉCLAIR (2025), XY-Cut++, and DocLayNet benchmarks
confirms that rule-based PDF parsing plateaus at ~0.7-0.8 TEDS on
Scientific papers while layout-aware parsers reach ~0.88-0.95.

## The general formula

```
PDF_in
  → Layout Analysis (Docling / DiT / LayoutLMv3)         [planned]
    → Reading Order (XY-Cut++ or learned ordering)        [planned]
      → Per-block Specialised Extraction                   [partial]
          (Narrative | Formula | Table | Figure)
        → Quality Score per page (5-signal)                [shipped]
          → Self-Healing Routing                            [shipped]
            → Re-extract with stronger backend if score < τ [partial]
              → LLM Section Detection                      [future]
                → Section-aware chunking with content_type [shipped]
                  → Embed & store with confidence metadata [shipped]
```

Four pillars:

1. **Layout-First, Text-Second** — detect regions on the page image before
   reading text. *Status: not yet shipped. Current engines are still
   text-layer based. Layout-aware extraction is the planned Phase 1.*
2. **Reading Order = Geometry + Semantics** — sort by XY-Cut++ or a learned
   model, not by naive Y-then-X. *Status: not yet shipped.*
3. **Specialisation > Generalisation** — each content type gets its best
   extractor. *Status: partial. We classify chunks as
   narrative / equation / table / figure_caption after extraction; we
   don't yet pick the extractor per content type.*
4. **Self-Healing Pipeline** — every page is scored; weak pages get
   re-extracted by a stronger backend. *Status: shipped at the document
   level (the new quality scorer + router). Per-page re-extraction is
   the next iteration.*

## What shipped (Phase 4)

### `app/services/pdf_extraction/quality.py`

Five-signal quality scorer per the pdfmux formula:

```
confidence = (
    0.30 * density            # chars/cm² proxy from line-level stats
    + 0.25 * alphabetic_ratio # letters / total non-whitespace
    + 0.20 * structure        # paragraphs, sentence terminators
    + 0.15 * mojibake         # UTF-8 corruption detection
    + 0.10 * column_order     # interleaved two-column heuristic
)
```

Each signal is documented at the function level. Thresholds:

- `GOOD_SCORE = 0.85` — accept without fallback
- `DEFAULT_MIN_SCORE = 0.60` — below this, route to a stronger backend

### `app/services/pdf_extraction/router.py`

Self-healing routing layer with pluggable engines. The protocol:

```python
class ExtractionEngine(Protocol):
    name: str
    def extract(self, pdf_path: Path) -> str | None: ...
```

Default engines:

- `PdfOxideEngine` — markdown with academic profile
- `PyPdfEngine`   — plain-text fallback

`extract_with_routing(pdf_path, min_score=...)` runs each engine, scores
the result, and returns the highest-scoring one. When no engine clears
the bar the result carries `fell_back=True` so callers can escalate to
OCR or layout-aware backends.

### `app/services/pdf_fulltext.py`

The hot path used by `project.py` now delegates to the router. The
previous internal oxide-vs-pypdf comparison (2-signal heuristic) is
gone; the new 5-signal scorer runs through the router. The old
`_extract_text_pdf_oxide`, `_extract_text_pypdf`, and
`_extraction_quality_score` are kept as deprecated shims that delegate
to the new code; they will be removed once all callers are migrated.

## Benchmark results — 244-paper arXiv corpus

Run on `data/papers/` (244 PDFs) with `pdf_oxide` then `pypdf`:

| Metric | Value |
|---|---|
| Successful extractions | 244 / 244 (100%) |
| Above good score (≥0.85) | 212 (86.9%) |
| Between min and good | 31 (12.7%) |
| Below min score | 1 (0.4%) |
| pdf_oxide wins | 191 (78.3%) |
| pypdf wins | 53 (21.7%) |
| Median composite score | 0.903 |
| Median time per paper | 0.95 s |

Interpretation:

- The current two-engine pipeline handles ~87% of papers at the "good"
  bar. No further work is needed for those.
- ~13% are in the gap where layout-aware extraction (Docling) is the
  expected win. This is the priority for Phase 1.
- ~0.4% are scanned / image-only and need OCR (Nougat or Mistral OCR).
- pdf_oxide wins most of the time but pypdf is meaningfully better on
  ~22% — keep both engines in the routing chain.

The one paper that fell below the min bar
(`advances_and_challenges_in_artificial_intelligence_...pdf`, score
0.378) is image-heavy with sparse text — exactly the failure mode OCR
is designed to handle.

## What's next

### Phase 1: Docling fallback — SHIPPED

Added `DoclingEngine` (in `app/services/pdf_extraction/engines/docling.py`)
that activates as a **fallback tier** when the fast pdf_oxide + pypdf pair
fails to clear the `min_score` bar. Install with:

```bash
uv sync --extra docling
```

The engine is optional — `register_optional_fallback_engines()` (called
from `app.main` lifespan) registers Docling only when the dep is
installed, and the router runs the fallback tier only when the fast
tier falls below threshold. The hot path stays fast (~1s/paper for
87% of the corpus).

Benchmark on 32 papers where the fast tier scored below 0.85
(`scripts/benchmark_docling_fallback.py`):

| Metric | Value |
|---|---|
| Papers tested | 32 |
| Docling succeeded | 32 / 32 (100%) |
| Reached GOOD_SCORE (≥0.85) | 29 / 32 (90.6%) |
| Mean score lift | **+0.095** |
| Median score lift | **+0.099** |
| Big wins (≥0.10 lift) | 16 / 32 (50.0%) |
| Moderate wins (0.03-0.10 lift) | 12 / 32 (37.5%) |
| Ties | 4 / 32 (12.5%) |
| Regressions | 0 / 32 (0%) |
| Mean per-paper latency | 14.4s |
| Median per-paper latency | 4.8s |
| p90 latency | 18.3s |

**Docling never regressed.** On the 32 papers where the fast tier was
struggling, Docling cleared the GOOD_SCORE bar on 90.6% of them with
a median +0.10 lift. The full per-paper report is in
`data/local_pdf_full_extract/docling-benchmark.json`.

This validates Phase 1 as worth the install cost. Combined with the
Phase 4 fast tier (87% of papers above GOOD_SCORE), the production
pipeline now reaches:

- **~87% papers** — fast tier (pdf_oxide + pypdf), ~1s/paper
- **~12% papers** — Docling fallback, ~5-15s/paper
- **~0.4% papers** — need OCR (Surya/Mistral), future work

#### Pipeline throughput (20-paper end-to-end test)

Full pipeline (extract → chunk → score, skipping embedding API call)
on a stratified sample of 20 papers:

| Config | Wall clock | Throughput | Notes |
|---|---|---|---|
| Sequential (1 thread) | 43.95s | 0.45 papers/s | Baseline |
| ThreadPoolExecutor (2 threads) | 46.58s | 0.43 papers/s | GIL-bound, **no improvement** |
| ProcessPoolExecutor (all cores) | **22.05s** | **0.91 papers/s** | **2x speedup** |

Per-paper latency (ProcessPoolExecutor run):
- Fast-tier only (95% of papers): mean 2.44s, median 1.28s, p90 7.88s
- With Docling fallback (5%): mean 18.23s, median 18.23s

Implications for production:
- **Use ProcessPoolExecutor** for batch ingestion (Celery worker, etc.)
- **Single async process** is fine for the FastAPI hot path — the
 5-signal fast tier keeps p95 latency well under 8s
- Docling is GPU-bound so it doesn't parallelise well; running it in
  a separate worker pool keeps the fast tier responsive

The DoclingEngine was also upgraded to emit formulas as ``$$…$$``
blocks by walking ``document.texts`` and reading the ``orig`` field
(this is lost by ``export_to_markdown()``). Benchmark re-run on
1503.05723.pdf showed score 0.970 → **0.975** because formula blocks
now contribute to density / structure signals.

### Phase 2: Per-page re-extraction — SHIPPED

Added ``extract_pages_with_routing`` to the router. The new function:

1. Runs each fast-tier engine page-by-page (``pdf_oxide`` and ``pypdf``
   both expose per-page APIs natively; the engines implement
   :meth:`ExtractionEngine.extract_pages`).
2. Picks the engine with the highest page coverage.
3. Scores each page individually with the 5-signal audit.
4. If fewer than 50% of pages are weak: re-extracts *only the weak
   pages* with the fallback tier (Docling) and splices them in. This
   keeps the per-paper cost proportional to the damage instead of the
   document size.
5. If 50% or more pages are weak: re-extracts the whole document via
   the fallback tier (cheaper than running Docling page-by-page
   because of model warmup cost).

Why this matters:

- Most "in-between" papers have only 1-3 weak pages (a tricky figure
  caption, a scanned table, a maths-heavy page that pdf_oxide rendered
  as word soup). With Phase 2 we pay for Docling on those few pages,
  not for the whole document.
- A 10-page paper with 1 weak page now spends ~5s on Docling instead
  of ~15-20s.

### Phase 3: Engine-aware cleanup — SHIPPED

Split ``_normalize_text`` into two passes:

- ``_strip_markdown_noise(text)`` — engine-agnostic. Strips bold/italic/
  code/link markers, collapses whitespace. Runs for every backend
  (both pdf_oxide markdown and Docling markdown emit some noise).
- ``_strip_layout_artifacts(text)`` — fast-tier only. Drops arXiv
  watermarks, page numbers, email footers, TOC entries, journal
  boilerplate, mid-paragraph page-number injection. **Skipped when
  ``source_engine="docling"``** because Docling already excludes page
  furniture at the source.

New API:

- ``chunk_text(text, source_engine=None)`` — pass the engine name so
  downstream code can choose the right cleanup path.
- ``extract_and_chunk(pdf_path)`` — convenience wrapper that runs
  extraction + chunking with the engine name propagated automatically.

Tests added (5 new):
- Normalize skips layout cleanup for Docling output
- Normalize runs layout cleanup for fast-tier
- Legacy ``source_engine=None`` preserves old behaviour
- Markdown noise strip is engine-agnostic
- Layout artifact strip drops arXiv watermark

### Classifier fix (equation false positives) — SHIPPED

The previous ``_classify_chunk_text`` heuristic marked narrative
chunks as ``equation`` whenever they contained any operator or Greek
letter. After Phase 1 we observed 13/21 narrative chunks from pypdf
being misclassified as equation (because pypdf inserts spaces mid-word
like ``stude nts`` which triggered the math detector).

Fix: tightened ``_looks_like_equation_line`` to require *two*
independent signals before flagging a line as equation:

- LaTeX command (``\alpha``, ``\frac``, ...) **and** math operator, OR
- 3+ Unicode math symbols on a short line, OR
- 1+ Unicode math symbol + operator on a line ≤ 80 chars (catches
  broken pdf_oxide ASCII output), OR
- Equation label ``(12)`` + math marker immediately adjacent.

Plus a high-confidence early exit: ``$$…$$`` or ``\[…\]`` blocks →
``equation`` regardless of the line-level heuristic (so Docling's
LaTeX chunks classify correctly even in otherwise narrative context).

Tests added (3 new):
- Narrative paragraph with Greek letters stays narrative
- ``$$…$$`` block classifies as equation even inside prose
- (existing) single inline formula stays narrative

## Files

## Files

```
app/services/pdf_extraction/
  __init__.py             # public API surface
  quality.py              # 5-signal ExtractionQuality scorer
  router.py               # ExtractionEngine protocol + extract_with_routing + fallback tier
  engines/
    __init__.py           # engines package marker
    docling.py            # DoclingEngine (layout-aware, optional dep)
app/services/pdf_fulltext.py       # hot path; delegates to router
app/main.py                         # lifespan registers optional fallback engines
tests/test_pdf_extraction_quality.py        # 35 unit tests
scripts/benchmark_extraction_quality.py     # corpus benchmark CLI (fast tier)
scripts/benchmark_docling_fallback.py       # Docling fallback benchmark CLI
scripts/benchmark_pipeline_throughput.py    # 20-paper end-to-end pipeline test
data/local_pdf_full_extract/quality-benchmark-full.json   # 244-paper fast-tier run
data/local_pdf_full_extract/docling-benchmark.json        # 32-paper Docling comparison
data/local_pdf_full_extract/pipeline-throughput.json      # 20-paper pipeline test
```