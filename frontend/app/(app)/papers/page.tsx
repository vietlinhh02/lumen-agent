"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import {
  FileText,
  MagnifyingGlass,
  ArrowSquareOut,
  SortAscending,
  SortDescending,
} from "@phosphor-icons/react";
import { Dropdown } from "@/components/ui/Dropdown";

interface PaperItem {
  id: string;
  paper_id: string;
  project_id: string;
  project_title: string;
  title: string;
  abstract: string | null;
  authors: string[];
  year: number | null;
  venue: string | null;
  doi: string | null;
  arxiv_id: string | null;
  url: string | null;
  citation_count: number | null;
  source_names: string[];
  saved_at: string;
  relevance_label: string | null;
}

type SortKey = "title" | "year" | "citations" | "saved_at";

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

  // Unique projects for filter
  const projects = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of papers) map.set(p.project_id, p.project_title);
    return Array.from(map, ([id, title]) => ({ id, title }));
  }, [papers]);

  // Filter + sort
  const filtered = useMemo(() => {
    let result = papers;

    if (projectFilter) {
      result = result.filter((p) => p.project_id === projectFilter);
    }

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
        case "title":
          cmp = a.title.localeCompare(b.title);
          break;
        case "year":
          cmp = (a.year ?? 0) - (b.year ?? 0);
          break;
        case "citations":
          cmp = (a.citation_count ?? 0) - (b.citation_count ?? 0);
          break;
        case "saved_at":
          cmp = new Date(a.saved_at).getTime() - new Date(b.saved_at).getTime();
          break;
      }
      return sortAsc ? cmp : -cmp;
    });

    return result;
  }, [papers, search, projectFilter, sortKey, sortAsc]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  function SortIcon({ column }: { column: SortKey }) {
    if (sortKey !== column) return null;
    return sortAsc ? (
      <SortAscending size={12} className="text-primary" />
    ) : (
      <SortDescending size={12} className="text-primary" />
    );
  }

  return (
    <div className="px-4 sm:px-6 py-6">
      <div className="flex flex-col gap-5">
        {/* Header */}
        <div>
          <h1
            className="font-display text-[28px] font-bold leading-[1.0] text-ink"
            style={{ letterSpacing: "-0.5px" }}
          >
            Saved Papers
          </h1>
          <p className="mt-1.5 text-sm text-charcoal">
            {papers.length} papers across {projects.length} projects
          </p>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <MagnifyingGlass
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-ash"
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search title, author, venue…"
              className="focus-ring h-[38px] w-full rounded-full bg-surface-card pl-9 pr-4 font-ui text-sm text-ink outline-none"
              style={{ border: "1px solid var(--hairline)" }}
            />
          </div>

          {/* Project filter */}
          <div className="min-w-[200px]">
            <Dropdown
              options={[
                { value: "", label: "All projects" },
                ...projects.map((p) => ({
                  value: p.id,
                  label: p.title,
                })),
              ]}
              value={projectFilter}
              onChange={setProjectFilter}
              placeholder="All projects"
            />
          </div>
        </div>

        {/* Table */}
        <div
          className="rounded-[12px] bg-surface-card overflow-hidden"
          style={{ border: "1px solid var(--hairline)" }}
        >
          {loading ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div
                  key={i}
                  className="h-12 rounded bg-surface-bone animate-pulse"
                />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <FileText size={36} className="text-stone mb-3" />
              <p className="font-ui text-sm font-medium text-ink">
                {search || projectFilter
                  ? "No papers match your filters"
                  : "No saved papers yet"}
              </p>
              {!search && !projectFilter && (
                <button
                  onClick={() => router.push("/search")}
                  className="focus-ring font-ui mt-4 inline-flex items-center gap-2 h-[36px] rounded-full bg-primary px-4 text-[13px] font-semibold text-on-primary transition-colors hover:bg-primary-deep"
                >
                  Search Papers
                </button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-surface-bone/50">
                    <th
                      onClick={() => toggleSort("title")}
                      className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-5 py-3 cursor-pointer hover:text-ink transition-colors w-[40%]"
                    >
                      <span className="inline-flex items-center gap-1">
                        Title <SortIcon column="title" />
                      </span>
                    </th>
                    <th className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-4 py-3 w-[20%]">
                      Authors
                    </th>
                    <th
                      onClick={() => toggleSort("year")}
                      className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-4 py-3 cursor-pointer hover:text-ink transition-colors"
                    >
                      <span className="inline-flex items-center gap-1">
                        Year <SortIcon column="year" />
                      </span>
                    </th>
                    <th className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-4 py-3">
                      Venue
                    </th>
                    <th
                      onClick={() => toggleSort("citations")}
                      className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-right px-4 py-3 cursor-pointer hover:text-ink transition-colors"
                    >
                      <span className="inline-flex items-center gap-1 justify-end">
                        Cited <SortIcon column="citations" />
                      </span>
                    </th>
                    <th className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-4 py-3">
                      Project
                    </th>
                    <th className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-center px-4 py-3 w-[60px]">
                      Link
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((p) => (
                    <tr
                      key={p.id}
                      className="hover:bg-surface-bone/30 transition-colors"
                      style={{ borderTop: "1px solid var(--hairline)" }}
                    >
                      <td className="px-5 py-3">
                        <p className="font-ui text-[13px] font-medium text-ink line-clamp-2">
                          {p.title}
                        </p>
                      </td>
                      <td className="px-4 py-3">
                        <p className="font-ui text-[12px] text-charcoal line-clamp-2">
                          {p.authors.slice(0, 3).join(", ")}
                          {p.authors.length > 3 && " et al."}
                        </p>
                      </td>
                      <td className="px-4 py-3 font-ui text-[13px] text-ink">
                        {p.year ?? "—"}
                      </td>
                      <td className="px-4 py-3 font-ui text-[12px] text-charcoal line-clamp-1 max-w-[160px]">
                        {p.venue ?? "—"}
                      </td>
                      <td className="px-4 py-3 font-ui text-[13px] text-ink text-right tabular-nums">
                        {p.citation_count ?? "—"}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() =>
                            router.push(`/projects/${p.project_id}`)
                          }
                          className="font-ui text-[12px] text-primary hover:underline truncate max-w-[140px] block"
                        >
                          {p.project_title}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-center">
                        {p.url ? (
                          <a
                            href={p.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center justify-center h-[28px] w-[28px] rounded-[6px] text-charcoal hover:text-primary hover:bg-primary/10 transition-colors"
                          >
                            <ArrowSquareOut size={14} />
                          </a>
                        ) : (
                          <span className="text-stone">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
