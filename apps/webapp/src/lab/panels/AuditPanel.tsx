import type { LabOverviewWire } from "../../lib/api";
import { LabChip, LabPanelShell } from "./labParts";

export function AuditPanel({ data }: { data: LabOverviewWire }) {
  return (
    <LabPanelShell
      title="Audit & evidence trail"
      status={<LabChip label={`${data.audit.length} recent row(s)`} tone="analytical" />}
      testId="lab-audit-panel"
    >
      <p className="panel-note">
        Append-only, hash-chained. A captured value is never written to a row; each row commits to
        the previous row's digest.
      </p>
      <table className="ui-table" data-testid="lab-audit-events">
        <thead>
          <tr>
            <th>Seq</th>
            <th>Action</th>
            <th>Object</th>
            <th>Outcome</th>
            <th>At</th>
            <th>Row hash</th>
          </tr>
        </thead>
        <tbody>
          {data.audit.map((event) => (
            <tr key={event.seq}>
              <td>{event.seq}</td>
              <td>{event.action}</td>
              <td className="ui-id">
                {event.object_type} · {event.object_id}
              </td>
              <td>{event.outcome}</td>
              <td className="ui-id">{event.at}</td>
              <td className="ui-id">{event.row_hash.slice(0, 16)}…</td>
            </tr>
          ))}
        </tbody>
      </table>
    </LabPanelShell>
  );
}
