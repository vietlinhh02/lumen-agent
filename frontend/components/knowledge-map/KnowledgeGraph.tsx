"use client";

import { useEffect, useRef, useState } from "react";
import type { LayoutOptions } from "cytoscape";
import type { KnowledgeGraphResponse, GraphNodeResponse } from "@/lib/types";

// ── Built-in layouts only (no extensions) ────────────────────────────────

const LAYOUT_CONFIGS: Record<string, LayoutOptions> = {
  cose: {
    name: "cose",
    idealEdgeLength: 120,
    nodeOverlap: 24,
    gravity: 0.22,
    numIter: 1500,
    animate: false,
    randomize: false,
    componentSpacing: 90,
    nodeRepulsion: 7200,
  },
  breadthfirst: {
    name: "breadthfirst",
    directed: false,
    spacingFactor: 1.2,
    animate: false,
  },
  concentric: {
    name: "concentric",
    minNodeSpacing: 50,
    animate: false,
    concentric: (node: { degree: () => number }) => node.degree(),
    levelWidth: () => 2,
  },
  circle: {
    name: "circle",
    animate: false,
    avoidOverlap: true,
  },
  grid: {
    name: "grid",
    animate: false,
    avoidOverlap: true,
    condense: true,
  },
};

const NODE_COLORS: Record<string, string> = {
  paper: "#fffdf8",
  method: "#dff3e7",
  dataset: "#fff0dc",
  limitation: "#fde6e3",
};

const NODE_BORDERS: Record<string, string> = {
  paper: "#202020",
  method: "#2b9a66",
  dataset: "#ea580c",
  limitation: "#dc2626",
};

const EDGE_COLORS: Record<string, string> = {
  uses_method: "#2b9a66",
  evaluates_dataset: "#ea580c",
  has_limitation: "#dc2626",
  shares_method: "#8d8d8d",
  shares_dataset: "#8d8d8d",
};

const EDGE_STYLES: Record<string, string> = {
  uses_method: "solid",
  evaluates_dataset: "dashed",
  has_limitation: "dotted",
  shares_method: "solid",
  shares_dataset: "solid",
};

// ── Props ────────────────────────────────────────────────────────────────

interface Props {
  data: KnowledgeGraphResponse;
  layout: string;
  visibleTypes: Set<string>;
  onNodeClick: (node: GraphNodeResponse | null) => void;
}

interface HoverCardState {
  left: number;
  top: number;
  title: string;
  type: string;
}

// ── Component ────────────────────────────────────────────────────────────

export default function KnowledgeGraphCanvas({ data, layout, visibleTypes, onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const cyRef = useRef<any>(null);
  const onNodeClickRef = useRef(onNodeClick);
  const [hoverCard, setHoverCard] = useState<HoverCardState | null>(null);

  useEffect(() => {
    onNodeClickRef.current = onNodeClick;
  }, [onNodeClick]);

  const filteredNodes = data.nodes.filter((n) => visibleTypes.has(n.type));
  const visibleNodeIds = new Set(filteredNodes.map((n) => n.id));
  const filteredLinks = data.links.filter((l) => visibleNodeIds.has(l.source) && visibleNodeIds.has(l.target));

  const elements = [
    ...filteredNodes.map((n) => ({ data: { ...n, id: n.id }, classes: n.type })),
    ...filteredLinks.map((l, i) => ({ data: { id: `edge-${i}`, source: l.source, target: l.target, relation: l.relation }, classes: l.relation })),
  ];

  // Init + teardown — deferred with requestAnimationFrame to avoid React 19 conflicts
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let destroyed = false;
    let rafId: number;

    import("cytoscape").then((mod) => {
      if (destroyed) return;

      // Defer to next frame so React has finished committing DOM
      rafId = requestAnimationFrame(() => {
        if (destroyed || !containerRef.current) return;
        const cytoscape = mod.default;

        const cy = cytoscape({
          container: containerRef.current,
          elements,
          style: [
            {
              selector: "node",
              style: {
                label: "data(label)",
                "text-wrap": "ellipsis",
                "text-max-width": "120px",
                "font-size": "11px",
                "font-weight": 600,
                "text-valign": "bottom",
                "text-margin-y": 10,
                color: "#202020",
                "text-background-color": "rgba(255,253,248,0.92)",
                "text-background-opacity": 1,
                "text-background-shape": "roundrectangle",
                "text-background-padding": "2px",
                "overlay-opacity": 0,
                "background-opacity": 1,
                "border-width": 2,
                "border-opacity": 1,
              },
            },
            {
              selector: "node.paper",
              style: {
                "background-color": NODE_COLORS.paper,
                shape: "round-rectangle",
                width: (el: { degree: () => number }) => Math.min(36 + Math.sqrt(el.degree()) * 9, 72),
                height: 28,
                "border-color": NODE_BORDERS.paper,
                "border-width": 2.5,
                "corner-radius": "12px",
              },
            },
            {
              selector: "node.method",
              style: {
                "background-color": NODE_COLORS.method,
                shape: "round-rectangle",
                width: 42,
                height: 30,
                "border-color": NODE_BORDERS.method,
                "border-width": 2,
                "corner-radius": "10px",
              },
            },
            {
              selector: "node.dataset",
              style: {
                "background-color": NODE_COLORS.dataset,
                shape: "diamond",
                width: 34,
                height: 34,
                "border-color": NODE_BORDERS.dataset,
                "border-width": 2,
              },
            },
            {
              selector: "node.limitation",
              style: {
                "background-color": NODE_COLORS.limitation,
                shape: "triangle",
                width: 32,
                height: 32,
                "border-color": NODE_BORDERS.limitation,
                "border-width": 2,
              },
            },
            {
              selector: "edge",
              style: {
                width: 1.2,
                opacity: 0.45,
                "curve-style": "bezier",
              },
            },
            ...Object.entries(EDGE_COLORS).map(([cls, color]) => ({
              selector: `edge.${cls}`,
              style: {
                "line-color": color,
                "target-arrow-color": color,
                "line-style": EDGE_STYLES[cls] as "solid" | "dashed" | "dotted",
                width: cls.startsWith("shares_") ? 1 : 1.8,
                opacity: cls.startsWith("shares_") ? 0.28 : 0.55,
              },
            })),
            {
              selector: "node.highlighted",
              style: {
                "border-width": 3.5,
                "border-opacity": 1,
                "z-index": 10,
              },
            },
            {
              selector: "node.dimmed",
              style: { opacity: 0.2 },
            },
            {
              selector: "edge.highlighted",
              style: { opacity: 1, width: 2.8 },
            },
            {
              selector: "edge.dimmed",
              style: { opacity: 0.08 },
            },
          ],
          layout: LAYOUT_CONFIGS[layout] || LAYOUT_CONFIGS.cose,
          userPanningEnabled: true,
          userZoomingEnabled: true,
          boxSelectionEnabled: false,
          selectionType: "single",
          minZoom: 0.3,
          maxZoom: 3,
        });

      cy.on("mouseover", "node", (e) => {
        const neighborhood = e.target.closedNeighborhood();
        cy.elements().addClass("dimmed");
        neighborhood.removeClass("dimmed").addClass("highlighted");
        const renderedPosition = e.target.renderedPosition();
        const nodeData = e.target.data() as GraphNodeResponse;
        const left = Math.min(
          Math.max(renderedPosition.x + 12, 12),
          Math.max(cy.width() - 272, 12),
        );
        const top = Math.min(
          Math.max(renderedPosition.y + 12, 12),
          Math.max(cy.height() - 84, 12),
        );
        setHoverCard({
          left,
          top,
          title: nodeData.full_label?.trim() || nodeData.label,
          type: nodeData.type,
        });
      });

      cy.on("mouseout", "node", () => {
        cy.elements().removeClass("dimmed").removeClass("highlighted");
        setHoverCard(null);
      });

      cy.on("tap", "node", (e) => onNodeClickRef.current(e.target.data() as GraphNodeResponse));
      cy.on("tap", (e) => {
        if (e.target === cy) {
          onNodeClickRef.current(null);
        }
        setHoverCard(null);
      });

      cyRef.current = cy;
      }); // end requestAnimationFrame
    });

    return () => {
      destroyed = true;
      cancelAnimationFrame(rafId);
      if (cyRef.current) { cyRef.current.destroy(); cyRef.current = null; }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, visibleTypes]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.layout(LAYOUT_CONFIGS[layout] || LAYOUT_CONFIGS.cose).run();
  }, [layout]);

  return (
    <div
      ref={containerRef}
      className="h-full w-full rounded-[18px]"
      style={{
        position: "relative",
        background:
          "radial-gradient(circle at top left, rgba(255,106,61,0.10), transparent 28%), linear-gradient(180deg, #fffdf8 0%, #f6f1e6 100%)",
      }}
    >
      {hoverCard ? (
        <div
          className="pointer-events-none absolute z-20 max-w-[260px] rounded-[14px] bg-surface-card px-3 py-2 shadow-sm"
          style={{
            left: hoverCard.left,
            top: hoverCard.top,
            border: "1px solid var(--hairline)",
          }}
        >
          <p className="font-ui text-[10px] font-semibold uppercase tracking-[0.14em] text-ash">
            {hoverCard.type}
          </p>
          <p className="mt-1 text-[12px] font-semibold leading-[1.4] text-ink">
            {hoverCard.title}
          </p>
        </div>
      ) : null}
    </div>
  );
}
