"use client";

import { create } from "zustand";
import { fetchKnowledgeGraph } from "@/lib/api/knowledge-graph";
import { useAuthStore } from "./auth-store";
import { useProjectsStore } from "./projects-store";
import type {
  KnowledgeGraphResponse,
  GraphNodeResponse,
} from "@/lib/types";

interface KnowledgeMapState {
  // State
  selectedProjectId: string;
  layout: string;
  minConnections: number;
  visibleTypes: Set<string>;
  searchQuery: string;
  selectedNodeId: string | null;
  data: KnowledgeGraphResponse | null;
  loadingGraph: boolean;

  // Actions
  setSelectedProjectId: (id: string) => void;
  setLayout: (l: string) => void;
  setMinConnections: (n: number) => void;
  toggleType: (t: string) => void;
  setSearchQuery: (q: string) => void;
  setSelectedNodeId: (id: string | null) => void;
  fetchGraph: () => Promise<void>;
  selectedNode: () => GraphNodeResponse | null;
  filteredData: () => KnowledgeGraphResponse | null;
  resolvedProjectId: () => string;
  reset: () => void;
}

export const useKnowledgeMapStore = create<KnowledgeMapState>()((set, get) => ({
  selectedProjectId: "",
  layout: "cose",
  minConnections: 1,
  visibleTypes: new Set(["paper", "method", "dataset", "limitation"]),
  searchQuery: "",
  selectedNodeId: null,
  data: null,
  loadingGraph: false,

  setSelectedProjectId(id) {
    set({ selectedProjectId: id, selectedNodeId: null });
  },
  setLayout(l) {
    set({ layout: l });
  },
  setMinConnections(n) {
    set({ minConnections: n, selectedNodeId: null });
  },
  toggleType(t) {
    set((s) => {
      const next = new Set(s.visibleTypes);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return { visibleTypes: next };
    });
  },
  setSearchQuery(q) {
    set({ searchQuery: q });
  },
  setSelectedNodeId(id) {
    set({ selectedNodeId: id });
  },

  async fetchGraph() {
    const token = useAuthStore.getState().token;
    const projectId = get().resolvedProjectId();
    if (!token || !projectId) return;
    set({ loadingGraph: true });
    try {
      const data = await fetchKnowledgeGraph(projectId, token, {
        minConnections: get().minConnections,
      });
      set({ data });
    } finally {
      set({ loadingGraph: false });
    }
  },

  resolvedProjectId() {
    // Read the projects list from the central projects store so we don't
    // duplicate the /projects API call.
    const { selectedProjectId } = get();
    if (selectedProjectId) return selectedProjectId;
    const projects = useProjectsStore.getState().projects;
    return projects.length === 1 ? projects[0].id : "";
  },

  selectedNode() {
    const { data, selectedNodeId } = get();
    if (!data || !selectedNodeId) return null;
    return data.nodes.find((n) => n.id === selectedNodeId) ?? null;
  },

  filteredData() {
    const { data, searchQuery } = get();
    if (!data) return null;
    if (!searchQuery) return data;
    const q = searchQuery.toLowerCase();
    const nodes = data.nodes.filter((n) =>
      (n.full_label ?? n.label).toLowerCase().includes(q),
    );
    const visibleNodeIds = new Set(nodes.map((n) => n.id));
    const links = data.links.filter(
      (l) => visibleNodeIds.has(l.source) && visibleNodeIds.has(l.target),
    );
    return { ...data, nodes, links };
  },

  reset() {
    set({
      selectedProjectId: "",
      layout: "cose",
      minConnections: 1,
      visibleTypes: new Set(["paper", "method", "dataset", "limitation"]),
      searchQuery: "",
      selectedNodeId: null,
      data: null,
    });
  },
}));
