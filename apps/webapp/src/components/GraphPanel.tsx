import { useEffect, useRef } from "react";

import { formatLinkReason, linkColor } from "../lib/donor/links";

export interface GraphElement {
  id: string;
  label: string;
  kind: "node" | "edge";
  source?: string;
  target?: string;
}

interface Props {
  elements: GraphElement[];
  title?: string;
}

/**
 * Graph canvas panel (T057, US2): a Cytoscape rendering of the graph region for
 * discovery/exploration. Node/edge palette is the vendored PANO set
 * (CC BY-NC-4.0, src/styles/donors/pano/pano-tokens.css).
 */
export function GraphPanel({ elements, title = "Graph region" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined" || typeof document === "undefined") return;
    if (elements.length === 0) return;
    let cy: cytoscape.Core | undefined;
    // Lazily import Cytoscape only when the panel actually has content.
    import("cytoscape").then((mod) => {
      if (!containerRef.current) return;
      cy = mod.default({
        container: containerRef.current,
        elements: [
          ...elements
            .filter((e) => e.kind === "node")
            .map((e) => ({
              data: { id: e.id, label: e.label },
            })),
          ...elements
            .filter((e) => e.kind === "edge")
            .map((e) => ({
              data: {
                id: e.id,
                source: e.source,
                target: e.target,
                label: formatLinkReason(e.label),
              },
              style: { "line-color": linkColor(e.label) },
            })),
        ],
        style: [
          {
            selector: "node",
            style: {
              label: "data(label)",
              "background-color": "var(--c-graph-node, #2d2d30)",
              color: "var(--c-graph-node-label, #e6e6e6)",
              "border-width": 1.5,
              "border-color": "var(--c-graph-node-sel, #37373a)",
              "text-valign": "bottom",
            },
          },
          {
            selector: "edge",
            style: {
              "line-color": "var(--c-graph-edge, #646464)",
              width: 1.2,
              "curve-style": "bezier",
            },
          },
        ],
        layout: { name: "cose" },
      });
    });
    return () => cy?.destroy();
  }, [elements]);

  return (
    <section className="graph-panel" data-testid="graph-panel">
      <h3>{title}</h3>
      {elements.length === 0 ? (
        <p className="graph-empty">No graph region to render.</p>
      ) : (
        <div ref={containerRef} className="graph-canvas" data-testid="graph-canvas" />
      )}
    </section>
  );
}
