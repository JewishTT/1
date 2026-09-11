import { useCallback, useEffect, useState } from "react";

import { api, Connector, ReconPlan } from "../lib/api";
import { ConnectorsPage } from "../pages/ConnectorsPage";

export function ConnectorsContainer() {
  const [connectors, setConnectors] = useState<Connector[] | null>(null);
  const [plans, setPlans] = useState<ReconPlan[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, p] = await Promise.all([api.listConnectors(), api.listReconPlans()]);
      setConnectors(c.connectors);
      setPlans(p.plans);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <LoadingView message="Loading connectors…" />;
  if (error) return <ErrorView error={error} onRetry={load} />;
  if (!connectors || !plans) return <LoadingView message="Loading…" />;

  return (
    <ConnectorsPage
      connectors={connectors}
      plans={plans}
      register={async (body) => {
        await api.registerConnector(body);
        await load();
      }}
      activate={async (name) => {
        await api.activateConnector(name);
        await load();
      }}
      createPlan={async (connectorName, investigationId) => {
        await api.createReconPlan(connectorName, { investigation_id: investigationId });
        await load();
      }}
      reload={load}
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