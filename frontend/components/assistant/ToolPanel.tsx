/**
 * ToolPanel - Right panel showing tool artifacts and previews.
 * 
 * Sub-views:
 * - PaperListView: List of papers from search/save
 * - MatrixPreview: Literature matrix preview
 * - GapListView: Research gaps list
 * - ReportPreview: Report preview
 * - EvidenceChunksView: Evidence chunks from retrieval
 */

"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAssistantStore } from "@/lib/stores/assistant-store";
import { useAssistantSessions } from "@/lib/stores/assistant-store";
import { MathText } from "@/components/search/MathText";
import {
  X,
  FileText,
  Table,
  Lightbulb,
  PencilLine,
  MagnifyingGlass,
  ArrowSquareOut,
  Folder,
} from "@phosphor-icons/react";

interface ToolPanelProps {
  onClose: () => void;
}

export function ToolPanel({ onClose }: ToolPanelProps) {
  const currentArtifact = useAssistantStore((s) => s.currentToolArtifact);
  const currentSession = useAssistantStore((s) => s.currentSession);
  const [activeView, setActiveView] = useState<string | null>(
    currentArtifact?.type ?? null
  );

  const projectId = currentSession?.project_id ?? currentArtifact?.projectId;

  // Quick switch views
  const renderViewSelector = () => {
    if (!currentArtifact) return null;
    
    return (
      <div className="flex flex-wrap gap-1 p-2 border-b" style={{ borderColor: "var(--hairline)" }}>
        <button
          onClick={() => setActiveView(currentArtifact.type)}
          className="flex items-center gap-1.5 rounded-lg bg-primary/10 px-2.5 py-1.5 font-ui text-xs font-medium text-primary"
        >
          {getArtifactIcon(currentArtifact.type)}
          {currentArtifact.title}
        </button>
      </div>
    );
  };

  // Render content based on artifact type
  const renderContent = () => {
    if (!currentArtifact) {
      return (
        <div className="flex flex-col items-center justify-center h-full text-center p-6">
          <MagnifyingGlass size={40} className="text-charcoal/30 mb-3" />
          <p className="font-ui text-sm text-charcoal">
            Tool results will appear here
          </p>
          <p className="font-ui text-xs text-charcoal/60 mt-1">
            As the assistant runs tools, their results will show in this panel
          </p>
        </div>
      );
    }

    switch (currentArtifact.type) {
      case "papers":
        return <PaperListView data={currentArtifact.data} projectId={projectId} />;
      case "matrix":
        return <MatrixPreview data={currentArtifact.data} projectId={projectId} />;
      case "gaps":
        return <GapListView data={currentArtifact.data} projectId={projectId} />;
      case "conflicts":
        return <ConflictListView data={currentArtifact.data} projectId={projectId} />;
      case "report":
        return (
          <ReportPreview
            data={currentArtifact.data}
            projectId={projectId}
            reportId={currentArtifact.reportId}
          />
        );
      case "evidence":
        return <EvidenceChunksView data={currentArtifact.data} />;
      case "project":
        return <ProjectListView data={currentArtifact.data} />;
      default:
        return (
          <div className="p-4">
            <pre className="font-mono text-xs text-charcoal overflow-auto">
              {JSON.stringify(currentArtifact.data, null, 2)}
            </pre>
          </div>
        );
    }
  };

  return (
    <div className="flex h-full flex-col bg-canvas">
      {/* Header */}
      <div
        className="flex items-center justify-between h-14 px-4 border-b"
        style={{ borderColor: "var(--hairline)" }}
      >
        <span className="font-ui font-medium text-sm text-ink">
          Tool Results
        </span>
        <button
          onClick={onClose}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-charcoal hover:text-ink hover:bg-surface-bone transition-colors"
        >
          <X size={18} />
        </button>
      </div>

      {/* View selector */}
      {renderViewSelector()}

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {renderContent()}
      </div>
    </div>
  );
}

/* ── Sub-views ─────────────────────────────────────────────────────────────── */

function getArtifactIcon(type: string | null) {
  switch (type) {
    case "papers":
      return <FileText size={12} />;
    case "matrix":
      return <Table size={12} />;
    case "gaps":
      return <Lightbulb size={12} />;
    case "report":
      return <PencilLine size={12} />;
    case "project":
      return <Folder size={12} />;
    default:
      return null;
  }
}

function PaperListView({
  data,
  projectId,
}: {
  data: unknown;
  projectId: string | null | undefined;
}) {
  const papers = Array.isArray(data) ? data : [];
  const router = useRouter();

  return (
    <div className="p-2 space-y-2">
      {papers.length === 0 ? (
        <p className="font-ui text-xs text-charcoal text-center py-4">No papers</p>
      ) : (
        papers.slice(0, 10).map((paper: Record<string, unknown>, i: number) => (
          <div
            key={i}
            className="rounded-lg border border-charcoal/10 bg-surface-card p-3 hover:border-charcoal/20 transition-colors"
          >
            <p className="font-ui text-sm font-medium text-ink line-clamp-2">
              <MathText text={(paper.title as string) || "Untitled"} />
            </p>
            {Array.isArray(paper.authors) && paper.authors.length > 0 && (
              <p className="font-ui text-xs text-charcoal mt-1 line-clamp-1">
                {((paper.authors as Array<{ name: string }>) ?? [])
                  .slice(0, 3)
                  .map((a) => a.name)
                  .join(", ")}
                {(paper.authors as Array<unknown>)?.length > 3 && " et al."}
              </p>
            )}
            <div className="flex items-center gap-2 mt-2">
              {typeof paper.year === "number" && (
                <span className="font-ui text-[10px] text-charcoal/60">
                  {paper.year}
                </span>
              )}
              {typeof paper.citation_count === "number" && (
                <span className="font-ui text-[10px] text-charcoal/60">
                  {paper.citation_count} citations
                </span>
              )}
            </div>
          </div>
        ))
      )}
      {papers.length > 10 && (
        <p className="font-ui text-xs text-charcoal text-center py-2">
          +{papers.length - 10} more papers
        </p>
      )}
      {projectId && (
        <a
          href={`/projects/${projectId}/papers`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-1.5 w-full rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 font-ui text-xs font-medium text-primary hover:bg-primary/10 transition-colors"
        >
          <ArrowSquareOut size={12} />
          View all in Papers
        </a>
      )}
    </div>
  );
}

function MatrixPreview({
  data,
  projectId,
}: {
  data: unknown;
  projectId: string | null | undefined;
}) {
  const rows = Array.isArray(data) ? data : [];

  return (
    <div className="p-2">
      <div className="rounded-lg border border-charcoal/10 overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-surface-bone">
            <tr>
              <th className="px-2 py-1.5 text-left font-medium text-charcoal">Paper</th>
              <th className="px-2 py-1.5 text-left font-medium text-charcoal">Method</th>
            </tr>
          </thead>
          <tbody>
            {(rows as Array<Record<string, unknown>>).slice(0, 5).map((row, i) => (
              <tr key={i} className="border-t border-charcoal/10">
                <td className="px-2 py-1.5 text-ink truncate max-w-[120px]">
                  {(row.paper_title as string)?.slice(0, 40) || "—"}
                </td>
                <td className="px-2 py-1.5 text-charcoal truncate max-w-[100px]">
                  {(row.method as string)?.slice(0, 25) || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > 5 && (
        <p className="font-ui text-xs text-charcoal text-center py-2">
          +{rows.length - 5} more rows
        </p>
      )}
      {projectId && (
        <a
          href={`/projects/${projectId}/matrix`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-1.5 w-full rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 font-ui text-xs font-medium text-primary hover:bg-primary/10 transition-colors mt-2"
        >
          <ArrowSquareOut size={12} />
          Open full matrix
        </a>
      )}
    </div>
  );
}

function GapListView({
  data,
  projectId,
}: {
  data: unknown;
  projectId: string | null | undefined;
}) {
  const gaps = Array.isArray(data) ? data : [];

  return (
    <div className="p-2 space-y-2">
      {gaps.length === 0 ? (
        <p className="font-ui text-xs text-charcoal text-center py-4">No gaps detected</p>
      ) : (
        (gaps as Array<Record<string, unknown>>).slice(0, 5).map((gap, i) => (
          <div
            key={i}
            className="rounded-lg border border-charcoal/10 bg-surface-card p-3"
          >
            <p className="font-ui text-sm font-medium text-ink">
              {(gap.title as string) || "Untitled Gap"}
            </p>
            <p className="font-ui text-xs text-charcoal mt-1 line-clamp-2">
              {(gap.description as string)?.slice(0, 100)}...
            </p>
            {typeof gap.confidence === "string" && (
              <span className="inline-flex items-center rounded bg-primary/10 px-1.5 py-0.5 font-ui text-[10px] text-primary mt-2">
                {gap.confidence} confidence
              </span>
            )}
          </div>
        ))
      )}
      {gaps.length > 5 && (
        <p className="font-ui text-xs text-charcoal text-center py-2">
          +{gaps.length - 5} more gaps
        </p>
      )}
      {projectId && (
        <a
          href={`/projects/${projectId}/gaps`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-1.5 w-full rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 font-ui text-xs font-medium text-primary hover:bg-primary/10 transition-colors"
        >
          <ArrowSquareOut size={12} />
          View all gaps
        </a>
      )}
    </div>
  );
}

function ConflictListView({
  data,
  projectId,
}: {
  data: unknown;
  projectId: string | null | undefined;
}) {
  const conflicts = Array.isArray(data) ? data : [];

  return (
    <div className="p-2 space-y-2">
      {conflicts.length === 0 ? (
        <p className="font-ui text-xs text-charcoal text-center py-4">No conflicts found</p>
      ) : (
        (conflicts as Array<Record<string, unknown>>).slice(0, 5).map((conflict, i) => (
          <div
            key={i}
            className="rounded-lg border border-amber-200 bg-amber-50 p-3"
          >
            <p className="font-ui text-sm font-medium text-amber-800">
              {(conflict.title as string) || "Conflicting Finding"}
            </p>
            <p className="font-ui text-xs text-amber-700 mt-1 line-clamp-2">
              {(conflict.description as string)?.slice(0, 100)}...
            </p>
          </div>
        ))
      )}
    </div>
  );
}

function ReportPreview({
  data,
  projectId,
  reportId,
}: {
  data: unknown;
  projectId: string | null | undefined;
  reportId: string | null | undefined;
}) {
  const report = data as Record<string, unknown>;

  return (
    <div className="p-3 space-y-3">
      {typeof report.title === "string" && (
        <h3 className="font-ui text-sm font-semibold text-ink">
          {report.title}
        </h3>
      )}

      {typeof report.validation_status === "string" && (
        <div className="flex items-center gap-2">
          <span
            className={`rounded px-2 py-0.5 font-ui text-xs font-medium ${
              report.validation_status === "valid"
                ? "bg-green-100 text-green-700"
                : "bg-amber-100 text-amber-700"
            }`}
          >
            {report.validation_status}
          </span>
          {typeof report.citation_audit === "object" && report.citation_audit !== null && (
            <span className="font-ui text-xs text-charcoal">
              {(report.citation_audit as Record<string, number>).total_citations} citations
            </span>
          )}
        </div>
      )}

      {typeof report.content_markdown === "string" && (
        <div className="rounded-lg border border-charcoal/10 bg-surface-card p-3 max-h-48 overflow-y-auto">
          <pre className="font-ui text-xs text-ink whitespace-pre-wrap">
            {report.content_markdown.slice(0, 500)}...
          </pre>
        </div>
      )}

      {projectId && reportId && (
        <a
          href={`/projects/${projectId}/reports`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-1.5 w-full rounded-lg bg-primary px-3 py-2 font-ui text-xs font-medium text-white hover:bg-primary/90 transition-colors"
        >
          <ArrowSquareOut size={12} />
          Open full report
        </a>
      )}
    </div>
  );
}

function EvidenceChunksView({ data }: { data: unknown }) {
  const chunks = Array.isArray(data) ? data : [];

  return (
    <div className="p-2 space-y-2">
      {chunks.length === 0 ? (
        <p className="font-ui text-xs text-charcoal text-center py-4">No evidence found</p>
      ) : (
        (chunks as Array<Record<string, unknown>>).slice(0, 5).map((chunk, i) => (
          <div
            key={i}
            className="rounded-lg border border-charcoal/10 bg-surface-card p-3"
          >
            <p className="font-ui text-xs text-ink line-clamp-3">
              {(chunk.chunk_text as string)?.slice(0, 150)}...
            </p>
            <div className="flex items-center justify-between mt-2">
              {typeof chunk.title === "string" && (
                <span className="font-ui text-[10px] text-charcoal truncate max-w-[150px]">
                  {chunk.title}
                </span>
              )}
              {typeof chunk.score === "number" && (
                <span className="font-ui text-[10px] text-primary">
                  Score: {chunk.score.toFixed(2)}
                </span>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

function ProjectListView({ data }: { data: unknown }) {
  const projects = Array.isArray(data) ? data : [];

  return (
    <div className="p-2 space-y-2">
      {projects.length === 0 ? (
        <p className="font-ui text-xs text-charcoal text-center py-4">No projects</p>
      ) : (
        (projects as Array<Record<string, unknown>>).slice(0, 10).map((project, i) => (
          <div
            key={i}
            className="rounded-lg border border-charcoal/10 bg-surface-card p-3"
          >
            <p className="font-ui text-sm font-medium text-ink">
              {String(project.title || project.name || "")}
            </p>
            {typeof project.topic === "string" && (
              <p className="font-ui text-xs text-charcoal mt-1 truncate">
                {project.topic}
              </p>
            )}
          </div>
        ))
      )}
    </div>
  );
}
