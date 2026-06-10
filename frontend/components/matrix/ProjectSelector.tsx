"use client";

import type { ProjectResponse } from "@/lib/types";
import { Dropdown, type DropdownOption } from "@/components/ui/Dropdown";

interface Props {
  projects: ProjectResponse[];
  selectedId: string;
  onChange: (id: string) => void;
}

export function ProjectSelector({ projects, selectedId, onChange }: Props) {
  const options: DropdownOption[] = projects.map((p) => ({
    value: p.id,
    label: p.title,
    description: `${p.paper_count} papers · ${p.status}`,
  }));

  return (
    <Dropdown
      options={options}
      value={selectedId}
      onChange={onChange}
      label="Project"
      placeholder="Select a project…"
    />
  );
}
