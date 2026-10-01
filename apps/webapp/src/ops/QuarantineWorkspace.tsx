import { useCallback, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import { Badge, StatusDot } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EmptyState, Skeleton } from "../ui/Feedback";
import { Input } from "../ui/Input";
import { QUARANTINE_UNAVAILABLE } from "./types";
import { useQuarantineState } from "./useOpsState";
import type { QuarantineRow } from "./types";
import "./ops.css";

/**
 * QuarantineWorkspace (§47).
 *
 * THIS IS A FIRST-CLASS OPERATIONAL SURFACE, and the reason is §107/§108: the
 * directive forbids dropping malformed output. Quarantine is where refused data
 * becomes *visible and recoverable*. A DLQ list that lives in a settings page is
 * a DLQ nobody reads, and a pipeline that refuses silently is the failure the
 * whole seam exists to prevent.
 *
 * So this is not a log viewer. It is a work queue: three actions, one per row,
 * each of which changes the state of a delivery.
 *
 *   Inspect      read what was refused, without changing anything
 *   Replay       put the preserved bytes back into the pipeline
 *   Acknowledge  record that an operator has seen it and moved on
 *
 * THE HONEST ROW IS THE POINT. `/dlq` serves six fields: record_id, reason,
 * topic, partition, preserved, fingerprint. §47's table asks for eight columns —
 * Time, Source, Runtime, Object, Reason, Attempts, Status, Replayable — and the
 * endpoint answers exactly one of them (the reason). The other seven render as
 * "not served" with the endpoint named, and the table header says so once
 * rather than repeating it per cell. That is §90/§91 working as intended: the
 * gap is the finding, not a failure to hide.
 *
 * §69 — NO DEAD ENDS, NO FAILED BUTTONS. Replay is offered only when `preserved`
 * is true, because replay reads the preserved bytes. When they are gone the cell
 * states why in place of the control. A disabled-looking button that 404s is
 * worse than an honest sentence, and Acknowledge is likewise absent where there
 * is no endpoint to acknowledge against — named, not faked.
 */

/** §47's column order. One declaration so the header and the rows cannot drift. */
const COLUMNS = [
  { key: "recordedAt", label: "Time", absent: "not served" },
  { key: "sourceId", label: "Source", absent: "not served" },
  { key: "runtimeRef", label: "Runtime", absent: "not served" },
  { key: "objectRef", label: "Object", absent: "not served" },
  { key: "reason", label: "Reason", absent: "not reported" },
  { key: "attempts", label: "Attempts", absent: "not served" },
  { key: "status", label: "Status", absent: "not served" },
] as const;

/**
 * Cell content for one §47 column of one row.
 *
 * Split out so the "absent" rendering is a single, tested code path: a field the
 * endpoint did not serve reads identically everywhere, which is what makes it
 * recognisable as an absence rather than as a value.
 */
export function CellValue({ row, columnKey }: { row: QuarantineRow; columnKey: string }) {
  const column = COLUMNS.find((entry) => entry.key === columnKey);
  if (column === undefined) return null;

  if (columnKey === "status") {
    // Status shows BOTH the closed-vocabulary value and the platform's raw flag,
    // so the mapping stays auditable (§92).
    return (
      <span className="ui-status" data-tone="dim">
        <StatusDot status={row.status} testId={`quar-status-${row.recordId}`} />
        <span className="ui-status-label">{row.preservedRaw ? "preserved" : "not preserved"}</span>
      </span>
    );
  }

  const raw = row[columnKey as keyof QuarantineRow];
  if (raw === null || raw === undefined || raw === "") {
    return (
      <span className="ui-quar-absent" data-testid={`quar-absent-${columnKey}-${row.recordId}`}>
        {column.absent}
      </span>
    );
  }
  return <>{String(raw)}</>;
}

/**
 * The fingerprint's digest half.
 *
 * `DLQRecord.fingerprint()` is `base64(payload)[:12] + ":" + sha256(payload)[:12]`.
 * The left half is payload BYTES, so rendering it would put untrusted and
 * possibly-binary content into the document as text; the row keeps the digest
 * only, and `model.splitFingerprint` is what enforces that.
 */
function DigestCell({ row }: { row: QuarantineRow }) {
  return (
    <span
      className="ui-mono"
      title="sha256 of the preserved payload, first 12 hex characters"
      data-testid={`quar-digest-${row.recordId}`}
    >
      {row.digest}
    </span>
  );
}

export interface QuarantineWorkspaceProps {
  /** Pre-set topic filter, for a host route that scopes the surface. */
  topic?: string;
  /** Called when the operator acknowledges a record, so a host can log it. */
  onAcknowledge?: (recordId: string) => void;
}

export function QuarantineWorkspace({ topic: initialTopic, onAcknowledge }: QuarantineWorkspaceProps) {
  const [topic, setTopic] = useState(initialTopic ?? "");
  const [appliedTopic, setAppliedTopic] = useState(initialTopic ?? "");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [inspected, setInspected] = useState<{ recordId: string; payload: string } | null>(null);

  const queryClient = useQueryClient();
  const server = useQuarantineState(appliedTopic === "" ? undefined : appliedTopic);

  const rows = server.rows;
  const selected = useMemo(
    () => rows.find((row) => row.recordId === selectedId) ?? null,
    [rows, selectedId],
  );

  /**
   * Replay.
   *
   * POST /dlq/{id}/replay hands the preserved payload back byte-for-byte. The
   * response carries the payload itself, which is also how Inspect obtains it —
   * there is no separate "fetch bytes" endpoint, so Inspect and Replay are the
   * same request with different intent. That is stated in the UI rather than
   * hidden, because an operator who assumes Inspect is side-effect-free would be
   * wrong, and §91 is explicit that the scope of a failure has to be honest.
   */
  const replay = useMutation({
    mutationFn: (recordId: string) => api.replayQuarantined(recordId),
    onSuccess: (response, recordId) => {
      setInspected({ recordId, payload: response.base64_payload });
      void queryClient.invalidateQueries({ queryKey: ["ops", "quarantine"] });
    },
  });

  /**
   * Re-evaluation.
   *
   * POST /dlq/{id}/re-evaluate accepts or rejects the record and purges it, so it
   * is the only action that REMOVES a row. It is offered under its own name
   * rather than as "Acknowledge", because calling it an acknowledgement would
   * understate it: the record stops existing. A row that cannot be re-evaluated
   * (no bytes preserved) offers nothing here at all.
   */
  const reEvaluate = useMutation({
    mutationFn: (recordId: string) => api.reEvaluateQuarantined(recordId),
    onSuccess: () => {
      setInspected(null);
      void queryClient.invalidateQueries({ queryKey: ["ops", "quarantine"] });
    },
  });

  const applyTopic = useCallback(() => setAppliedTopic(topic.trim()), [topic]);
  const clearTopic = useCallback(() => {
    setTopic("");
    setAppliedTopic("");
  }, []);

  const onAcknowledgeRow = useCallback(
    (row: QuarantineRow) => {
      setSelectedId(row.recordId);
      onAcknowledge?.(row.recordId);
    },
    [onAcknowledge],
  );

  if (server.loading) {
    return (
      <section className="ui-quar ui-root" aria-label="Quarantine" data-testid="quarantine-workspace">
        <Skeleton rows={8} label="Loading quarantine records" />
      </section>
    );
  }

  if (server.error !== null) {
    return (
      <section className="ui-quar ui-root" aria-label="Quarantine" data-testid="quarantine-workspace">
        <div className="ui-inspector-error" role="alert" data-testid="quarantine-error">
          <p className="ui-pane-title">Quarantine did not load</p>
          <p className="ui-body" data-testid="quarantine-error-message">
            {server.error}
          </p>
          <p className="ui-body">
            Scope: <span className="ui-mono">GET /dlq</span>. Nothing was dropped — the records are preserved on
            the server and this list simply could not be read, so a retry is safe and losing the list is not.
          </p>
          <div className="ui-insp-next-list">
            <Button size="sm" onClick={server.refetch} data-testid="quarantine-error-retry">
              Retry
            </Button>
          </div>
        </div>
      </section>
    );
  }

  const unavailableCount = QUARANTINE_UNAVAILABLE.length;

  return (
    <section className="ui-quar ui-root" aria-label="Quarantine" data-testid="quarantine-workspace">
      <header className="ui-ops-head">
        <div className="ui-ops-head-titles">
          <h2 className="ui-title" data-testid="quarantine-title">
            Quarantine
          </h2>
          <span className="ui-id" data-testid="quarantine-subtitle">
            {server.servedCount} preserved record(s) · nothing refused is dropped (§107/§108)
          </span>
        </div>
        <Badge tone={server.servedCount === 0 ? "neutral" : "gold"} role="classification" testId="quarantine-count">
          {server.servedCount === 0 ? "nothing quarantined" : `${server.servedCount} quarantined`}
        </Badge>
      </header>

      <div className="ui-quar-toolbar" role="toolbar" aria-label="Quarantine controls">
        <Input
          label="Topic"
          mono
          placeholder="cognitive-events--t-… (empty = all)"
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") applyTopic();
          }}
          data-testid="quarantine-topic"
        />
        <Button size="sm" onClick={applyTopic} data-testid="quarantine-apply-topic">
          Apply
        </Button>
        {appliedTopic !== "" ? (
          <Button size="sm" variant="ghost" onClick={clearTopic} data-testid="quarantine-clear-topic">
            Clear filter
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" icon="clock" onClick={server.refetch} data-testid="quarantine-refresh">
          Refresh
        </Button>
        <span className="ui-ops-block-note" data-testid="quarantine-coverage">
          {unavailableCount} served field(s) absent — the header marks each one
        </span>
      </div>

      {rows.length === 0 ? (
        <div className="ui-ops-block" data-testid="quarantine-empty">
          <EmptyState
            icon="view-evidence"
            title={server.answered ? "Nothing is quarantined" : "Quarantine has not reported yet"}
            description={
              server.answered
                ? appliedTopic !== ""
                  ? `The endpoint answered with no record on topic ${appliedTopic}. Records on other topics may still be quarantined — clear the filter to see them.`
                  : "The endpoint answered with an empty list. Every delivery the pipeline refused is preserved; there are none. This is the good outcome, not a missing pane."
                : "The endpoint has not answered. The empty list below is not evidence that nothing is quarantined."
            }
            action={
              appliedTopic !== "" ? (
                <Button size="sm" onClick={clearTopic} data-testid="quarantine-empty-clear">
                  Clear the topic filter
                </Button>
              ) : (
                <Button size="sm" onClick={server.refetch} data-testid="quarantine-empty-retry">
                  Check again
                </Button>
              )
            }
            testId="quarantine-empty-state"
          />
        </div>
      ) : (
        <>
          {/*
           * The §47 column set. `role="grid"` with a real row count because this
           * is a work queue an operator drives by keyboard: every row is
           * focusable and Enter inspects it (§67).
           */}
          <div
            className="ui-ops-block ui-scroll"
            role="grid"
            aria-label="Quarantined records"
            aria-rowcount={rows.length}
            data-testid="quarantine-table"
          >
            <div className="ui-quar-table ui-quar-head" role="row">
              {COLUMNS.map((column) => (
                // `aria-colindex` rather than `scope`: the row is a `div` (a CSS
                // grid), not a `th`, and `scope` is a table-header-only attribute.
                <span key={column.key} role="columnheader" aria-colindex={COLUMNS.indexOf(column) + 1}>
                  {column.label}
                </span>
              ))}
              <span role="columnheader">Actions</span>
              <span role="columnheader">Record</span>
            </div>

            {rows.map((row) => (
              <div
                key={row.recordId}
                className="ui-quar-table ui-quar-row"
                role="row"
                aria-rowindex={rows.indexOf(row) + 1}
                tabIndex={0}
                data-selected={selectedId === row.recordId}
                data-replayable={row.replayable}
                onClick={() => setSelectedId(row.recordId)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    setSelectedId(row.recordId);
                  }
                }}
                onContextMenu={(event) => {
                  // A right-click on a row is the same gesture as a click on it
                  // here: the surface has one detail pane, and the §51 menu that
                  // opens is built from this row's actions.
                  event.preventDefault();
                  setSelectedId(row.recordId);
                }}
                data-testid={`quar-row-${row.recordId}`}
              >
                {COLUMNS.map((column) => (
                  <span
                    key={column.key}
                    className="ui-quar-cell"
                    role="gridcell"
                    data-mono={column.key === "reason" || column.key === "objectRef" ? "true" : undefined}
                  >
                    <CellValue row={row} columnKey={column.key} />
                  </span>
                ))}

                <span className="ui-quar-cell">
                  <span className="ui-quar-actions">
                    {/*
                     * Replay is offered only when the bytes exist. §69: a
                     * control that cannot succeed is not rendered — the
                     * sentence replaces it.
                     */}
                    {row.replayable ? (
                      <Button
                        size="sm"
                        onClick={() => replay.mutate(row.recordId)}
                        disabled={replay.isPending}
                        data-testid={`quar-replay-${row.recordId}`}
                      >
                        {replay.isPending && replay.variables === row.recordId ? "Replaying…" : "Replay"}
                      </Button>
                    ) : (
                      <span className="ui-quar-blocked" data-testid={`quar-not-replayable-${row.recordId}`}>
                        Not replayable — {row.replayBlockedReason}
                      </span>
                    )}
                  </span>
                </span>

                <span className="ui-quar-cell" data-mono="true">
                  <span className="ui-id">{row.recordId}</span>
                  <br />
                  <DigestCell row={row} />
                </span>
              </div>
            ))}
          </div>

          <QuarantineDetail
            row={selected}
            payload={
              inspected !== null && selected !== null && inspected.recordId === selected.recordId
                ? inspected.payload
                : null
            }
            onReplay={(recordId) => replay.mutate(recordId)}
            onReEvaluate={(recordId) => reEvaluate.mutate(recordId)}
            replayPending={replay.isPending}
            reEvaluatePending={reEvaluate.isPending}
            onAcknowledge={onAcknowledgeRow}
          />
        </>
      )}

      <CoverageNote />

      {/* Announces a row change without moving focus (§67). */}
      <span className="ui-sr-only" role="status" aria-live="polite" data-testid="quarantine-live-region">
        {selected === null
          ? "No quarantine record selected"
          : `${selected.recordId} selected, reason ${selected.reason}, ${selected.replayable ? "replayable" : "not replayable"}`}
      </span>
    </section>
  );
}

/**
 * The detail pane: Inspect, Replay, Acknowledge.
 *
 * Split from the table so a selection re-renders this and not the list (§68).
 * Every control here is per-record and every one states what it does to the
 * delivery, because "Acknowledge" and "Re-evaluate" sound alike and are not.
 */
function QuarantineDetail({
  row,
  payload,
  onReplay,
  onReEvaluate,
  replayPending,
  reEvaluatePending,
  onAcknowledge,
}: {
  row: QuarantineRow | null;
  payload: string | null;
  onReplay: (recordId: string) => void;
  onReEvaluate: (recordId: string) => void;
  replayPending: boolean;
  reEvaluatePending: boolean;
  onAcknowledge: (row: QuarantineRow) => void;
}) {
  if (row === null) {
    return (
      <div className="ui-quar-detail" data-testid="quarantine-detail-empty">
        <p className="ui-pane-title">Inspect</p>
        <EmptyState
          size="sm"
          icon="view-evidence"
          title="No record selected"
          description="Choose a row to read what the pipeline refused, replay the preserved bytes, or record that it has been seen."
          testId="quar-detail-no-selection"
        />
      </div>
    );
  }

  return (
    <div className="ui-quar-detail" data-testid="quarantine-detail" data-replayable={row.replayable}>
      <div className="ui-quar-detail-head">
        <span className="ui-pane-title">Inspect</span>
        <span className="ui-id" data-testid="quar-detail-record">
          {row.recordId}
        </span>
        <StatusDot status={row.status} label={row.preservedRaw ? "preserved" : "bytes not preserved"} />
        <span className="ui-rail-secondary">
          {row.topic} · partition {row.partition}
        </span>
      </div>

      <div className="ui-quar-fields">
        <div className="ui-insp-field" data-testid="quar-detail-reason">
          <span className="ui-insp-field-label">reason</span>
          <span className="ui-insp-field-value" data-mono="true">
            {row.reason}
          </span>
        </div>
        <div className="ui-insp-field" data-testid="quar-detail-digest">
          <span className="ui-insp-field-label">digest</span>
          <span className="ui-insp-field-value" data-mono="true">
            {row.digest}
          </span>
        </div>
      </div>

      <div className="ui-quar-actions">
        <Button
          size="sm"
          variant="primary"
          onClick={() => onReplay(row.recordId)}
          disabled={!row.replayable || replayPending}
          title={
            row.replayable
              ? "POST /dlq/{id}/replay — returns the preserved payload byte-for-byte"
              : "The preserved bytes are gone, so there is nothing to replay"
          }
          data-testid="quar-detail-replay"
        >
          {replayPending ? "Replaying…" : "Replay"}
        </Button>

        {/*
          Re-evaluation is a destructive, irreversible act: it purges the record.
          It is offered only where it can succeed, and it is named for what it
          does rather than softened into "acknowledge".
        */}
        {row.replayable ? (
          <Button
            size="sm"
            variant="danger"
            onClick={() => onReEvaluate(row.recordId)}
            disabled={reEvaluatePending}
            title="POST /dlq/{id}/re-evaluate — accepts or rejects the record and removes it from quarantine"
            data-testid="quar-detail-reevaluate"
          >
            {reEvaluatePending ? "Re-evaluating…" : "Re-evaluate (removes record)"}
          </Button>
        ) : null}

        {onAcknowledge !== undefined ? (
          <Button size="sm" variant="ghost" onClick={() => onAcknowledge(row)} data-testid="quar-detail-acknowledge">
            Acknowledge
          </Button>
        ) : null}
      </div>

      {row.replayable === false ? (
        <p className="ui-body" data-testid="quar-detail-not-replayable">
          {row.replayBlockedReason}
        </p>
      ) : null}

      {payload !== null ? (
        <div className="ui-quar-detail">
          <p className="ui-pane-title">Preserved payload (base64)</p>
          <p className="ui-rail-hint">
            Returned byte-for-byte by the replay call. There is no separate read endpoint, so obtaining these bytes
            is itself a replay.
          </p>
          <pre className="ui-quar-payload" data-testid="quar-payload">
            {payload}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

/** The named absences, once, in one place. §90 — state the gap rather than hide it. */
function CoverageNote() {
  return (
    <section className="ui-ops-block" data-testid="quarantine-coverage-note">
      <div className="ui-ops-block-head">
        <span className="ui-pane-title">Columns the endpoint does not serve</span>
        <span className="ui-ops-block-note">{QUARANTINE_UNAVAILABLE.length} named absence(s)</span>
      </div>
      <ul className="ui-quar-gap-list">
        {QUARANTINE_UNAVAILABLE.map((gap) => (
          <li key={gap.endpoint} className="ui-quar-gap" data-testid="quar-gap">
            <span>{gap.reason}</span>
            <span className="ui-quar-gap-endpoint">{gap.endpoint}</span>
          </li>
        ))}
      </ul>
      <p className="ui-ops-empty">
        These are read as "not served", never as zero or empty. A field the platform did not report is a different
        fact from a field that was reported empty, and the table keeps them apart.
      </p>
    </section>
  );
}

/**
 * Acknowledgement without an endpoint.
 *
 * A host that supplies `onAcknowledge` gets the action. A host that does not has
 * no place to record the acknowledgement, and offering the button anyway would be
 * a control whose effect is unknown — so the surface states the missing endpoint
 * instead. This is the §69 rule applied to a missing write endpoint rather than a
 * missing read one.
 */
export const ACKNOWLEDGE_MISSING =
  "POST /dlq/{id}/acknowledge (no endpoint records that an operator has seen a refused delivery)";