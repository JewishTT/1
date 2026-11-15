import { useCallback, useEffect, useMemo, useState } from "react";

import type { SpecOpsGraphResponse, ToolRun, ToolSpec } from "../lib/api";
import { api } from "../lib/api";
import type { EntityToolbarTarget } from "../lib/specopsGraph";
import { graphToCytoscape } from "../lib/specopsGraph";
import { SpecOpsPage } from "../pages/SpecOpsPage";
import { EmptyState, ErrorView, LoadingView } from "../ui/Feedback";
import { Button } from "../ui/Button";

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
  // Was an ErrorView claiming failure for a successful null payload.
  if (!graph)
    return (
      <EmptyState
        testId="specops-graph-empty"
        title="No entity graph"
        description="The graph endpoint answered with no projection. There is no graph to draw yet, and no failure to investigate."
        action={
          <Button size="sm" variant="ghost" onClick={() => void load()}>
            Ask again
          </Button>
        }
      />
    );

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
