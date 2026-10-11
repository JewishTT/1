import { useCallback, useEffect, useState } from "react";

import { api, Connector, ReconPlan } from "../lib/api";
import { ConnectorsPage } from "../pages/ConnectorsPage";
import { EmptyState, ErrorView, LoadingView } from "../ui/Feedback";
import { Button } from "../ui/Button";

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
  // Same reasoning as the quarantine screen: settled request, null payload. Calling that
  // "Loading…" left the analyst watching a spinner for something that had already happened.
  if (!connectors || !plans)
    return (
      <EmptyState
        testId="connectors-empty"
        title="Nothing returned"
        description="The connector endpoints answered, but with no catalogue. Nothing has been registered yet, or the registry is genuinely empty."
        action={
          <Button size="sm" variant="ghost" onClick={() => void load()}>
            Ask again
          </Button>
        }
      />
    );

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
