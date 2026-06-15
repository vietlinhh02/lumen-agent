"use client";

import { useAssistantStore } from "@/lib/stores/assistantStore";
import type { SandboxConfigFE } from "@/lib/types";
import {
  Cloud,
  CloudSlash,
  GearSix,
  ShippingContainer,
  Stack,
} from "@phosphor-icons/react";

interface Props {
  compact?: boolean;
}

function PillIcon({ mode, enabled }: { mode: string; enabled: boolean }) {
  if (!enabled) return <CloudSlash size={12} weight="bold" />;
  if (mode === "docker") return <ShippingContainer size={12} weight="bold" />;
  if (mode === "stub") return <Stack size={12} weight="bold" />;
  return <Cloud size={12} weight="bold" />;
}

function pillTone(cfg: SandboxConfigFE | null | undefined): string {
  if (!cfg) return "bg-stone-100 text-stone-700 border-stone-200";
  if (!cfg.enabled) return "bg-stone-100 text-stone-600 border-stone-200";
  if (cfg.mode === "docker") return "bg-indigo-50 text-indigo-700 border-indigo-200";
  if (cfg.mode === "stub") return "bg-amber-50 text-amber-800 border-amber-200";
  return "bg-stone-50 text-stone-700 border-stone-200";
}

export function SandboxStatusPill({ compact = false }: Props) {
  const status = useAssistantStore((s) => s.state.sandboxStatus);
  const calls = useAssistantStore((s) => s.state.sandboxToolCalls);
  const cfg = status?.config ?? null;
  const active = status?.active_projects ?? 0;

  const tone = pillTone(cfg);
  const label = cfg ? cfg.mode : "unknown";
  const enabled = cfg?.enabled ?? false;

  return (
    <span
      title={
        cfg
          ? `Sandbox · ${cfg.mode} · ${cfg.memory_limit} RAM · ${cfg.cpu_limit} CPU · ${cfg.network}`
          : "Sandbox status unknown"
      }
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-ui text-[10px] font-semibold ${tone}`}
    >
      <PillIcon mode={cfg?.mode ?? "?"} enabled={enabled} />
      <span className="uppercase tracking-wide">sandbox</span>
      <span className="font-mono normal-case text-[10px] opacity-80">{label}</span>
      {!compact && enabled && (
        <>
          <span className="text-charcoal/30">·</span>
          <span title="Active projects with a live sandbox handle">
            {active} active
          </span>
          <span className="text-charcoal/30">·</span>
          <span title="Total sandbox tool calls this session">
            <GearSix size={10} weight="bold" className="inline" /> {calls}
          </span>
        </>
      )}
    </span>
  );
}
