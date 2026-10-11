import { useCallback, useEffect, useState } from "react";

import { api, QuarantineRecord } from "../lib/api";
import { QuarantinePage } from "../pages/QuarantinePage";
import { EmptyState, ErrorView, LoadingView } from "../ui/Feedback";
import { Button } from "../ui/Button";

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
  // Reached once loading is false and error is null, so the request *succeeded* and the
  // payload was null. "Loading…" here was a claim about a request that had already finished,
  // and it rendered forever with no retry. An absent answer is an absent answer.
  if (!records)
    return (
      <EmptyState
        testId="quarantine-empty"
        title="Nothing returned"
        description="The quarantine endpoint answered, but with no records. That is not the same as an empty queue, and it is not an error either."
        action={
          <Button size="sm" variant="ghost" onClick={() => void load()}>
            Ask again
          </Button>
        }
      />
    );

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
