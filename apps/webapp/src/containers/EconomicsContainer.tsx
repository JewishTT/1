import { useEffect, useState } from "react";

import { OpsMetrics, fetchOpsMetrics } from "../lib/api";
import { EconomicsPage } from "../pages/EconomicsPage";

export function EconomicsContainer() {
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

  if (loading)
    return (
      <section data-testid="loading-view" style={{ padding: "var(--xl, 1.25rem)" }}>
        <p>Balancing the ledger…</p>
      </section>
    );
  if (error)
    return (
      <section data-testid="error-view" style={{ padding: "var(--xl, 1.25rem)" }}>
        <p style={{ color: "var(--c-danger)" }}>Error: {error}</p>
        <button type="button" className="btn btn-sm" onClick={() => void load()}>
          Retry
        </button>
      </section>
    );
  if (!metrics) return null;

  return <EconomicsPage metrics={metrics} onRefresh={load} />;
}