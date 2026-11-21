import type { CSSProperties } from "react";

import { EntityToolbar } from "../components/EntityToolbar";
import { SpecOpsGraphPanel } from "../components/SpecOpsGraphPanel";
import type { ToolRun, ToolSpec } from "../lib/api";
import type { CytoscapeElement, EntityToolbarTarget } from "../lib/specopsGraph";

interface Props {
  elements: CytoscapeElement[];
  entityCount: number;
  edgeCount: number;
  toolsCount: number;
  selectedEntity: EntityToolbarTarget | null;
  tools: ToolSpec[];
  busy: boolean;
  lastRun: ToolRun | null;
  runNote: string | null;
  onSelect: (entity: EntityToolbarTarget | null) => void;
  onRunTool: (tool: ToolSpec) => void;
}

const PAGE_STYLE: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) 340px",
  gap: "0.8rem",
  alignItems: "start",
};

const BANNER_STYLE: CSSProperties = { gridColumn: "1 / -1" };
const GRAPH_PANEL_STYLE: CSSProperties = { marginBottom: 0 };
const GRAPH_HOST_STYLE: CSSProperties = {
  position: "relative",
  height: "calc(100vh - var(--header-h) - 11.5rem)",
  minHeight: 420,
};

/** SpecOps page composition: banner + Maltego graph canvas + entity toolbar. */
export function SpecOpsPage({
  elements,
  entityCount,
  edgeCount,
  toolsCount,
  selectedEntity,
  tools,
  busy,
  lastRun,
  runNote,
  onSelect,
  onRunTool,
}: Props) {
  return (
    <section className="command-page specops-page" style={PAGE_STYLE} data-testid="specops-page">
      <div className="page-banner" style={BANNER_STYLE}>
        <div>
          <span className="op-label">SPEC // MALTEGO-STYLE ENTITY GRAPH</span>
          <h1>SpecOps entity graph</h1>
          <p className="panel-note">
            Click an entity node to arm Maltego-style tools for its type — every run is enqueued
            against the control plane.
          </p>
        </div>
        <span className="status-chip" data-testid="specops-counts">
          {entityCount} ENTITIES · {edgeCount} EDGES · {toolsCount} TOOLS
        </span>
      </div>

      <div className="panel command-panel" style={GRAPH_PANEL_STYLE}>
        <h2>Entity graph</h2>
        <div style={GRAPH_HOST_STYLE}>
          {elements.length === 0 ? (
            <p className="panel-note" data-testid="specops-graph-empty">
              No entity graph to render.
            </p>
          ) : (
            <SpecOpsGraphPanel
              elements={elements}
              selectedEntityId={selectedEntity?.id ?? null}
              onSelect={onSelect}
            />
          )}
        </div>
      </div>

      <EntityToolbar entity={selectedEntity} tools={tools} onRunTool={onRunTool} disabled={busy} />

      {lastRun ? (
        <div
          className="panel command-panel"
          style={{ gridColumn: "1 / -1", marginBottom: 0 }}
          data-testid="specops-last-run"
        >
          <h2>Last enqueued run</h2>
          <div className="chip-row">
            <span className="status-chip" data-testid="run-status">
              {lastRun.status}
            </span>
            <span className="status-chip" data-testid="run-tool">
              {lastRun.tool_id}
            </span>
            <span className="status-chip">{lastRun.entity_type}</span>
            <span className="status-chip">{lastRun.entity_value}</span>
          </div>
          <pre
            className="dlq-payload"
            data-testid="run-command"
            style={{
              margin: "0.5rem 0 0",
              padding: "0.5rem 0.6rem",
              border: "1px solid var(--c-border)",
              borderRadius: "0.45rem",
              background: "rgba(0, 0, 0, 0.35)",
            }}
          >
            {lastRun.command.join(" ")}
          </pre>
        </div>
      ) : null}

      {runNote ? (
        <p className="panel-note" style={{ gridColumn: "1 / -1" }} data-testid="specops-run-note">
          {runNote}
        </p>
      ) : null}
    </section>
  );
}