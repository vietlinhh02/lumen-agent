"use client";

/**
 * CustomSelect — a fully styled, accessible replacement for `<select>`.
 *
 * Features:
 * - Renders a button that matches the design system (rounded, hairline border)
 * - Opens a custom menu panel below the trigger
 * - Keyboard nav: Up/Down to move, Enter to select, Escape to close
 * - Optional left icon + label (for the trigger)
 * - Shows a check mark on the active option
 * - Optional section dividers / group headers via the `groups` prop
 * - Closes on outside click
 * - Mobile-friendly (taps work as expected)
 * - Optional `renderOption` to fully customize how each row looks (used
 *   by the column chooser for checkboxes)
 */

import { useEffect, useId, useRef, useState } from "react";
import { CaretDown, Check } from "@phosphor-icons/react";

export interface SelectOption<V extends string = string> {
  value: V;
  label: string;
  description?: string | null;
  /** Rendered as a small badge on the right side of the option row. */
  badge?: string | null;
  /** Disable the option (renders greyed out, can't be selected). */
  disabled?: boolean;
  /** Optional icon to render left of the label. */
  icon?: React.ReactNode;
}

export interface SelectGroup<V extends string = string> {
  label: string;
  options: SelectOption<V>[];
}

/** Helpers passed to a custom `renderOption` callback. */
export interface RenderOptionHelpers {
  isKeyboardActive: boolean;
  refSetter: (el: HTMLButtonElement | null) => void;
  tabIndex: number;
}

interface CommonProps<V extends string> {
  value: V | "";
  onChange: (v: V) => void;
  /** Show a placeholder option when value is "". */
  placeholder?: string;
  /** Left-side label rendered inside the trigger button. */
  label?: string;
  /** Optional icon rendered before the trigger label. */
  icon?: React.ReactNode;
  /** Tailwind width class for the trigger button. */
  triggerClassName?: string;
  /** Disable the whole control. */
  disabled?: boolean;
  /** Test-friendly id. */
  id?: string;
  /** Right side adornment inside the trigger (e.g. a small icon hint). */
  triggerSuffix?: React.ReactNode;
  /** Class for the menu panel. */
  menuClassName?: string;
  /**
   * Optional renderer for each option. When provided, replaces the
   * default "label / description / badge / check" layout. The renderer
   * should call `helpers.refSetter` on its primary interactive element
   * so keyboard focus works correctly.
   */
  renderOption?: (
    option: SelectOption<V>,
    helpers: RenderOptionHelpers,
  ) => React.ReactNode;
}

type Props<V extends string> =
  | (CommonProps<V> & {
      options?: SelectOption<V>[];
      groups?: never;
    })
  | (CommonProps<V> & {
      options?: never;
      groups?: SelectGroup<V>[];
    });

function isGrouped<V extends string>(
  p: Props<V>,
): p is CommonProps<V> & { groups: SelectGroup<V>[] } {
  return Array.isArray((p as { groups?: unknown }).groups);
}

function flatten<V extends string>(p: Props<V>): {
  optionList: SelectOption<V>[];
  groups?: SelectGroup<V>[];
} {
  if (isGrouped(p)) {
    return { optionList: p.groups.flatMap((g) => g.options), groups: p.groups };
  }
  return { optionList: p.options ?? [] };
}

export function CustomSelect<V extends string = string>(props: Props<V>) {
  const {
    value,
    onChange,
    placeholder = "Select…",
    label,
    icon,
    triggerClassName = "min-w-[120px]",
    disabled = false,
    id,
    triggerSuffix,
    menuClassName = "min-w-[200px]",
    renderOption,
  } = props;

  const { optionList, groups } = flatten(props);
  const activeOption = optionList.find((o) => o.value === value);
  const generatedId = useId();
  const triggerId = id ?? generatedId;
  const menuId = `${triggerId}-menu`;

  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState<number>(-1);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  // Close on outside click.
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
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // When opened, focus the active option (or first) so keyboard nav works.
  useEffect(() => {
    if (!open) return;
    const startIndex = activeOption
      ? optionList.findIndex((o) => o.value === activeOption.value)
      : 0;
    const safeIndex = startIndex >= 0 ? startIndex : 0;
    // Defer setState so the effect body doesn't call setState synchronously
    // (this triggers a React lint warning about cascading renders).
    queueMicrotask(() => setActiveIndex(safeIndex));
    // Defer focus to next tick so the menu is in the DOM.
    const t = setTimeout(() => {
      itemRefs.current[safeIndex]?.focus();
    }, 10);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function selectIndex(i: number) {
    const opt = optionList[i];
    if (!opt || opt.disabled) return;
    onChange(opt.value);
    setOpen(false);
    // Restore focus to the trigger so screen readers track the change.
    setTimeout(() => triggerRef.current?.focus(), 0);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;
    if (!open) {
      if (
        e.key === "Enter" ||
        e.key === " " ||
        e.key === "ArrowDown" ||
        e.key === "ArrowUp"
      ) {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = Math.min(optionList.length - 1, activeIndex + 1);
      setActiveIndex(next);
      itemRefs.current[next]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const next = Math.max(0, activeIndex - 1);
      setActiveIndex(next);
      itemRefs.current[next]?.focus();
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      selectIndex(activeIndex);
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  }

  // The trigger shows either the active option's label, the explicit
  // label, or a placeholder — in that order.
  const triggerText = activeOption?.label ?? label ?? placeholder;

  return (
    <div ref={containerRef} className="relative inline-block">
      <button
        ref={triggerRef}
        type="button"
        id={triggerId}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        disabled={disabled}
        onClick={() => !disabled && setOpen((v) => !v)}
        onKeyDown={handleKeyDown}
        className={`focus-ring font-ui inline-flex h-[28px] items-center gap-1 rounded-full border border-hairline-strong bg-surface-card px-2.5 text-[11px] text-ink transition-colors hover:bg-surface-bone disabled:opacity-50 disabled:cursor-not-allowed ${triggerClassName} ${
          open ? "ring-1 ring-primary/30" : ""
        }`}
      >
        {icon ? <span className="text-charcoal">{icon}</span> : null}
        <span className="truncate">{triggerText}</span>
        {triggerSuffix}
        <CaretDown
          size={10}
          weight="bold"
          className={`text-ash transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div
          id={menuId}
          role="listbox"
          aria-labelledby={triggerId}
          className={`absolute left-0 top-[32px] z-30 max-h-[360px] overflow-y-auto rounded-[12px] border border-hairline bg-surface-card p-1.5 shadow-xl animate-scale-in ${menuClassName}`}
          style={{ transformOrigin: "top left" }}
        >
          {groups
            ? groups.map((g) => (
                <div key={g.label} className="mb-1 last:mb-0">
                  <div className="px-2.5 py-1 font-ui text-[10px] font-semibold uppercase tracking-wider text-ash">
                    {g.label}
                  </div>
                  {g.options.map((opt) => {
                    const globalIndex = optionList.findIndex(
                      (o) => o.value === opt.value,
                    );
                    return (
                      <OptionRow
                        key={opt.value}
                        opt={opt}
                        active={opt.value === value}
                        isKeyboardActive={globalIndex === activeIndex}
                        onSelect={() => selectIndex(globalIndex)}
                        setRef={(el) => {
                          itemRefs.current[globalIndex] = el;
                        }}
                        renderOption={renderOption}
                      />
                    );
                  })}
                </div>
              ))
            : optionList.map((opt, i) => (
                <OptionRow
                  key={opt.value}
                  opt={opt}
                  active={opt.value === value}
                  isKeyboardActive={i === activeIndex}
                  onSelect={() => selectIndex(i)}
                  setRef={(el) => {
                    itemRefs.current[i] = el;
                  }}
                  renderOption={renderOption}
                />
              ))}
        </div>
      )}
    </div>
  );
}

function OptionRow<V extends string>({
  opt,
  active,
  isKeyboardActive,
  onSelect,
  setRef,
  renderOption,
}: {
  opt: SelectOption<V>;
  active: boolean;
  isKeyboardActive: boolean;
  onSelect: () => void;
  setRef: (el: HTMLButtonElement | null) => void;
  renderOption?: (
    option: SelectOption<V>,
    helpers: RenderOptionHelpers,
  ) => React.ReactNode;
}) {
  // Default row layout (label / description / badge / check).
  if (!renderOption) {
    return (
      <button
        ref={setRef}
        type="button"
        role="option"
        aria-selected={active}
        disabled={opt.disabled}
        tabIndex={isKeyboardActive ? 0 : -1}
        onClick={onSelect}
        className={`flex w-full items-center gap-2 rounded-[8px] px-2.5 py-1.5 font-ui text-left text-[12px] transition-colors ${
          opt.disabled
            ? "text-ash cursor-not-allowed"
            : isKeyboardActive
              ? "bg-primary/10 text-ink"
              : "text-ink hover:bg-surface-bone"
        }`}
      >
        {opt.icon ? (
          <span className="shrink-0 text-charcoal">{opt.icon}</span>
        ) : null}
        <span className="min-w-0 flex-1 truncate">
          <span className="block font-semibold">{opt.label}</span>
          {opt.description ? (
            <span className="mt-0.5 block text-[10.5px] font-normal text-charcoal">
              {opt.description}
            </span>
          ) : null}
        </span>
        {opt.badge ? (
          <span className="rounded-full bg-surface-bone px-1.5 py-0.5 font-ui text-[9.5px] font-semibold uppercase tracking-wider text-charcoal">
            {opt.badge}
          </span>
        ) : null}
        <span className="w-4 shrink-0 text-right">
          {active ? (
            <Check size={12} weight="bold" className="text-primary" />
          ) : null}
        </span>
      </button>
    );
  }
  // Custom row layout — caller is responsible for the element + onClick.
  // We use a fragment so the renderer's element is the direct child of
  // the menu (no extra wrapper DOM that would steal clicks/focus).
  return (
    <>
      {renderOption(opt, {
        isKeyboardActive,
        refSetter: setRef,
        tabIndex: isKeyboardActive ? 0 : -1,
      })}
    </>
  );
}
