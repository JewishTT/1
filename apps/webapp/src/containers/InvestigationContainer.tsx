import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { api, InvestigationView, OpsMetrics, fetchOpsMetrics } from "../lib/api";
import { EMPTY_METRICS, InvestigationMetrics, InvestigationPage } from "../pages/InvestigationPage";
import { ReviewContainer } from "./ReviewContainer";

/**
 * Adapt operational metrics + investigation metadata into the
 * InvestigationPage's InvestigationMetrics shape.
 *
 * Fields that the backend does not yet expose per-investigation
 * (interpretation / admission / knowledge counts, recrawl schedule)
 * are left at zero / placeholder pending full event-pipeline wiring.
 */
function adaptMetrics(inv: InvestigationView, ops: OpsMetrics | null): InvestigationMetrics {
  const maxLag = Object.values(ops?.lags_s ?? {}).reduce(
    (max, v) => Math.max(max, v),
    0,
  );
  const queueTotal = Object.values(ops?.queues ?? {}).reduce((a, v) => a + v, 0);

  return {
    objective: inv.name,
    acquisition: {
      qps: ops?.throughput_per_s ?? 0,
      queue: ops?.queues?.frontier ?? queueTotal,
      freshnessSec: maxLag,
    },
    interpretation: { documents: 0, mentions: 0, candidates: 0 },
    admission: { accepted: 0, rejected: 0, pendingApproval: 0 },
    knowledge: { entities: 0, assertions: 0, findings: 0 },
    recrawl: { intervalSec: 0, nextAt: "—" },
  };
}

export function InvestigationContainer() {
  const { id } = useParams<{ id: string }>();
  const [investigation, setInvestigation] = useState<InvestigationView | null>(null);
  const [metrics, setMetrics] = useState<InvestigationMetrics>(EMPTY_METRICS);
  const [pauseRequested, setPauseRequested] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) {
      setError("Investigation ID is required");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    Promise.all([api.getInvestigation(id), fetchOpsMetrics()])
      .then(([inv, ops]) => {
        setInvestigation(inv);
        setMetrics(adaptMetrics(inv, ops));
        setPauseRequested(inv.state === "PAUSED");
        setError(null);
      })
      .catch((err: Error) => {
        if (id === "0") {
          setError("No investigation is selected. Create one from the Investigations screen first.");
        } else {
          setError(err.message);
        }
      })
      .finally(() => setLoading(false));
  }, [id]);

  const handlePause = async () => {
    if (!investigation) return;
    try {
      await api.pauseInvestigation(investigation.investigation_id);
      setPauseRequested(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleResume = async () => {
    if (!investigation) return;
    try {
      await api.resumeInvestigation(investigation.investigation_id);
      setPauseRequested(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleUpdate = async (body: { policy_id?: string | null; objective?: string }) => {
    if (!investigation) return null;
    try {
      const updated = await api.updateInvestigation(
        investigation.investigation_id,
        body.objective?.trim()
          ? {
              policy_id: body.policy_id?.trim() || null,
              objective: JSON.parse(body.objective) as Record<string, unknown>,
            }
          : { policy_id: body.policy_id?.trim() || null },
      );
      setInvestigation(updated);
      setMetrics((m) => ({ ...m, objective: updated.name }));
      return null;
    } catch (err) {
      return err instanceof Error ? err.message : String(err);
    }
  };

  if (loading) return <LoadingView message="Loading investigation…" />;
  if (error) return <ErrorView error={error} />;
  if (!investigation) return <ErrorView error="Investigation not found" />;

  return (
    <>
      <InvestigationPage
        metrics={metrics}
        onPause={handlePause}
        onResume={handleResume}
        pauseRequested={pauseRequested}
        setPauseRequested={setPauseRequested}
      />
      <EditInvestigation investigation={investigation} onSave={handleUpdate} />
      <ReviewContainer investigationId={investigation.investigation_id} />
    </>
  );
}

function EditInvestigation({
  investigation,
  onSave,
}: {
  investigation: InvestigationView;
  onSave: (body: { policy_id?: string | null; objective?: string }) => Promise<string | null>;
}) {
  const [policyId, setPolicyId] = useState(investigation.policy_id ?? "");
  const [objective, setObjective] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  return (
    <div className="panel" data-testid="edit-investigation">
      <h2>Edit investigation</h2>
      <form
        className="conn-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setSaving(true);
          try {
            const err = await onSave({ policy_id: policyId || null, objective });
            setSaved(err ?? "Saved");
            if (!err) setObjective("");
          } finally {
            setSaving(false);
          }
        }}
      >
        <input
          data-testid="edit-policy"
          type="text"
          placeholder="policy id (e.g. policies/default)"
          value={policyId}
          onChange={(e) => setPolicyId(e.target.value)}
        />
        <input
          data-testid="edit-objective"
          type="text"
          placeholder='objective JSON, e.g. {"goal":"monitor"}'
          value={objective}
          onChange={(e) => setObjective(e.target.value)}
        />
        <button type="submit" className="btn btn-primary btn-sm" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
      </form>
      {saved && (
        <p className="dlq-note" data-testid="edit-status">
          {saved}
        </p>
      )}
    </div>
  );
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
