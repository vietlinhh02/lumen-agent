"use client";

import { useRouter } from "next/navigation";
import { FileText, MagnifyingGlass, ArrowSquareOut, SortAscending, SortDescending } from "@phosphor-icons/react";
import { Dropdown } from "@/components/ui/Dropdown";

export interface PaperItem {
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

export type SortKey = "title" | "year" | "citations" | "saved_at";

interface FiltersProps {
  search: string;
  onSearchChange: (v: string) => void;
  projectFilter: string;
  onProjectFilterChange: (v: string) => void;
  projects: Array<{ id: string; title: string }>;
}

export function PapersFilters({ search, onSearchChange, projectFilter, onProjectFilterChange, projects }: FiltersProps) {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      <div className="relative flex-1 min-w-[200px] max-w-sm">
        <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ash" />
        <input
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search title, author, venue…"
          className="focus-ring h-[38px] w-full rounded-full bg-surface-card pl-9 pr-4 font-ui text-sm text-ink outline-none"
          style={{ border: "1px solid var(--hairline)" }}
        />
      </div>
      <div className="min-w-[200px]">
        <Dropdown
          options={[
            { value: "", label: "All projects" },
            ...projects.map((p) => ({ value: p.id, label: p.title })),
          ]}
          value={projectFilter}
          onChange={onProjectFilterChange}
          placeholder="All projects"
        />
      </div>
    </div>
  );
}

interface TableProps {
  papers: PaperItem[];
  sortKey: SortKey;
  sortAsc: boolean;
  onToggleSort: (key: SortKey) => void;
  onNavigate: (path: string) => void;
}

export function PapersTable({ papers, sortKey, sortAsc, onToggleSort, onNavigate }: TableProps) {
  function SortIcon({ column }: { column: SortKey }) {
    if (sortKey !== column) return null;
    return sortAsc ? <SortAscending size={12} className="text-primary" /> : <SortDescending size={12} className="text-primary" />;
  }

  return (
    <div className="rounded-[12px] bg-surface-card overflow-hidden" style={{ border: "1px solid var(--hairline)" }}>
      {papers.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <FileText size={36} className="text-stone mb-3" />
          <p className="font-ui text-sm font-medium text-ink">No papers match your filters</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-surface-bone/50">
                <th onClick={() => onToggleSort("title")} className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-5 py-3 cursor-pointer hover:text-ink transition-colors w-[40%]">
                  <span className="inline-flex items-center gap-1">Title <SortIcon column="title" /></span>
                </th>
                <th className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-4 py-3 w-[20%]">Authors</th>
                <th onClick={() => onToggleSort("year")} className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-4 py-3 cursor-pointer hover:text-ink transition-colors">
                  <span className="inline-flex items-center gap-1">Year <SortIcon column="year" /></span>
                </th>
                <th className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-4 py-3">Venue</th>
                <th onClick={() => onToggleSort("citations")} className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-right px-4 py-3 cursor-pointer hover:text-ink transition-colors">
                  <span className="inline-flex items-center gap-1 justify-end">Cited <SortIcon column="citations" /></span>
                </th>
                <th className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-4 py-3">Project</th>
                <th className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-center px-4 py-3 w-[60px]">Link</th>
              </tr>
            </thead>
            <tbody>
              {papers.map((p) => (
                <tr key={p.id} className="hover:bg-surface-bone/30 transition-colors" style={{ borderTop: "1px solid var(--hairline)" }}>
                  <td className="px-5 py-3"><p className="font-ui text-[13px] font-medium text-ink line-clamp-2">{p.title}</p></td>
                  <td className="px-4 py-3"><p className="font-ui text-[12px] text-charcoal line-clamp-2">{p.authors.slice(0, 3).join(", ")}{p.authors.length > 3 && " et al."}</p></td>
                  <td className="px-4 py-3 font-ui text-[13px] text-ink">{p.year ?? "—"}</td>
                  <td className="px-4 py-3 font-ui text-[12px] text-charcoal line-clamp-1 max-w-[160px]">{p.venue ?? "—"}</td>
                  <td className="px-4 py-3 font-ui text-[13px] text-ink text-right tabular-nums">{p.citation_count ?? "—"}</td>
                  <td className="px-4 py-3">
                    <button onClick={() => onNavigate(`/projects/${p.project_id}`)} className="font-ui text-[12px] text-primary hover:underline truncate max-w-[140px] block">
                      {p.project_title}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-center">
                    {p.url ? (
                      <a href={p.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center justify-center h-[28px] w-[28px] rounded-[6px] text-charcoal hover:text-primary hover:bg-primary/10 transition-colors">
                        <ArrowSquareOut size={14} />
                      </a>
                    ) : <span className="text-stone">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
