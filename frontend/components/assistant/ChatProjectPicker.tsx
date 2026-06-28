"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAssistantStore } from "@/lib/stores/assistant-store";
import { useProjectsStore } from "@/lib/stores/projects-store";
import { useProjects } from "@/lib/hooks/useProjects";
import { Folder, CaretDown } from "@phosphor-icons/react";

/**
 * Compact project picker rendered inside the chat input area.
 *
 * Behaviour:
 * - If the active session is already linked to a project, we render a
 *   static label (the project name + folder icon) so the user can see
 *   the context but cannot re-link the session to a different project.
 * - If the session is unlinked, we render a clickable "Link project"
 *   button that opens a dropdown to pick a project.
 *
 * The intent is that the project link is a one-time decision per
 * session — once chosen, the project is fixed and clearly visible in
 * the chat.
 */
export function ChatProjectPicker() {
  const currentSession = useAssistantStore((s) => s.currentSession);
  const updateSessionProject = useAssistantStore((s) => s.updateSessionProject);
  const { projects } = useProjects();
  const fetchProjects = useProjectsStore((s) => s.fetchProjects);

  // Ensure the projects list is loaded when the picker mounts.
  useEffect(() => {
    void fetchProjects();
  }, [fetchProjects]);

  if (!currentSession) {
    return null;
  }

  return (
    <ProjectPicker
      projects={projects}
      currentProjectId={currentSession.project_id}
      onChange={(id) => void updateSessionProject(currentSession.id, id)}
    />
  );
}

function ProjectPicker({
  projects,
  currentProjectId,
  onChange,
}: {
  projects: import("@/lib/types").ProjectResponse[];
  currentProjectId: string | null;
  onChange: (id: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    if (!open) return;
    const onMouse = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onMouse);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onMouse);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const current = projects.find((p) => p.id === currentProjectId) ?? null;

  // Linked state: static label, not interactive
  if (current) {
    return (
      <div
        ref={ref}
        className="flex h-8 items-center gap-1.5 rounded-lg bg-primary/10 px-2 font-ui text-xs text-primary"
        title={`Linked to: ${current.title}`}
      >
        <Folder size={14} weight="fill" className="shrink-0" />
        <span className="max-w-[120px] truncate font-medium">
          {current.title}
        </span>
      </div>
    );
  }

  // Unlinked state: clickable picker that opens a dropdown
  const handleSelect = (id: string) => {
    onChange(id);
    setOpen(false);
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex h-8 items-center gap-1.5 rounded-lg px-2 font-ui text-xs transition-all duration-150 active:scale-95 text-charcoal hover:text-ink hover:bg-surface-bone"
        title="Link this chat to a project"
        aria-label="Link to a project"
      >
        <Folder size={14} weight="regular" className="shrink-0" />
        <span className="hidden sm:inline max-w-[120px] truncate font-medium">
          Link project
        </span>
        <CaretDown
          size={12}
          weight="bold"
          className={`hidden sm:inline transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          className="absolute left-0 bottom-[calc(100%+8px)] z-50 w-[280px] rounded-[12px] bg-canvas shadow-2xl overflow-hidden animate-scale-in"
          style={{ border: "1px solid var(--hairline)" }}
        >
          <div
            className="px-3 py-2"
            style={{ borderBottom: "1px solid var(--hairline)" }}
          >
            <p className="font-ui text-[10px] font-semibold uppercase tracking-[0.14em] text-ash">
              Link to project
            </p>
          </div>
          <div className="max-h-[320px] overflow-y-auto p-1">
            {projects.length === 0 ? (
              <p className="px-3 py-4 font-ui text-[12px] text-ash text-center">
                No projects yet
              </p>
            ) : (
              projects.slice(0, 12).map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handleSelect(p.id)}
                  className="flex w-full items-center gap-2 rounded-[8px] px-2.5 py-2 font-ui text-[13px] transition-colors text-left text-ink hover:bg-surface-bone"
                >
                  <Folder size={14} weight="regular" className="text-ash" />
                  <span className="truncate flex-1">{p.title}</span>
                  <span className="font-ui text-[10px] text-ash">
                    {p.paper_count}p
                  </span>
                </button>
              ))
            )}
            {projects.length > 12 && (
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  router.push("/projects");
                }}
                className="flex w-full items-center justify-center rounded-[8px] py-2 font-ui text-[12px] font-medium text-charcoal hover:bg-surface-bone"
              >
                View all {projects.length} projects →
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
