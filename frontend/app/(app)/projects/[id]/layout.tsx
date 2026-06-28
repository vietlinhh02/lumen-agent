/* eslint-disable */
"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useRef, useMemo } from "react";
import {
  CaretLeft,
  CaretDown,
  CaretUp,
  DotsThree,
  PencilSimple,
  Trash,
  House,
  FileText,
  MagnifyingGlass,
  Table,
  Graph,
  Lightbulb,
  PencilLine,
  Lock,
  ChatCircle,
  Spinner,
  ClipboardText,
  FlowArrow,
  Intersect,
  Check,
  Warning,
  X,
  ListChecks,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import { useAuth } from "@/lib/stores/auth-store";
import { useProjectsStore } from "@/lib/stores/projects-store";
import { useMatrixStore } from "@/lib/stores/matrix-store";
import { useGapsStore } from "@/lib/stores/gaps-store";
import { useClaimsStore } from "@/lib/stores/claims-store";
import { useReportsStore } from "@/lib/stores/reports-store";
import { useSearchStore } from "@/lib/stores/search-store";
import { useKnowledgeMapStore } from "@/lib/stores/knowledge-map-store";
import { useAssistantStore } from "@/lib/stores/assistant-store";
import { useRatingsStore } from "@/lib/stores/ratings-store";
import { EditProjectModal } from "@/components/EditProjectModal";
import { DeleteProjectModal } from "@/components/DeleteProjectModal";
import { ProjectOnboardingTour } from "@/components/onboarding/ProjectOnboardingTour";

const TABS = [
  { key: "overview", label: "Overview", href: "", icon: House, minStep: 1, addon: false },
  { key: "papers", label: "Papers", href: "/papers", icon: FileText, minStep: 1, addon: false },
  { key: "search", label: "Search", href: "/search", icon: MagnifyingGlass, minStep: 1, addon: false },
  { key: "matrix", label: "Matrix", href: "/matrix", icon: Table, minStep: 3, addon: false },
  { key: "map", label: "Map", href: "/map", icon: Graph, minStep: 4, addon: false },
  { key: "gaps", label: "Gaps", href: "/gaps", icon: Lightbulb, minStep: 4, addon: false },
  { key: "reports", label: "Reports", href: "/reports", icon: PencilLine, minStep: 5, addon: false },
  // Add-on tabs: useful but not part of the essential daily workflow.
  { key: "protocol", label: "Protocol", href: "/protocol", icon: ClipboardText, minStep: 1, addon: true },
  { key: "schema", label: "Schema", href: "/schema", icon: ListChecks, minStep: 1, addon: true },
  { key: "audit", label: "Audit", href: "/audit", icon: FlowArrow, minStep: 1, addon: true },
  { key: "claims", label: "Claims", href: "/claims", icon: Intersect, minStep: 4, addon: true },
] as const;

// Step definitions:
// 1 = project just created (no papers)
// 2 = papers saved (<5)
// 3 = >=5 papers saved (ready for matrix)
// 4 = matrix generated
// 5 = gaps detected
// 6 = reports generated
const STEP_NEXT_HREF: Record<number, { label: string; href: string }> = {
  1: { label: "Search for papers", href: "/search" },
  2: { label: "Add more papers", href: "/search" },
  3: { label: "Generate literature matrix", href: "/matrix" },
  4: { label: "Explore knowledge map", href: "/map" },
  5: { label: "Generate literature review", href: "/reports" },
};

function lockReasonForTab(tabKey: string, step: number, papersCount: number): string | null {
  if (tabKey === "matrix" && step < 3) {
    return papersCount === 0
      ? "Save at least 5 papers first"
      : `Save ${5 - papersCount} more paper${5 - papersCount === 1 ? "" : "s"} to unlock`;
  }
  if (tabKey === "map" && step < 4) return "Generate the literature matrix first";
  if (tabKey === "gaps" && step < 4) return "Generate the literature matrix first";
  if (tabKey === "reports" && step < 5) return "Detect research gaps first";
  return null;
}

export default function ProjectWorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const params = useParams<{ id: string }>();
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const projectId = params?.id ?? "";
  const token = useAuth((s) => s.token);

  const project = useProjectsStore((s) => s.currentProject);
  const loadingProject = useProjectsStore((s) => s.loadingProject);
  const fetchProject = useProjectsStore((s) => s.fetchProject);
  const fetchProjectPapers = useProjectsStore((s) => s.fetchProjectPapers);
  const currentPapers = useProjectsStore((s) => s.currentPapers);
  const deleteProject = useProjectsStore((s) => s.deleteProject);

  const fetchMatrixRows = useMatrixStore((s) => s.fetchRows);
  const matrixRows = useMatrixStore((s) => s.rows);

  const fetchGaps = useGapsStore((s) => s.fetchGaps);
  const fetchConflicts = useGapsStore((s) => s.fetchConflicts);
  const gaps = useGapsStore((s) => s.gaps);
  const conflicts = useGapsStore((s) => s.conflicts);

  const fetchClaims = useClaimsStore((s) => s.fetchClaims);
  const fetchClaimsAggregate = useClaimsStore((s) => s.fetchAggregate);
  const claims = useClaimsStore((s) => s.claims);

  const fetchReports = useReportsStore((s) => s.fetchReports);
  const reports = useReportsStore((s) => s.reports);

  const createSession = useAssistantStore((s) => s.createSession);
  const [startingChat, setStartingChat] = useState(false);

  const ratingSummary = useRatingsStore((s) => s.summary);
  const fetchRatingSummary = useRatingsStore((s) => s.fetchSummary);

  const [menuOpen, setMenuOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [userAddonsOpen, setUserAddonsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  // Reset all workflow stores when switching projects so we don't leak
  // data (rows, gaps, search sessions, etc.) between projects.
  useEffect(() => {
    if (!projectId) return;
    useMatrixStore.getState().reset();
    useGapsStore.getState().reset();
    useClaimsStore.getState().reset();
    useReportsStore.getState().reset();
    useSearchStore.getState().reset();
    useKnowledgeMapStore.getState().reset();
    useRatingsStore.getState().reset();
  }, [projectId]);

  // Always fetch project + papers for the workspace shell + counts.
  // Pre-fetch counts for tabs so the badges are populated immediately.
  useEffect(() => {
    if (!projectId) return;
    void fetchProject(projectId);
    void fetchProjectPapers(projectId);
    void fetchMatrixRows(projectId).catch(() => undefined);
    void fetchGaps(projectId).catch(() => undefined);
    void fetchConflicts(projectId).catch(() => undefined);
    void fetchClaims(projectId).catch(() => undefined);
    void fetchClaimsAggregate(projectId).catch(() => undefined);
    void fetchReports(projectId).catch(() => undefined);
    void fetchRatingSummary(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return;
    const hasExtracting = currentPapers.some((p) => p.full_text_status === "extracting" || p.full_text_status === "pending");
    if (!hasExtracting) return;
    const int = setInterval(() => {
      void fetchProjectPapers(projectId);
    }, 5000);
    return () => clearInterval(int);
  }, [projectId, currentPapers, fetchProjectPapers]);

  const activeKey = (() => {
    // Strip the /projects/[id] prefix and compare the remainder against
    // each tab's href. We use exact equality because `startsWith("")`
    // would always match Overview's empty href and steal the active
    // state from the other tabs.
    const base = `/projects/${projectId}`;
    const suffix = pathname === base ? "/" : pathname.startsWith(base + "/") ? pathname.slice(base.length) : pathname;
    const match = TABS.find((t) => {
      if (t.href === "") return suffix === "/" || suffix === "";
      return suffix === t.href || suffix.startsWith(t.href + "/");
    });
    return match?.key ?? "overview";
  })();

  const activeIsAddon = TABS.some((t) => t.key === activeKey && t.addon);
  const addonsOpen = activeIsAddon || userAddonsOpen;

  // Workflow step (mirrors ProjectOverviewPage step logic so tabs reflect
  // the same progress that the hero CTA uses). MUST be declared before
  // any early returns to satisfy the Rules of Hooks.
  const workflowStep = useMemo(() => {
    if (reports.length > 0) return 6;
    if (gaps.length > 0 || conflicts.length > 0) return 5;
    if (matrixRows.length > 0) return 4;
    if (currentPapers.length >= 5) return 3;
    if (currentPapers.length > 0) return 2;
    return 1;
  }, [reports.length, gaps.length, conflicts.length, matrixRows.length, currentPapers.length]);

  const coreTabs = TABS.filter((t) => !t.addon);
  const addonTabs = TABS.filter((t) => t.addon);

  function renderTabLink(t: (typeof TABS)[number], isCore = true) {
    const isActive = t.key === activeKey;
    const Icon = t.icon;
    const badge = badges[t.key];
    const isLocked = workflowStep < t.minStep;
    const lockReason = isLocked ? lockReasonForTab(t.key, workflowStep, currentPapers.length) : null;

    const isStepMode = workflowStep < 6;
    const isPipelineTab = isCore && t.key !== "overview";

    if (isStepMode && isPipelineTab) {
      const stepIndex = coreTabs.filter((x) => x.key !== "overview").findIndex((x) => x.key === t.key);
      const stepNum = stepIndex + 1;
      
      const doneThresholds: Record<string, number> = {
        search: 2,
        papers: 3,
        matrix: 4,
        map: 5,
        gaps: 6,
        reports: 7,
      };
      const isDone = workflowStep >= (doneThresholds[t.key] ?? 99);

      return (
        <div key={t.key} className="flex items-center py-1.5 sm:py-2">
          {stepIndex === 0 && (
             <div className="h-4 w-px bg-hairline mx-1 sm:mx-2" />
          )}
          {stepIndex > 0 && (
             <div className={`h-[2px] w-3 sm:w-5 mx-1 sm:mx-1.5 rounded-full ${isLocked ? "bg-surface-bone" : "bg-primary/30"}`} />
          )}
          <Link
            href={isLocked ? "#" : `${base}${t.href}`}
            onClick={(e) => {
              if (isLocked) {
                e.preventDefault();
                handleLockedTabClick(t.key, t.minStep);
              }
            }}
            title={lockReason ?? undefined}
            aria-disabled={isLocked}
            className={`relative flex shrink-0 items-center gap-1.5 px-2.5 py-1.5 sm:px-3 sm:py-2 rounded-full font-ui text-[12px] sm:text-[13px] font-medium transition-all whitespace-nowrap border ${
              isActive
                ? "border-primary bg-primary/5 text-primary"
                : isLocked
                  ? "border-transparent text-stone cursor-not-allowed hover:text-stone"
                  : "border-hairline bg-surface-card text-charcoal hover:border-ash hover:text-ink shadow-sm"
            }`}
          >
            {isDone && !isActive ? (
              <Check size={14} weight="bold" className="text-emerald-500" />
            ) : isLocked ? (
              <Lock size={12} weight="fill" className="text-stone" />
            ) : (
              <span className={`flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold ${isActive ? "bg-primary text-on-primary" : "bg-surface-bone text-ash"}`}>
                {stepNum}
              </span>
            )}
            <span>{t.label}</span>
          </Link>
        </div>
      );
    }

    let displayLabel: string = t.label;
    if (!isStepMode && isPipelineTab) {
      const stepIndex = coreTabs.filter((x) => x.key !== "overview").findIndex((x) => x.key === t.key);
      displayLabel = `${stepIndex + 1}. ${t.label}`;
    }

    return (
      <Link
        key={t.key}
        href={isLocked ? "#" : `${base}${t.href}`}
        onClick={(e) => {
          if (isLocked) {
            e.preventDefault();
            handleLockedTabClick(t.key, t.minStep);
          }
        }}
        title={lockReason ?? undefined}
        aria-disabled={isLocked}
        className={`relative flex shrink-0 items-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-2.5 sm:py-3 font-ui text-[12px] sm:text-[13px] font-medium transition-colors whitespace-nowrap ${isActive
            ? "text-ink"
            : isLocked
              ? "text-stone cursor-not-allowed hover:text-stone"
              : "text-charcoal hover:text-ink"
          }`}
      >
        <Icon size={15} weight={isActive ? "fill" : "regular"} />
        <span>{displayLabel}</span>
        {isLocked ? (
          <Lock size={10} weight="fill" className="ml-0.5 text-stone sm:hidden" />
        ) : (
          typeof badge === "number" &&
          badge > 0 && (
            <span
              className={`ml-1 rounded-full px-1.5 py-0.5 font-ui text-[10px] font-semibold leading-none ${isActive ? "bg-primary/15 text-primary" : "bg-surface-bone text-ash"
                }`}
            >
              {badge}
            </span>
          )
        )}
        {isActive && (
          <span className="absolute left-0 right-0 -bottom-px h-[2px] rounded-full bg-primary" />
        )}
      </Link>
    );
  }

  if (loadingProject && !project) {
    return (
    <div>
        <div className="mb-8">
          <div className="h-5 w-20 rounded bg-surface-bone animate-pulse" />
          <div className="mt-3 h-10 w-1/2 rounded bg-surface-bone animate-pulse" />
          <div className="mt-2 h-5 w-1/3 rounded bg-surface-bone animate-pulse" />
        </div>
        <div className="h-12 w-full rounded bg-surface-bone animate-pulse" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center animate-fade-in">
        <p className="font-ui text-lg font-semibold text-ink">Project not found</p>
        <Link
          href="/projects"
          className="font-ui mt-4 text-sm font-semibold text-primary hover:text-primary-deep underline underline-offset-2"
        >
          ← Back to Projects
        </Link>
      </div>
    );
  }

  const base = `/projects/${projectId}`;
  const badges: Record<string, number> = {
    papers: currentPapers.length,
    matrix: matrixRows.length,
    claims: claims.length,
    gaps: gaps.length + conflicts.length,
    reports: reports.length,
  };

  function handleLockedTabClick(tabKey: string, minStep: number) {
    const reason = lockReasonForTab(tabKey, workflowStep, currentPapers.length);
    const next = STEP_NEXT_HREF[workflowStep];
    if (reason) {
      toast.message(reason, {
        description: next ? `Next step: ${next.label}` : undefined,
        action: next
          ? {
            label: "Go",
            onClick: () => router.push(`${base}${next.href}`),
          }
          : undefined,
      });
    } else if (next) {
      router.push(`${base}${next.href}`);
    }
    // Keep TS happy about unused param.
    void minStep;
  }

  /**
   * Quick-action: spin up a new assistant session pre-linked to the
   * current project so the user can ask questions about this project's
   * papers / matrix / gaps without having to manually create a chat
   * and pick the project from the assistant sidebar.
   */
  async function handleAskAssistant() {
    if (startingChat) return;
    setStartingChat(true);
    try {
      const session = await createSession({ project_id: projectId });
      if (session) {
        router.push(`/assistant/sessions/${session.id}`);
      } else {
        toast.error("Failed to start a new chat. Please try again.");
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to start a new chat.",
      );
    } finally {
      setStartingChat(false);
    }
  }

  return (
    <div className="animate-fade-in">
      {/* Project header */}
      <div className="mb-4 sm:mb-5">
        <Link
          href="/projects"
          className="font-ui inline-flex items-center gap-1 text-[12px] sm:text-sm font-semibold text-charcoal hover:text-ink transition-colors mb-2 sm:mb-4"
        >
          <CaretLeft size={12} weight="bold" className="sm:hidden" />
          <CaretLeft size={14} weight="bold" className="hidden sm:inline" />
          All Projects
        </Link>

        <div className="flex items-start justify-between gap-3 sm:gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
              <h1
                className="font-display text-[17px] sm:text-[24px] md:text-[28px] lg:text-[32px] font-bold leading-[1.15] sm:leading-[1.1] text-ink break-words"
                style={{ letterSpacing: "-0.4px" }}
              >
                {project.title}
              </h1>
              <span
                className={`font-ui shrink-0 rounded-full px-2 sm:px-2.5 py-0.5 text-[10px] sm:text-[11px] font-semibold ${project.status === "active"
                    ? "bg-green-50 text-green-700"
                    : "bg-ash/10 text-ash"
                  }`}
              >
                {project.status === "active" ? "Active" : "Archived"}
              </span>
              {ratingSummary &&
                ratingSummary.accepted + ratingSummary.weak + ratingSummary.wrong > 0 && (
                  <span
                    className="font-ui inline-flex shrink-0 items-center gap-2 rounded-full bg-surface-bone px-2.5 py-0.5 text-[10px] sm:text-[11px] font-semibold"
                    title="Evidence quotes you've rated in this project"
                  >
                    <span className="inline-flex items-center gap-0.5 text-green-700">
                      <Check size={11} weight="bold" />
                      {ratingSummary.accepted}
                    </span>
                    <span className="inline-flex items-center gap-0.5 text-amber-700">
                      <Warning size={11} weight="bold" />
                      {ratingSummary.weak}
                    </span>
                    <span className="inline-flex items-center gap-0.5 text-red-700">
                      <X size={11} weight="bold" />
                      {ratingSummary.wrong}
                    </span>
                  </span>
                )}
              {currentPapers.some(p => p.full_text_status === "extracting" || p.full_text_status === "pending") && (
                <span className="font-ui inline-flex shrink-0 items-center gap-1.5 rounded-full bg-blue-50 px-2.5 py-0.5 text-[10px] sm:text-[11px] font-semibold text-blue-700" title="Papers are being extracted">
                  <Spinner size={12} className="animate-spin" />
                  Extracting...
                </span>
              )}
            </div>
            {project.topic && (
              <p className="mt-1 sm:mt-1.5 text-[12px] sm:text-[14px] leading-[1.45] sm:leading-[1.5] text-charcoal line-clamp-2">
                {project.topic}
              </p>
            )}
          </div>

          <div ref={menuRef} className="relative shrink-0 flex items-center gap-1.5 sm:gap-2">
            {/* Quick chat button — opens a fresh assistant session
                scoped to this project so the user can ask quick Q&A
                about the project's papers / matrix / gaps. */}
            <button
              data-tour="project-ask"
              onClick={handleAskAssistant}
              disabled={startingChat}
              className="focus-ring inline-flex h-[28px] sm:h-[32px] items-center gap-1 sm:gap-1.5 rounded-full bg-primary px-2.5 sm:px-3 font-ui text-[11px] sm:text-[12px] font-semibold text-on-primary transition-all hover:bg-primary-deep active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
              title="Ask the assistant about this project"
              aria-label="Ask assistant about this project"
            >
              {startingChat ? (
                <Spinner size={12} weight="bold" className="animate-spin" />
              ) : (
                <ChatCircle size={12} weight="fill" />
              )}
              <span>Ask Assistant</span>
            </button>

            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="flex h-[28px] w-[28px] sm:h-[32px] sm:w-[32px] items-center justify-center rounded-full text-charcoal hover:bg-surface-bone hover:text-ink transition-colors"
              aria-label="Project menu"
            >
              <DotsThree size={18} weight="bold" className="sm:hidden" />
              <DotsThree size={20} weight="bold" className="hidden sm:inline" />
            </button>

            {menuOpen && (
              <div
                className="absolute right-0 top-[40px] z-[60] w-[160px] rounded-[10px] bg-surface-card p-1 shadow-lg animate-scale-in"
                style={{ border: "1px solid var(--hairline)" }}
              >
                <button
                  onClick={() => { setMenuOpen(false); setEditOpen(true); }}
                  className="flex w-full items-center gap-2 rounded-[6px] px-3 py-2 font-ui text-[13px] font-medium text-ink hover:bg-surface-bone transition-colors"
                >
                  <PencilSimple size={14} />
                  Edit
                </button>
                <button
                  onClick={() => { setMenuOpen(false); setDeleteOpen(true); }}
                  className="flex w-full items-center gap-2 rounded-[6px] px-3 py-2 font-ui text-[13px] font-medium text-error hover:bg-red-50 transition-colors"
                >
                  <Trash size={14} />
                  Delete
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Tab nav — sticky below the 60px AppShell header */}
      <div
        data-tour="project-tabs"
        className="sticky top-0 z-50 bg-[var(--canvas)] mb-5 sm:mb-6 -mx-4 sm:-mx-6"
        style={{ borderBottom: "1px solid var(--hairline)" }}
      >
        <nav className="flex items-center gap-0.5 sm:gap-1 overflow-x-auto scrollbar-hide -mb-px px-4 sm:px-6">
          {coreTabs.map((t) => renderTabLink(t, true))}

          {addonTabs.length > 0 && (
            <>
              <button
                type="button"
                onClick={() => setUserAddonsOpen((v) => !v)}
                aria-expanded={addonsOpen}
                className={`relative flex shrink-0 items-center gap-1 px-2 sm:px-2.5 py-2.5 sm:py-3 font-ui text-[12px] sm:text-[13px] font-medium transition-colors whitespace-nowrap ${addonsOpen ? "text-ink" : "text-charcoal hover:text-ink"}`}
              >
                {addonsOpen ? <CaretUp size={12} weight="bold" /> : <CaretDown size={12} weight="bold" />}
                <span>More</span>
              </button>
              {addonsOpen && addonTabs.map((t) => renderTabLink(t, false))}
            </>
          )}
        </nav>
      </div>

      {/* Page content */}
      <div>{children}</div>

      {editOpen && (
        <EditProjectModal
          project={project}
          token={token}
          onClose={() => setEditOpen(false)}
          onSaved={() => void fetchProject(projectId)}
        />
      )}

      {deleteOpen && (
        <DeleteProjectModal
          projectId={project.id}
          token={token}
          onClose={() => setDeleteOpen(false)}
          onDeleted={async () => {
            const ok = await deleteProject(project.id);
            setDeleteOpen(false);
            if (ok) router.push("/projects");
          }}
        />
      )}
    </div>
  );
}
