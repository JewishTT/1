import { useEffect, useRef } from "react";
import type cytoscape from "cytoscape";

import type { EntityToolbarTarget, CytoscapeElement } from "../lib/specopsGraph";
import { ENTITY_TYPE_ACCENTS } from "../lib/specopsGraph";

interface Props {
  elements: CytoscapeElement[];
  selectedEntityId?: string | null;
  onSelect?: (entity: EntityToolbarTarget | null) => void;
}

/**
 * Maltego-style graph canvas (SpecOps): renders the entity graph with
 * Cytoscape, styling nodes by their entity-type class (colors are safe hex
 * defaults keyed by class — see ENTITY_TYPE_ACCENTS). Tapping a node pushes
 * its {id, label, entity_type, entity_value} target up to the toolbar.
 */
export function SpecOpsGraphPanel({ elements, selectedEntityId, onSelect }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (typeof window === "undefined" || typeof document === "undefined") return;
    if (elements.length === 0) return;
    let cy: cytoscape.Core | undefined;
    let cancelled = false;

    import("cytoscape").then((mod) => {
      if (cancelled || !hostRef.current) return;

      cy = mod.default({
        container: hostRef.current,
        elements,
        style: [
          {
            selector: "node",
            style: {
              "background-color": "#0a160d",
              "border-color": "#5b6d60",
              "border-width": 3.5,
              "border-style": "double",
              "border-opacity": 0.95,
              "shadow-blur": 26,
              "shadow-opacity": 0.6,
              width: 78,
              height: 78,
              shape: "ellipse",
              color: "#e7f4e5",
              "font-size": 10,
              label: "data(label)",
              "text-wrap": "wrap",
              "text-max-width": "140px",
              "text-valign": "bottom",
              "text-halign": "center",
              "line-height": 1.3,
              "font-family": "'Geist Mono', Consolas, monospace",
            } as never,
          },
          ...Object.entries(ENTITY_TYPE_ACCENTS).map(([cls, accent]) => ({
            selector: `node.${cls}`,
            style: {
              "border-color": accent,
              "shadow-color": accent,
              "background-gradient-start-color": accent,
              "background-gradient-stop-color": "#060b14",
              "background-gradient-direction": "to-bottom-right",
            } as never,
          })),
          {
            selector: "edge",
            style: {
              "curve-style": "bezier",
              "line-color": "#526a59",
              width: 1.2,
              color: "#8da58f",
              "font-size": 7,
              label: "data(label)",
              "label-background-color": "#020604",
              "label-background-opacity": 0.75,
              "label-background-padding": "2px",
              "text-wrap": "ellipsis",
              "text-max-width": "120px",
              "font-family": "'Geist Mono', Consolas, monospace",
            } as never,
          },
          {
            selector: ":selected",
            style: {
              "border-width": 3.5,
              "border-color": "#b5ff69",
              "shadow-blur": 30,
              "shadow-opacity": 0.85,
            } as cytoscape.Css.Node,
          },
          {
            selector: "node:hover",
            style: { "shadow-blur": 34, "shadow-opacity": 0.9 } as cytoscape.Css.Node,
          },
        ],
        layout: { name: "cose", animate: true, randomize: false, componentSpacing: 80, nodeRepulsion: 9000 },
        userZoomingEnabled: true,
        minZoom: 0.2,
        maxZoom: 3,
      });

      cyRef.current = cy;
      cy.on("tap", "node", (evt) => {
        const data = evt.target.data() as Record<string, unknown>;
        onSelectRef.current?.({
          id: String(data.id ?? ""),
          label: String(data.label ?? data.id ?? ""),
          entity_type: String(data.entity_type ?? "UNKNOWN"),
          entity_value: String(data.entity_value ?? data.id ?? ""),
        });
      });
      cy.on("tap", (evt) => {
        if (evt.target === cy) onSelectRef.current?.(null);
      });
      cy.fit(undefined, 40);
    });

    return () => {
      cancelled = true;
      cy?.destroy();
      if (cyRef.current === cy) cyRef.current = null;
    };
  }, [elements]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    if (selectedEntityId) {
      const node = cy.getElementById(selectedEntityId);
      if (node.length > 0) node.select();
    } else {
      cy.$(":selected").unselect();
    }
  }, [selectedEntityId]);

  return (
    <div
      ref={hostRef}
      className="cytoscape-host"
      data-testid="specops-cytoscape"
      style={{ width: "100%", height: "100%" }}
    />
  );
}