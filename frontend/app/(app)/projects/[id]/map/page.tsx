"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo } from "react";
import { toast } from "sonner";
import { Graph as GraphIcon } from "@phosphor-icons/react";
import { useKnowledgeMapStore } from "@/lib/stores/knowledge-map-store";
import { useProjectsStore } from "@/lib/stores/projects-store";
import KnowledgeGraphCanvas from "@/components/knowledge-map/KnowledgeGraph";
import GraphToolbar from "@/components/knowledge-map/GraphToolbar";
import NodeDetailPanel from "@/components/knowledge-map/NodeDetailPanel";

export default function ProjectMapPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = id ?? "";

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
  const filteredData = useKnowledgeMapStore((s) => s.filteredData());
  const selectedNode = useKnowledgeMapStore((s) => s.selectedNode());

  const projects = useProjectsStore((s) => s.projects);

  // Bind the active project id
  useEffect(() => {
    if (projectId) setSelectedProjectId(projectId);
  }, [projectId, setSelectedProjectId]);

  // Re-fetch graph when project or minConnections changes
  useEffect(() => {
    if (!projectId) return;
    void fetchGraph().catch((err) => {
      toast.error(err instanceof Error ? err.message : "Failed to load knowledge graph");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, minConnections]);

  const isEmpty = loadingGraph || !data || data.nodes.length === 0;
  const projectTitle = useMemo(
    () => projects.find((p) => p.id === projectId)?.title ?? "Knowledge Map",
    [projects, projectId],
  );

  return (
    <div className="flex flex-col h-[calc(100vh-140px)] sm:h-[calc(100vh-180px)] lg:h-[calc(100vh-220px)]">
      <div className="mb-3 shrink-0">
        <h2 className="font-display text-[20px] sm:text-[22px] font-bold leading-[1.1] text-ink">
          Knowledge Map
        </h2>
        <p className="mt-1 font-ui text-[12px] text-charcoal">
          Follow recurring methods, datasets, and limitations across the saved corpus.
        </p>
      </div>

      {!isEmpty && data && (
        <div className="mb-3 flex flex-wrap gap-1.5 sm:gap-2">
          {[
            { label: "papers", value: data.stats.paper_count },
            { label: "methods", value: data.stats.method_count },
            { label: "datasets", value: data.stats.dataset_count },
            { label: "limits", value: data.stats.limitation_count },
            { label: "edges", value: data.stats.total_edges },
          ].map((item) => (
            <div
              key={item.label}
              className="rounded-full bg-surface-card px-2 sm:px-2.5 py-1"
              style={{ border: "1px solid var(--hairline)" }}
            >
              <span className="font-ui text-[9px] sm:text-[10px] font-semibold uppercase tracking-[0.14em] text-ash">
                {item.label}
              </span>
              <span className="ml-1 sm:ml-1.5 font-ui text-[11px] sm:text-[12px] font-semibold text-ink">
                {item.value}
              </span>
            </div>
          ))}
          <div className="rounded-full bg-primary px-2 sm:px-2.5 py-1 text-on-primary max-w-[160px] truncate">
            <span className="font-ui text-[9px] sm:text-[10px] font-semibold uppercase tracking-[0.14em]">
              focus
            </span>
            <span className="ml-1 sm:ml-1.5 font-ui text-[11px] sm:text-[12px] font-semibold truncate">
              {projectTitle}
            </span>
          </div>
        </div>
      )}

      {!isEmpty && data && (
        <div className="mb-3 shrink-0">
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

      <div
        className="rounded-[14px] bg-surface-card p-2 sm:p-2.5 flex-1 min-h-0 overflow-hidden"
        style={{ border: "1px solid var(--hairline)" }}
      >
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center py-12 sm:py-16 text-center px-4 h-full">
            <div className="w-14 h-14 rounded-2xl bg-surface-bone border border-[var(--hairline)] flex items-center justify-center mx-auto mb-3">
              <GraphIcon size={28} className="text-ash" />
            </div>
            <h3 className="text-base font-semibold text-ink">
              {loadingGraph ? "Loading…" : "No graph data"}
            </h3>
            <p className="mt-2 text-sm text-ash max-w-md">
              {loadingGraph
                ? "Loading knowledge graph…"
                : "Generate a literature matrix first to see the knowledge map."}
            </p>
          </div>
        ) : (
          <div className="flex gap-3 h-full min-h-0">
            <div className="min-w-0 flex-1 min-h-0 relative">
              {filteredData ? (
                <KnowledgeGraphCanvas
                  data={filteredData}
                  layout={layout}
                  visibleTypes={visibleTypes}
                  onNodeClick={(node) => setSelectedNodeId(node?.id ?? null)}
                />
              ) : null}

              {/* Mobile: tap a node opens a bottom drawer with details */}
              {selectedNode && (
                <div className="lg:hidden absolute inset-x-2 bottom-2 z-10 max-h-[60%] overflow-y-auto rounded-[12px] bg-surface-card p-1 shadow-2xl"
                  style={{ border: "1px solid var(--hairline)" }}
                >
                  <NodeDetailPanel
                    node={selectedNode}
                    graphData={data}
                    searchQuery={searchQuery}
                    onClose={() => setSelectedNodeId(null)}
                    onNavigate={(nodeId) => setSelectedNodeId(nodeId)}
                  />
                </div>
              )}
            </div>
            {/* Desktop: persistent side panel */}
            <div className="hidden lg:block w-[320px] shrink-0 overflow-y-auto">
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
