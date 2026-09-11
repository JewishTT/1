import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { api, Correlation, EntityView } from "../lib/api";
import { EntityViewPage } from "../pages/EntityViewPage";

export function EntityViewContainer() {
  const { id } = useParams<{ id: string }>();
  const [entity, setEntity] = useState<(EntityView & { tenant_id: string }) | null>(null);
  const [correlations, setCorrelations] = useState<Correlation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) {
      setError("Entity ID is required");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    api
      .getEntity(id)
      .then((entityData) => {
        setEntity(entityData);
        return api.getCorrelations(id);
      })
      .then((corrData) => {
        setCorrelations(corrData.correlations);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <LoadingView message="Loading entity…" />;
  if (error) return <ErrorView error={error} />;
  if (!entity) return <ErrorView error="Entity not found" />;

  const entityWithCorrelations: EntityView = {
    ...entity,
    correlations: entity.correlations ?? correlations,
  };

  return <EntityViewPage entity={entityWithCorrelations} />;
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
