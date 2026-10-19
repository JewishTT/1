import { useCallback, useState } from "react";

import { Input } from "../../ui/Input";
import { api } from "../../lib/api";
import type { CiForensicsWire } from "../../lib/api";
import { forensicsComparison } from "../model";
import type { ForensicsRow } from "../types";
import { CiEmpty, CiPanelShell, NamedAbsence, StatusChip } from "./panelParts";

/**
 * APT forensics panel (US6).
 *
 * For a completed emulation run, compare the telemetry the plan EXPECTED against
 * the observations the platform ACTUALLY recorded. An unmatched expectation is a
 * detection gap and is listed, never silently dropped (FR-010). ATT&CK coverage
 * is shown as a per-technique covered/not-covered readout.
 */
export function ForensicsPanel() {
  const [operationId, setOperationId] = useState("");
  const [forensics, setForensics] = useState<ForensicsRow | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async () => {
    if (!operationId.trim()) return;
    setBusy(true);
    setNote(null);
    try {
      const res = await api.getForensics(operationId.trim());
      setForensics(toForensicsRow(res.forensics));
    } catch (err) {
      setForensics(null);
      setNote(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [operationId]);

  return (
    <CiPanelShell title="APT forensics" scope="tenant-wide" testId="ci-forensics-panel">
      <div className="ui-ci-col">
        <span className="ui-pane-title">Completed operation</span>
        <Input
          value={operationId}
          onChange={(e) => setOperationId(e.target.value)}
          placeholder="operation id"
          aria-label="Operation id"
          data-testid="ci-forensics-op-input"
        />
        <button
          type="button"
          className="ui-btn"
          data-size="sm"
          disabled={busy}
          onClick={() => void run()}
          data-testid="ci-forensics-run"
        >
          Compare expected vs actual
        </button>
      </div>

      {forensics ? (
        <div className="ui-ci-col" data-testid="ci-forensics">
          <ul className="ui-ci-list" data-testid="ci-forensics-comparison">
            {forensics.comparison.map((c) => (
              <li key={c.ability_id} data-status={c.status} className="ui-ci-list-row">
                <div className="ui-ci-list-main">
                  <strong>{c.technique}</strong>
                  <span className="ui-id">expected: {c.expected}</span>
                  <span className="ui-id">
                    actual: {c.actual.length > 0 ? c.actual.join(", ") : "—"}
                  </span>
                </div>
                <StatusChip
                  label={c.status === "gap" ? "detection gap" : "corroborated"}
                  tone={c.status === "gap" ? "danger" : "accent"}
                  testId={`ci-forensics-${c.status}`}
                />
              </li>
            ))}
          </ul>
          <div className="ui-ci-col">
            <span className="ui-pane-title">ATT&CK coverage</span>
            <ul className="ui-ci-coverage" data-testid="ci-coverage">
              {forensics.coverage.map((c) => (
                <li key={c.technique} data-covered={c.covered}>
                  <span>{c.technique}</span>
                  <StatusChip
                    label={c.covered ? "covered" : "gap"}
                    tone={c.covered ? "accent" : "danger"}
                  />
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : (
        <CiEmpty>Enter a completed operation id to compare expected vs actual telemetry.</CiEmpty>
      )}

      {note ? (
        <p className="panel-note" data-testid="ci-forensics-note">
          {note}
        </p>
      ) : null}
      <NamedAbsence testId="ci-forensics-missing" missing={[]} />
    </CiPanelShell>
  );
}

function toForensicsRow(w: CiForensicsWire): ForensicsRow {
  const comparison = w.comparison.map(forensicsComparison);
  return {
    operation_id: w.operation_id,
    comparison,
    coverage: deriveCoverage(comparison),
  };
}

/** Coverage is derived from the comparison, not served separately — honest by construction. */
function deriveCoverage(comparison: ForensicsRow["comparison"]): ForensicsRow["coverage"] {
  const byTech = new Map<string, boolean>();
  for (const c of comparison) {
    const covered = c.status === "corroborated";
    byTech.set(c.technique, (byTech.get(c.technique) ?? false) || covered);
  }
  return [...byTech.entries()].map(([technique, covered]) => ({ technique, covered }));
}
