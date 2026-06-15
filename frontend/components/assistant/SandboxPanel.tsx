"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { getSandboxStatus } from "@/lib/api/assistant";
import { useAssistantStore } from "@/lib/stores/assistantStore";
import {
  ArrowClockwise,
  CircleNotch,
  CloudArrowDown,
  Cpu,
  HardDrives,
  Hourglass,
  Stack,
  Terminal,
  X,
} from "@phosphor-icons/react";
import { SandboxFileTree } from "./SandboxFileTree";
import { SandboxOpsList } from "./SandboxOpsList";

function fmtBytes(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function fmtAge(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
}

export function SandboxPanel() {
  const { token } = useAuth();
  const projectId = useAssistantStore((s) => s.state.projectId);
  const open = useAssistantStore((s) => s.state.sandboxPanelOpen);
  const setOpen = useAssistantStore((s) => s.setSandboxPanel);
  const status = useAssistantStore((s) => s.state.sandboxStatus);
  const setStatus = useAssistantStore((s) => s.setSandboxStatus);
  const loading = useAssistantStore((s) => s.state.sandboxLoading);
  const setLoading = useAssistantStore((s) => s.setSandboxLoading);
  const error = useAssistantStore((s) => s.state.sandboxError);
  const setError = useAssistantStore((s) => s.setSandboxError);

  const [activeTab, setActiveTab] = useState<"files" | "ops" | "config">("files");

  const refresh = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getSandboxStatus(token, projectId);
      setStatus(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load sandbox status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!open || !token) return;
    void refresh();
    const id = setInterval(() => {
      void refresh();
    }, 8000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, token, projectId]);

  if (!open) return null;

  const cfg = status?.config;
  const handles = status?.handles ?? [];
  const myHandle = projectId
    ? handles.find((h) => h.project_id === projectId) ?? null
    : null;
  const otherHandles = projectId
    ? handles.filter((h) => h.project_id !== projectId)
    : handles;
  const files = status?.files ?? [];

  return (
    <div className="fixed inset-0 top-[60px] z-30 flex justify-end xl:ml-[56px]">
      <button
        type="button"
        aria-label="Close sandbox panel"
        onClick={() => setOpen(false)}
        className="flex-1 bg-charcoal/30 backdrop-blur-[1px]"
      />
      <div className="flex h-full w-full max-w-md flex-col border-l border-hairline bg-canvas shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-hairline bg-surface-bone/40 px-3 py-2 md:px-4 md:py-3">
          <div className="flex min-w-0 items-center gap-2">
            <Terminal size={16} weight="duotone" className="text-primary" />
            <h2 className="font-display text-sm font-semibold text-ink md:text-base">
              Sandbox
            </h2>
            {cfg && (
              <span
                className={`rounded-full border px-2 py-0.5 font-ui text-[10px] font-semibold ${
                  cfg.mode === "docker"
                    ? "border-indigo-200 bg-indigo-50 text-indigo-700"
                    : cfg.mode === "stub"
                      ? "border-amber-200 bg-amber-50 text-amber-800"
                      : "border-stone-200 bg-stone-100 text-stone-600"
                }`}
              >
                {cfg.mode}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => void refresh()}
              disabled={loading}
              className="rounded-md p-1.5 text-charcoal hover:bg-surface-bone disabled:opacity-50"
              title="Refresh"
            >
              {loading ? (
                <CircleNotch size={14} className="animate-spin" />
              ) : (
                <ArrowClockwise size={14} weight="bold" />
              )}
            </button>
            <button
              onClick={() => setOpen(false)}
              className="rounded-md p-1.5 text-charcoal hover:bg-surface-bone"
              title="Close"
            >
              <X size={14} weight="bold" />
            </button>
          </div>
        </div>

        {/* My handle summary */}
        <div className="border-b border-hairline bg-canvas px-3 py-2 md:px-4">
          {myHandle ? (
            <div className="space-y-1 text-[11px]">
              <Row
                icon={<HardDrives size={11} weight="bold" />}
                label="Workspace"
                value={`${myHandle.workspace_files} files · ${fmtBytes(myHandle.workspace_bytes)}`}
              />
              {myHandle.container_id && (
                <Row
                  icon={<Stack size={11} weight="bold" />}
                  label="Container"
                  value={
                    <span className="font-mono">
                      {myHandle.container_id.slice(0, 12)}
                    </span>
                  }
                />
              )}
              <Row
                icon={<Hourglass size={11} weight="bold" />}
                label="Last used"
                value={`${fmtAge(myHandle.idle_for_seconds)} ago`}
              />
            </div>
          ) : cfg?.enabled ? (
            <p className="text-[11px] text-charcoal/60">
              {projectId
                ? "No live handle for this project yet. The agent will spawn one the first time a sandbox tool is called."
                : "Select a project to spawn a sandbox handle."}
            </p>
          ) : (
            <p className="text-[11px] text-charcoal/60">
              Sandbox is disabled. Set <code className="rounded bg-surface-bone px-1 py-0.5 font-mono text-[10px]">LUMEN_SANDBOX_MODE</code> to
              docker or stub.
            </p>
          )}
          {error && (
            <p className="mt-2 text-[11px] text-red-700">{error}</p>
          )}
        </div>

        {/* Tabs */}
        <div className="flex shrink-0 border-b border-hairline bg-canvas">
          {(
            [
              { key: "files", label: "Files", icon: HardDrives, count: files.length },
              { key: "ops", label: "Operations", icon: CloudArrowDown, count: null },
              { key: "config", label: "Config", icon: Cpu, count: null },
            ] as const
          ).map(({ key, label, icon: Icon, count }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex flex-1 items-center justify-center gap-1.5 border-b-2 px-2 py-2 text-[11px] font-semibold transition-colors md:text-xs ${
                activeTab === key
                  ? "border-primary text-ink"
                  : "border-transparent text-charcoal hover:text-ink"
              }`}
            >
              <Icon size={12} weight="bold" />
              <span>{label}</span>
              {count != null && count > 0 && (
                <span className="rounded-full bg-surface-bone px-1.5 text-[10px] text-charcoal">
                  {count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-3 py-2 md:px-4">
          {activeTab === "files" && (
            <SandboxFileTree files={files} />
          )}
          {activeTab === "ops" && <SandboxOpsList />}
          {activeTab === "config" && cfg && (
            <div className="space-y-2 text-[11px]">
              <Row icon={<Cpu size={11} weight="bold" />} label="Mode" value={cfg.mode} />
              <Row icon={<Cpu size={11} weight="bold" />} label="Image" value={cfg.image} />
              <Row
                icon={<Cpu size={11} weight="bold" />}
                label="Resources"
                value={`${cfg.memory_limit} RAM · ${cfg.cpu_limit} CPU`}
              />
              <Row
                icon={<Cpu size={11} weight="bold" />}
                label="Network"
                value={cfg.network}
              />
              <Row
                icon={<Hourglass size={11} weight="bold" />}
                label="Idle TTL"
                value={`${Math.round(cfg.idle_ttl_seconds / 60)} min`}
              />
              <Row
                icon={<Hourglass size={11} weight="bold" />}
                label="Spawn timeout"
                value={`${cfg.spawn_timeout_seconds}s`}
              />
              <Row
                icon={<HardDrives size={11} weight="bold" />}
                label="Workspace root"
                value={
                  <span className="break-all font-mono text-[10px]">
                    {cfg.workspace_root}
                  </span>
                }
              />
              {otherHandles.length > 0 && (
                <div className="mt-3 border-t border-hairline pt-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-charcoal/70">
                    Other active sandboxes ({otherHandles.length})
                  </p>
                  <ul className="mt-1 space-y-1">
                    {otherHandles.slice(0, 6).map((h) => (
                      <li
                        key={h.project_id}
                        className="flex items-center justify-between rounded border border-hairline bg-surface-bone/30 px-2 py-1 font-mono text-[10px]"
                      >
                        <span className="truncate">{h.project_id.slice(0, 8)}…</span>
                        <span className="text-charcoal/60">
                          {fmtAge(h.idle_for_seconds)} idle
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
          {activeTab === "config" && !cfg && (
            <p className="text-[11px] text-charcoal/60">Loading config…</p>
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t border-hairline bg-surface-bone/30 px-3 py-2 text-[10px] text-charcoal/60 md:px-4">
          Auto-refreshes every 8s. Containers are reaped after the idle TTL.
        </div>
      </div>
    </div>
  );
}

function Row({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-ash">{icon}</span>
      <span className="w-20 shrink-0 text-charcoal/70">{label}</span>
      <span className="ml-auto truncate text-right text-ink">{value}</span>
    </div>
  );
}
