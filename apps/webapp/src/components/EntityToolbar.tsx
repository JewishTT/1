import type { ToolSpec } from "../lib/api";
import type { EntityToolbarTarget } from "../lib/specopsGraph";
import { typeStyle } from "../lib/specopsGraph";

interface Props {
  entity: EntityToolbarTarget | null;
  tools: ToolSpec[];
  onRunTool: (tool: ToolSpec) => void;
  disabled?: boolean;
}

/**
 * Maltego-style tool toolbar: when an entity node is selected, this panel
 * lists the registered tools whose entity_types match that node's type.
 * Each tool button enqueues a run (disabled while one is in flight).
 */
export function EntityToolbar({ entity, tools, onRunTool, disabled = false }: Props) {
  const style = entity ? typeStyle(entity.entity_type) : null;
  const matching =
    entity === null
      ? []
      : tools.filter(
          (tool) =>
            tool.entity_types.length === 0 || tool.entity_types.includes(entity.entity_type),
        );

  return (
    <aside className="panel command-panel specops-toolbar" data-testid="entity-toolbar">
      <div className="intel-inspector-head">
        <span className="op-label">MALTEGO TOOLS</span>
        {entity && style ? (
          <span className="status-chip" data-testid="toolbar-type">
            {style.icon} {entity.entity_type}
          </span>
        ) : (
          <span className="status-chip">IDLE</span>
        )}
      </div>

      {entity === null ? (
        <p className="panel-note" data-testid="toolbar-hint">
          Select an entity node…</p>
      ) : (
        <>
          <div className="node-card-ring">
            <div className="node-card-title" data-testid="toolbar-entity-name">
              {style ? style.icon : "?"} {entity.label}
            </div>
            <div className="node-card-id" data-testid="toolbar-entity-value">
              {entity.entity_type} · {entity.entity_value}
            </div>
          </div>

          {matching.length === 0 ? (
            <p className="panel-note" data-testid="toolbar-no-tools">
              No tools registered for {entity.entity_type} yet.
            </p>
          ) : (
            <div className="tiles" data-testid="tool-list">
              {matching.map((tool) => (
                <button
                  key={tool.tool_id}
                  type="button"
                  className="op-tile"
                  disabled={disabled}
                  onClick={() => onRunTool(tool)}
                  data-testid={`specops-tool-${tool.tool_id}`}
                  title={tool.description}
                >
                  <span className="op-label">{tool.category}</span>
                  <span className="op-value">{tool.name}</span>
                  <span className="insp-row">
                    {tool.method} · {tool.license}
                  </span>
                </button>
              ))}
            </div>
          )}

          <p className="panel-note" data-testid="toolbar-dispatch-hint">
            {disabled
              ? "Dispatching…"
              : "Click a tool to enqueue a run against this entity."}
          </p>
        </>
      )}
    </aside>
  );
}
