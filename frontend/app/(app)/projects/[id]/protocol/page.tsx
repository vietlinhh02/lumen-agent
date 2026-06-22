"use client";

import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { FloppyDisk, Plus, Sparkle, Trash } from "@phosphor-icons/react";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "@/lib/stores/auth-store";
import { useProjectsStore } from "@/lib/stores/projects-store";
import type { ProjectResponse, ReviewProtocol } from "@/lib/types";

const EMPTY_PROTOCOL: ReviewProtocol = {
  research_questions: [],
  inclusion_criteria: [],
  exclusion_criteria: [],
  population: null,
  intervention_or_topic: null,
  comparison: null,
  outcome: null,
  date_range: null,
  source_list: [],
  notes: null,
};

function parseLines(value: string) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function formatLines(value: string[]) {
  return value.join("\n");
}

function textOrNull(value: string) {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export default function ProjectProtocolPage() {
  const project = useProjectsStore((s) => s.currentProject);
  const loadingProject = useProjectsStore((s) => s.loadingProject);

  if (loadingProject && !project) {
    return (
      <div className="w-full animate-pulse">
        <div className="h-7 w-48 rounded bg-surface-bone" />
        <div className="mt-2 h-4 w-[420px] max-w-full rounded bg-surface-bone" />
        <div className="mt-6 grid gap-4 xl:grid-cols-4">
          <div className="h-[170px] rounded-[16px] bg-surface-bone" />
          <div className="h-[170px] rounded-[16px] bg-surface-bone" />
          <div className="h-[170px] rounded-[16px] bg-surface-bone" />
          <div className="h-[170px] rounded-[16px] bg-surface-bone" />
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="py-16 text-center">
        <p className="font-ui text-sm font-semibold text-charcoal">Project not loaded</p>
      </div>
    );
  }

  return <ProtocolForm key={`${project.id}-${project.updated_at}`} project={project} />;
}

function ProtocolForm({ project }: { project: ProjectResponse }) {
  const token = useAuthStore((s) => s.token);
  const updateProject = useProjectsStore((s) => s.updateProject);
  const fetchProject = useProjectsStore((s) => s.fetchProject);
  const protocol = useMemo(
    () => ({ ...EMPTY_PROTOCOL, ...(project.review_protocol ?? {}) }),
    [project.review_protocol],
  );

  const [researchQuestions, setResearchQuestions] = useState(
    formatLines(protocol.research_questions),
  );
  const [inclusionCriteria, setInclusionCriteria] = useState(
    formatLines(protocol.inclusion_criteria),
  );
  const [exclusionCriteria, setExclusionCriteria] = useState(
    formatLines(protocol.exclusion_criteria),
  );
  const [population, setPopulation] = useState(protocol.population ?? "");
  const [interventionOrTopic, setInterventionOrTopic] = useState(
    protocol.intervention_or_topic ?? "",
  );
  const [comparison, setComparison] = useState(protocol.comparison ?? "");
  const [outcome, setOutcome] = useState(protocol.outcome ?? "");
  const [dateRange, setDateRange] = useState(protocol.date_range ?? "");
  const [sourceList, setSourceList] = useState(formatLines(protocol.source_list));
  const [notes, setNotes] = useState(protocol.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);

  function renderProtocol(next: ReviewProtocol) {
    setResearchQuestions(formatLines(next.research_questions));
    setInclusionCriteria(formatLines(next.inclusion_criteria));
    setExclusionCriteria(formatLines(next.exclusion_criteria));
    setPopulation(next.population ?? "");
    setInterventionOrTopic(next.intervention_or_topic ?? "");
    setComparison(next.comparison ?? "");
    setOutcome(next.outcome ?? "");
    setDateRange(next.date_range ?? "");
    setSourceList(formatLines(next.source_list));
    setNotes(next.notes ?? "");
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    const review_protocol: ReviewProtocol = {
      research_questions: parseLines(researchQuestions),
      inclusion_criteria: parseLines(inclusionCriteria),
      exclusion_criteria: parseLines(exclusionCriteria),
      population: textOrNull(population),
      intervention_or_topic: textOrNull(interventionOrTopic),
      comparison: textOrNull(comparison),
      outcome: textOrNull(outcome),
      date_range: textOrNull(dateRange),
      source_list: parseLines(sourceList),
      notes: textOrNull(notes),
    };
    try {
      const updated = await updateProject(project.id, { review_protocol });
      if (!updated) throw new Error("Failed to save protocol");
      await fetchProject(project.id);
      toast.success("Protocol saved");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save protocol");
    } finally {
      setSaving(false);
    }
  }

  function seedCommonSources() {
    setSourceList("Semantic Scholar\nOpenAlex\narXiv\nEurope PMC\nPubMed Central");
  }

  async function generateProtocol() {
    setGenerating(true);
    try {
      const draft = await apiFetch<ReviewProtocol>(`/projects/${project.id}/protocol:suggest`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      renderProtocol(draft);
      toast.success("AI drafted a protocol. Review it before saving.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to generate protocol");
    } finally {
      setGenerating(false);
    }
  }

  function clearProtocol() {
    setResearchQuestions("");
    setInclusionCriteria("");
    setExclusionCriteria("");
    setPopulation("");
    setInterventionOrTopic("");
    setComparison("");
    setOutcome("");
    setDateRange("");
    setSourceList("");
    setNotes("");
  }

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-[22px] font-bold leading-[1.0] text-ink">
            Review Protocol
          </h2>
          <p className="mt-1 max-w-[620px] font-ui text-[12px] leading-[1.5] text-charcoal">
            Define the review question, eligibility criteria, sources, and screening scope
            before saving papers into the corpus.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={generateProtocol}
            disabled={generating || saving || !token}
            className="focus-ring inline-flex h-[36px] items-center justify-center gap-1.5 rounded-full bg-ink px-4 font-ui text-[13px] font-semibold text-on-dark transition-colors hover:bg-charcoal disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Sparkle size={14} weight="fill" className={generating ? "animate-spin" : ""} />
            {generating ? "Generating..." : "AI Generate"}
          </button>
          <button
            type="submit"
            disabled={saving || generating}
            className="focus-ring inline-flex h-[36px] items-center justify-center gap-1.5 rounded-full bg-primary px-4 font-ui text-[13px] font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:cursor-not-allowed disabled:opacity-50"
          >
            <FloppyDisk size={14} weight="bold" />
            {saving ? "Saving..." : "Save Protocol"}
          </button>
        </div>
      </div>

      <div className="mb-3">
        <h3 className="font-ui text-[13px] font-semibold text-ink">Review Scope</h3>
        <p className="mt-1 font-ui text-[12px] leading-[1.5] text-charcoal">
          Population is the group or domain being studied. Comparison is the baseline
          or alternative method the review compares against.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <ProtocolInput
          label="Population"
          helper="Who or what the papers must study"
          value={population}
          onChange={setPopulation}
          placeholder="e.g. clinical QA systems, medical datasets"
        />
        <ProtocolInput
          label="Intervention / Topic"
          helper="Main method, exposure, or topic"
          value={interventionOrTopic}
          onChange={setInterventionOrTopic}
          placeholder="e.g. retrieval-augmented generation"
        />
        <ProtocolInput
          label="Comparison"
          helper="Baseline or alternative being compared"
          value={comparison}
          onChange={setComparison}
          placeholder="e.g. fine-tuned LLMs, standard search"
        />
        <ProtocolInput
          label="Outcome"
          helper="What evidence or metric matters"
          value={outcome}
          onChange={setOutcome}
          placeholder="e.g. answer accuracy, citation quality"
        />
        <ProtocolInput
          label="Date Range"
          helper="Publication window"
          value={dateRange}
          onChange={setDateRange}
          placeholder="e.g. 2020-2026"
        />
      </div>

      <div className="mt-5 mb-3">
        <h3 className="font-ui text-[13px] font-semibold text-ink">Screening Rules</h3>
        <p className="mt-1 font-ui text-[12px] leading-[1.5] text-charcoal">
          These rules decide which papers enter the project corpus and which ones get
          rejected with a recorded reason.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        <ProtocolTextarea
          label="Research Questions"
          value={researchQuestions}
          onChange={setResearchQuestions}
          placeholder="One question per line"
        />
        <ProtocolTextarea
          label="Inclusion Criteria"
          value={inclusionCriteria}
          onChange={setInclusionCriteria}
          placeholder={"Empirical study\nUses project-relevant methods\nReports outcomes"}
        />
        <ProtocolTextarea
          label="Exclusion Criteria"
          value={exclusionCriteria}
          onChange={setExclusionCriteria}
          placeholder={"Wrong population\nWrong topic\nInsufficient evidence"}
        />
        <ProtocolTextarea
          label="Source List"
          value={sourceList}
          onChange={setSourceList}
          placeholder={"Semantic Scholar\nOpenAlex\narXiv"}
          action={
            <button
              type="button"
              onClick={seedCommonSources}
              className="inline-flex items-center gap-1 rounded-full bg-surface-bone px-2 py-1 text-[11px] font-semibold text-charcoal hover:text-ink"
            >
              <Plus size={11} weight="bold" />
              Common sources
            </button>
          }
        />
      </div>

      <div className="mt-4">
        <ProtocolTextarea
          label="Protocol Notes"
          value={notes}
          onChange={setNotes}
          rows={5}
          placeholder="Search strategy notes, reviewer decisions, or scope caveats"
        />
      </div>

      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={clearProtocol}
          className="focus-ring inline-flex h-[34px] items-center gap-1.5 rounded-full bg-surface-bone px-4 font-ui text-[12px] font-semibold text-charcoal hover:text-ink"
        >
          <Trash size={13} weight="bold" />
          Clear
        </button>
      </div>
    </form>
  );
}

function ProtocolInput({
  label,
  helper,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  helper?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="font-ui mb-1.5 block text-sm font-semibold text-ink">{label}</span>
      {helper && (
        <span className="mb-1.5 block min-h-[30px] font-ui text-[11px] leading-[1.35] text-ash">
          {helper}
        </span>
      )}
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="focus-ring h-[42px] w-full rounded-full bg-surface-card px-4 font-ui text-sm text-ink placeholder:text-ash"
        style={{ border: "1px solid var(--hairline)" }}
      />
    </label>
  );
}

function ProtocolTextarea({
  label,
  value,
  onChange,
  placeholder,
  action,
  rows = 6,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  action?: ReactNode;
  rows?: number;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-center justify-between gap-2">
        <span className="font-ui text-sm font-semibold text-ink">{label}</span>
        {action}
      </span>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={rows}
        placeholder={placeholder}
        className="focus-ring min-h-[120px] w-full resize-y rounded-[16px] bg-surface-card px-4 py-3 font-ui text-sm leading-[1.5] text-ink placeholder:text-ash"
        style={{ border: "1px solid var(--hairline)" }}
      />
    </label>
  );
}
