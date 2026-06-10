"use client";

import { ArrowSquareOut, Sparkle, X } from "@phosphor-icons/react";
import type { GraphNodeResponse, KnowledgeGraphResponse } from "@/lib/types";

const TYPE_LABELS: Record<string, string> = {
  paper: "Paper",
  method: "Method",
  dataset: "Dataset",
  limitation: "Limitation",
};

const TYPE_COLORS: Record<string, string> = {
  paper: "#2563eb",
  method: "#2b9a66",
  dataset: "#ea580c",
  limitation: "#dc2626",
};

const RELATION_LEGEND = [
  { label: "Uses method", color: "#2b9a66", dash: "solid" },
  { label: "Evaluates dataset", color: "#ea580c", dash: "dashed" },
  { label: "States limitation", color: "#dc2626", dash: "dotted" },
  { label: "Paper similarity", color: "#6b7280", dash: "solid" },
];

interface Props {
  node: GraphNodeResponse | null;
  graphData: KnowledgeGraphResponse;
  searchQuery: string;
  onClose: () => void;
  onNavigate: (nodeId: string) => void;
}

function getDisplayLabel(node: GraphNodeResponse): string {
  return node.full_label?.trim() || node.label;
}

function getConnectedNodes(
  node: GraphNodeResponse,
  graphData: KnowledgeGraphResponse,
): GraphNodeResponse[] {
  return graphData.links
    .filter((link) => link.source === node.id || link.target === node.id)
    .map((link) => {
      const otherId = link.source === node.id ? link.target : link.source;
      return graphData.nodes.find((candidate) => candidate.id === otherId);
    })
    .filter(Boolean) as GraphNodeResponse[];
}

function getTopNodes(graphData: KnowledgeGraphResponse, type: string): GraphNodeResponse[] {
  return graphData.nodes
    .filter((node) => node.type === type)
    .sort((left, right) => right.connections - left.connections)
    .slice(0, 5);
}

function SearchSection({
  graphData,
  searchQuery,
  onNavigate,
}: Pick<Props, "graphData" | "searchQuery" | "onNavigate">) {
  if (!searchQuery.trim()) {
    return null;
  }

  const results = graphData.nodes
    .filter((node) => getDisplayLabel(node).toLowerCase().includes(searchQuery.toLowerCase()))
    .slice(0, 6);

  if (!results.length) {
    return (
      <div className="rounded-[12px] bg-surface-bone/70 p-3">
        <p className="font-ui text-[12px] text-ink">No search matches</p>
        <p className="mt-1 text-[12px] text-charcoal">
          Try a shorter keyword or switch back to overview mode.
        </p>
      </div>
    );
  }

  return (
    <section className="space-y-2">
      <SectionLabel label={`Search matches (${results.length})`} />
      <div className="space-y-2">
        {results.map((result) => (
          <JumpButton key={result.id} node={result} onNavigate={onNavigate} />
        ))}
      </div>
    </section>
  );
}

function SectionLabel({ label }: { label: string }) {
  return (
    <p className="font-ui text-[11px] uppercase tracking-[0.18em] text-ash">
      {label}
    </p>
  );
}

function JumpButton({
  node,
  onNavigate,
}: {
  node: GraphNodeResponse;
  onNavigate: (nodeId: string) => void;
}) {
  return (
    <button
      onClick={() => onNavigate(node.id)}
      className="w-full rounded-[12px] bg-surface-card px-3 py-2.5 text-left transition-colors hover:bg-surface-bone"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <div className="flex items-center gap-2">
        <span
          className="h-2 w-2 rounded-full"
          style={{ background: TYPE_COLORS[node.type] ?? "#6b7280" }}
        />
        <span className="font-ui text-[11px] uppercase tracking-[0.14em] text-ash">
          {TYPE_LABELS[node.type] ?? node.type}
        </span>
      </div>
      <p className="mt-1 break-words text-[13px] leading-[1.4] text-ink">
        {getDisplayLabel(node)}
      </p>
      <p className="mt-1 text-[11px] text-charcoal">{node.connections} links</p>
    </button>
  );
}

function OverviewSection({ graphData, onNavigate }: Pick<Props, "graphData" | "onNavigate">) {
  const topMethods = getTopNodes(graphData, "method");
  const topDatasets = getTopNodes(graphData, "dataset");
  const topLimitations = getTopNodes(graphData, "limitation");

  return (
    <>
      <div
        className="rounded-[16px] p-4 text-on-dark"
        style={{
          background:
            "linear-gradient(135deg, rgba(234,40,4,0.96) 0%, rgba(255,106,61,0.9) 100%)",
        }}
      >
        <div className="flex items-center gap-2">
          <Sparkle size={16} weight="fill" />
          <p className="font-ui text-[11px] uppercase tracking-[0.18em]">
            Knowledge overview
          </p>
        </div>
        <p className="mt-3 font-display text-[24px] font-medium leading-none">
          Read the field before diving into single papers.
        </p>
        <p className="mt-3 text-[13px] leading-[1.5] text-on-dark/85">
          Start with the strongest recurring concepts, then jump into supporting papers on the
          graph. This keeps the map closer to a research workflow than a graph demo.
        </p>
      </div>

      <section className="space-y-2">
        <SectionLabel label="How to read" />
        <div className="grid gap-2">
          {RELATION_LEGEND.map((item) => (
            <div
              key={item.label}
              className="flex items-center gap-3 rounded-[12px] bg-surface-card px-3 py-2.5"
              style={{ border: "1px solid var(--hairline)" }}
            >
              <span
                className="h-[2px] w-8 shrink-0"
                style={{
                  background: item.color,
                  borderTop: item.dash === "solid" ? undefined : `2px ${item.dash} ${item.color}`,
                }}
              />
              <span className="text-[12px] text-charcoal">{item.label}</span>
            </div>
          ))}
        </div>
      </section>

      <TopConceptSection label="Top methods" nodes={topMethods} onNavigate={onNavigate} />
      <TopConceptSection label="Top datasets" nodes={topDatasets} onNavigate={onNavigate} />
      <TopConceptSection label="Frequent limitations" nodes={topLimitations} onNavigate={onNavigate} />
    </>
  );
}

function TopConceptSection({
  label,
  nodes,
  onNavigate,
}: {
  label: string;
  nodes: GraphNodeResponse[];
  onNavigate: (nodeId: string) => void;
}) {
  if (!nodes.length) {
    return null;
  }

  return (
    <section className="space-y-2">
      <SectionLabel label={label} />
      <div className="space-y-2">
        {nodes.map((node) => (
          <JumpButton key={node.id} node={node} onNavigate={onNavigate} />
        ))}
      </div>
    </section>
  );
}

function PaperDetails({ node }: { node: GraphNodeResponse }) {
  return (
    <>
      {node.authors ? (
        <DetailBlock label="Authors" value={node.authors} />
      ) : null}
      {node.year || node.venue ? (
        <div className="grid grid-cols-2 gap-3">
          {node.year ? <DetailBlock label="Year" value={String(node.year)} /> : <div />}
          {node.venue ? <DetailBlock label="Venue" value={node.venue} /> : <div />}
        </div>
      ) : null}
      {node.abstract ? (
        <DetailBlock
          label="Abstract"
          value={node.abstract.length > 420 ? `${node.abstract.slice(0, 420)}…` : node.abstract}
        />
      ) : null}
      {node.url ? (
        <a
          href={node.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[12px] text-primary hover:underline"
        >
          Open paper <ArrowSquareOut size={12} />
        </a>
      ) : null}
    </>
  );
}

function DetailBlock({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="font-ui text-[11px] uppercase tracking-[0.14em] text-ash">
        {label}
      </p>
      <p className="mt-1 break-words text-[13px] leading-[1.5] text-charcoal">{value}</p>
    </div>
  );
}

function ActiveNodeSection({
  node,
  graphData,
  onNavigate,
}: {
  node: GraphNodeResponse;
  graphData: KnowledgeGraphResponse;
  onNavigate: (nodeId: string) => void;
}) {
  const connectedNodes = getConnectedNodes(node, graphData);
  const color = TYPE_COLORS[node.type] ?? "#6b7280";
  const supportingPapers = connectedNodes.filter((item) => item.type === "paper");

  return (
    <>
      <div className="rounded-[16px] bg-surface-card p-4" style={{ border: "1px solid var(--hairline)" }}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
              <span className="font-ui text-[11px] uppercase tracking-[0.16em]" style={{ color }}>
                {TYPE_LABELS[node.type] ?? node.type}
              </span>
            </div>
            <h3 className="mt-2 break-words font-ui text-[18px] leading-[1.35] text-ink">
              {getDisplayLabel(node)}
            </h3>
          </div>
          <div className="rounded-full bg-surface-bone px-3 py-1 text-[11px] text-charcoal">
            {node.connections} links
          </div>
        </div>
      </div>

      <section className="space-y-3 rounded-[16px] bg-surface-card p-4" style={{ border: "1px solid var(--hairline)" }}>
        <SectionLabel label="Evidence card" />
        {node.type === "paper" ? (
          <PaperDetails node={node} />
        ) : (
          <>
            <p className="text-[13px] leading-[1.5] text-charcoal">
              {supportingPapers.length} saved paper{supportingPapers.length === 1 ? "" : "s"} support
              this concept in the current project corpus.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <DetailBlock label="Type" value={TYPE_LABELS[node.type] ?? node.type} />
              <DetailBlock label="Support" value={`${supportingPapers.length} papers`} />
            </div>
          </>
        )}
      </section>

      <section className="space-y-2">
        <SectionLabel
          label={node.type === "paper" ? "Related concepts" : "Supporting papers"}
        />
        <div className="space-y-2">
          {connectedNodes.slice(0, 10).map((connectedNode) => (
            <JumpButton key={connectedNode.id} node={connectedNode} onNavigate={onNavigate} />
          ))}
          {connectedNodes.length > 10 ? (
            <p className="px-1 text-[11px] text-ash">
              +{connectedNodes.length - 10} more connected nodes on the graph
            </p>
          ) : null}
        </div>
      </section>
    </>
  );
}

export default function NodeDetailPanel({
  node,
  graphData,
  searchQuery,
  onClose,
  onNavigate,
}: Props) {
  return (
    <div className="flex h-full flex-col rounded-[18px] bg-surface-card" style={{ border: "1px solid var(--hairline)" }}>
      <div className="flex items-center justify-between border-b border-[var(--hairline)] px-4 py-3">
        <div>
          <p className="font-ui text-[11px] uppercase tracking-[0.18em] text-ash">
            Insight panel
          </p>
          <p className="mt-1 text-[13px] text-charcoal">
            {node ? "Focused on one node and its evidence." : "Overview, legend, and quick entry points."}
          </p>
        </div>
        {node ? (
          <button onClick={onClose} className="rounded-full p-2 transition-colors hover:bg-surface-bone">
            <X size={14} className="text-ash" />
          </button>
        ) : null}
      </div>

      <div className="scrollbar-hide flex-1 space-y-4 overflow-y-auto p-4">
        {node ? (
          <ActiveNodeSection node={node} graphData={graphData} onNavigate={onNavigate} />
        ) : (
          <OverviewSection graphData={graphData} onNavigate={onNavigate} />
        )}
        <SearchSection graphData={graphData} searchQuery={searchQuery} onNavigate={onNavigate} />
      </div>
    </div>
  );
}
