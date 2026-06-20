"use client";

import Link from "next/link";
import {
  ArrowRight,
  CheckCircle,
  CircleNotch,
  FileText,
  Lightning,
  Warning,
} from "@phosphor-icons/react";
import type { StatsData } from "@/lib/stores/projects-store";

interface ActivityItem {
  icon: "circle" | "check" | "file" | "warning" | "lightning";
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
  const workflows = stats?.project_workflows ?? [];
  const activeWorkflow = workflows.find((p) => p.status === "active") ?? workflows[0];

  if (activeWorkflow) {
    const base = `/projects/${activeWorkflow.id}`;
    const missingFullText = activeWorkflow.paper_count - activeWorkflow.full_text_count;
    const missingMatrix = activeWorkflow.paper_count - activeWorkflow.matrix_count;

    if (activeWorkflow.paper_count === 0) {
      items.push({
        icon: "file",
        iconColor: "text-amber-500",
        text: "No papers saved in the active project",
        sub: "Search and save papers to create a research corpus",
        href: `${base}/search`,
      });
    }
    if (missingFullText > 0 && activeWorkflow.paper_count >= 5) {
      items.push({
        icon: "warning",
        iconColor: "text-amber-500",
        text: `${missingFullText} saved paper${missingFullText === 1 ? "" : "s"} need full text`,
        sub: "Open saved papers before trusting downstream synthesis",
        href: `${base}/papers`,
      });
    }
    if (missingMatrix > 0 && activeWorkflow.paper_count >= 5) {
      items.push({
        icon: "lightning",
        iconColor: "text-emerald-500",
        text: `${missingMatrix} paper${missingMatrix === 1 ? "" : "s"} missing matrix rows`,
        sub: "Generate or refresh the literature matrix",
        href: `${base}/matrix`,
      });
    }
    if (activeWorkflow.gap_count === 0 && activeWorkflow.matrix_count > 0) {
      items.push({
        icon: "circle",
        iconColor: "text-violet-500",
        text: "Research gaps not detected yet",
        sub: "Use matrix evidence to find defensible gaps",
        href: `${base}/gaps`,
      });
    }
    if (activeWorkflow.conflict_count > 0) {
      const conflictLabel = activeWorkflow.conflict_count === 1 ? "" : "s";
      items.push({
        icon: "warning",
        iconColor: "text-rose-500",
        text: `${activeWorkflow.conflict_count} conflicting finding${conflictLabel}`,
        sub: "Review contradictions before writing the final synthesis",
        href: `${base}/gaps`,
      });
    }
    if (activeWorkflow.report_count === 0 && activeWorkflow.gap_count > 0) {
      items.push({
        icon: "circle",
        iconColor: "text-blue-500",
        text: "Citation-safe review not generated yet",
        sub: "Turn the evidence-backed gaps into a draft review",
        href: `${base}/reports`,
      });
    }
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-[12px] px-4 py-8 text-center sm:py-10">
        <CheckCircle size={32} className="text-emerald-400 mb-3" weight="fill" />
        <p className="font-ui text-sm font-semibold text-ink">All caught up</p>
        <p className="mt-1 font-ui text-[12px] leading-snug text-charcoal">
          Start by creating a project or searching papers.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item, i) => {
        const IconEl = item.icon === "check" ? CheckCircle
          : item.icon === "warning" ? Warning
          : item.icon === "file" ? FileText
          : item.icon === "lightning" ? Lightning
          : CircleNotch;
        return (
          <div
            key={i}
            className="grid gap-3 rounded-[10px] bg-surface-card p-3 sm:flex sm:items-start"
            style={{ border: "1px solid var(--hairline)" }}
          >
            <div className="flex min-w-0 items-start gap-3">
              <IconEl size={16} className={item.iconColor + " mt-0.5 shrink-0"} weight="fill" />
              <div className="min-w-0 flex-1">
                <p className="font-ui text-[13px] font-medium leading-snug text-ink">
                  {item.text}
                </p>
              {item.sub && (
                  <p className="mt-0.5 font-ui text-[11px] leading-snug text-ash">
                    {item.sub}
                  </p>
              )}
              </div>
            </div>
            {item.href && (
              <Link
                href={item.href}
                className="inline-flex h-8 w-full shrink-0 items-center justify-center gap-1 rounded-full bg-primary/10 font-ui text-[11px] font-semibold text-primary transition-colors hover:text-primary-deep sm:h-auto sm:w-auto sm:bg-transparent"
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
