import { useCallback, useEffect, useMemo, useState } from "react";

import type { SpecOpsGraphResponse, ToolRun, ToolSpec } from "../lib/api";
import { api } from "../lib/api";
import type { EntityToolbarTarget } from "../lib/specopsGraph";
import { graphToCytoscape } from "../lib/specopsGraph";
import { SpecOpsPage } from "../pages/SpecOpsPage";

export function SpecOpsContainer() {
  const [graph, setGraph] = useState<SpecOpsGraphResponse | null>(null);
  const [tools, setTools] = useState<ToolSpec[]>([]);
  const [selectedEntity, setSelectedEntity] = useState<EntityToolbarTarget | null>(null);
  const [lastRun, setLastRun] = useState<ToolRun | null>(null);
  const [runNote, setRunNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [graphRes, toolsRes] = await Promise.all([api.specOpsGraph(), api.listTools()]);
      setGraph(graphRes);
      setTools(toolsRes.tools);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onSelect = useCallback((entity: EntityToolbarTarget | null) => {
    setSelectedEntity(entity);
    setLastRun(null);
    setRunNote(null);
  }, []);

  const onRunTool = useCallback(
    async (tool: ToolSpec) => {
      if (!selectedEntity) return;
      setBusy(true);
      setRunNote(null);
      try {
        const res = await api.enqueueTool(tool.tool_id, {
          entity_type: selectedEntity.entity_type,
          entity_value: selectedEntity.entity_value,
          entity_id: selectedEntity.id,
        });
        setLastRun(res.run);
        setRunNote(`${tool.name} enqueued → ${res.run.status}`);
      } catch (err) {
        setLastRun(null);
        setRunNote(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [selectedEntity],
  );

  const elements = useMemo(() => (graph ? graphToCytoscape(graph) : []), [graph]);

  if (loading) return <LoadingView message="Loading SpecOps graph…" />;
  if (error) return <ErrorView error={error} onRetry={load} />;
  if (!graph) return <ErrorView error="No entity graph available" onRetry={load} />;

  return (
    <SpecOpsPage
      elements={elements}
      entityCount={graph.nodes.length}
      edgeCount={graph.edges.length}
      toolsCount={tools.length}
      selectedEntity={selectedEntity}
      tools={tools}
      busy={busy}
      lastRun={lastRun}
      runNote={runNote}
      onSelect={onSelect}
      onRunTool={(tool) => void onRunTool(tool)}
    />
  );
}

function LoadingView({ message }: { message: string }) {
  return (
    <section data-testid="loading-view" style={{ padding: "var(--xl, 1.25rem)" }}>
      <p>{message}</p>
    </section>
  );
}

function ErrorView({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <section data-testid="error-view" style={{ padding: "var(--xl, 1.25rem)" }}>
      <p style={{ color: "var(--c-danger)" }}>Error: {error}</p>
      <button
        type="button"
        onClick={() => void onRetry()}
        style={{
          marginTop: "0.5rem",
          padding: "0.4rem 0.8rem",
          background: "var(--c-surface-2)",
          border: "1px solid var(--c-border)",
          borderRadius: "0.3rem",
          color: "var(--c-text)",
          cursor: "pointer",
        }}
      >
        Retry
      </button>
    </section>
  );
}