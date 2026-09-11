import { useEffect, useState } from "react";

import { OpsMetrics, fetchOpsMetrics } from "../lib/api";
import { OpsDashboardPage } from "../pages/OpsDashboardPage";

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
  if (!metrics) return <ErrorView error="No metrics available" onRetry={load} />;

  return <OpsDashboardPage metrics={metrics} onRefresh={load} />;
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
