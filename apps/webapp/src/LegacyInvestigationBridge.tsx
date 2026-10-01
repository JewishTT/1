import { useEffect, useState } from "react";

import { api, fetchOpsMetrics } from "./lib/api";
import { adaptMetrics } from "./containers/InvestigationContainer";
import { EMPTY_METRICS, InvestigationMetrics, InvestigationPage } from "./pages/InvestigationPage";
import { useQuery } from "@tanstack/react-query";

/**
 * Legacy investigation content, mounted inside the UI 2.0 Overview canvas (§10).
 *
 * §97: legacy routes become thin wrappers. This is the wrapper. It fetches
 * exactly what `InvestigationContainer` fetches, adapts with the very same
 * `adaptMetrics`, and renders the very same `InvestigationPage` with the same
 * props. No behaviour is reimplemented and no probe is duplicated.
 *
 * `InvestigationContainer` keeps its own route and its own tests; the two never
 * import each other.
 */
export function InvestigationContentBridge({ id }: { id: string }) {
  const [metrics, setMetrics] = useState<InvestigationMetrics>(EMPTY_METRICS);
  const [pauseRequested, setPauseRequested] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const investigation = useQuery({
    queryKey: ["workspace", "investigation-page", id],
    queryFn: () => api.getInvestigation(id),
    enabled: id !== "" && id !== "0",
  });

  const ops = useQuery({
    queryKey: ["workspace", "ops-metrics"],
    queryFn: fetchOpsMetrics,
    staleTime: 15_000,
  });

  useEffect(() => {
    if (!investigation.data) return;
    setMetrics(adaptMetrics(investigation.data, ops.data ?? null));
    setPauseRequested(investigation.data.state === "PAUSED");
  }, [investigation.data, ops.data]);

  useEffect(() => {
    const failure = investigation.error ?? ops.error;
    if (!failure) {
      setError(null);
      return;
    }
    setError(failure instanceof Error ? failure.message : String(failure));
  }, [investigation.error, ops.error]);

  if (investigation.isPending && ops.isPending) {
    return (
      <div className="ui-root" data-testid="investigation-content-loading">
        <p className="ui-body">Loading investigation…</p>
      </div>
    );
  }

  if (error !== null) {
    return (
      <div className="ui-root" data-testid="investigation-content-error">
        <p className="ui-insp-unreported">Error: {error}</p>
      </div>
    );
  }

  const handlePause = async () => {
    try {
      await api.pauseInvestigation(id);
      setPauseRequested(true);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  const handleResume = async () => {
    try {
      await api.resumeInvestigation(id);
      setPauseRequested(false);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  return (
    <InvestigationPage
      metrics={metrics}
      onPause={handlePause}
      onResume={handleResume}
      pauseRequested={pauseRequested}
      setPauseRequested={setPauseRequested}
    />
  );
}