"use client";

import { useMemo } from "react";
import { useAuth } from "@/lib/stores/auth-store";
import type { StatsData } from "@/lib/stores/projects-store";

interface Props {
  stats: StatsData | null;
  runningJobs: number;
}

const QUOTES = [
  "Research is formalized curiosity.",
  "Stand on the shoulders of giants.",
  "Every paper is a conversation; your review is the synthesis.",
  "A good literature review does not just report — it reveals patterns.",
  "Read widely, think deeply, write clearly.",
  "The best research begins with a better question.",
  "Curiosity is the engine of scholarship.",
  "Synthesis is the moment separate voices become one argument.",
  "Knowledge grows when connections are made visible.",
  "Your review is the map you draw across the field.",
  "Ideas are cheap; evidence is expensive.",
  "Great researchers are ruthless curators of sources.",
];

export function DashboardHeader({ stats, runningJobs }: Props) {
  const user = useAuth((s) => s.user);

  const { greeting, quote, status } = useMemo(() => {
    const hour = new Date().getHours();
    const base = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
    const name = user?.display_name?.trim() || user?.email?.split("@")[0] || "researcher";
    const cap = name.charAt(0).toUpperCase() + name.slice(1);

    const quoteIndex = new Date().getDate() % QUOTES.length;
    const quote = QUOTES[quoteIndex];

    let status = "";
    if (runningJobs > 0) {
      status = `${runningJobs} AI job${runningJobs > 1 ? "s" : ""} running`;
    } else if (stats) {
      if (stats.report_count > 0) status = "Review pipeline complete";
      else if (stats.gap_count > 0) status = "Gaps detected — ready to review";
      else if (stats.matrix_count > 0) status = "Matrix ready — find the gaps";
      else if (stats.paper_count > 0) status = `${stats.paper_count} paper${stats.paper_count !== 1 ? "s" : ""} saved`;
      else status = "Start by creating a project";
    }

    return { greeting: `${base}, ${cap}`, quote, status };
  }, [user, stats, runningJobs]);

  return (
    <div className="animate-fade-in">
      <h1 className="font-display text-[28px] font-bold leading-[1.05] text-ink sm:text-[36px]">
        {greeting}.
      </h1>
      <p className="mt-2 max-w-2xl text-sm font-medium italic leading-[1.6] text-charcoal sm:text-base sm:leading-[1.65]">
        “{quote}”
      </p>
      {status && (
        <p className="mt-1.5 font-ui text-[12px] text-ash">
          {status}
        </p>
      )}
    </div>
  );
}
