"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useAuth } from "@/lib/stores/auth-store";
import { usePapersStore, useFilteredPapers } from "@/lib/stores/papers-store";
import { PapersFilters, PapersTable } from "@/components/papers";
import type { SortKey } from "@/components/papers";

export default function PapersPage() {
  const token = useAuth((s) => s.token);
  const router = useRouter();
  const loading = usePapersStore((s) => s.loading);
  const search = usePapersStore((s) => s.search);
  const setSearch = usePapersStore((s) => s.setSearch);
  const projectFilter = usePapersStore((s) => s.projectFilter);
  const setProjectFilter = usePapersStore((s) => s.setProjectFilter);
  const sortKey = usePapersStore((s) => s.sortKey);
  const sortAsc = usePapersStore((s) => s.sortAsc);
  const toggleSort = usePapersStore((s) => s.toggleSort);
  const fetchPapers = usePapersStore((s) => s.fetchPapers);
  const { filtered, projectList: projects } = useFilteredPapers();

  useEffect(() => {
    if (token) {
      void fetchPapers().catch(() => toast.error("Failed to load papers"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <div className="px-4 sm:px-6 py-6">
      <div className="flex flex-col gap-5">
        <div>
          <h1 className="font-display text-[28px] font-bold leading-[1.0] text-ink" style={{ letterSpacing: "-0.5px" }}>Saved Papers</h1>
          <p className="mt-1.5 text-sm text-charcoal">{filtered.length} papers across {projects.length} projects</p>
        </div>
        <PapersFilters
          search={search}
          onSearchChange={setSearch}
          projectFilter={projectFilter}
          onProjectFilterChange={setProjectFilter}
          projects={projects}
        />
        {loading ? (
          <div className="rounded-[12px] bg-surface-card p-6 space-y-3" style={{ border: "1px solid var(--hairline)" }}>
            {[1, 2, 3, 4, 5].map((i) => <div key={i} className="h-12 rounded bg-surface-bone animate-pulse" />)}
          </div>
        ) : (
          <PapersTable papers={filtered} sortKey={sortKey} sortAsc={sortAsc} onToggleSort={toggleSort} onNavigate={router.push} />
        )}
      </div>
    </div>
  );
}
