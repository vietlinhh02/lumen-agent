"use client";

const STYLES: Record<string, string> = {
  high: "bg-emerald-50 text-emerald-700",
  medium: "bg-amber-50 text-amber-700",
  low: "bg-red-50 text-red-600",
};

export function ConfidenceBadge({ level }: { level: string }) {
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-[11px] font-ui font-semibold ${
        STYLES[level] || STYLES.medium
      }`}
    >
      {level}
    </span>
  );
}
