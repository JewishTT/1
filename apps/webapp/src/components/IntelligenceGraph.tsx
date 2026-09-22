import { useEffect, useRef } from "react";
import { IntelGraph } from "../lib/intelGraph";

interface Props {
  graph: IntelGraph;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  onExpand?: (id: string) => void;
}

const NODE_STYLE: Record<string, object> = {
  entity: {
    "background-color": "#0e1626",
    "border-color": "#22d3ee",
    "border-width": 2,
    "border-opacity": 0.9,
    "shadow-blur": 18,
    "shadow-color": "#22d3ee",
    "shadow-opacity": 0.55,
    width: 56,
    height: 56,
    shape: "ellipse",
    color: "#e6edf7",
    "font-size": 10,
    label: "data(label)",
    "text-valign": "bottom",
    "text-margin-y": 6,
    "font-family": "'Geist Mono', Consolas, monospace",
  },
  correlate: {
    "background-color": "transparent",
    "background-image": "data(image)",
    "background-opacity": 0,
    "border-color": "#f0a832",
    "border-width": 2,
    "border-style": "dashed",
    "shadow-blur": 14,
    "shadow-color": "#f0a832",
    "shadow-opacity": 0.4,
    width: 44,
    height: 44,
    shape: "round-rectangle",
    color: "#aeb9c9",
    "font-size": 9,
    label: "data(label)",
    "text-valign": "bottom",
    "text-margin-y": 5,
    "font-family": "'Geist Mono', Consolas, monospace",
  },
  relationship: {
    "background-color": "#131e33",
    "border-color": "#a78bfa",
    "border-width": 1.5,
    "shadow-blur": 12,
    "shadow-color": "#a78bfa",
    "shadow-opacity": 0.4,
    width: 34,
    height: 34,
    shape: "triangle",
    color: "#c9cfe3",
    "font-size": 8,
    label: "",
    "font-family": "'Geist Mono', Consolas, monospace",
  },
};

const EDGE_STYLE: Record<string, object> = {
  possible_match: { "line-color": "#22d3ee", width: 1.6, "line-style": "solid", "arrow-color": "#22d3ee" },
  assertion: { "line-color": "#e879f9", width: 1.3, "line-style": "dotted", "arrow-color": "#e879f9" },
  relationship: { "line-color": "#a78bfa", width: 1.1, "line-style": "dashed", "arrow-color": "#a78bfa" },
};

export function IntelligenceGraph({ graph, onSelect, onExpand }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined" || typeof document === "undefined") return;
    if (graph.nodes.length === 0) return;
    let cy: cytoscape.Core | undefined;
    let cancelled = false;

    import("cytoscape").then((mod) => {
      if (cancelled || !hostRef.current) return;
      cy = mod.default({
        container: hostRef.current,
        elements: [
          ...graph.nodes.map((n) => ({
            data: { id: n.id, label: n.label, kind: n.kind },
          })),
          ...graph.edges.map((e) => ({
            data: { id: e.id, source: e.source, target: e.target, kind: e.kind, reason: e.reason },
            style: {
              label: e.reason,
              "font-size": 7,
              "label-background-color": "#05070d",
              "label-background-opacity": 0.75,
              "label-background-padding": "2px",
              "label-rotation": "autorotate",
              "text-wrap": "ellipsis",
              "text-max-width": "120px",
              color: "#7c889d",
              "font-family": "'Geist Mono', Consolas, monospace",
            },
          })),
        ],
        style: [
          {
            selector: "node",
            style: {
              "background-color": "#0e1626",
              color: "#e6edf7",
              label: "data(label)",
              "font-family": "'Geist Mono', Consolas, monospace",
            },
          },
          {
            selector: 'node[kind="entity"]',
            style: NODE_STYLE.entity as never,
          },
          {
            selector: 'node[kind="correlate"]',
            style: NODE_STYLE.correlate as never,
          },
          {
            selector: 'node[kind="relationship"]',
            style: NODE_STYLE.relationship as never,
          },
          {
            selector: "edge",
            style: {
              "curve-style": "bezier",
              "line-color": "#3b4a63",
              width: 1.2,
              color: "#7c889d",
              "font-size": 7,
              "font-family": "'Geist Mono', Consolas, monospace",
            },
          },
          {
            selector: 'edge[kind="possible_match"]',
            style: EDGE_STYLE.possible_match as never,
          },
          {
            selector: 'edge[kind="assertion"]',
            style: EDGE_STYLE.assertion as never,
          },
          {
            selector: 'edge[kind="relationship"]',
            style: EDGE_STYLE.relationship as never,
          },
          {
            selector: ":selected",
            style: {
              "border-width": 3,
              "border-color": "#22d3ee",
              "shadow-blur": 24,
              "shadow-opacity": 0.8,
            } as cytoscape.Css.Node,
          },
        ],
        layout: { name: "cose", animate: true, randomize: false, componentSpacing: 60, nodeRepulsion: 7000 },
        userZoomingEnabled: true,
        minZoom: 0.2,
        maxZoom: 3,
      });

      cy.on("tap", "node", (evt) => onSelect?.(evt.target.id()));
      cy.on("tap", (evt) => {
        if (evt.target === cy) onSelect?.(null);
      });
      cy.on("dbltap", "node", (evt) => onExpand?.(evt.target.id()));
      cy.fit(undefined, 40);
    });

    return () => {
      cancelled = true;
      cy?.destroy();
    };
  }, [graph, onSelect, onExpand]);

  return (
    <div
      ref={hostRef}
      className="cytoscape-host"
      data-testid="intel-cytoscape"
      style={{ width: "100%", height: "100%" }}
    />
  );
}