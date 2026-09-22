import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { api, Correlation, EntityView } from "../lib/api";
import { buildEntityGraphElements } from "../lib/entityGraph";
import { usePipelineStream } from "../lib/stream";
import { EntityViewPage } from "../pages/EntityViewPage";

export function EntityViewContainer() {
  const { id } = useParams<{ id: string }>();
  const [entity, setEntity] = useState<(EntityView & { tenant_id: string }) | null>(null);
  const [correlations, setCorrelations] = useState<Correlation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (entityId: string) => {
    setLoading(true);
    setError(null);
    try {
      const [entityData, corrData] = await Promise.all([
        api.getEntity(entityId),
        api.getCorrelations(entityId),
      ]);
      setEntity(entityData);
      setCorrelations(corrData.correlations);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!id) {
      setError("Entity ID is required");
      setLoading(false);
      return;
    }
    void refresh(id);
  }, [id, refresh]);

  // Live reactivity: a review recorded (or any pipeline mutation of this
  // entity) refreshes the detail + graph without a manual reload.
  usePipelineStream((event) => {
    if (event.event === "entity.updated") {
      const payload = event.data as { entity_id?: string } | null;
      if (id && payload?.entity_id === id) void refresh(id);
    }
  });

  if (loading) return <LoadingView message="Loading entity…" />;
  if (error) return <ErrorView error={error} />;
  if (!entity) return <ErrorView error="Entity not found" />;

  const entityWithCorrelations: EntityView = {
    ...entity,
    correlations: entity.correlations ?? correlations,
  };
  const graphElements = buildEntityGraphElements(entityWithCorrelations, correlations);

  return <EntityViewPage entity={entityWithCorrelations} graphElements={graphElements} />;
}

function LoadingView({ message }: { message: string }) {
  return (
    <section data-testid="loading-view" style={{ padding: "var(--xl, 1.25rem)" }}>
      <p>{message}</p>
    </section>
  );
}

function ErrorView({ error }: { error: string }) {
  return (
    <section data-testid="error-view" style={{ padding: "var(--xl, 1.25rem)" }}>
      <p style={{ color: "var(--c-danger)" }}>Error: {error}</p>
    </section>
  );
}