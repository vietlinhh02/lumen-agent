"use client";

import { useEffect, useRef, useState } from "react";

interface Props {
  value: string | null;
  onSave: (value: string) => void;
  className?: string;
}

export function EditableCell({ value, onSave, className = "" }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing && ref.current) {
      ref.current.focus();
      ref.current.selectionStart = ref.current.value.length;
    }
  }, [editing]);

  function startEdit() {
    setDraft(value || "");
    setEditing(true);
  }

  function save() {
    setEditing(false);
    if (draft !== (value || "")) onSave(draft);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      save();
    }
    if (e.key === "Escape") {
      setDraft(value || "");
      setEditing(false);
    }
  }

  if (editing) {
    return (
      <textarea
        ref={ref}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={save}
        onKeyDown={handleKeyDown}
        className={`focus-ring w-full rounded-[10px] bg-surface-card px-3 py-2 text-[13px] font-ui text-ink placeholder:text-ash outline-none resize-y min-h-[56px] transition-shadow ${className}`}
        style={{ border: "1px solid var(--hairline-strong, #202020)" }}
      />
    );
  }

  return (
    <span
      onClick={startEdit}
      className={`block cursor-pointer rounded-[4px] px-1 py-0.5 text-[13px] font-ui leading-[1.5] transition-colors hover:bg-surface-bone ${
        value ? "text-body" : "text-stone italic"
      } ${className}`}
    >
      {value || "not specified"}
    </span>
  );
}
