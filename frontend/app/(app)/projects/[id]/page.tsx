/* eslint-disable */
"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo } from "react";
import {
  FileText,
  MagnifyingGlass,
  Table,
  Graph,
  Lightbulb,
  PencilLine,
  ArrowRight,
  Sparkle,
  Calendar,
  PencilSimple,
  CheckCircle,
  Warning,
  CircleNotch,
  Lightning,
} from "@phosphor-icons/react";
import { useProjectsStore } from "@/lib/stores/projects-store";
import { useMatrixStore } from "@/lib/stores/matrix-store";
import { useGapsStore } from "@/lib/stores/gaps-store";
import { useReportsStore } from "@/lib/stores/reports-store";
import { useKnowledgeMapStore } from "@/lib/stores/knowledge-map-store";
import { formatDate, relativeTime } from "@/lib/utils";
import { ProjectOnboardingTour } from "@/components/onboarding/ProjectOnboardingTour";



export default function ProjectOverviewPage() {
  const params = useParams<{ id: string }>();
  const projectId = params?.id ?? "";

  const project = useProjectsStore((s) => s.currentProject);
  const papers = useProjectsStore((s) => s.currentPapers);
  const matrixRows = useMatrixStore((s) => s.rows);
  const loadingMatrix = useMatrixStore((s) => s.loading);
  const gaps = useGapsStore((s) => s.gaps);
  const conflicts = useGapsStore((s) => s.conflicts);
  const loadingGaps = useGapsStore((s) => s.loadingGaps);
  const reports = useReportsStore((s) => s.reports);
  const loadingReports = useReportsStore((s) => s.loading);
  const kmData = useKnowledgeMapStore((s) => s.data);

  const base = `/projects/${projectId}`;

  const recentPapers = useMemo(() => {
    const sorted = [...papers].sort(
      (a, b) => +new Date(b.saved_at || 0) - +new Date(a.saved_at || 0),
    );
    return sorted.slice(0, 5);
  }, [papers]);

  if (!project) {
    return null; // layout already handles loading/not-found
  }

  const matrixReady = matrixRows.length > 0;
  const gapsReady = gaps.length > 0;
  const reportsReady = reports.length > 0;
  const papersCount = papers.length;

  // Pipeline progress: 1=created, 2=papers, 3=matrix, 4=map, 5=gaps, 6=reports
  const step = useMemo(() => {
    if (reportsReady) return 6;
    if (gapsReady) return 5;
    if (matrixReady) return 4;
    if (papersCount >= 5) return 3;
    if (papersCount > 0) return 2;
    return 1;
  }, [reportsReady, gapsReady, matrixReady, papersCount]);
  const progress = Math.round(((step - 1) / 5) * 100);

  const nextStep: { label: string; href: string; icon: typeof Sparkle } = (() => {
    if (step === 1) return { label: "Search for papers", href: `${base}/search`, icon: MagnifyingGlass };
    if (step === 2) return { label: papersCount < 5 ? `Add more papers (${papersCount}/5)` : "Generate literature matrix", href: matrixReady ? `${base}/matrix` : `${base}/matrix`, icon: Table };
    if (step === 3) return { label: "Explore knowledge map", href: `${base}/map`, icon: Graph };
    if (step === 4) return { label: "Detect research gaps", href: `${base}/gaps`, icon: Lightbulb };
    if (step === 5) return { label: "Generate literature review", href: `${base}/reports`, icon: PencilLine };
    return { label: "Open literature review", href: `${base}/reports`, icon: PencilLine };
  })();

  const kmStats = kmData?.stats;

  return (
    <div data-tour="project-welcome" className="space-y-5 sm:space-y-6 animate-slide-up">
      <ProjectOnboardingTour />
      
      {/* Workspace Snapshot Pill */}
      <section data-tour="project-snapshot">
        <div
          className="w-fit rounded-full bg-primary/[0.06] px-3 py-1.5 font-ui text-[11px] sm:text-[12px]"
          style={{ border: "1px solid rgba(234, 40, 4, 0.22)" }}
        >
          <span className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
            <Link href={`${base}/papers`} className="inline-flex items-center gap-1 hover:text-primary transition-colors">
              <span className="font-semibold text-primary">{papersCount}</span>
              <span className="text-ink">Papers</span>
            </Link>
            <span className="text-primary/40">·</span>
            
            <Link href={`${base}/matrix`} className="inline-flex items-center gap-1 hover:text-primary transition-colors">
              <span className="font-semibold text-primary">{loadingMatrix ? "…" : matrixRows.length}</span>
              <span className="text-ink">Matrix</span>
            </Link>
            <span className="text-primary/40">·</span>

            <Link href={`${base}/map`} className="inline-flex items-center gap-1 hover:text-primary transition-colors">
              <span className="font-semibold text-primary">{kmStats ? kmStats.paper_count : (matrixReady ? "Ready" : "—")}</span>
              <span className="text-ink">Graph</span>
            </Link>
            <span className="text-primary/40">·</span>

            <Link href={`${base}/gaps`} className="inline-flex items-center gap-1 hover:text-primary transition-colors">
              <span className="font-semibold text-primary">{loadingGaps ? "…" : gaps.length}</span>
              <span className="text-ink">Gaps</span>
            </Link>
            <span className="text-primary/40">·</span>

            <Link href={`${base}/gaps`} className="inline-flex items-center gap-1 hover:text-primary transition-colors">
              <span className="font-semibold text-primary">{loadingGaps ? "…" : conflicts.length}</span>
              <span className="text-ink">Conflicts</span>
            </Link>
            <span className="text-primary/40">·</span>

            <Link href={`${base}/reports`} className="inline-flex items-center gap-1 hover:text-primary transition-colors">
              <span className="font-semibold text-primary">{loadingReports ? "…" : reports.length}</span>
              <span className="text-ink">Reviews</span>
            </Link>
          </span>
        </div>
      </section>

      {/* Pipeline progress */}
      <section
        data-tour="project-progress"
        className="rounded-[16px] bg-surface-card p-4 sm:p-6"
        style={{ border: "1px solid var(--hairline)" }}
      >
        <div className="mb-1 flex items-center gap-2">
          <span className="font-ui text-[10px] font-semibold uppercase tracking-[0.18em] text-ash">
            Workflow Progress
          </span>
          <span className="font-ui text-[12px] text-ash">· step {step} of 6</span>
        </div>
        <p className="font-ui text-[13px] sm:text-[14px] leading-[1.5] text-charcoal">
          {step === 1 && "Start by searching and saving papers related to your research question."}
          {step === 2 && (papersCount < 5
            ? `Save at least 5 papers to unlock matrix generation (${papersCount}/5).`
            : "Ready to generate a literature matrix once you have enough papers.")}
          {step === 3 && "Literature matrix is ready. Explore the knowledge map next."}
          {step === 4 && "Matrix and knowledge map are ready. Detect research gaps next."}
          {step === 5 && "Gaps detected. Generate a citation-safe literature review."}
          {step === 6 && "All done! Open the latest report or regenerate any step."}
        </p>

        <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-surface-bone">
          <div
            className="h-full rounded-full bg-primary transition-all duration-700"
            style={{ width: progress + "%" }}
          />
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 sm:gap-3">
          <Link
            href={nextStep.href}
            className="focus-ring inline-flex h-9 sm:h-10 items-center gap-1.5 sm:gap-2 rounded-full bg-primary px-4 sm:px-5 font-ui text-[12px] sm:text-[13px] font-semibold text-on-primary transition-all duration-200 hover:bg-primary-deep active:scale-[0.98]"
          >
            <nextStep.icon size={13} weight="fill" />
            {nextStep.label}
            <ArrowRight size={12} weight="bold" />
          </Link>
          <Link
            href={`${base}/papers`}
            className="font-ui inline-flex h-9 sm:h-10 items-center gap-1.5 sm:gap-2 rounded-full bg-surface-bone px-4 sm:px-5 text-[12px] sm:text-[13px] font-semibold text-ink transition-colors hover:bg-hairline active:scale-[0.98]"
          >
            View All Papers
          </Link>
        </div>
      </section>



      {/* Two-column layout: recent papers + project meta */}
      <section className="grid gap-4 sm:gap-5 lg:grid-cols-3">
        {/* Recent papers */}
        <div className="lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-ui text-[12px] font-semibold uppercase tracking-wider text-ash">
              Recent Papers
            </h2>
            <Link
              href={`${base}/papers`}
              className="font-ui inline-flex items-center gap-1 text-[12px] font-medium text-charcoal hover:text-ink"
            >
              View all <ArrowRight size={12} />
            </Link>
          </div>

          {papersCount === 0 ? (
            <div
              className="flex flex-col items-center justify-center rounded-[14px] bg-surface-card py-10 sm:py-12 text-center px-4"
              style={{ border: "1px solid var(--hairline)" }}
            >
              <FileText size={28} className="text-stone mb-3" weight="light" />
              <p className="font-ui text-[13px] font-semibold text-ink">No papers yet</p>
              <p className="mt-1 font-ui text-[12px] text-charcoal">Search and save papers to start your literature review.</p>
              <Link
                href={`${base}/search`}
                className="focus-ring mt-4 inline-flex h-9 items-center gap-2 rounded-full bg-primary px-4 font-ui text-[12px] font-semibold text-on-primary transition-colors hover:bg-primary-deep"
              >
                <MagnifyingGlass size={13} weight="bold" />
                Search Papers
              </Link>
            </div>
          ) : (
            <div className="space-y-2">
              {recentPapers.map((p) => (
                <div
                  key={p.id}
                  className="rounded-[12px] bg-surface-card p-3 sm:p-3.5 transition-colors hover:bg-surface-bone"
                  style={{ border: "1px solid var(--hairline)" }}
                >
                  <p className="font-ui line-clamp-1 text-[13px] font-semibold text-ink">
                    {p.title}
                  </p>
                  <div className="mt-1 flex items-center gap-2 font-ui text-[11px] text-ash">
                    {p.year && <span>{p.year}</span>}
                    {p.venue && (
                      <>
                        <span>·</span>
                        <span className="line-clamp-1">{p.venue}</span>
                      </>
                    )}
                    {p.saved_at && (
                      <>
                        <span>·</span>
                        <span>Added {relativeTime(p.saved_at)}</span>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Project meta + activity */}
        <div className="space-y-3 sm:space-y-4">
          {/* Research question */}
          {project.research_question && (
            <div
              className="rounded-[14px] bg-surface-card p-3.5 sm:p-4"
              style={{ border: "1px solid var(--hairline)" }}
            >
              <p className="font-ui mb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-ash">
                Research Question
              </p>
              <p className="font-ui text-[13px] leading-[1.55] text-ink break-words">
                {project.research_question}
              </p>
            </div>
          )}

          {/* Activity */}
          <div
            className="rounded-[14px] bg-surface-card p-3.5 sm:p-4"
            style={{ border: "1px solid var(--hairline)" }}
          >
            <p className="font-ui mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-ash">
              Activity
            </p>
            <ul className="space-y-2.5">
              {matrixReady && (
                <li className="flex items-start gap-2">
                  <CheckCircle size={13} className="text-emerald-500 mt-0.5 shrink-0" weight="fill" />
                  <Link href={`${base}/matrix`} className="font-ui text-[12px] text-ink hover:text-primary">
                    {matrixRows.length} matrix row{matrixRows.length !== 1 ? "s" : ""} generated
                  </Link>
                </li>
              )}
              {gapsReady && (
                <li className="flex items-start gap-2">
                  <CheckCircle size={13} className="text-violet-500 mt-0.5 shrink-0" weight="fill" />
                  <Link href={`${base}/gaps`} className="font-ui text-[12px] text-ink hover:text-primary">
                    {gaps.length} research gap{gaps.length !== 1 ? "s" : ""} identified
                  </Link>
                </li>
              )}
              {conflicts.length > 0 && (
                <li className="flex items-start gap-2">
                  <Warning size={13} className="text-rose-500 mt-0.5 shrink-0" weight="fill" />
                  <Link href={`${base}/gaps`} className="font-ui text-[12px] text-ink hover:text-primary">
                    {conflicts.length} conflicting finding{conflicts.length !== 1 ? "s" : ""} detected
                  </Link>
                </li>
              )}
              {reportsReady && (
                <li className="flex items-start gap-2">
                  <CheckCircle size={13} className="text-blue-500 mt-0.5 shrink-0" weight="fill" />
                  <Link href={`${base}/reports`} className="font-ui text-[12px] text-ink hover:text-primary">
                    {reports.length} literature review{reports.length !== 1 ? "s" : ""} generated
                  </Link>
                </li>
              )}
              {papersCount > 0 && !matrixReady && (
                <li className="flex items-start gap-2">
                  <Lightning size={13} className="text-amber-500 mt-0.5 shrink-0" weight="fill" />
                  <Link href={`${base}/matrix`} className="font-ui text-[12px] text-ink hover:text-primary">
                    {papersCount} paper{papersCount !== 1 ? "s" : ""} saved — ready for matrix
                  </Link>
                </li>
              )}
              {papersCount === 0 && (
                <li className="flex items-start gap-2">
                  <CircleNotch size={13} className="text-ash mt-0.5 shrink-0" weight="fill" />
                  <Link href={`${base}/search`} className="font-ui text-[12px] text-ink hover:text-primary">
                    Start by searching papers
                  </Link>
                </li>
              )}
            </ul>
          </div>

          {/* Dates */}
          <div
            className="rounded-[14px] bg-surface-card p-3.5 sm:p-4"
            style={{ border: "1px solid var(--hairline)" }}
          >
            <p className="font-ui mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-ash">
              Project Info
            </p>
            <dl className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <dt className="font-ui text-[11px] text-ash inline-flex items-center gap-1.5">
                  <Calendar size={11} /> Created
                </dt>
                <dd className="font-ui text-[11px] text-charcoal text-right">{formatDate(project.created_at)}</dd>
              </div>
              <div className="flex items-center justify-between gap-2">
                <dt className="font-ui text-[11px] text-ash inline-flex items-center gap-1.5">
                  <PencilSimple size={11} /> Updated
                </dt>
                <dd className="font-ui text-[11px] text-charcoal text-right">{relativeTime(project.updated_at)}</dd>
              </div>
            </dl>
          </div>
        </div>
      </section>
    </div>
  );
}
