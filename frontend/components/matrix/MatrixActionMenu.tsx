"use client";

/**
 * MatrixActionMenu — a small popover trigger that opens a styled action
 * menu (similar to CustomSelect but for actions rather than form values).
 *
 * Each item is a row with an icon, label, optional description and badge.
 * Clicking an item calls the action callback and closes the menu.
 */

import { useEffect, useId, useRef, useState } from "react";
import { CaretDown } from "@phosphor-icons/react";

export interface MatrixActionItem {
  key: string;
  label: string;
  description?: string;
  icon?: React.ReactNode;
  /** Render with a red/destructive style. */
  destructive?: boolean;
  /** Show a small badge on the right side (e.g. count of low rows). */
  badge?: string | number | null;
  disabled?: boolean;
  onClick: () => void;
}

interface Props {
  label: string;
  icon?: React.ReactNode;
  items: MatrixActionItem[];
  /** Tailwind class for the trigger. */
  triggerClassName?: string;
  /** Whether the trigger should look "primary" or "neutral". */
  variant?: "primary" | "neutral";
  testId?: string;
}

export function MatrixActionMenu({
  label,
  icon,
  items,
  triggerClassName = "",
  variant = "neutral",
  testId,
}: Props) {
  const [open, setOpen] = useState(false);
  const generatedId = useId();
  const menuId = `${generatedId}-menu`;
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    const escHandler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("keydown", escHandler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", escHandler);
    };
  }, [open]);

  const baseTrigger =
    "focus-ring font-ui inline-flex h-[32px] sm:h-[36px] items-center gap-1.5 rounded-full px-3 sm:px-4 text-[12px] sm:text-[13px] font-semibold transition-all active:scale-95";
  const variantClass =
    variant === "primary"
      ? "bg-primary text-on-primary hover:bg-primary-deep disabled:opacity-50"
      : "border border-hairline-strong bg-surface-card text-ink hover:bg-surface-bone";

  return (
    <div ref={containerRef} className="relative inline-block">
      <button
        ref={triggerRef}
        type="button"
        data-testid={testId}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((v) => !v)}
        className={`${baseTrigger} ${variantClass} ${triggerClassName}`}
      >
        {icon ? <span className="shrink-0">{icon}</span> : null}
        <span className="truncate">{label}</span>
        <CaretDown
          size={11}
          weight="bold"
          className={`shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          className="absolute right-0 top-[40px] z-30 w-[260px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-[12px] border border-hairline bg-surface-card shadow-xl animate-scale-in"
          style={{ transformOrigin: "top right" }}
        >
          <div className="p-1.5">
            {items.map((item) => (
              <button
                key={item.key}
                type="button"
                role="menuitem"
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false);
                  item.onClick();
                }}
                className={`flex w-full items-start gap-2.5 rounded-[8px] px-2.5 py-2 font-ui text-left text-[12px] transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                  item.destructive
                    ? "text-red-700 hover:bg-red-50"
                    : "text-ink hover:bg-surface-bone"
                }`}
              >
                {item.icon ? (
                  <span className="mt-0.5 shrink-0">{item.icon}</span>
                ) : null}
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 font-semibold">
                    {item.label}
                    {item.badge !== undefined && item.badge !== null ? (
                      <span className="rounded-full bg-surface-bone px-1.5 py-0.5 font-ui text-[10px] font-semibold text-charcoal">
                        {item.badge}
                      </span>
                    ) : null}
                  </span>
                  {item.description ? (
                    <span className="mt-0.5 block text-[10.5px] font-normal text-charcoal">
                      {item.description}
                    </span>
                  ) : null}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
