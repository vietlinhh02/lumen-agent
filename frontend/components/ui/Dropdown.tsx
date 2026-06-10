"use client";

import { useEffect, useRef, useState } from "react";
import { CaretDown, Check } from "@phosphor-icons/react";

export interface DropdownOption {
  value: string;
  label: string;
  description?: string;
}

interface Props {
  options: DropdownOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label?: string;
  className?: string;
}

export function Dropdown({
  options,
  value,
  onChange,
  placeholder = "Select…",
  label,
  className = "",
}: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const selected = options.find((o) => o.value === value);

  return (
    <div className={className}>
      {label && (
        <label className="font-ui mb-1.5 block text-[12px] font-semibold text-charcoal">
          {label}
        </label>
      )}
      <div ref={ref} className="relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex h-[44px] w-full max-w-md items-center justify-between gap-2 rounded-full bg-surface-card px-4 font-ui text-[14px] text-ink transition-all outline-none hover:bg-surface-bone focus:ring-2 focus:ring-primary/30"
          style={{ border: "1px solid var(--hairline)" }}
        >
          <span className={`truncate ${selected ? "" : "text-ash"}`}>
            {selected ? selected.label : placeholder}
          </span>
          <CaretDown
            size={14}
            className={`shrink-0 text-ash transition-transform duration-200 ${
              open ? "rotate-180" : ""
            }`}
          />
        </button>

        {open && (
          <div
            className="absolute left-0 top-[52px] z-50 w-full min-w-[280px] rounded-[10px] bg-surface-card p-1 shadow-lg animate-scale-in"
            style={{ border: "1px solid var(--hairline)" }}
          >
            {options.map((opt) => {
              const isSelected = opt.value === value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => {
                    onChange(opt.value);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center gap-3 rounded-[6px] px-3 py-2.5 text-left transition-colors ${
                    isSelected
                      ? "bg-violet-50 text-ink"
                      : "text-ink hover:bg-surface-bone"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <span className="block font-ui text-[13px] font-medium truncate">
                      {opt.label}
                    </span>
                    {opt.description && (
                      <span className="block font-ui text-[11px] text-ash truncate mt-0.5">
                        {opt.description}
                      </span>
                    )}
                  </div>
                  {isSelected && (
                    <Check size={14} weight="bold" className="shrink-0 text-primary" />
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
