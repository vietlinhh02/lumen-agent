"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import {
  Folder,
  FileText,
  Table,
  Lightbulb,
  PencilLine,
  ArrowRight,
  MagnifyingGlass,
} from "@phosphor-icons/react";

interface Stats {
  project_count: number;
  paper_count: number;
  matrix_count: number;
  gap_count: number;
  report_count: number;
  recent_projects: Array<{
    id: string;
    title: string;
    status: string;
    updated_at: string;
  }>;
}

export default function DashboardPage() {
  const { token } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    if (!token) return;
    apiFetch<Stats>("/stats", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(setStats)
      .catch(() => toast.error("Failed to load stats"));
  }, [token]);

  const statCards = stats
    ? [
        { label: "Projects", value: stats.project_count, icon: Folder, color: "text-primary", bg: "bg-primary/10" },
        { label: "Papers Saved", value: stats.paper_count, icon: FileText, color: "text-blue-600", bg: "bg-blue-50" },
        { label: "Matrix Rows", value: stats.matrix_count, icon: Table, color: "text-emerald-600", bg: "bg-emerald-50" },
        { label: "Research Gaps", value: stats.gap_count, icon: Lightbulb, color: "text-amber-600", bg: "bg-amber-50" },
        { label: "Reports", value: stats.report_count, icon: PencilLine, color: "text-violet-600", bg: "bg-violet-50" },
      ]
    : [];

  const quickActions = [
    { label: "Search Papers", description: "Find papers from academic databases", icon: MagnifyingGlass, href: "/search", color: "text-primary", bg: "bg-primary/10" },
    { label: "Create Project", description: "Start a new research workspace", icon: Folder, href: "/projects", color: "text-blue-600", bg: "bg-blue-50" },
    { label: "View Matrix", description: "Compare papers side by side", icon: Table, href: "/matrix", color: "text-emerald-600", bg: "bg-emerald-50" },
    { label: "Generate Review", description: "Create a citation-safe literature review", icon: PencilLine, href: "/reports", color: "text-violet-600", bg: "bg-violet-50" },
  ];

  function timeAgo(dateStr: string): string {
    const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-8">
        <h1 className="font-display text-[36px] font-bold leading-[1.0] text-ink" style={{ letterSpacing: "-1px" }}>
          Welcome back
        </h1>
        <p className="mt-2 text-base text-charcoal">Your AI literature review workspace at a glance.</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-8">
        {stats
          ? statCards.map((card) => (
              <div key={card.label} className="rounded-[12px] bg-surface-card p-4 transition-shadow hover:shadow-sm" style={{ border: "1px solid var(--hairline)" }}>
                <div className="flex items-center gap-3">
                  <div className={`flex h-[36px] w-[36px] items-center justify-center rounded-[10px] ${card.bg}`}>
                    <card.icon size={18} className={card.color} />
                  </div>
                  <div>
                    <p className="font-display text-[24px] font-bold text-ink leading-none">{card.value}</p>
                    <p className="font-ui text-[11px] text-ash mt-0.5">{card.label}</p>
                  </div>
                </div>
              </div>
            ))
          : [1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="rounded-[12px] bg-surface-card p-4 animate-pulse" style={{ border: "1px solid var(--hairline)" }}>
                <div className="h-[36px] w-[36px] rounded-[10px] bg-surface-bone mb-2" />
                <div className="h-6 w-12 rounded bg-surface-bone" />
                <div className="h-3 w-16 rounded bg-surface-bone mt-1" />
              </div>
            ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Quick Actions */}
        <div className="lg:col-span-1">
          <h2 className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-3">Quick Actions</h2>
          <div className="space-y-2">
            {quickActions.map((action) => (
              <button
                key={action.label}
                onClick={() => router.push(action.href)}
                className="w-full flex items-center gap-3 rounded-[10px] bg-surface-card px-4 py-3 text-left transition-all hover:shadow-sm group"
                style={{ border: "1px solid var(--hairline)" }}
              >
                <div className={`flex h-[32px] w-[32px] items-center justify-center rounded-[8px] ${action.bg} shrink-0`}>
                  <action.icon size={16} className={action.color} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-ui text-[13px] font-semibold text-ink">{action.label}</p>
                  <p className="font-ui text-[11px] text-ash">{action.description}</p>
                </div>
                <ArrowRight size={14} className="text-stone group-hover:text-ink transition-colors shrink-0" />
              </button>
            ))}
          </div>
        </div>

        {/* Recent Projects */}
        <div className="lg:col-span-2">
          <h2 className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide mb-3">Recent Projects</h2>
          <div className="rounded-[12px] bg-surface-card overflow-hidden" style={{ border: "1px solid var(--hairline)" }}>
            {stats && stats.recent_projects.length > 0 ? (
              <div>
                {stats.recent_projects.map((p, i) => (
                  <button
                    key={p.id}
                    onClick={() => router.push(`/projects/${p.id}`)}
                    className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-surface-bone/50 transition-colors"
                    style={{ borderTop: i > 0 ? "1px solid var(--hairline)" : undefined }}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <Folder size={18} className="text-primary shrink-0" />
                      <div className="min-w-0">
                        <p className="font-ui text-[14px] font-medium text-ink truncate">{p.title}</p>
                        <p className="font-ui text-[11px] text-ash">{timeAgo(p.updated_at)}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={`font-ui text-[11px] font-semibold px-2 py-0.5 rounded-full ${p.status === "active" ? "bg-green-50 text-green-700" : "bg-ash/10 text-ash"}`}>
                        {p.status}
                      </span>
                      <ArrowRight size={14} className="text-stone" />
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <Folder size={32} className="text-stone mb-3" />
                <p className="font-ui text-sm font-medium text-ink">No projects yet</p>
                <p className="font-ui text-[12px] text-charcoal mt-1">Create your first project to get started</p>
                <button
                  onClick={() => router.push("/projects")}
                  className="focus-ring font-ui mt-4 inline-flex items-center gap-2 h-[36px] rounded-full bg-primary px-4 text-[13px] font-semibold text-on-primary transition-colors hover:bg-primary-deep"
                >
                  Create Project
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
