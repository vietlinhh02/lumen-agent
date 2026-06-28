"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { List } from "@phosphor-icons/react";
import { extractText, normalizeMarkdownForDisplay } from "@/lib/markdown";
import type { TocEntry, ParsedSection } from "@/lib/markdown";
import type { ReportDetailResponse, ReferenceResponse } from "@/lib/types";
import { CitationPdfModal } from "./CitationPdfModal";

/** Strip brackets/whitespace so "[1]" and "1" (or "[I-1]"/"I-1") compare equal. */
function normLabel(s: string): string {
  return s.replace(/[[\]\s]/g, "");
}

interface Props {
  detail: ReportDetailResponse;
  filteredSections: ParsedSection[];
  parsedSections: ParsedSection[];
  toc: TocEntry[];
  searchQuery: string;
  activeSection: string | null;
  onSetActiveSection: (id: string | null) => void;
}

export function ReportContent({
  detail,
  filteredSections,
  parsedSections,
  toc,
  searchQuery,
  activeSection,
  onSetActiveSection,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const sectionRefs = useRef<Record<string, HTMLElement>>({});

  // T3 Phase 4: clickable citations. Map normalized label → reference so a
  // [1] superscript in the prose can open that paper's source PDF.
  const refByLabel = useMemo(() => {
    const map = new Map<string, ReferenceResponse>();
    for (const ref of detail.references) {
      map.set(normLabel(ref.citation_label), ref);
    }
    return map;
  }, [detail.references]);

  const [citationPdf, setCitationPdf] = useState<{
    title: string;
    label: string;
    url: string;
  } | null>(null);

  function openCitation(norm: string) {
    const ref = refByLabel.get(norm);
    if (!ref) return;
    if (ref.pdf_path) {
      setCitationPdf({ title: ref.title, label: ref.citation_label, url: ref.pdf_path });
    } else if (ref.url) {
      window.open(ref.url, "_blank", "noopener,noreferrer");
    }
  }

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) onSetActiveSection(entry.target.id);
        }
      },
      { root: container, rootMargin: "-80px 0px -60% 0px", threshold: 0 },
    );
    const sections = container.querySelectorAll("[data-section]");
    sections.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [detail, onSetActiveSection]);

  function scrollToSection(id: string) {
    const el = sectionRefs.current[id];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      onSetActiveSection(id);
    }
  }

  return (
    <div className="flex-1 overflow-hidden flex">
      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-hide">
        <div className="px-4 sm:px-6 lg:px-10 py-5 sm:py-8 space-y-4 sm:space-y-6">
          <AuditPills audit={detail.citation_audit} />

          {detail.references.length > 0 && (
            <details className="group">
              <summary className="font-ui text-[12px] font-semibold text-ash uppercase tracking-wide cursor-pointer hover:text-ink transition-colors list-none flex items-center gap-2">
                <List size={14} />
                References ({detail.references.length})
                <span className="text-[10px] text-ash group-open:rotate-90 transition-transform">▸</span>
              </summary>
              <div className="mt-3 grid gap-1.5">
                {detail.references.map((ref) => (
                  <div
                    key={ref.project_paper_id}
                    className="rounded-[6px] bg-surface-card px-3 py-2"
                    style={{ border: "1px solid var(--hairline)" }}
                  >
                    <p className="font-ui text-[13px] text-ink">
                      <span className="font-semibold text-primary mr-1">{ref.citation_label}</span>
                      {ref.title}
                    </p>
                    <p className="font-ui text-[11px] text-charcoal mt-0.5">
                      {ref.authors.slice(0, 3).join(", ")}
                      {ref.authors.length > 3 && " et al."}
                      {ref.year && ` (${ref.year})`}
                    </p>
                  </div>
                ))}
              </div>
            </details>
          )}

          {searchQuery.trim() && (
            <p className="font-ui text-[12px] text-ash">
              {filteredSections.length} of {parsedSections.length} sections match &quot;{searchQuery}&quot;
            </p>
          )}

          {filteredSections.map((section) => (
            <div
              key={section.id}
              id={section.id}
              data-section
              ref={(el) => {
                if (el) sectionRefs.current[section.id] = el;
              }}
              className={`rounded-[8px] sm:rounded-[12px] bg-surface-card transition-all ${
                activeSection === section.id
                  ? "ring-2 ring-primary/20 shadow-sm"
                  : "hover:shadow-sm"
              }`}
              style={{ border: "1px solid var(--hairline)", scrollMarginTop: "80px" }}
            >
              {section.heading && (
                <div
                  className="px-4 sm:px-6 lg:px-8 pt-4 sm:pt-6 pb-2 sm:pb-3"
                  style={{ borderBottom: "1px solid var(--hairline)" }}
                >
                  <h2 className="font-display text-[18px] sm:text-[20px] font-bold text-ink tracking-tight">
                    {section.heading}
                  </h2>
                </div>
              )}
              <div
                className={`prose max-w-none px-4 sm:px-6 lg:px-8 ${section.heading ? "py-5" : "py-6"}
                  prose-p:text-ink prose-p:leading-[1.85] prose-p:text-[14px] sm:prose-p:text-[15px] prose-p:mb-4
                  prose-strong:text-ink prose-strong:font-semibold
                  prose-em:text-charcoal
                  prose-li:text-ink prose-li:text-[14px] sm:prose-li:text-[15px] prose-li:leading-[1.8] prose-li:mb-1
                  prose-ol:my-4 prose-ul:my-4
                  prose-a:text-primary prose-a:no-underline hover:prose-a:underline prose-a:font-medium
                  prose-blockquote:border-l-[3px] prose-blockquote:border-l-primary prose-blockquote:text-charcoal prose-blockquote:italic prose-blockquote:pl-5 prose-blockquote:my-4
                  prose-hr:my-6 prose-hr:border-[var(--hairline)]
                  prose-table:text-[14px] prose-table:my-4
                  prose-th:text-left prose-th:font-semibold prose-th:text-ink prose-th:pb-2 prose-th:border-b prose-th:border-[var(--hairline)]
                  prose-td:py-2 prose-td:border-b prose-td:border-[var(--hairline)]`}
              >
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeRaw]}
                  components={{
                    sup: ({ children }) => {
                      const text = extractText(children);
                      const label = text.replace(/[\[\]]/g, "");
                      const norm = normLabel(text);
                      const ref = refByLabel.get(norm);
                      const clickable = !!(ref && (ref.pdf_path || ref.url));
                      if (!clickable) {
                        return (
                          <sup
                            className="inline-flex items-center justify-center min-w-[20px] h-[18px] px-1 rounded-full bg-primary/10 text-primary text-[10px] font-bold leading-none mx-0.5 cursor-default"
                            style={{ verticalAlign: "super" }}
                          >
                            {label}
                          </sup>
                        );
                      }
                      return (
                        <sup
                          role="button"
                          tabIndex={0}
                          onClick={() => openCitation(norm)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              openCitation(norm);
                            }
                          }}
                          title={ref?.pdf_path ? "Open source PDF" : "Open source link"}
                          className="focus-ring inline-flex items-center justify-center min-w-[20px] h-[18px] px-1 rounded-full bg-primary/10 text-primary text-[10px] font-bold leading-none mx-0.5 cursor-pointer hover:bg-primary/25 transition-colors"
                          style={{ verticalAlign: "super" }}
                        >
                          {label}
                        </sup>
                      );
                    },
                    blockquote: ({ children }) => (
                      <div className="my-3 border-l-[3px] border-primary/40 pl-4">
                        <div className="text-[14px] leading-[1.75] text-charcoal min-w-0">{children}</div>
                      </div>
                    ),
                    hr: () => (
                      <div className="my-5">
                        <div className="h-px bg-[var(--hairline)]" />
                      </div>
                    ),
                    table: ({ children }) => (
                      <div className="overflow-x-auto my-6">
                        <table className="w-full text-left border-collapse min-w-[600px]">{children}</table>
                      </div>
                    ),
                    th: ({ children }) => (
                      <th className="font-semibold text-ink pb-2 px-3 border-b border-[var(--hairline)] bg-surface-bone/30">
                        {children}
                      </th>
                    ),
                    td: ({ children }) => (
                      <td className="py-2 px-3 border-b border-[var(--hairline)] align-top">
                        {children}
                      </td>
                    ),
                    strong: ({ children }) => {
                      const text = extractText(children);
                      const isLabel = /^(Key synthesis|Key finding|Research gap|Limitation):?$/i.test(text.trim());
                      if (isLabel) {
                        return <strong className="italic font-semibold text-primary/70">{children}</strong>;
                      }
                      return <strong className="font-semibold text-ink">{children}</strong>;
                    },
                    em: ({ children }) => {
                      const text = typeof children === "string" ? children : "";
                      if (text.length > 30) {
                        return <span className="text-ink font-medium not-italic">{children}</span>;
                      }
                      return <em className="text-charcoal">{children}</em>;
                    },
                  }}
                >
                  {normalizeMarkdownForDisplay(section.content)}
                </ReactMarkdown>
              </div>
            </div>
          ))}
        </div>
      </div>

      {toc.length > 2 && (
        <TocSidebar toc={toc} activeId={activeSection} onSelect={scrollToSection} />
      )}

      {citationPdf && (
        <CitationPdfModal
          open
          onClose={() => setCitationPdf(null)}
          title={citationPdf.title}
          citationLabel={citationPdf.label}
          pdfUrl={citationPdf.url}
        />
      )}
    </div>
  );
}

function AuditPills({ audit }: { audit: { total_citations: number; valid_citations: number; invalid_citations: number } }) {
  return (
    <div className="flex items-center gap-3 sm:gap-5 flex-wrap">
      <AuditPill label="Citations" value={audit.total_citations} />
      <AuditPill label="Valid" value={audit.valid_citations} color="text-green-700" />
      {audit.invalid_citations > 0 && (
        <AuditPill label="Invalid" value={audit.invalid_citations} color="text-red-700" />
      )}
    </div>
  );
}

function AuditPill({ label, value, color = "text-ink" }: { label: string; value: number; color?: string }) {
  return (
    <span className="font-ui inline-flex items-center gap-1.5 text-[11px] text-charcoal">
      <span className={`font-display text-[15px] font-bold ${color}`}>{value}</span>
      {label}
    </span>
  );
}

function TocSidebar({
  toc,
  activeId,
  onSelect,
}: {
  toc: TocEntry[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div
      className="hidden lg:block w-[220px] shrink-0 bg-surface-card/50 overflow-y-auto scrollbar-hide"
      style={{ borderLeft: "1px solid var(--hairline)" }}
    >
      <div className="px-3 py-4 sticky top-0">
        <p className="font-ui text-[10px] font-semibold text-ash uppercase tracking-wide mb-2 px-1">
          Contents
        </p>
        <nav className="space-y-0.5">
          {toc.map((entry) => (
            <button
              key={entry.id}
              onClick={() => onSelect(entry.id)}
              className={`block w-full text-left font-ui text-[12px] px-2 py-1 rounded transition-colors ${
                entry.level === 3 ? "pl-5" : ""
              } ${
                activeId === entry.id
                  ? "text-primary font-semibold bg-primary/5"
                  : "text-charcoal hover:text-ink hover:bg-surface-bone"
              }`}
            >
              {entry.text}
            </button>
          ))}
        </nav>
      </div>
    </div>
  );
}
