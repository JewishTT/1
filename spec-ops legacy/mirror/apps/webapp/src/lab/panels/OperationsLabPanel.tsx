import { useEffect, useState } from "react";

import { api, type CiPlanWire, type LabOverviewWire } from "../../lib/api";
import { Input } from "../../ui/Input";
import { shortId } from "../model";
import { labErrorText, useLabAction } from "../useLabAction";
import { LabActionButton, LabChip, LabNote, LabPanelShell } from "./labParts";

export function OperationsLabPanel({
  data,
  refresh,
}: {
  data: LabOverviewWire;
  refresh: () => Promise<void>;
}) {
  const { busy, note, setNote, run } = useLabAction(refresh);
  const [plans, setPlans] = useState<CiPlanWire[]>([]);
  const [planId, setPlanId] = useState("");
  const [roeId, setRoeId] = useState("");
  const [campaignId, setCampaignId] = useState("");
  const [operationId, setOperationId] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .listEmulationPlans()
      .then((res) => {
        if (cancelled) return;
        setPlans(res.plans);
        if (res.plans[0]) setPlanId(res.plans[0].plan_id);
      })
      .catch((err) => {
        if (!cancelled) setNote(`Caldera/AEL plans unavailable: ${labErrorText(err)}`);
      });
    return () => {
      cancelled = true;
    };
  }, [setNote]);

  const launch = () =>
    run(
      () =>
        api.labLaunchOperation({
          plan_id: planId,
          lab_fixture: "specops/lab-target",
          roe_id: roeId,
        }),
      "Operation launched against the lab fixture only.",
    );

  const link = () =>
    run(
      () => api.labLinkAssessment({ campaign_id: campaignId, operation_id: operationId }),
      "Assessment linked. Report figures can now name the operation's abilities.",
    );

  return (
    <LabPanelShell
      title="Operations (Caldera / AEL spine)"
      status={<LabChip label={`${data.operations.length} operation(s)`} />}
      testId="lab-operations-panel"
    >
      <div className="lab-grid">
        <div className="ui-ci-col">
          <span className="ui-pane-title">Launch plan</span>
          <label className="ui-field-label" htmlFor="lab-plan-id">
            Donor plan
          </label>
          <select
            id="lab-plan-id"
            className="ui-input"
            value={planId}
            onChange={(e) => setPlanId(e.target.value)}
            data-testid="lab-plan-id"
          >
            {plans.length === 0 ? <option value="">no plan loaded</option> : null}
            {plans.map((plan) => (
              <option key={plan.plan_id} value={plan.plan_id}>
                {plan.plan_id} · {plan.source_donor}
              </option>
            ))}
          </select>
          <Input
            label="RoE id"
            value={roeId}
            onChange={(e) => setRoeId(e.target.value)}
            placeholder="recorded sign-off id"
            data-testid="lab-operation-roe"
          />
          <span className="ui-id">lab_fixture is pinned to specops/lab-target; other fixtures are refused.</span>
          <LabActionButton
            onClick={() => void launch()}
            disabled={busy || !planId}
            testId="lab-launch-operation"
          >
            Launch operation
          </LabActionButton>
        </div>

        <div className="ui-ci-col">
          <span className="ui-pane-title">Link assessment</span>
          <label className="ui-field-label" htmlFor="lab-campaign-link">
            Campaign
          </label>
          <select
            id="lab-campaign-link"
            className="ui-input"
            value={campaignId}
            onChange={(e) => setCampaignId(e.target.value)}
            data-testid="lab-campaign-link"
          >
            <option value="">select campaign</option>
            {data.campaigns.map((campaign) => (
              <option key={campaign.campaign_id} value={campaign.campaign_id}>
                {campaign.name} · {campaign.campaign_id}
              </option>
            ))}
          </select>
          <label className="ui-field-label" htmlFor="lab-operation-link">
            Operation
          </label>
          <select
            id="lab-operation-link"
            className="ui-input"
            value={operationId}
            onChange={(e) => setOperationId(e.target.value)}
            data-testid="lab-operation-link"
          >
            <option value="">select operation</option>
            {data.operations.map((operation) => (
              <option key={operation.operation_id} value={operation.operation_id}>
                {operation.operation_id} · {operation.plan_id}
              </option>
            ))}
          </select>
          <LabActionButton
            onClick={() => void link()}
            disabled={busy || !campaignId || !operationId}
            testId="lab-link-assessment"
          >
            Link operation to campaign
          </LabActionButton>
        </div>
      </div>

      <div className="ui-ci-col" data-testid="lab-operation-list">
        {data.operations.length === 0 ? <p className="panel-note">No operation yet.</p> : null}
        {data.operations.map((operation) => (
          <div key={operation.operation_id} className="ui-ci-col" data-testid={`lab-operation-${operation.operation_id}`}>
            <div className="ui-ci-list-head">
              <span className="ui-pane-title">{shortId(operation.operation_id)}</span>
              <LabChip label={operation.state} tone={operation.state === "complete" ? "accent" : "analytical"} />
              <LabChip label={`RoE ${operation.roe_status}`} tone={operation.roe_status === "confirmed" ? "accent" : "gold"} />
              <span className="ui-id">{operation.plan_id}</span>
            </div>
            <span className="ui-id">
              {operation.lab_fixture} · {operation.abilities.length} abilities · started {operation.started_at ?? "not started"}
            </span>
            <ul className="ui-ci-abilities">
              {operation.abilities.map((ability) => (
                <li key={ability.ability_id} data-state={ability.state === "executed" ? "executed" : "planned"}>
                  <span className="ui-ci-list-main">
                    <span className="ui-ci-ability-tech">
                      {ability.technique} · {ability.ability_id}
                    </span>
                    <span className="ui-id">
                      {ability.tactic} · {ability.executor}
                    </span>
                  </span>
                  <LabChip label={ability.state} tone={ability.state === "executed" ? "accent" : "neutral"} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <LabNote note={note} testId="lab-operations-note" />
    </LabPanelShell>
  );
}
