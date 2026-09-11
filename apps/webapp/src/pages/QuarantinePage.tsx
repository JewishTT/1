import { FormEvent, useState } from "react";

import { QuarantineRecord } from "../lib/api";

interface Props {
  records: QuarantineRecord[];
  tenantId: string;
  onReplay: (recordId: string) => Promise<string>; // returns base64 payload
  onReEvaluate: (recordId: string) => Promise<void>;
  onFilter: (topic: string) => void;
  reload: () => void;
}

/**
 * Dead-letter quarantine surface (T065, FR-023): preserved rejects are
 * listed, replayable byte-for-byte, or re-evaluable. Nothing is dropped
 * silently — every poisoned candidate stays recoverable (SC-007).
 */
export function QuarantinePage({
  records,
  tenantId,
  onReplay,
  onReEvaluate,
  onFilter,
  reload,
}: Props) {
  const [topic, setTopic] = useState("");
  const [replayed, setReplayed] = useState<{ id: string; payload: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  function onSubmitFilter(e: FormEvent) {
    e.preventDefault();
    onFilter(topic.trim());
  }

  async function replay(recordId: string) {
    setBusy(`replay:${recordId}`);
    try {
      const payload = await onReplay(recordId);
      setReplayed({ id: recordId, payload });
    } finally {
      setBusy(null);
    }
  }

  async function reEvaluate(recordId: string) {
    setBusy(`reeval:${recordId}`);
    try {
      await onReEvaluate(recordId);
      setReplayed(null);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section data-testid="quarantine-page">
      <h1>Quarantine (DLQ)</h1>

      <form className="dlq-toolbar" onSubmit={onSubmitFilter} data-testid="dlq-filter">
        <input
          data-testid="dlq-topic"
          type="text"
          placeholder="topic filter (empty = all)"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        />
        <button type="submit" className="btn btn-sm">
          Filter
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={reload}>
          Refresh
        </button>
        <span className="text-dim" style={{ fontSize: "0.7rem" }}>
          tenant {tenantId} · {records.length} record(s)
        </span>
      </form>

      <table className="dlq-table" data-testid="dlq-list">
        <thead>
          <tr>
            <th>Record</th>
            <th>Topic</th>
            <th>Reason</th>
            <th>Fingerprint</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {records.length === 0 && (
            <tr>
              <td colSpan={5} className="text-dim">
                No quarantined records.
              </td>
            </tr>
          )}
          {records.map((r) => (
            <tr key={r.record_id} data-testid="dlq-record">
              <td>
                <code>{r.record_id}</code>{" "}
                {r.preserved ? <span className="status-chip ACTIVE">preserved</span> : null}
              </td>
              <td>
                <code>{r.topic}</code>
                <div className="text-dim">partition {r.partition}</div>
              </td>
              <td>{r.reason}</td>
              <td>
                <code>{r.fingerprint}</code>
              </td>
              <td>
                <div className="dlq-actions">
                  <button
                    type="button"
                    className="btn btn-sm"
                    data-testid={`replay-${r.record_id}`}
                    disabled={busy !== null}
                    onClick={() => void replay(r.record_id)}
                  >
                    {busy === `replay:${r.record_id}` ? "Replaying…" : "Replay"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    data-testid={`reeval-${r.record_id}`}
                    disabled={busy !== null}
                    onClick={() => void reEvaluate(r.record_id)}
                  >
                    {busy === `reeval:${r.record_id}` ? "Re-evaluating…" : "Re-evaluate"}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {replayed && (
        <div className="dlq-payload" data-testid="dlq-payload">
          <div className="text-dim" style={{ marginBottom: "0.4rem" }}>
            replayed <code>{replayed.id}</code> — preserved payload (base64):
          </div>
          {replayed.payload}
        </div>
      )}

      <p className="dlq-note">
        Replay returns the original payload byte-for-byte; re-evaluation keeps the
        preservation guarantee (I-11) and marks the record rejected/accepted.
      </p>
    </section>
  );
}