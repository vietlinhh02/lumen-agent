"use client";

import Link from "next/link";
import { CircleNotch, CheckCircle, Warning, Lightning, ArrowRight } from "@phosphor-icons/react";
import type { StatsData } from "@/lib/stores/projects-store";

interface ActivityItem {
  icon: "circle" | "check" | "warning" | "lightning";
  iconColor: string;
  text: string;
  sub?: string;
  href?: string;
}

interface Props {
  stats: StatsData | null;
}

export function ActivityFeed({ stats }: Props) {
  const items: ActivityItem[] = [];

  if (stats) {
    if (stats.matrix_count > 0) {
      items.push({
        icon: "check",
        iconColor: "text-emerald-500",
        text: stats.matrix_count + " matrix row" + (stats.matrix_count !== 1 ? "s" : "") + " generated",
        sub: "Ready to review",
      });
    }
    if (stats.paper_count > 0 && stats.matrix_count === 0) {
      items.push({
        icon: "lightning",
        iconColor: "text-amber-500",
        text: stats.paper_count + " paper" + (stats.paper_count !== 1 ? "s" : "") + " saved",
        sub: "Generate matrix to analyze",
        href: "/matrix",
      });
    }
    if (stats.gap_count === 0 && stats.matrix_count > 0) {
      items.push({
        icon: "circle",
        iconColor: "text-violet-500",
        text: "Gaps not detected yet",
        sub: "Find research gaps in your literature",
        href: "/gaps",
      });
    }
    if (stats.report_count === 0 && stats.matrix_count > 0) {
      items.push({
        icon: "circle",
        iconColor: "text-blue-500",
        text: "Review not generated yet",
        sub: "Export a citation-safe literature review",
        href: "/reports",
      });
    }
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-[12px] py-10 text-center">
        <CheckCircle size={32} className="text-emerald-400 mb-3" weight="fill" />
        <p className="font-ui text-sm font-semibold text-ink">All caught up</p>
        <p className="mt-1 font-ui text-[12px] text-charcoal">Start by creating a project or searching papers.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item, i) => {
        const IconEl = item.icon === "check" ? CheckCircle
          : item.icon === "warning" ? Warning
          : item.icon === "lightning" ? Lightning
          : CircleNotch;
        return (
          <div
            key={i}
            className="flex items-start gap-3 rounded-[10px] bg-surface-card p-3"
            style={{ border: "1px solid var(--hairline)" }}
          >
            <IconEl size={16} className={item.iconColor + " mt-0.5 shrink-0"} weight="fill" />
            <div className="min-w-0 flex-1">
              <p className="font-ui text-[13px] font-medium text-ink">{item.text}</p>
              {item.sub && (
                <p className="font-ui text-[11px] text-ash">{item.sub}</p>
              )}
            </div>
            {item.href && (
              <Link
                href={item.href}
                className="shrink-0 inline-flex items-center gap-1 font-ui text-[11px] font-medium text-primary hover:text-primary-deep transition-colors"
              >
                Go <ArrowRight size={11} />
              </Link>
            )}
          </div>
        );
      })}
    </div>
  );
}
