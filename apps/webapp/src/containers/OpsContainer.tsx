import { useEffect, useState } from "react";

import { OpsMetrics, fetchOpsMetrics } from "../lib/api";
import { OpsDashboardPage } from "../pages/OpsDashboardPage";
import { EmptyState, ErrorView, LoadingView } from "../ui/Feedback";
import { Button } from "../ui/Button";

export function OpsContainer() {
  const [metrics, setMetrics] = useState<OpsMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await fetchOpsMetrics();
      setMetrics(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  if (loading) return <LoadingView message="Loading metrics…" />;
  if (error) return <ErrorView error={error} onRetry={load} />;
  // Was an ErrorView, which asserts the request failed. It did not: metrics came back null.
  // Reporting a successful empty answer as a failure sends the analyst hunting for an outage
  // that is not there.
  if (!metrics)
    return (
      <EmptyState
        testId="ops-empty"
        title="No metrics served"
        description="The metrics endpoint answered without a payload. The platform has nothing measured to show yet — which is not the same as an error."
        action={
          <Button size="sm" variant="ghost" onClick={() => void load()}>
            Ask again
          </Button>
        }
      />
    );

  return <OpsDashboardPage metrics={metrics} onRefresh={load} />;
}
