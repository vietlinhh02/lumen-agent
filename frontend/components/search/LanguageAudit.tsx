"use client";

import type { LanguageBiasAudit, QueryVariant } from "@/lib/types";

interface Props {
  audit: LanguageBiasAudit;
  detectedLanguage?: string | null;
  queryVariants?: QueryVariant[];
}

export function LanguageAudit({ audit, detectedLanguage, queryVariants }: Props) {
  return (
    <div className="flex items-center gap-2 text-[11px] text-ash">
      <span>·</span>
      {detectedLanguage && <span>{detectedLanguage.toUpperCase()}</span>}
      {Object.entries(audit.candidate_counts_by_language).map(([lang, count]) => (
        <span key={lang}>{lang.toUpperCase()}: {count}</span>
      ))}
      <span
        className={`font-semibold ${
          audit.english_dominance_score < 0.7
            ? "text-emerald-600"
            : audit.english_dominance_score < 0.85
              ? "text-amber-600"
              : "text-red-500"
        }`}
      >
        EN {Math.round(audit.english_dominance_score * 100)}%
      </span>
      {queryVariants && queryVariants.length > 0 && (
        <span className="relative group">
          <span className="cursor-help border-b border-dashed border-stone">{queryVariants.length} queries</span>
          <div
            className="hidden group-hover:block absolute left-0 top-full z-20 mt-1 w-[420px] rounded-lg bg-surface-card p-3 shadow-lg"
            style={{ border: "1px solid var(--hairline)" }}
          >
            {queryVariants.map((v, i) => (
              <div key={i} className="flex items-start gap-2 text-[11px] py-0.5">
                <span className="font-semibold text-charcoal shrink-0">{v.source}</span>
                <span className="text-mute break-words">{v.query}</span>
              </div>
            ))}
          </div>
        </span>
      )}
    </div>
  );
}
