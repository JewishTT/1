import { FormEvent, useState } from "react";

import { Connector, ReconPlan } from "../lib/api";

export interface ConnectorsState {
  connectors: Connector[];
  plans: ReconPlan[];
}

interface Props {
  connectors: Connector[];
  plans: ReconPlan[];
  register: (body: { name: string; source_types: string[] }) => Promise<void>;
  activate: (name: string) => Promise<void>;
  createPlan: (connectorName: string, investigationId: string) => Promise<void>;
  reload: () => void;
}

/**
 * Connector registry + recon-plan surface (T026, FR-008/FR-009).
 * SpiderFoot-style source connectors, reNgine-style recon plans.
 */
export function ConnectorsPage({
  connectors,
  plans,
  register,
  activate,
  createPlan,
  reload,
}: Props) {
  const [name, setName] = useState("");
  const [sourceTypes, setSourceTypes] = useState("HTTP");
  const [planFor, setPlanFor] = useState("");
  const [invId, setInvId] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  async function onSubmitRegister(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy("register");
    try {
      await register({ name: name.trim(), source_types: parseSourceTypes() });
      setName("");
    } finally {
      setBusy(null);
    }
  }

  function parseSourceTypes(): string[] {
    return sourceTypes
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  async function onActivate(connector: Connector) {
    setBusy(`activate:${connector.name}`);
    try {
      await activate(connector.name);
    } finally {
      setBusy(null);
    }
  }

  async function onSubmitPlan(e: FormEvent) {
    e.preventDefault();
    if (!planFor || !invId.trim()) return;
    setBusy(`plan:${planFor}`);
    try {
      await createPlan(planFor, invId.trim());
      setInvId("");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section data-testid="connectors-page">
      <h1>Connectors &amp; recon plans</h1>

      <form className="conn-form" onSubmit={onSubmitRegister} data-testid="register-form">
        <input
          data-testid="conn-name"
          type="text"
          placeholder="connector name (e.g. subdomains-http)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          data-testid="conn-sources"
          type="text"
          placeholder="source types (comma separated)"
          value={sourceTypes}
          onChange={(e) => setSourceTypes(e.target.value)}
        />
        <button type="submit" className="btn btn-primary" disabled={busy !== null || !name.trim()}>
          {busy === "register" ? "Registering…" : "Register"}
        </button>
        <button type="button" onClick={reload} className="btn btn-ghost btn-sm">
          Refresh
        </button>
      </form>

      <div className="conn-grid" data-testid="connector-list">
        {connectors.length === 0 && <p className="text-dim">No connectors registered yet.</p>}
        {connectors.map((c) => (
          <div key={c.connector_id} className="conn-card" data-testid="connector">
            <div>
              <div className="conn-name">
                {c.name} <span className="status-chip">{c.status}</span>
                {c.contract_compliant && <span className="status-chip ACTIVE">compliant</span>}
              </div>
              <div className="conn-meta">
                {c.connector_id} · {c.source_types.join(" + ") || "no source types"} · v{c.version}
                {" · "}
                {c.policy_id}
              </div>
            </div>
            <div className="conn-actions">
              <button
                type="button"
                className="btn btn-sm"
                title="Create recon plan for this connector"
                onClick={() => setPlanFor(c.name)}
              >
                Plan
              </button>
              {c.status !== "ACTIVE" && (
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  data-testid={`activate-${c.name}`}
                  disabled={busy === `activate:${c.name}`}
                  onClick={() => void onActivate(c)}
                >
                  {busy === `activate:${c.name}` ? "Activating…" : "Activate"}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {planFor && (
        <form className="conn-form" onSubmit={onSubmitPlan} data-testid="plan-form">
          <strong className="text-dim">Recon plan → {planFor}</strong>
          <input
            data-testid="plan-investigation"
            type="text"
            placeholder="investigation id"
            value={invId}
            onChange={(e) => setInvId(e.target.value)}
          />
          <button
            type="submit"
            className="btn btn-primary btn-sm"
            disabled={busy !== null || !invId.trim()}
          >
            {busy === `plan:${planFor}` ? "Starting…" : "Start plan"}
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPlanFor("")}>
            Cancel
          </button>
        </form>
      )}

      <h2 style={{ marginTop: "1.5rem" }}>Recon plans</h2>
      <ul className="plan-list" data-testid="plan-list">
        {plans.length === 0 && <p className="text-dim">No recon plans yet.</p>}
        {plans.map((p) => (
          <li key={p.plan_id} className="plan-item" data-testid="plan">
            <code>{p.plan_id}</code>{" "}
            <span className="status-chip">{p.status}</span>{" "}
            <span className="text-dim">
              inv <code>{p.investigation_id}</code> · connector{" "}
              {String(p.strategy.connector ?? "-")} · {p.task_ids.length} tasks
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}