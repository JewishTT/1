import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type cytoscape from "cytoscape";
import { EntityType, IntelGraph, IntelNode } from "../lib/intelGraph";

interface Props {
  graph: IntelGraph;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  onExpand?: (id: string) => void;
  onMaterialize?: (id: string) => void;
  onReady?: (cy: cytoscape.Core) => void;
}

// ── Volumetric entity-type palette ─────────────────────────────────────
export const TYPE_META: Record<EntityType, { accent: string; icon: string }> = {
  account: { accent: "#b5ff69", icon: "M12 8a4 4 0 1 0-4-4 4 4 0 0 0 4 4Zm0 2c-4.67 0-8 2.6-8 6v1h16v-1c0-3.4-3.33-6-8-6Z" },
  organisation: { accent: "#ff8d70", icon: "M5 21V4a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v17M3 21h16M9 7h3M9 11h3M9 15h3" },
  device: { accent: "#8ce3a0", icon: "M8 2h8a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Zm4 18h.01" },
  location: { accent: "#8ed7db", icon: "M12 21s-6.5-5.66-6.5-10.5A6.5 6.5 0 0 1 18.5 10.5C18.5 15.34 12 21 12 21ZM12 12.5a2 2 0 1 0-2-2 2 2 0 0 0 2 2Z" },
  infrastructure: { accent: "#82adff", icon: "M4 4h16v7H4Zm0 9h16v7H4Zm4 1.5h.01M4 7.5h.01M20 7.5h.01" },
  tool: { accent: "#ff6670", icon: "m21 3-3.6 3.6M8.5 12A4.5 4.5 0 1 0 13.6 5.4L10 9 8.5 12Zm-2 2-3.5 3.5A2.1 2.1 0 0 0 3 21h0a2.1 2.1 0 0 0 3.5-0.5L10 17" },
  unknown: { accent: "#9aac9d", icon: "M12 21a9 9 0 1 0-9-9 9 9 0 0 0 9 9Zm.5-10.5c.83-.5 1.5-1 1.5-2a2 2 0 1 0-4 0M12 16h.01" },
};

function tint(hex: string, amount: number): string {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.min(255, Math.round(((n >> 16) & 255) + 255 * amount));
  const g = Math.min(255, Math.round(((n >> 8) & 255) + 255 * amount));
  const b = Math.min(255, Math.round((n & 255) + 255 * amount));
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
}

function svgIcon(paths: string, color: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 24 24"><g fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${paths}</g></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function entitySublabel(node: IntelNode): string {
  if (node.kind !== "entity" || !node.counts) return node.id;
  const { ev, tl, versions, signals } = node.counts;
  return `${node.id} · ${ev} ev · ${tl} tl · ${versions} v${signals > 0 ? ` · ${signals} sig` : ""}`;
}

const VOLUME: Record<string, object> = {
  entity: {
    "background-color": "#0a160d",
    "border-width": 2.5,
    "border-opacity": 0.95,
    "shadow-blur": 26,
    "shadow-opacity": 0.6,
    width: 78,
    height: 78,
    shape: "ellipse",
    color: "#e7f4e5",
    "font-size": 10,
    label: "data(label)\ndata(sublabel)",
    "text-wrap": "wrap",
    "text-max-width": "140px",
    "text-valign": "bottom",
    "text-margin-y": 10,
    "text-halign": "center",
    "line-height": 1.3,
    "font-family": "'Geist Mono', Consolas, monospace",
    "underlay-color": "#020604",
    "underlay-opacity": 0.4,
    "underlay-padding": 7,
  },
  correlate: {
    "background-color": "#100d0b",
    "border-width": 2,
    "border-style": "dashed",
    "border-opacity": 0.85,
    "shadow-blur": 16,
    "shadow-opacity": 0.45,
    width: 56,
    height: 56,
    shape: "round-rectangle",
    color: "#d7c5b7",
    "font-size": 9,
    label: "data(label)\ndata(sublabel)",
    "text-wrap": "wrap",
    "text-max-width": "110px",
    "text-valign": "bottom",
    "text-margin-y": 7,
    "font-family": "'Geist Mono', Consolas, monospace",
  },
  relationship: {
    "background-color": "#0f1110",
    "border-width": 1.5,
    "border-opacity": 0.9,
    "shadow-blur": 12,
    "shadow-opacity": 0.4,
    width: 40,
    height: 40,
    shape: "triangle",
    color: "#cbd9ca",
    "font-size": 8,
    label: "",
    "font-family": "'Geist Mono', Consolas, monospace",
  },
  observation: {
    "background-color": "#06120a",
    "border-color": "#a6ff4d",
    "border-width": 1.5,
    "border-opacity": 0.9,
    "shadow-blur": 12,
    "shadow-color": "#a6ff4d",
    "shadow-opacity": 0.5,
    width: 36,
    height: 36,
    shape: "diamond",
    color: "#a5b4c7",
    "font-size": 8,
    label: "data(label)",
    "text-valign": "bottom",
    "text-margin-y": 5,
    "font-family": "'Geist Mono', Consolas, monospace",
  },
  source: {
    "background-color": "#0a100c",
    "border-color": "#8ca28d",
    "border-width": 1,
    "border-opacity": 0.7,
    "shadow-blur": 8,
    "shadow-color": "#8ca28d",
    "shadow-opacity": 0.3,
    width: 30,
    height: 30,
    shape: "round-hexagon",
    color: "#7c889d",
    "font-size": 7,
    label: "data(label)",
    "text-valign": "bottom",
    "text-margin-y": 4,
    "font-family": "'Geist Mono', Consolas, monospace",
  },
};

const EDGE_STYLE: Record<string, object> = {
  possible_match: { "line-color": "#b5ff69", width: 1.8, "line-style": "solid", "arrow-color": "#b5ff69" },
  assertion: { "line-color": "#ff9b82", width: 1.3, "line-style": "dotted", "arrow-color": "#ff9b82" },
  relationship: { "line-color": "#8ed7db", width: 1.1, "line-style": "dashed", "arrow-color": "#8ed7db" },
  evidence: { "line-color": "#8ce3a0", width: 1.3, "line-style": "dashed", "arrow-color": "#8ce3a0" },
  source_host: { "line-color": "#526a59", width: 0.9, "line-style": "dotted", "arrow-color": "#526a59" },
};

// ── Maltego Detail-View card overlaid on the canvas near the node ─────────
function NodeInfoCard({
  node,
  cy,
  hostRef,
  accent,
  onClose,
  onExpand,
  onMaterialize,
}: {
  node: IntelNode;
  cy?: cytoscape.Core | null;
  hostRef: React.RefObject<HTMLDivElement | null>;
  accent: string;
  onClose: () => void;
  onExpand: (id: string) => void;
  onMaterialize: (id: string) => void;
}) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  const place = useCallback(() => {
    if (!cy || typeof cy.getElementById !== "function") {
      setPos({ x: 16, y: 16 });
      return;
    }
    const el = cy.getElementById(node.id);
    if (!el || el.length === 0 || typeof el.renderedPosition !== "function") {
      setPos(null);
      return;
    }
    const { x, y } = el.renderedPosition();
    const rect = hostRef.current?.getBoundingClientRect();
    const cw = rect?.width ?? 0;
    const ch = rect?.height ?? 0;
    const cardW = cardRef.current?.offsetWidth ?? 300;
    const cardH = cardRef.current?.offsetHeight ?? 260;
    let cx = x + 34;
    if (cx + cardW > cw - 8 && cw > 0) cx = Math.max(8, x - cardW - 20);
    const cy2 = Math.max(8, Math.min(y - cardH / 2, Math.max(8, ch - cardH - 8)));
    setPos({ x: cx, y: cy2 });
  }, [cy, node.id, hostRef]);

  useEffect(() => {
    place();
    if (!cy) return;
    cy.on("pan zoom render drag position", place);
    window.addEventListener("resize", place);
    return () => {
      if (typeof cy.off === "function") cy.off("pan zoom render drag position", place);
      window.removeEventListener("resize", place);
    };
  }, [cy, place]);

  const provenance =
    node.kind === "observation"
      ? "Immutable observation slot (I-1) — provenance evidence node, not an addressable catalog entity."
      : node.kind === "source"
        ? "Hosting domain inferred from the observation URI — aggregated source decorator."
        : node.kind === "correlate"
          ? "Correlate node — candidate not yet materialized into the atomic catalog."
          : node.kind === "relationship"
            ? `Linked by relationship edge · ${node.reason ?? "—"}`
            : null;

  return (
    <div
      ref={cardRef}
      className="node-card"
      data-testid={`node-card-${node.id}`}
      style={{ left: pos?.x ?? 100, top: pos?.y ?? 100, ["--acc" as never]: accent }}
    >
      <div className="node-card-head">
        <div>
          <div className="chip-row">
            <span className="status-chip">{node.kind.toUpperCase()}</span>
            {node.kind === "entity" ? <span className="status-chip">{node.type.toUpperCase()}</span> : null}
            {node.materialized ? <span className="status-chip">MATERIALIZED</span> : null}
          </div>
          <div className="node-card-title">{node.label}</div>
          <div className="node-card-id">{node.id}</div>
        </div>
        <button type="button" className="toolbar-btn" onClick={onClose} aria-label="close node card" data-testid="node-card-close">
          ✕
        </button>
      </div>

      <div className="node-card-ring">
        <span className="op-label">SIGNAL MARK</span>
        <div className="chip-row">
          <span className="status-chip">EV {node.counts?.ev ?? 0}</span>
          <span className="status-chip">TL {node.counts?.tl ?? 0}</span>
          <span className="status-chip">VERSIONS {node.counts?.versions ?? 0}</span>
          <span className="status-chip">SIG {node.counts?.signals ?? 0}</span>
        </div>
      </div>

      {node.kind === "entity" && node.attrs && (
        <>
          <div className="node-card-ring">
            <span className="op-label">ATOMIC IDENTITY</span>
            <div className="node-card-attrs" data-testid="node-card-attrs">
              {Object.entries(node.attrs).map(([k, v]) => (
                <div key={k} className="node-card-attr">
                  <span className="node-card-attr-k">{k}</span>
                  <span className="node-card-attr-v">{String(v)}</span>
                </div>
              ))}
            </div>
          </div>
          {node.aliases && node.aliases.length > 0 && (
            <div className="node-card-ring">
              <span className="op-label">ALIASES</span>
              <div className="chip-row">{node.aliases.map((a) => <span key={a} className="status-chip">{a}</span>)}</div>
            </div>
          )}
          {node.assertions && node.assertions.length > 0 && (
            <div className="node-card-ring">
              <span className="op-label">SUPPORTING ASSERTIONS</span>
              <div className="chip-row">{node.assertions.map((a) => <span key={a} className="status-chip">{a}</span>)}</div>
            </div>
          )}
          {node.evidence && node.evidence.length > 0 && (
            <div className="node-card-ring">
              <span className="op-label">ANCHORED EVIDENCE</span>
              <div className="node-card-rows">
                {node.evidence.map((e) => (
                  <div key={e.evidence_id} className="node-card-row">
                    <span className="node-card-attr-v">{e.evidence_id}</span>
                    <span className="op-label">{e.observation_id}</span>
                    <span className="status-chip">{e.immutable ? "IMMUTABLE" : "VOLATILE"}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {provenance ? <p className="panel-note" style={{ marginTop: 8 }}>{provenance}</p> : null}

      <div className="panel-actions">
        {node.kind === "entity" && (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => onExpand(node.id)} data-testid="node-card-expand">
            ⧉ EXPAND NEIGHBOURHOOD
          </button>
        )}
        {node.kind === "correlate" && !node.materialized && (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => onMaterialize(node.id)} data-testid="node-card-materialize">
            ◉ MATERIALIZE ENTITY
          </button>
        )}
        <Link to={`/entities/${node.id}`} className="btn btn-sm">
          OPEN ENTITY PAGE
        </Link>
      </div>
    </div>
  );
}

export function IntelligenceGraph({ graph, selectedId, onSelect, onExpand, onMaterialize, onReady }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const onExpandRef = useRef(onExpand);
  onExpandRef.current = onExpand;

  const selectedNode = graph.nodes.find((n) => n.id === selectedId) ?? null;

  useEffect(() => {
    if (typeof window === "undefined" || typeof document === "undefined") return;
    if (graph.nodes.length === 0) return;
    let cy: cytoscape.Core | undefined;
    let cancelled = false;

    import("cytoscape").then((mod) => {
      if (cancelled || !hostRef.current) return;

      const entityStyle = (Object.entries(TYPE_META) as Array<[EntityType, { accent: string; icon: string }]>)
        .map(([type, meta]) => ({
          selector: `node[kind="entity"][type="${type}"]`,
          style: {
            "border-color": meta.accent,
            "shadow-color": meta.accent,
            "background-image": svgIcon(meta.icon, tint(meta.accent, 0.35)),
            "background-image-opacity": 1,
            "background-width": "26px",
            "background-height": "26px",
            "background-fit": "none",
            "background-position-x": "50%",
            "background-position-y": "42%",
            "background-gradient-start-color": tint(meta.accent, 0.22),
            "background-gradient-stop-color": "#060b14",
            "background-gradient-direction": "to-bottom-right",
          } as never,
        }));

      cy = mod.default({
        container: hostRef.current,
        elements: [
          ...graph.nodes.map((n) => ({
            data: {
              id: n.id,
              label: n.label,
              kind: n.kind,
              type: n.type,
              sublabel: entitySublabel(n),
              ev: n.counts?.ev ?? 0,
              tl: n.counts?.tl ?? 0,
            },
          })),
          ...graph.edges.map((e) => ({
            data: { id: e.id, source: e.source, target: e.target, kind: e.kind, reason: e.reason },
            style: {
              label: e.reason,
              "font-size": 7,
              "label-background-color": "#020604",
              "label-background-opacity": 0.75,
              "label-background-padding": "2px",
              "label-rotation": "autorotate",
              "text-wrap": "ellipsis",
              "text-max-width": "120px",
              color: "#8da58f",
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
          { selector: 'node[kind="entity"]', style: VOLUME.entity as never },
          { selector: 'node[kind="correlate"]', style: VOLUME.correlate as never },
          { selector: 'node[kind="relationship"]', style: VOLUME.relationship as never },
          { selector: 'node[kind="observation"]', style: VOLUME.observation as never },
          { selector: 'node[kind="source"]', style: VOLUME.source as never },
          ...entityStyle,
          {
            selector: "edge",
            style: {
              "curve-style": "bezier",
              "line-color": "#526a59",
              width: 1.2,
              color: "#8da58f",
              "font-size": 7,
              "font-family": "'Geist Mono', Consolas, monospace",
            },
          },
          { selector: 'edge[kind="possible_match"]', style: EDGE_STYLE.possible_match as never },
          { selector: 'edge[kind="assertion"]', style: EDGE_STYLE.assertion as never },
          { selector: 'edge[kind="relationship"]', style: EDGE_STYLE.relationship as never },
          { selector: 'edge[kind="evidence"]', style: EDGE_STYLE.evidence as never },
          { selector: 'edge[kind="source_host"]', style: EDGE_STYLE.source_host as never },
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
      cy.on("tap", "node", (evt) => onSelectRef.current?.(evt.target.id()));
      cy.on("tap", (evt) => {
        if (evt.target === cy) onSelectRef.current?.(null);
      });
      cy.on("dbltap", "node", (evt) => onExpandRef.current?.(evt.target.id()));
      cy.fit(undefined, 40);
      onReadyRef.current?.(cy);
    });

    return () => {
      cancelled = true;
      cy?.destroy();
      if (cyRef.current === cy) cyRef.current = null;
    };
  }, [graph, onSelect, onExpand, onReady]);

  const accent =
    selectedNode?.kind === "entity"
      ? TYPE_META[selectedNode.type]?.accent ?? "#22d3ee"
      : selectedNode?.kind === "observation"
        ? "#34d399"
        : selectedNode?.kind === "correlate"
          ? "#f0a832"
          : "#7c889d";

  return (
    <div
      ref={hostRef}
      className="cytoscape-host"
      data-testid="intel-cytoscape"
      style={{ width: "100%", height: "100%" }}
    >
      {selectedNode ? (
        <NodeInfoCard
          key={selectedNode.id}
          node={selectedNode}
          cy={cyRef.current}
          hostRef={hostRef}
          accent={accent}
          onClose={() => onSelectRef.current?.(null)}
          onExpand={(id) => onExpandRef.current?.(id)}
          onMaterialize={(id) => onMaterialize?.(id)}
        />
      ) : null}
    </div>
  );
}