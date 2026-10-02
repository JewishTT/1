import { useEffect, useRef } from "react";

import { formatLinkReason, linkColor } from "../lib/donor/links";
import { readLegacyNodeTokens } from "../ui/tokens";

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
    const tokens = readLegacyNodeTokens(containerRef.current);
    // Lazily import Cytoscape only when the panel actually has content.
    import("cytoscape").then((mod) => {
      if (!containerRef.current) return;
      cy = mod.default({
        container: containerRef.current,
        elements: [
          ...elements
            .filter((e) => e.kind === "node")
            .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
            .map((e) => ({
              data: { id: e.id, label: e.label },
            })),
          ...elements
            .filter((e) => e.kind === "edge")
            .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
            .map((e) => ({
              data: {
                id: e.id,
                source: e.source,
                target: e.target,
                label: formatLinkReason(e.label),
              },
              style: { "line-color": linkColor(e.label, tokens) },
            })),
        ],
        style: [
          {
            selector: "node",
            style: {
              label: "data(label)",
              // Cytoscape paints to a canvas, so it cannot resolve `var()`: the
              // token has to be read out of the cascade and handed over as a
              // string. `LEGACY_NODE_TOKENS` is the closed `--c-*` set from
              // styles/legacy/legacy-tokens.css, which is the right token family
              // for a surface that has not been migrated to `--ui-*` yet (§62).
              // The hex that used to sit inline as a `var()` fallback is gone:
              // the variable IS declared, so the fallback was unreachable, and it
              // was the only colour in the file that no token governed.
              "background-color": tokens.nodeFill,
              color: tokens.nodeLabel,
              "border-width": 1.5,
              "border-color": tokens.nodeSelected,
              "text-valign": "bottom",
            },
          },
          {
            selector: "edge",
            style: {
              "line-color": tokens.edge,
              width: 1.2,
              "curve-style": "bezier",
            },
          },
        ],
        layout: { name: "cose", randomize: false },
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
