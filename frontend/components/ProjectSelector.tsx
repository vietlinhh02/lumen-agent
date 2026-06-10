"use client";

import type { ProjectResponse } from "@/lib/types";
import { Dropdown, type DropdownOption } from "@/components/ui/Dropdown";

interface Props {
  projects: ProjectResponse[];
  selectedId: string;
  onChange: (id: string) => void;
  label?: string;
  placeholder?: string;
  showStatus?: boolean;
}

export function ProjectSelector({
  projects,
  selectedId,
  onChange,
  label = "Project",
  placeholder = "Select a project…",
  showStatus = true,
}: Props) {
  const options: DropdownOption[] = projects.map((p) => ({
    value: p.id,
    label: p.title,
    description: showStatus
      ? `${p.paper_count} papers · ${p.status}`
      : `${p.paper_count} papers`,
  }));

  return (
    <Dropdown
      options={options}
      value={selectedId}
      onChange={onChange}
      label={label}
      placeholder={placeholder}
    />
  );
}
