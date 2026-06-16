"use client";

import { useEffect, useMemo } from "react";
import { toast } from "sonner";
import { Graph as GraphIcon } from "@phosphor-icons/react";
import { useKnowledgeMapStore } from "@/lib/stores/knowledge-map-store";
import { useProjectsStore } from "@/lib/stores/projects-store";
import KnowledgeGraphCanvas from "@/components/knowledge-map/KnowledgeGraph";
import GraphToolbar from "@/components/knowledge-map/GraphToolbar";
import NodeDetailPanel from "@/components/knowledge-map/NodeDetailPanel";
import { Dropdown } from "@/components/ui/Dropdown";

export default function KnowledgeMapPage() {
  const selectedProjectId = useKnowledgeMapStore((s) => s.selectedProjectId);
  const setSelectedProjectId = useKnowledgeMapStore((s) => s.setSelectedProjectId);
  const layout = useKnowledgeMapStore((s) => s.layout);
  const setLayout = useKnowledgeMapStore((s) => s.setLayout);
  const minConnections = useKnowledgeMapStore((s) => s.minConnections);
  const setMinConnections = useKnowledgeMapStore((s) => s.setMinConnections);
  const visibleTypes = useKnowledgeMapStore((s) => s.visibleTypes);
  const toggleType = useKnowledgeMapStore((s) => s.toggleType);
  const searchQuery = useKnowledgeMapStore((s) => s.searchQuery);
  const setSearchQuery = useKnowledgeMapStore((s) => s.setSearchQuery);
  const selectedNodeId = useKnowledgeMapStore((s) => s.selectedNodeId);
  const setSelectedNodeId = useKnowledgeMapStore((s) => s.setSelectedNodeId);
  const data = useKnowledgeMapStore((s) => s.data);
  const loadingGraph = useKnowledgeMapStore((s) => s.loadingGraph);
  const fetchGraph = useKnowledgeMapStore((s) => s.fetchGraph);
  const resolvedProjectId = useKnowledgeMapStore((s) => s.resolvedProjectId());
  const filteredData = useKnowledgeMapStore((s) => s.filteredData());
  const selectedNode = useKnowledgeMapStore((s) => s.selectedNode());

  // Read the projects list from the central projects store – it is
  // pre-fetched by the AppLayout and shared across pages, so we don't
  // need to call the API again here.
  const projects = useProjectsStore((s) => s.projects);
  const loadingProjects = useProjectsStore((s) => s.loading);

  // Re-fetch graph when project or minConnections changes
  useEffect(() => {
    if (!resolvedProjectId) return;
    void fetchGraph().catch((err) => {
      toast.error(err instanceof Error ? err.message : "Failed to load knowledge graph");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedProjectId, minConnections]);

  const isEmpty = !resolvedProjectId || loadingGraph || !data || data.nodes.length === 0;
  const projectTitle = useMemo(
    () => projects.find((p) => p.id === resolvedProjectId)?.title ?? "Knowledge Map",
    [projects, resolvedProjectId],
  );
  const loading = loadingProjects || loadingGraph;

  return (
    <div className="fixed inset-0 top-[60px] bg-canvas flex flex-col overflow-hidden z-10 ml-0 xl:ml-[56px]">
      <div
        className="shrink-0 px-6 pt-2.5 pb-2"
        style={{ borderBottom: "1px solid var(--hairline)" }}
      >
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-[220px] flex-1">
            <p className="font-ui text-[10px] font-semibold uppercase tracking-[0.18em] text-ash">
              Research workspace
            </p>
            <h1 className="mt-1 font-display text-[24px] font-bold leading-[0.95] text-ink">
              Knowledge Map
            </h1>
            <p className="mt-1 max-w-2xl text-[12px] leading-[1.45] text-charcoal">
              Follow recurring methods, datasets, and limitations across your saved corpus instead
              of reading isolated nodes one by one.
            </p>
          </div>

          <div className="w-full max-w-sm">
            <p className="mb-1 font-ui text-[10px] font-semibold uppercase tracking-[0.16em] text-ash">
              Active project
            </p>
            <div className="rounded-[14px] bg-surface-card p-1.5" style={{ border: "1px solid var(--hairline)" }}>
              <Dropdown
                options={projects.map((p) => ({
                  value: p.id,
                  label: p.title,
                  description: `${p.paper_count} papers`,
                }))}
                value={resolvedProjectId}
                onChange={(value) => setSelectedProjectId(value)}
                placeholder="Select project…"
              />
            </div>
          </div>
        </div>
      </div>

      {!isEmpty && data && (
        <div
          className="shrink-0 space-y-2 px-6 py-2"
          style={{ borderBottom: "1px solid var(--hairline)" }}
        >
          <div className="flex flex-wrap gap-2">
            {[
              { label: "papers", value: data.stats.paper_count },
              { label: "methods", value: data.stats.method_count },
              { label: "datasets", value: data.stats.dataset_count },
              { label: "limits", value: data.stats.limitation_count },
              { label: "edges", value: data.stats.total_edges },
            ].map((item) => (
              <div
                key={item.label}
                className="rounded-full bg-surface-card px-2.5 py-1"
                style={{ border: "1px solid var(--hairline)" }}
              >
                <span className="font-ui text-[10px] font-semibold uppercase tracking-[0.14em] text-ash">
                  {item.label}
                </span>
                <span className="ml-1.5 font-ui text-[12px] font-semibold text-ink">
                  {item.value}
                </span>
              </div>
            ))}
            <div className="rounded-full bg-primary px-2.5 py-1 text-on-primary">
              <span className="font-ui text-[10px] font-semibold uppercase tracking-[0.14em]">
                focus
              </span>
              <span className="ml-1.5 font-ui text-[12px] font-semibold">
                {projectTitle}
              </span>
            </div>
          </div>

          <GraphToolbar
            layout={layout}
            onLayoutChange={setLayout}
            visibleTypes={visibleTypes}
            onToggleType={toggleType}
            minConnections={minConnections}
            onMinConnectionsChange={setMinConnections}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            stats={data.stats}
          />
        </div>
      )}

      <div className="flex-1 min-h-0 flex">
        {isEmpty ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center space-y-3 max-w-sm">
              <div className="w-14 h-14 rounded-2xl bg-surface-card border border-[var(--hairline)] flex items-center justify-center mx-auto">
                <GraphIcon size={28} className="text-ash" />
              </div>
              <h3 className="text-base font-semibold text-ink">
                {loading ? "Loading…" : !selectedProjectId ? "Select a project" : "No graph data"}
              </h3>
              <p className="text-sm text-ash">
                {loading
                  ? "Loading knowledge graph…"
                  : !resolvedProjectId
                    ? "Choose a project above to view its knowledge map."
                    : "Generate a literature matrix first to see the knowledge map."}
              </p>
            </div>
          </div>
        ) : (
          <div className="flex flex-1 min-h-0 gap-4 px-4 py-3">
            <div className="min-w-0 flex-1">
              <div
                className="flex h-full flex-col rounded-[18px] bg-surface-card p-2.5"
                style={{ border: "1px solid var(--hairline)" }}
              >
                <div className="flex flex-wrap items-start justify-between gap-2 px-2 pb-2">
                  <div>
                    <p className="font-ui text-[10px] font-semibold uppercase tracking-[0.16em] text-ash">
                      Graph canvas
                    </p>
                    <p className="mt-0.5 text-[12px] text-charcoal">
                      Zoom for local evidence, then use the insight panel to jump between concepts.
                    </p>
                  </div>
                  <div className="rounded-[12px] bg-surface-bone px-2.5 py-1.5">
                    <p className="font-ui text-[10px] font-semibold uppercase tracking-[0.14em] text-ash">
                      Current filter
                    </p>
                    <p className="mt-0.5 text-[12px] font-semibold text-ink">
                      {minConnections === 1 ? "All visible nodes" : `${minConnections}+ links only`}
                    </p>
                  </div>
                </div>

                <div className="min-h-0 flex-1">
                  {filteredData ? (
                    <KnowledgeGraphCanvas
                      data={filteredData}
                      layout={layout}
                      visibleTypes={visibleTypes}
                      onNodeClick={(node) => setSelectedNodeId(node?.id ?? null)}
                    />
                  ) : null}
                </div>
              </div>
            </div>

            <div className="w-[360px] shrink-0">
              <NodeDetailPanel
                node={selectedNode}
                graphData={data}
                searchQuery={searchQuery}
                onClose={() => setSelectedNodeId(null)}
                onNavigate={(nodeId) => setSelectedNodeId(nodeId)}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
