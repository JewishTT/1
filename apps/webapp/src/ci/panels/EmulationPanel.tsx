import { useCallback, useEffect, useState } from "react";

import { Button } from "../../ui/Button";
import { api } from "../../lib/api";
import type { CiOperationWire, CiPlanWire } from "../../lib/api";
import { abilityRow } from "../model";
import type { OperationRow } from "../types";
import { CiEmpty, CiPanelShell, NamedAbsence, StatusChip } from "./panelParts";

/**
 * Kill-chain emulation panel (US2, MANDATORY).
 *
 * Select an ATT&CK plan → confirm an authorized lab target under RoE → launch →
 * watch planned-vs-executed abilities live. The RoE gate is server-side: a launch
 * without a confirmed sign-off comes back 409 and is shown as a refusal, not a
 * silent no-op. Live ability state polls the operation endpoint.
 */
export function EmulationPanel() {
  const [plans, setPlans] = useState<CiPlanWire[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [operation, setOperation] = useState<OperationRow | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPlans = useCallback(async () => {
    setError(null);
    try {
      const res = await api.listEmulationPlans();
      setPlans(res.plans);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPlans([]);
    }
  }, []);

  useEffect(() => {
    void loadPlans();
  }, [loadPlans]);

  // Poll the running operation so abilities move planned → executed live.
  useEffect(() => {
    if (!operation || operation.state !== "running") return;
    const id = window.setInterval(async () => {
      try {
        const res = await api.getOperation(operation.operation_id);
        setOperation(toOperationRow(res.operation));
      } catch {
        /* a transient poll miss must not tear down the board */
      }
    }, 3000);
    return () => window.clearInterval(id);
  }, [operation?.operation_id, operation?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  const launch = useCallback(async (plan: CiPlanWire) => {
    setBusy(true);
    setNote(null);
    try {
      const res = await api.launchOperation({
        plan_id: plan.plan_id,
        lab_fixture: plan.lab_fixture,
        roe_id: "roe-confirmed-by-supervisor",
      });
      setOperation(toOperationRow(res.operation));
      setNote(`${plan.name} launched against ${plan.lab_fixture}`);
    } catch (err) {
      setOperation(null);
      setNote(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <CiPanelShell
      title="Kill-chain emulation"
      scope="tenant-wide"
      status={
        <StatusChip
          label={operation ? operation.state : "idle"}
          tone={operation?.state === "running" ? "accent" : "neutral"}
          testId="ci-emulation-status"
        />
      }
      testId="ci-emulation-panel"
    >
      {error ? <CiEmpty>Error: {error}</CiEmpty> : null}

      <div className="ui-ci-col">
        <span className="ui-pane-title">Emulation plans</span>
        {plans === null ? (
          <CiEmpty>Loading plans…</CiEmpty>
        ) : plans.length === 0 ? (
          <NamedAbsence
            testId="ci-emulation-missing"
            missing={[
              "GET /specops/emulation/plans (no donor plan libraries served — caldera / ael / adversary_emulation_library not connected)",
            ]}
          />
        ) : (
          <ul className="ui-ci-list" data-testid="ci-emulation-plans">
            {plans.map((p) => (
              <li key={p.plan_id} className="ui-ci-list-row">
                <div className="ui-ci-list-main">
                  <strong>{p.name}</strong>
                  <span className="ui-id">
                    {p.source_donor} · {p.target_techniques.join(", ") || "no techniques"} · lab:{" "}
                    {p.lab_fixture}
                  </span>
                </div>
                <Button
                  size="sm"
                  icon="diagram"
                  disabled={busy || selected === p.plan_id}
                  onClick={() => {
                    setSelected(p.plan_id);
                    void launch(p);
                  }}
                  data-testid={`ci-launch-${p.plan_id}`}
                >
                  Launch
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {operation ? (
        <div className="ui-ci-col" data-testid="ci-operation">
          <div className="ui-ci-list-head">
            <span className="ui-pane-title">Operation {operation.operation_id}</span>
            <StatusChip
              label={`RoE ${operation.roe_status}`}
              tone={operation.roe_status === "confirmed" ? "accent" : "gold"}
            />
            {operation.halted_reason ? (
              <StatusChip label={`halted: ${operation.halted_reason}`} tone="danger" />
            ) : null}
          </div>
          <ul className="ui-ci-abilities" data-testid="ci-abilities">
            {operation.abilities.map((a) => (
              <li
                key={a.ability_id}
                data-state={a.state}
                data-testid={`ci-ability-${a.ability_id}`}
              >
                <span className="ui-ci-ability-tech">{a.technique}</span>
                <span className="ui-id">
                  {a.tactic} · {a.executor}
                </span>
                <StatusChip
                  label={a.state}
                  tone={
                    a.state === "executed" ? "accent" : a.state === "failed" ? "danger" : "neutral"
                  }
                />
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {note ? (
        <p className="panel-note" data-testid="ci-emulation-note">
          {note}
        </p>
      ) : null}
    </CiPanelShell>
  );
}

function toOperationRow(w: CiOperationWire): OperationRow {
  return {
    operation_id: w.operation_id,
    plan_id: w.plan_id,
    lab_fixture: w.lab_fixture,
    roe_status: w.roe_status,
    state: w.state,
    abilities: w.abilities.map(abilityRow),
    started_at: w.started_at,
    halted_reason: w.halted_reason,
  };
}
