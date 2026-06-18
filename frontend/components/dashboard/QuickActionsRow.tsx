"use client";

import Link from "next/link";
import {
  MagnifyingGlass,
  Table,
  Lightbulb,
  PencilLine,
  ArrowRight,
  Folder,
} from "@phosphor-icons/react";
import { WorkflowPipeline } from "./WorkflowPipeline";

const ACTIONS = [
  {
    href: "/search",
    label: "Search Papers",
    sub: "Find & save papers",
    icon: MagnifyingGlass,
    color: "bg-primary/10 text-primary",
  },
  {
    href: "/matrix",
    label: "Matrix",
    sub: "Compare papers",
    icon: Table,
    color: "bg-amber-50 text-amber-600",
  },
  {
    href: "/gaps",
    label: "Gaps",
    sub: "Find research gaps",
    icon: Lightbulb,
    color: "bg-violet-50 text-violet-600",
  },
  {
    href: "/reports",
    label: "Review",
    sub: "Export citation-safe review",
    icon: PencilLine,
    color: "bg-emerald-50 text-emerald-600",
  },
];

interface Props {
  projectCount: number;
}

export function QuickActionsRow({ projectCount }: Props) {
  return (
    <div className="mb-8 animate-slide-up delay-100">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-ui text-[12px] font-semibold uppercase tracking-wider text-ash">
          Quick Actions
        </h2>
        {projectCount > 0 && (
          <Link
            href="/projects/new"
            className="font-ui inline-flex items-center gap-1.5 text-[12px] font-medium text-primary hover:text-primary-deep transition-colors"
          >
            New Project <ArrowRight size={12} weight="bold" />
          </Link>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {ACTIONS.map((a) => (
          <Link
            key={a.href}
            href={a.href}
            className="group flex items-center gap-3 rounded-[12px] bg-surface-card p-4 transition-all hover:shadow-sm active:scale-[0.98]"
            style={{ border: "1px solid var(--hairline)" }}
          >
            <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] ${a.color}`}>
              <a.icon size={18} weight="bold" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-ui text-[13px] font-semibold text-ink">{a.label}</p>
              <p className="font-ui text-[11px] text-ash">{a.sub}</p>
            </div>
            <ArrowRight
              size={14}
              className="shrink-0 text-stone transition-colors group-hover:text-ink"
            />
          </Link>
        ))}
      </div>
    </div>
  );
}
