"use client";

import { useMemo } from "react";
import { useAuth } from "@/lib/stores/auth-store";
import type { StatsData } from "@/lib/stores/projects-store";

interface Props {
  stats: StatsData | null;
  runningJobs: number;
}

export function DashboardHeader({ stats, runningJobs }: Props) {
  const user = useAuth((s) => s.user);

  const { greeting, sub } = useMemo(() => {
    const hour = new Date().getHours();
    const base = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
    const name = user?.email?.split("@")[0] ?? "researcher";
    const cap = name.charAt(0).toUpperCase() + name.slice(1);

    const parts: string[] = [];
    if (runningJobs > 0) parts.push(`${runningJobs} AI job${runningJobs > 1 ? "s" : ""} running`);
    if (stats) {
      if (stats.paper_count === 0) parts.push("no papers saved yet");
      else if (stats.matrix_count === 0) parts.push(`${stats.paper_count} paper${stats.paper_count !== 1 ? "s" : ""} ready to analyze`);
      else if (stats.gap_count === 0) parts.push("gaps not detected yet");
      else if (stats.report_count === 0) parts.push("review not generated yet");
      else parts.push("all systems active");
    }

    const sub = parts.length > 0
      ? `You have ${parts.join(", ")}.`
      : "Everything is up to date.";

    return { greeting: `${base}, ${cap}`, sub };
  }, [user, stats, runningJobs]);

  return (
    <div className="mb-8 animate-fade-in">
      <h1
        className="font-display text-[36px] font-bold leading-[1.0] text-ink"
        style={{ letterSpacing: "-1px" }}
      >
        {greeting}.
      </h1>
      <p className="mt-2 max-w-2xl text-base leading-[1.6] text-charcoal">{sub}</p>
    </div>
  );
}
