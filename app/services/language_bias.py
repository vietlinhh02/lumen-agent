"""Language bias detection, query variant generation, and audit computation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.ai.prompts import LANGUAGE_BIAS_SYSTEM, LANGUAGE_BIAS_USER
from app.ai.provider import get_provider

logger = logging.getLogger(__name__)


@dataclass
class QueryVariant:
    source: str
    query: str
    language: str


@dataclass
class LanguageBiasAudit:
    policy: str = "balanced"
    candidate_counts_by_language: dict[str, int] = field(default_factory=dict)
    english_dominance_score: float = 0.0
    adjustments_applied: list[str] = field(default_factory=list)


async def detect_and_generate_variants(
    query: str,
    target_languages: list[str],
) -> tuple[list[QueryVariant], str]:
    """Detect query language and generate search variants in one LLM call.

    Returns (variants, detected_language).
    Falls back gracefully on LLM failure.
    """
    try:
        provider = get_provider()
        user_msg = LANGUAGE_BIAS_USER.format(query=query)
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            system=LANGUAGE_BIAS_SYSTEM,
            schema={
                "type": "object",
                "properties": {
                    "detected_language": {"type": "string"},
                    "variants": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"},
                                "query": {"type": "string"},
                                "language": {"type": "string"},
                            },
                            "required": ["source", "query", "language"],
                        },
                        "minItems": 1,
                        "maxItems": 5,
                    },
                },
                "required": ["detected_language", "variants"],
            },
            tool_name="language_bias",
            max_tokens=1000,
        )
        detected_lang = result.get("detected_language", "en")
        variants = [
            QueryVariant(
                source=v["source"],
                query=v["query"],
                language=v["language"],
            )
            for v in result.get("variants", [])
        ]
        if not variants:
            variants = [
                QueryVariant(source="semantic_scholar", query=query, language=detected_lang)
            ]

        return variants, detected_lang

    except Exception as exc:
        logger.warning("Language bias detection failed: %s, falling back to 'en'", exc)
        return [QueryVariant(source="semantic_scholar", query=query, language="en")], "en"


def assign_variants_to_sources(
    variants: list[QueryVariant],
    all_sources: list[str],
) -> dict[str, str]:
    """Map each source to the best query from the variants list.

    Academic sources (semantic_scholar, arxiv) get English variant.
    Discovery sources (exa, firecrawl) get original-language variant if available.
    Falls back to first variant if no language match.
    """
    variant_map: dict[str, str] = {}

    en_variants = [v for v in variants if v.language == "en"]
    non_en_variants = [v for v in variants if v.language != "en"]
    academic_sources = {"semantic_scholar", "arxiv", "openalex"}
    discovery_sources = {"exa", "firecrawl"}

    for src in all_sources:
        if src in academic_sources:
            chosen = en_variants[0] if en_variants else variants[0]
        elif src in discovery_sources:
            chosen = (
                non_en_variants[0]
                if non_en_variants
                else en_variants[0]
                if en_variants
                else variants[0]
            )
        else:
            chosen = variants[0]
        variant_map[src] = chosen.query

    return variant_map


def compute_bias_audit(
    source_diagnostics: list[dict],
    policy: str,
    variants: list[QueryVariant],
) -> LanguageBiasAudit:
    """Compute language coverage audit from source diagnostics.

    Maps each source's result count to the language of the variant sent.
    Computes english_dominance_score = en_count / total_count.
    """
    adjustments: list[str] = []

    variant_lang_map: dict[str, str] = {}
    for v in variants:
        variant_lang_map[v.source] = v.language

    has_non_en = any(v.language != "en" for v in variants)
    if has_non_en:
        adjustments.append("included_original_language_query")

    counts: dict[str, int] = {}
    for diag in source_diagnostics:
        count = diag.get("result_count", 0)
        if count <= 0:
            continue
        source_name = diag.get("source", "")
        lang = variant_lang_map.get(source_name, "en")
        counts[lang] = counts.get(lang, 0) + count

    total = sum(counts.values()) or 1
    en_count = counts.get("en", 0)
    score = round(en_count / total, 2)

    return LanguageBiasAudit(
        policy=policy,
        candidate_counts_by_language=counts,
        english_dominance_score=score,
        adjustments_applied=adjustments,
    )
