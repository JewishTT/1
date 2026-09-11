import { useCallback, useEffect, useState } from "react";

import { api, QuarantineRecord } from "../lib/api";
import { QuarantinePage } from "../pages/QuarantinePage";

export function QuarantineContainer() {
  const [records, setRecords] = useState<QuarantineRecord[] | null>(null);
  const [tenantId, setTenantId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (topic?: string) => {
    setLoading(true);
    try {
      const res = await api.listQuarantine(topic);
      setRecords(res.records);
      setTenantId(res.tenant_id);
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

  if (loading) return <LoadingView message="Loading quarantine…" />;
  if (error) return <ErrorView error={error} onRetry={() => load()} />;
  if (!records) return <LoadingView message="Loading…" />;

  return (
    <QuarantinePage
      records={records}
      tenantId={tenantId}
      onReplay={async (recordId) => {
        const res = await api.replayQuarantined(recordId);
        return res.base64_payload;
      }}
      onReEvaluate={async (recordId) => {
        await api.reEvaluateQuarantined(recordId);
        await load();
      }}
      onFilter={(topic) => void load(topic)}
      reload={() => load()}
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