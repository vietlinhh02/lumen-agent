"""Cost tracker service — logs LLM token usage to DB and aggregates monthly reports.

Usage:
    from app.services.cost_tracker import log_llm_usage, get_monthly_report
    from app.ai.provider import LLMUsage

    text, usage = await provider.complete_with_usage(messages)
    await log_llm_usage(db, user_id=user.id, usage=usage, context="report")
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import LLMUsage

logger = logging.getLogger(__name__)

# ── Pricing table (USD per 1M tokens, public rates as of 2026-06) ─────────────

_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-5":        {"input": 3.00,  "output": 15.00},
    "claude-haiku-3-5":         {"input": 0.80,  "output": 4.00},
    "claude-opus-4-5":          {"input": 15.00, "output": 75.00},
    "deepseek-chat":            {"input": 0.27,  "output": 1.10},
    "deepseek-reasoner":        {"input": 0.55,  "output": 2.19},
    "gpt-4o":                   {"input": 5.00,  "output": 15.00},
    "gpt-4o-mini":              {"input": 0.15,  "output": 0.60},
    "mimo-v2.5":                {"input": 0.435, "output": 0.87},
    "mimo-v2.5-pro":            {"input": 0.435, "output": 0.87},
    "mimo-v2.5-lite":           {"input": 0.15,  "output": 0.30},
    # Free / embedding providers
    "nvidia/nemotron":          {"input": 0.0,   "output": 0.0},
    "text-embedding-3-small":   {"input": 0.02,  "output": 0.0},
}

_DEFAULT_PRICING = {"input": 0.0, "output": 0.0}


def _compute_cost(usage: LLMUsage) -> float:
    """Compute USD cost from usage. Returns 0.0 for unknown models."""
    # Normalise model name: strip provider prefix (e.g. "anthropic/claude-…")
    model_key = usage.model.split("/")[-1] if "/" in usage.model else usage.model
    pricing = _PRICING.get(model_key, _DEFAULT_PRICING)
    return (
        usage.input_tokens * pricing["input"]
        + usage.output_tokens * pricing["output"]
    ) / 1_000_000


# ── DB write ──────────────────────────────────────────────────────────────────


async def log_llm_usage(
    db: AsyncSession,
    user_id: UUID,
    usage: LLMUsage,
    context: str,
) -> None:
    """Write one LLMUsageLog row.

    Args:
        db: Async DB session (caller must commit or be in autocommit scope).
        user_id: The authenticated user who triggered this LLM call.
        usage: LLMUsage returned by complete_with_usage().
        context: One of "report" | "matrix" | "assistant" | "screening" | "gaps" | "other".
    """
    # Import here to avoid circular imports at module load time
    from app.db.models import LLMUsageLog  # type: ignore[attr-defined]

    cost = _compute_cost(usage)
    log = LLMUsageLog(
        user_id=user_id,
        model=usage.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=cost,
        context=context,
    )
    db.add(log)
    # Do not commit here — let the caller's transaction manage it.
    # Use db.flush() if you need the ID immediately.
    logger.debug(
        "llm_usage: user=%s model=%s in=%d out=%d cost=$%.6f ctx=%s",
        user_id, usage.model, usage.input_tokens, usage.output_tokens, cost, context,
    )


# ── Monthly report ────────────────────────────────────────────────────────────


async def get_monthly_report(
    db: AsyncSession,
    user_id: UUID,
    year: int,
    month: int,
) -> dict:
    """Return aggregated cost breakdown for a given calendar month.

    Args:
        db: Async DB session.
        user_id: The user to report on.
        year: Calendar year (e.g. 2026).
        month: Calendar month 1-12.

    Returns:
        dict with keys: period, total_usd, by_model, by_context,
        tokens, projected_monthly_usd.
    """
    from app.db.models import LLMUsageLog  # type: ignore[attr-defined]

    # Month bounds in UTC
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)

    base_where = (
        LLMUsageLog.user_id == user_id,
        LLMUsageLog.created_at >= start,
        LLMUsageLog.created_at < end,
    )

    # Total cost + tokens
    totals_stmt = select(
        func.coalesce(func.sum(LLMUsageLog.cost_usd), 0).label("total_usd"),
        func.coalesce(func.sum(LLMUsageLog.input_tokens), 0).label("total_input"),
        func.coalesce(func.sum(LLMUsageLog.output_tokens), 0).label("total_output"),
    ).where(*base_where)

    # By model
    by_model_stmt = select(
        LLMUsageLog.model,
        func.coalesce(func.sum(LLMUsageLog.cost_usd), 0).label("cost"),
    ).where(*base_where).group_by(LLMUsageLog.model)

    # By context
    by_ctx_stmt = select(
        LLMUsageLog.context,
        func.coalesce(func.sum(LLMUsageLog.cost_usd), 0).label("cost"),
    ).where(*base_where).group_by(LLMUsageLog.context)

    totals_row = (await db.execute(totals_stmt)).one()
    by_model_rows = (await db.execute(by_model_stmt)).all()
    by_ctx_rows = (await db.execute(by_ctx_stmt)).all()

    total_usd = float(totals_row.total_usd)
    total_input = int(totals_row.total_input)
    total_output = int(totals_row.total_output)

    # Project to full month based on days elapsed
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    days_in_month = (end - start).days
    if now < end:
        days_elapsed = max(1, (now - start).days)
        projected = total_usd * days_in_month / days_elapsed
    else:
        projected = total_usd

    return {
        "period": f"{year}-{month:02d}",
        "total_usd": round(total_usd, 6),
        "by_model": {r.model: round(float(r.cost), 6) for r in by_model_rows},
        "by_context": {(r.context or "other"): round(float(r.cost), 6) for r in by_ctx_rows},
        "tokens": {
            "input": total_input,
            "output": total_output,
            "total": total_input + total_output,
        },
        "projected_monthly_usd": round(projected, 6),
    }
