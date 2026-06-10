"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { PapersFilters, PapersTable } from "@/components/papers";
import type { PaperItem, SortKey } from "@/components/papers";

export default function PapersPage() {
  const { token } = useAuth();
  const router = useRouter();
  const [papers, setPapers] = useState<PaperItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [projectFilter, setProjectFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("saved_at");
  const [sortAsc, setSortAsc] = useState(false);

  useEffect(() => {
    if (!token) return;
    apiFetch<{ items: PaperItem[]; total: number }>("/papers/all", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((data) => setPapers(data.items || []))
      .catch(() => toast.error("Failed to load papers"))
      .finally(() => setLoading(false));
  }, [token]);

  const projects = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of papers) map.set(p.project_id, p.project_title);
    return Array.from(map, ([id, title]) => ({ id, title }));
  }, [papers]);

  const filtered = useMemo(() => {
    let result = papers;
    if (projectFilter) result = result.filter((p) => p.project_id === projectFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (p) =>
          p.title.toLowerCase().includes(q) ||
          p.authors.some((a) => a.toLowerCase().includes(q)) ||
          (p.venue && p.venue.toLowerCase().includes(q)) ||
          (p.abstract && p.abstract.toLowerCase().includes(q)),
      );
    }
    result = [...result].sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "title": cmp = a.title.localeCompare(b.title); break;
        case "year": cmp = (a.year ?? 0) - (b.year ?? 0); break;
        case "citations": cmp = (a.citation_count ?? 0) - (b.citation_count ?? 0); break;
        case "saved_at": cmp = new Date(a.saved_at).getTime() - new Date(b.saved_at).getTime(); break;
      }
      return sortAsc ? cmp : -cmp;
    });
    return result;
  }, [papers, search, projectFilter, sortKey, sortAsc]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  }

  return (
    <div className="px-4 sm:px-6 py-6">
      <div className="flex flex-col gap-5">
        <div>
          <h1 className="font-display text-[28px] font-bold leading-[1.0] text-ink" style={{ letterSpacing: "-0.5px" }}>Saved Papers</h1>
          <p className="mt-1.5 text-sm text-charcoal">{papers.length} papers across {projects.length} projects</p>
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
