"use client";

import type { MatrixRowResponse } from "@/lib/types";

interface Props {
  rows: MatrixRowResponse[];
}

export function MatrixStats({ rows }: Props) {
  if (rows.length === 0) return null;

  const aiCount = rows.filter((r) => r.created_by === "ai").length;
  const userCount = rows.filter((r) => r.created_by === "user").length;
  const highCount = rows.filter((r) => r.extraction_confidence === "high").length;

  return (
    <div
      className="flex items-center gap-x-5 gap-y-1 rounded-[10px] bg-surface-card px-4 py-3 font-ui text-[13px] text-ash"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <span><strong className="font-semibold text-charcoal">{rows.length}</strong> papers analyzed</span>
      <span><strong className="font-semibold text-charcoal">{aiCount}</strong> by AI</span>
      <span><strong className="font-semibold text-charcoal">{userCount}</strong> manually edited</span>
      <span><strong className="font-semibold text-charcoal">{highCount}</strong> high confidence</span>
    </div>
  );
}
