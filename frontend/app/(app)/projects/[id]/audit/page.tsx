"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ClipboardText,
  DownloadSimple,
  FlowArrow,
  MagnifyingGlass,
  FileText,
  Warning,
  CheckCircle,
  CircleNotch,
  Sparkle,
  ChartBar,
  ChartLineUp,
  Buildings,
  Gauge,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "@/lib/stores/auth-store";
import { useProjectsStore } from "@/lib/stores/projects-store";
import { useReportsStore } from "@/lib/stores/reports-store";
import { formatDate } from "@/lib/utils";
import type { PrismaAuditResponse } from "@/lib/types";

export default function ProjectAuditPage() {
  const params = useParams<{ id: string }>();
  const projectId = params?.id ?? "";

  const project = useProjectsStore((s) => s.currentProject);
  const loadingProject = useProjectsStore((s) => s.loadingProject);
  const fetchProject = useProjectsStore((s) => s.fetchProject);
  const token = useAuthStore((s) => s.token);
  const reports = useReportsStore((s) => s.reports);

  const [audit, setAudit] = useState<PrismaAuditResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState<"markdown" | "csv" | null>(null);

  const loadAudit = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const data = await apiFetch<PrismaAuditResponse>(`/projects/${projectId}/audit`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setAudit(data);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load audit");
      setAudit(null);
    } finally {
      setLoading(false);
    }
  }, [projectId, token]);

  useEffect(() => {
    // Data-fetch effect — `loadAudit` calls setState inside the async chain
    // to reflect loading + result. This is the documented Next.js pattern
    // for client components that fetch on mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadAudit();
  }, [loadAudit]);

  useEffect(() => {
    if (projectId) void fetchProject(projectId);
  }, [projectId, fetchProject]);

  async function exportAudit(fmt: "markdown" | "csv") {
    if (!projectId) return;
    setExporting(fmt);
    try {
      const res = await fetch(
        `/api/projects/${projectId}/audit/export?fmt=${fmt}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const safe = (audit?.project_title ?? "project").replace(/[^a-z0-9]+/gi, "_");
      a.download = `prisma_audit_${safe}.${fmt === "csv" ? "csv" : "md"}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(`Exported ${fmt.toUpperCase()}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(null);
    }
  }

  if (loadingProject && !project) {
    return (
      <div className="w-full animate-pulse">
        <div className="h-7 w-48 rounded bg-surface-bone" />
        <div className="mt-2 h-4 w-[420px] max-w-full rounded bg-surface-bone" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="py-16 text-center">
        <p className="font-ui text-sm font-semibold text-charcoal">Project not loaded</p>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-[22px] font-bold leading-[1.0] text-ink">
            PRISMA Audit
          </h2>
          <p className="mt-1 max-w-[620px] font-ui text-[12px] leading-[1.5] text-charcoal">
            A defensible summary of the search, screening, full-text retrieval, and
            exclusion decisions made for this project. Export the artifact as Markdown
            for paper appendices or CSV for downstream analysis.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => exportAudit("markdown")}
            disabled={!audit || exporting !== null}
            className="focus-ring inline-flex h-[36px] items-center gap-1.5 rounded-full bg-ink px-4 font-ui text-[13px] font-semibold text-on-dark transition-colors hover:bg-charcoal disabled:cursor-not-allowed disabled:opacity-50"
          >
            {exporting === "markdown" ? (
              <CircleNotch size={14} weight="bold" className="animate-spin" />
            ) : (
              <DownloadSimple size={14} weight="bold" />
            )}
            Export MD
          </button>
          <button
            type="button"
            onClick={() => exportAudit("csv")}
            disabled={!audit || exporting !== null}
            className="focus-ring inline-flex h-[36px] items-center gap-1.5 rounded-full bg-surface-bone px-4 font-ui text-[13px] font-semibold text-ink transition-colors hover:bg-hairline disabled:cursor-not-allowed disabled:opacity-50"
          >
            {exporting === "csv" ? (
              <CircleNotch size={14} weight="bold" className="animate-spin" />
            ) : (
              <DownloadSimple size={14} weight="bold" />
            )}
            Export CSV
          </button>
        </div>
      </header>

      {loading ? (
        <div className="flex items-center gap-2 font-ui text-[12px] text-charcoal">
          <CircleNotch size={14} className="animate-spin" weight="bold" />
          Computing audit…
        </div>
      ) : !audit ? (
        <div
          className="rounded-[14px] bg-surface-card p-4 font-ui text-[12px] text-charcoal"
          style={{ border: "1px solid var(--hairline)" }}
        >
          No audit data available.
        </div>
      ) : (
        <PrismaFlow
          audit={audit}
          reportsCount={reports.length}
          projectId={projectId}
        />
      )}
    </div>
  );
}

function PrismaFlow({
  audit,
  reportsCount,
  projectId,
}: {
  audit: PrismaAuditResponse;
  reportsCount: number;
  projectId: string;
}) {
  const afterDedupe = Math.max(audit.records_identified - audit.duplicates_removed, 0);
  const afterScreening = Math.max(afterDedupe - audit.records_excluded_screening, 0);
  const afterFullText = Math.max(afterScreening - audit.full_text_not_retrieved, 0);
  // The final "Included" chip shows the actual `records_included` (status='saved')
  // rather than the cascade result, because not every paper that passes screening
  // is necessarily saved by the user. Any gap between `afterFullText` and the
  // saved count represents papers that passed screening but were never saved —
  // a real and defensible workflow signal.
  const includedActual = audit.records_included;
  const notSavedAfterScreening = Math.max(afterFullText - includedActual, 0);

  const stages: Array<{
    key: string;
    title: string;
    icon: React.ComponentType<{ size?: number; weight?: "regular" | "fill" | "bold" | "duotone"; className?: string }>;
    color: string;
    rows: Array<{ label: string; value: number; emphasis?: boolean }>;
  }> = [
    {
      key: "identification",
      title: "Identification",
      icon: MagnifyingGlass,
      color: "bg-sky-50 text-sky-600",
      rows: [
        ...audit.identified_by_source.map((s) => ({ label: s.source, value: s.count })),
        { label: "Total identified", value: audit.records_identified, emphasis: true },
      ],
    },
    {
      key: "screening",
      title: "Screening",
      icon: FlowArrow,
      color: "bg-amber-50 text-amber-600",
      rows: [
        { label: "Duplicates removed", value: audit.duplicates_removed },
        { label: "Records screened", value: audit.records_screened },
        { label: "Excluded at screening", value: audit.records_excluded_screening },
      ],
    },
    {
      key: "eligibility",
      title: "Eligibility",
      icon: FileText,
      color: "bg-violet-50 text-violet-600",
      rows: [
        { label: "Full-text assessed", value: audit.full_text_assessed },
        { label: "Full-text not retrieved", value: audit.full_text_not_retrieved },
      ],
    },
    {
      key: "included",
      title: "Included",
      icon: CheckCircle,
      color: "bg-emerald-50 text-emerald-600",
      rows: [
        { label: "Studies included", value: audit.records_included, emphasis: true },
        { label: "Pending review", value: audit.records_uncertain },
        { label: "Excluded after full-text", value: audit.records_excluded_final },
      ],
    },
  ];

  const empty = audit.records_identified === 0 && audit.records_included === 0;

  return (
    <div className="space-y-4">
      {audit.protocol_notes && (
        <div
          className="rounded-[14px] bg-surface-card p-3.5"
          style={{ border: "1px solid var(--hairline)" }}
        >
          <p className="font-ui mb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-ash">
            <ClipboardText size={11} className="mr-1 inline" weight="bold" />
            Protocol notes
          </p>
          <p className="font-ui whitespace-pre-wrap text-[12px] leading-[1.55] text-ink">
            {audit.protocol_notes}
          </p>
        </div>
      )}

      {empty ? (
        <EmptyState />
      ) : (
        <>
          <FlowSummary
            identified={audit.records_identified}
            afterDedupe={afterDedupe}
            afterScreening={afterScreening}
            afterFullText={afterFullText}
            afterFinal={includedActual}
            notSavedAfterScreening={notSavedAfterScreening}
          />

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {stages.map((stage) => (
              <FlowStage key={stage.key} stage={stage} />
            ))}
          </div>

          {audit.exclusion_reasons.length > 0 && (
            <section
              className="rounded-[14px] bg-surface-card p-4"
              style={{ border: "1px solid var(--hairline)" }}
            >
              <h3 className="font-ui mb-2 text-[11px] font-semibold uppercase tracking-wider text-ash">
                <Warning size={12} className="mr-1 inline" weight="fill" />
                Exclusion reasons
              </h3>
              <ul className="grid gap-1.5 sm:grid-cols-2">
                {audit.exclusion_reasons.map((r) => (
                  <li
                    key={r.reason}
                    className="flex items-center justify-between rounded-[8px] bg-surface-bone px-3 py-1.5 font-ui text-[12px]"
                  >
                    <span className="text-ink">{r.label}</span>
                    <span className="font-semibold text-rose-600">{r.count}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <Synthesis audit={audit} reportsCount={reportsCount} />

          {(audit.year_distribution.length > 0 || audit.top_venues.length > 0) && (
            <Coverage audit={audit} />
          )}

          {audit.recent_search_sessions.length > 0 && (
            <SearchHistory sessions={audit.recent_search_sessions} />
          )}

          {audit.inclusion_timeline.length > 0 && (
            <InclusionTimeline points={audit.inclusion_timeline} />
          )}

          <QualityMetrics metrics={audit.quality_metrics} />

          {audit.extraction_schema && (
            <SchemaCoverage
              schema={audit.extraction_schema}
              projectId={projectId}
            />
          )}
        </>
      )}

      <p className="font-ui text-[11px] text-ash">
        Generated {formatDate(audit.generated_at)}
      </p>
    </div>
  );
}

function FlowSummary({
  identified,
  afterDedupe,
  afterScreening,
  afterFullText,
  afterFinal,
  notSavedAfterScreening,
}: {
  identified: number;
  afterDedupe: number;
  afterScreening: number;
  afterFullText: number;
  afterFinal: number;
  notSavedAfterScreening: number;
}) {
  return (
    <section
      className="rounded-[14px] bg-surface-card p-3.5"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <p className="font-ui mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-ash">
        Funnel
      </p>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-ui text-[12px] text-charcoal">
        <FunnelChip label="Identified" value={identified} />
        <Arrow />
        <FunnelChip label="After dedup" value={afterDedupe} />
        <Arrow />
        <FunnelChip label="After screening" value={afterScreening} />
        <Arrow />
        <FunnelChip label="After full-text" value={afterFullText} />
        <Arrow />
        <FunnelChip label="Included" value={afterFinal} emphasis />
      </div>
      {notSavedAfterScreening > 0 && (
        <p className="mt-2 font-ui text-[11px] text-charcoal">
          <span className="font-semibold text-amber-700">
            {notSavedAfterScreening.toLocaleString()}
          </span>{" "}
          record{notSavedAfterScreening === 1 ? "" : "s"} passed screening but were
          not saved to the project. Save them from the Search tab to include them in
          the synthesis.
        </p>
      )}
    </section>
  );
}

function Arrow() {
  return <span className="text-ash">›</span>;
}

function FunnelChip({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: number;
  emphasis?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 ${
        emphasis ? "bg-emerald-50 text-emerald-700" : "bg-surface-bone text-ink"
      }`}
    >
      <span className="text-[10px] uppercase tracking-wider text-ash">{label}</span>
      <span className="font-semibold">{value.toLocaleString()}</span>
    </span>
  );
}

function FlowStage({
  stage,
}: {
  stage: {
    title: string;
    icon: React.ComponentType<{ size?: number; weight?: "regular" | "fill" | "bold" | "duotone"; className?: string }>;
    color: string;
    rows: Array<{ label: string; value: number; emphasis?: boolean }>;
  };
}) {
  const Icon = stage.icon;
  return (
    <section
      className="rounded-[14px] bg-surface-card p-3.5"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <div className="mb-2 flex items-center gap-1.5">
        <span
          className={`flex h-5 w-5 items-center justify-center rounded-[5px] ${stage.color}`}
        >
          <Icon size={11} weight="bold" />
        </span>
        <p className="font-ui text-[10px] font-semibold uppercase tracking-wider text-ash">
          {stage.title}
        </p>
      </div>
      <dl className="space-y-1">
        {stage.rows.map((row, i) => (
          <div
            key={`${stage.title}-${i}`}
            className="flex items-baseline justify-between gap-2"
          >
            <dt className="font-ui text-[11px] text-charcoal line-clamp-1">{row.label}</dt>
            <dd
              className={`font-ui text-[13px] font-semibold ${
                row.emphasis ? "text-primary" : "text-ink"
              }`}
            >
              {row.value.toLocaleString()}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Synthesis({
  audit,
  reportsCount,
}: {
  audit: PrismaAuditResponse;
  reportsCount: number;
}) {
  const items = [
    { label: "Matrix rows", value: audit.matrix_rows },
    { label: "Reports generated", value: Math.max(audit.reports_generated, reportsCount) },
    { label: "Unique papers cited", value: audit.cited_in_reports },
  ];
  return (
    <section
      className="rounded-[14px] bg-surface-card p-4"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <h3 className="font-ui mb-2 text-[11px] font-semibold uppercase tracking-wider text-ash">
        <Sparkle size={12} className="mr-1 inline" weight="fill" />
        Synthesis
      </h3>
      <div className="grid grid-cols-3 gap-3">
        {items.map((it) => (
          <div key={it.label} className="flex flex-col gap-0.5">
            <span className="font-display text-[20px] font-bold leading-none text-ink">
              {it.value.toLocaleString()}
            </span>
            <span className="font-ui text-[10px] uppercase tracking-wider text-ash">
              {it.label}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function EmptyState() {
  return (
    <div
      className="flex flex-col items-center justify-center rounded-[14px] bg-surface-card py-10 text-center"
      style={{ border: "1px dashed var(--hairline)" }}
    >
      <FlowArrow size={28} className="text-stone mb-2" weight="light" />
      <p className="font-ui text-[13px] font-semibold text-ink">No audit data yet</p>
      <p className="mt-1 max-w-[360px] font-ui text-[12px] text-charcoal">
        Run a search and save papers to populate the PRISMA flow. Counts update
        automatically as you progress through screening.
      </p>
    </div>
  );
}

// ── Enrichment sections ─────────────────────────────────────────────────

function SectionCard({
  title,
  subtitle,
  icon: Icon,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  icon: React.ComponentType<{ size?: number; weight?: "regular" | "fill" | "bold" | "duotone" | undefined; className?: string }>;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section
      className="rounded-[14px] bg-surface-card p-4"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <header className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h3 className="font-ui flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ash">
            <Icon size={12} className="inline" weight="fill" />
            {title}
          </h3>
          {subtitle && (
            <p className="mt-0.5 font-ui text-[11px] text-charcoal">
              {subtitle}
            </p>
          )}
        </div>
        {actions}
      </header>
      {children}
    </section>
  );
}

function Coverage({ audit }: { audit: PrismaAuditResponse }) {
  const yearMax = Math.max(
    ...audit.year_distribution.map((b) => b.count),
    1,
  );
  const venueMax = Math.max(
    ...audit.top_venues.map((v) => v.count),
    1,
  );
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {audit.year_distribution.length > 0 && (
        <SectionCard title={`Publication years (${audit.year_min}–${audit.year_max})`} icon={ChartBar}>
          <ul className="space-y-1.5">
            {audit.year_distribution.map((b) => (
              <li key={b.key} className="flex items-center gap-2 font-ui text-[12px]">
                <span className="w-12 shrink-0 text-[11px] text-ash">{b.key}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-bone">
                  <div
                    className="h-full rounded-full bg-primary"
                    style={{ width: `${(b.count / yearMax) * 100}%` }}
                  />
                </div>
                <span className="w-8 text-right text-[11px] font-semibold text-ink">
                  {b.count}
                </span>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}
      {audit.top_venues.length > 0 && (
        <SectionCard title="Top venues" icon={Buildings}>
          <ul className="space-y-1.5">
            {audit.top_venues.map((v) => (
              <li key={v.key} className="flex items-center gap-2 font-ui text-[12px]">
                <span className="min-w-0 flex-1 truncate text-ink">{v.key}</span>
                <div className="h-2 w-20 overflow-hidden rounded-full bg-surface-bone">
                  <div
                    className="h-full rounded-full bg-violet-500"
                    style={{ width: `${(v.count / venueMax) * 100}%` }}
                  />
                </div>
                <span className="w-8 text-right text-[11px] font-semibold text-ink">
                  {v.count}
                </span>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}
    </div>
  );
}

function SearchHistory({
  sessions,
}: {
  sessions: PrismaAuditResponse["recent_search_sessions"];
}) {
  return (
    <SectionCard title="Recent search sessions" icon={ChartLineUp}>
      <div className="overflow-x-auto">
        <table className="w-full font-ui text-[12px]">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wider text-ash">
              <th className="pb-1.5 pr-3 font-semibold">Date</th>
              <th className="pb-1.5 pr-3 font-semibold">Query</th>
              <th className="pb-1.5 pr-3 text-right font-semibold">Results</th>
              <th className="pb-1.5 pr-3 text-right font-semibold">Screened</th>
              <th className="pb-1.5 text-right font-semibold">High</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id} className="border-t border-hairline/60">
                <td className="py-1.5 pr-3 text-[11px] text-ash">
                  {formatDate(s.created_at)}
                </td>
                <td className="max-w-[260px] truncate py-1.5 pr-3 text-ink">
                  {s.user_query || (
                    <span className="italic text-stone">(empty query)</span>
                  )}
                </td>
                <td className="py-1.5 pr-3 text-right font-semibold text-ink">
                  {s.total_results.toLocaleString()}
                </td>
                <td className="py-1.5 pr-3 text-right text-charcoal">
                  {s.screened_count.toLocaleString()}
                </td>
                <td className="py-1.5 text-right font-semibold text-emerald-700">
                  {s.high_score_count.toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

function InclusionTimeline({
  points,
}: {
  points: PrismaAuditResponse["inclusion_timeline"];
}) {
  const max = Math.max(...points.map((p) => p.count), 1);
  return (
    <SectionCard title="Inclusion timeline (last 30 days)" icon={ChartLineUp}>
      <div className="flex h-[88px] items-end gap-[2px]">
        {points.map((p) => {
          const h = Math.max(2, Math.round((p.count / max) * 80));
          return (
            <div
              key={p.date}
              className="group relative flex-1"
              title={`${p.date}: ${p.count} paper${p.count === 1 ? "" : "s"} saved`}
            >
              <div
                className="mx-auto w-full rounded-t-[2px] bg-emerald-500/80 transition-colors group-hover:bg-emerald-600"
                style={{ height: `${h}px` }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 flex justify-between font-ui text-[10px] text-ash">
        <span>{points[0]?.date}</span>
        <span>{points[points.length - 1]?.date}</span>
      </div>
    </SectionCard>
  );
}

function QualityMetrics({
  metrics,
}: {
  metrics: PrismaAuditResponse["quality_metrics"];
}) {
  const fmtPct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);
  const items: Array<{
    label: string;
    value: string;
    tone: "good" | "warn" | "neutral";
  }> = [
    {
      label: "Matrix confidence (avg, 1–3)",
      value: metrics.matrix_avg_confidence == null ? "—" : metrics.matrix_avg_confidence.toFixed(2),
      tone: "neutral",
    },
    {
      label: "Full-text success rate",
      value: fmtPct(metrics.full_text_success_rate),
      tone:
        metrics.full_text_success_rate == null
          ? "neutral"
          : metrics.full_text_success_rate >= 0.8
            ? "good"
            : metrics.full_text_success_rate >= 0.5
              ? "warn"
              : "warn",
    },
    {
      label: "Citation validity rate",
      value: fmtPct(metrics.citation_validity_rate),
      tone:
        metrics.citation_validity_rate == null
          ? "neutral"
          : metrics.citation_validity_rate >= 0.8
            ? "good"
            : "warn",
    },
    {
      label: "Reports (valid / invalid / pending)",
      value: `${metrics.reports_by_validation.valid ?? 0} / ${
        metrics.reports_by_validation.invalid ?? 0
      } / ${metrics.reports_by_validation.pending ?? 0}`,
      tone: "neutral",
    },
  ];
  return (
    <SectionCard title="AI quality signals" icon={Gauge}>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {items.map((it) => (
          <div key={it.label} className="flex flex-col gap-0.5">
            <span
              className={`font-display text-[18px] font-bold leading-none ${
                it.tone === "good"
                  ? "text-emerald-600"
                  : it.tone === "warn"
                    ? "text-amber-600"
                    : "text-ink"
              }`}
            >
              {it.value}
            </span>
            <span className="font-ui text-[10px] uppercase tracking-wider text-ash">
              {it.label}
            </span>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

function SchemaCoverage({
  schema,
  projectId,
}: {
  schema: PrismaAuditResponse["extraction_schema"];
  projectId: string;
}) {
  if (!schema) return null;
  return (
    <SectionCard
      title="Extraction schema coverage"
      subtitle={
        schema.is_default
          ? `Seven system-default fields — no custom fields defined.`
          : `${schema.fields_total} field${schema.fields_total === 1 ? "" : "s"} (${schema.custom_fields_total} custom) — schema v${schema.version}.`
      }
      icon={ClipboardText}
      actions={
        <Link
          href={`/projects/${projectId}/schema`}
          className="font-ui inline-flex items-center gap-1 rounded-full bg-primary px-3 py-1 text-[11px] font-semibold text-on-primary hover:bg-primary-deep"
        >
          Edit schema
        </Link>
      }
    >
      <ul className="grid gap-2 sm:grid-cols-2">
        {schema.fields.map((f) => {
          const rate = f.coverage_rate;
          const tone =
            rate >= 0.8
              ? "bg-green-500"
              : rate >= 0.5
                ? "bg-amber-500"
                : "bg-red-500";
          return (
            <li
              key={f.key}
              className="rounded-[12px] border border-hairline bg-canvas p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-ui text-[12px] font-semibold text-ink">
                    {f.label}
                    {!f.is_reserved && (
                      <span className="ml-1.5 rounded-full bg-primary/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-primary">
                        custom
                      </span>
                    )}
                    {f.required && (
                      <span className="ml-1 text-red-600">*</span>
                    )}
                  </p>
                  <p className="font-mono text-[10px] text-ash">
                    {f.key} · {f.type}
                  </p>
                </div>
                <p className="font-mono text-[12px] text-charcoal">
                  {f.populated}/{f.rows_total}
                </p>
              </div>
              <div className="mt-2 h-1.5 w-full rounded-full bg-surface-bone">
                <div
                  className={`h-full rounded-full ${tone}`}
                  style={{ width: `${Math.round(rate * 100)}%` }}
                />
              </div>
              <p className="mt-1 font-ui text-[10px] text-ash">
                {Math.round(rate * 100)}% populated
              </p>
            </li>
          );
        })}
      </ul>
    </SectionCard>
  );
}
