import { useCallback, useMemo, useState, type ReactNode } from "react";

import { Badge, StatusDot } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/Feedback";
import { THRESHOLDS, formatBytes } from "./model";
import { useOpsState } from "./useOpsState";
import type { SignalRow, WorkerPoolRow } from "./types";
import "./ops.css";

/**
 * OperationsWorkspace (§46).
 *
 * §46 is the requirement that shapes this whole file: the operations surface is
 * a DIFFERENT SURFACE from the analyst workspace, and it must read as
 * operational rather than analytical. Three consequences, all load-bearing:
 *
 *   1. ACTIONABLE STATE, NOT GAUSES (§70, §71). Every row is a number with a
 *      consequence and, when it is off nominal, an instruction. There is no
 *      sparkline, no chart, no decorative card, and no metric without an
 *      operator meaning. A dashboard that shows forty numbers and says nothing
 *      about any of them is a §70 violation and useless in an incident.
 *
 *   2. WHAT IT IS AUTHORITATIVE FOR. This surface owns exactly one question:
 *      *is the pipeline healthy right now, and if not, what does an operator do
 *      first?* It is authoritative for worker health, queue depth, stage-hop
 *      lag, resource utilisation, failure rate, duplicate-delivery ratio and
 *      quarantine volume. It is NOT authoritative for anything about any single
 *      investigation — and it says so, because `/metrics` is tenant-wide and an
 *      operator reading "142 obs/s" must not conclude it describes the case they
 *      are working.
 *
 *   3. CLOSED STATUS VOCABULARY (§92). Every status is a `WorkStatus` from
 *      `src/ui/status.ts`. The platform's own strings are shown verbatim beside
 *      the mapped status so the translation stays auditable, and an unrecognised
 *      spelling arrives as `Unknown` rather than becoming a new colour.
 *
 * The severity thresholds are the UI's declared operating points, and
 * `thresholdMissing: true` on every row says the platform publishes no SLO. That
 * matters: an operator must be able to tell "the platform says this is fine"
 * from "nothing has said".
 */

/** Endpoint coverage shown once, in the footer. Named, not glossed over (§99). */
function CoverageFooter({ loaded, missing }: { loaded: ReadonlyArray<string>; missing: ReadonlyArray<string> }) {
  return (
    <footer className="ui-ops-block" data-testid="ops-coverage">
      <div className="ui-ops-block-head">
        <span className="ui-pane-title">Coverage</span>
        <span className="ui-ops-block-note">
          served: {loaded.length === 0 ? "nothing" : loaded.join(", ")} · not served: {missing.length}
        </span>
      </div>
      <ul className="ui-blockers">
        {missing.map((endpoint) => (
          <li key={endpoint} className="ui-blocker" data-testid="ops-missing-endpoint">
            <span className="ui-blocker-name">not served</span>
            <span className="ui-blocker-settled">{endpoint.split(" (")[0]}</span>
            <span className="ui-signal-meaning">
              {endpoint.includes("(") ? endpoint.slice(endpoint.indexOf("(") + 1, -1) : "No endpoint exposes this."}
            </span>
          </li>
        ))}
      </ul>
    </footer>
  );
}

/** One signal row: key, value, status, meaning, and the action when it matters. */
function SignalLine({ row }: { row: SignalRow }) {
  return (
    <div className="ui-signal" data-severity={row.severity} data-testid={`ops-signal-${row.key}`}>
      <span className="ui-signal-key">{row.key}</span>
      <span className="ui-signal-value" data-testid={`ops-signal-${row.key}-value`}>
        {formatSignalValue(row)}
      </span>
      <StatusDot status={row.status} label={row.severity} />
      <span className="ui-signal-meaning">{row.meaning}</span>
      {row.action !== null ? <span className="ui-signal-action">{row.action}</span> : null}
    </div>
  );
}

/**
 * Format a signal's value with its unit.
 *
 * The unit is rendered rather than implied: a bare `142` next to a bare `0.41`
 * on the same board invites reading them as the same kind of quantity, which
 * they are not.
 */
export function formatSignalValue(row: SignalRow): string {
  switch (row.unit) {
    case "seconds":
      return `${row.value.toFixed(1)} s`;
    case "bytes":
      return formatBytes(row.value);
    case "ratio":
      return `${(row.value * 100).toFixed(1)} %`;
    case "per_second":
      return `${row.value.toFixed(1)} /s`;
    case "currency":
      return `$${row.value.toFixed(2)}`;
    default:
      return row.value.toLocaleString();
  }
}

function SignalBlock({
  title,
  rows,
  note,
  testId,
}: {
  title: string;
  rows: ReadonlyArray<SignalRow>;
  note?: string;
  testId: string;
}) {
  return (
    <section className="ui-ops-block" data-testid={testId}>
      <div className="ui-ops-block-head">
        <span className="ui-pane-title">{title}</span>
        <span className="ui-ops-block-note">{note ?? `${rows.length} series`}</span>
      </div>
      {rows.length === 0 ? (
        <p className="ui-ops-empty">
          The endpoint answered with no series. That is a report of an empty pipeline, not a rendering
          failure — nothing is queued, lagging or growing right now.
        </p>
      ) : (
        <div className="ui-ops-rows">
          {rows.map((row) => (
            <SignalLine key={row.key} row={row} />
          ))}
        </div>
      )}
    </section>
  );
}

/**
 * The attention board.
 *
 * One short list, worst first. When it is clear it says so in words, because an
 * empty panel would read as "the board did not load" and an operator would go
 * looking for a fault that is not there (§90).
 */
function AttentionBoard({ rows }: { rows: ReadonlyArray<SignalRow> }) {
  return (
    <section
      className="ui-ops-block ui-ops-attention"
      data-clear={rows.length === 0}
      data-testid="ops-attention"
      aria-label="Signals needing an operator"
    >
      <div className="ui-ops-block-head">
        <span className="ui-pane-title">Needs a decision</span>
        <span className="ui-ops-block-note" data-testid="ops-attention-count">
          {rows.length === 0 ? "nothing off nominal" : `${rows.length} signal(s) off nominal`}
        </span>
      </div>
      {rows.length === 0 ? (
        <p className="ui-ops-empty" data-testid="ops-attention-clear">
          Nothing is off nominal. Every queue is below {THRESHOLDS.queueWatchCount.toLocaleString()} items, every
          stage lag is under {THRESHOLDS.lagWatchSeconds}s, and every pool has headroom. The board below carries the
          detail.
        </p>
      ) : (
        <div className="ui-ops-rows">
          {rows.map((row) => (
            <SignalLine key={row.key} row={row} />
          ))}
        </div>
      )}
    </section>
  );
}

/** One worker pool. The four served numbers, the verdict, and the action. */
function PoolRow({ row }: { row: WorkerPoolRow }) {
  return (
    <div className="ui-pool" data-status={row.status} data-testid={`ops-pool-${row.pool}`}>
      <span className="ui-pool-name">{row.pool}</span>
      <StatusDot status={row.status} testId={`ops-pool-${row.pool}-status`} />
      <span className="ui-pool-num" data-testid={`ops-pool-${row.pool}-active`}>
        {row.active}
      </span>
      <span className="ui-pool-num">{row.capacity}</span>
      <span className="ui-pool-num" data-testid={`ops-pool-${row.pool}-failures`}>
        {row.failures}
      </span>
      <span className="ui-pool-note">
        {row.saturation !== null ? `${(row.saturation * 100).toFixed(0)}% of capacity` : "capacity not reported"}
        {row.failureRate !== null ? ` · ${(row.failureRate * 100).toFixed(0)}% of active units failed` : ""}
        {row.action !== null ? ` — ${row.action}` : ""}
      </span>
    </div>
  );
}

function PoolBlock({ pools }: { pools: ReadonlyArray<WorkerPoolRow> }) {
  return (
    <section className="ui-ops-block" data-testid="ops-pools">
      <div className="ui-ops-block-head">
        <span className="ui-pane-title">Worker pools</span>
        <span className="ui-ops-block-note">{pools.length} pool(s) · active / capacity / failures</span>
      </div>
      <div className="ui-pool ui-pool-head" aria-hidden="true">
        <span>pool</span>
        <span />
        <span className="ui-pool-head">active</span>
        <span className="ui-pool-head">cap</span>
        <span className="ui-pool-head">fails</span>
        <span />
      </div>
      {pools.length === 0 ? (
        <p className="ui-ops-empty">
          `/metrics/pools` answered with no pools. The registry has nothing registered for this tenant, which is
          different from every pool being idle — no work can be dispatched until one exists.
        </p>
      ) : (
        <div className="ui-ops-rows">
          {pools.map((row) => (
            <PoolRow key={row.pool} row={row} />
          ))}
        </div>
      )}
    </section>
  );
}

/**
 * §192 — duplicate delivery has to be *visible*, not merely absent.
 *
 * The panel reports the served ratio and states plainly that it cannot name
 * which delivery was suppressed. That limitation is the point: an operator who
 * believes a delivery was deduplicated needs to know whether the evidence is
 * aggregate or per-delivery, and an aggregate shown without that caveat is a
 * false reassurance.
 */
function DuplicateDeliveryPanel({ state }: { state: ReturnType<typeof useOpsState>["duplicateDelivery"] }) {
  return (
    <section className="ui-ops-block" data-testid="ops-duplicates">
      <div className="ui-ops-block-head">
        <span className="ui-pane-title">Duplicate delivery</span>
        <span className="ui-ops-block-note">§192 — deduplicated deliveries must be visible as deduplicated</span>
      </div>
      <div className="ui-ops-rows">
        <div className="ui-signal" data-severity={state.unreported ? "watch" : "nominal"}>
          <span className="ui-signal-key">duplicate ratio</span>
          <span className="ui-signal-value" data-testid="ops-duplicate-ratio">
            {state.ratio === null ? (
              <span className="ui-quar-absent">not served</span>
            ) : (
              `${(state.ratio * 100).toFixed(1)} %`
            )}
          </span>
          <StatusDot status={state.unreported ? "Unknown" : "Healthy"} label={state.unreported ? "unreported" : "reported"} />
          <span className="ui-signal-meaning">
            Share of deliveries the pipeline recognised as already-seen, tenant-wide. Not this investigation's
            ratio.
          </span>
        </div>
        <div className="ui-signal" data-severity="nominal">
          <span className="ui-signal-key">useful observations</span>
          <span className="ui-signal-value" data-testid="ops-useful-observations">
            {state.usefulObservations === null ? (
              <span className="ui-quar-absent">not served</span>
            ) : (
              state.usefulObservations.toLocaleString()
            )}
          </span>
          <StatusDot status={state.usefulObservations === null ? "Unknown" : "Healthy"} />
          <span className="ui-signal-meaning">
            Observations that survived deduplication and became records. Platform-wide count.
          </span>
        </div>
      </div>
      <div className="ui-quar-fields">
        <p className="ui-body" data-testid="ops-duplicate-mechanism">
          {state.mechanism}
        </p>
        <p className="ui-rail-hint" data-testid="ops-duplicate-gap">
          Per-delivery proof is not available: {state.perDeliveryProof.reason}. Closing it needs{" "}
          <span className="ui-quar-gap-endpoint">{state.perDeliveryProof.endpoint}</span>.
        </p>
      </div>
    </section>
  );
}

/**
 * §160's blocker list, as operational state.
 *
 * Every row reads `not observable here` and names the audit that settles it. A
 * dashboard that showed sixteen green ticks from a payload containing none of
 * them would be claiming a release guarantee it cannot see (§99) — which is the
 * failure mode §160 exists to prevent, reproduced in a UI.
 */
function BlockerAudit({ blockers }: { blockers: ReadonlyArray<ReturnType<typeof useOpsState>["blockers"][number]> }) {
  return (
    <section className="ui-ops-block" data-testid="ops-blockers">
      <div className="ui-ops-block-head">
        <span className="ui-pane-title">§160 release blockers</span>
        <span className="ui-ops-block-note">
          {blockers.length} blocker(s) · none observable from this surface's endpoints
        </span>
      </div>
      <ul className="ui-blockers">
        {blockers.map((row) => (
          <li key={row.id} className="ui-blocker" data-testid={`ops-blocker-${row.id}`}>
            <span className="ui-blocker-name">{row.blocker}</span>
            <span className="ui-blocker-settled">not observable here</span>
            <span className="ui-signal-meaning">
              settled by <span className="ui-quar-gap-endpoint">{row.settledBy}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="ui-ops-empty">
        This surface reads <span className="ui-mono">/metrics</span>, <span className="ui-mono">/metrics/pools</span>{" "}
        and <span className="ui-mono">/dlq</span>. None of them carries the evidence any §160 blocker is settled
        by, so none can be reported clear or present from here. Each row names the audit that does settle it.
      </p>
    </section>
  );
}

/**
 * An error that names the scope and offers a way forward (§91).
 *
 * The quarantine affordance is rendered only when a handler was supplied. A
 * button that navigates nowhere because the host route has nowhere to navigate
 * is §69's dead end in its purest form, so the alternative is no button.
 */
function OpsError({
  message,
  onRetry,
  onOpenQuarantine,
}: {
  message: string;
  onRetry: () => void;
  onOpenQuarantine?: () => void;
}) {
  return (
    <div className="ui-inspector-error" role="alert" data-testid="ops-error">
      <p className="ui-pane-title">The operations board did not load</p>
      <p className="ui-body" data-testid="ops-error-message">
        {message}
      </p>
      <p className="ui-body">
        Scope: <span className="ui-mono">GET /metrics</span> and <span className="ui-mono">GET /metrics/pools</span>.{" "}
        The workspace selection, filters and time range are untouched, and the investigation surfaces keep working —
        this board reads tenant-wide pipeline state, not an investigation's records.
      </p>
      <div className="ui-insp-next-list">
        <Button size="sm" onClick={onRetry} data-testid="ops-error-retry">
          Retry
        </Button>
        {onOpenQuarantine !== undefined ? (
          <Button size="sm" icon="alert" onClick={onOpenQuarantine} data-testid="ops-error-quarantine">
            Check quarantine
          </Button>
        ) : null}
      </div>
    </div>
  );
}

/** Props for the operations board. */
export interface OperationsWorkspaceProps {
  /** Set false to hold the queries at pending, so a harness can capture loading. */
  enabled?: boolean;
  /** Rendered after the blocks. Used by routes that mount this inside a shell. */
  children?: ReactNode;
  /**
   * Where "check quarantine" goes. Omitted by hosts with no quarantine route,
   * and the affordance is then not rendered at all rather than rendered inert.
   */
  onOpenQuarantine?: () => void;
}

export function OperationsWorkspace({ enabled = true, children, onOpenQuarantine }: OperationsWorkspaceProps) {
  const server = useOpsState(enabled);
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);

  const onRetry = useCallback(() => {
    server.refetch();
    setLastRefresh(new Date().toISOString());
  }, [server]);

  const headline = useMemo(() => {
    const failedPools = server.pools.filter((row) => row.status === "Failed" || row.status === "Blocked").length;
    if (server.loading) return "loading";
    if (server.silent) return "no series reported";
    if (failedPools > 0) return `${failedPools} pool(s) down`;
    if (server.attention.length > 0) return `${server.attention.length} signal(s) need attention`;
    return "nominal";
  }, [server.loading, server.silent, server.pools, server.attention.length]);

  if (server.loading) {
    return (
      <section className="ui-ops ui-root" aria-label="Operations" data-testid="operations-workspace">
        <Skeleton rows={10} label="Loading operational metrics" />
      </section>
    );
  }

  if (server.error !== null) {
    return (
      <section className="ui-ops ui-root" aria-label="Operations" data-testid="operations-workspace">
        <OpsError message={server.error} onRetry={onRetry} onOpenQuarantine={onOpenQuarantine} />
      </section>
    );
  }

  return (
    <section className="ui-ops ui-root" aria-label="Operations" data-testid="operations-workspace">
      <header className="ui-ops-head">
        <div className="ui-ops-head-titles">
          <h2 className="ui-title" data-testid="ops-title">
            Operations
          </h2>
          <span className="ui-id" data-testid="ops-scope">
            tenant-wide pipeline state · not scoped to one investigation
          </span>
        </div>
        <Badge
          tone={headline === "nominal" ? "accent" : "gold"}
          role="classification"
          testId="ops-headline"
        >
          {headline}
        </Badge>
        <div className="ui-ops-actions">
          <Button size="sm" icon="clock" onClick={onRetry} data-testid="ops-refresh">
            Refresh
          </Button>
        </div>
      </header>

      {lastRefresh !== null ? (
        <p className="ui-rail-hint" role="status" aria-live="polite" data-testid="ops-refreshed">
          Refreshed at {lastRefresh.slice(11, 19)}Z. The board polls every 15s on its own.
        </p>
      ) : null}

      <AttentionBoard rows={server.attention} />
      <PoolBlock pools={server.pools} />
      <SignalBlock
        title="Stage-hop lag"
        rows={server.lags}
        note="seconds behind · lower is better · not Redpanda consumer-group offset"
        testId="ops-lags"
      />
      <SignalBlock title="Queues" rows={server.queues} note="items waiting for capacity" testId="ops-queues" />
      <SignalBlock title="Storage growth" rows={server.storage} note="bytes accumulated per series" testId="ops-storage" />

      <section className="ui-ops-block" data-testid="ops-rates">
        <div className="ui-ops-block-head">
          <span className="ui-pane-title">Throughput and yield</span>
          <span className="ui-ops-block-note">tenant-wide · declared operating points, no platform SLO served</span>
        </div>
        <div className="ui-ops-rows">
          {[server.throughput, server.discoveryYield].map((row) =>
            row === null ? (
              <p key="absent" className="ui-ops-empty" data-testid="ops-rate-absent">
                <span className="ui-quar-absent">not served</span> — the endpoint omitted this field. It is not zero,
                and a zero here would be a claim about the pipeline that nothing reported.
              </p>
            ) : (
              <SignalLine key={row.key} row={row} />
            ),
          )}
        </div>
      </section>

      <DuplicateDeliveryPanel state={server.duplicateDelivery} />
      <BlockerAudit blockers={server.blockers} />
      <CoverageFooter loaded={server.loaded} missing={server.missing} />

      {children}

      {/* Announces a change of state without moving focus (§67). */}
      <span className="ui-sr-only" role="status" aria-live="polite" data-testid="ops-live-region">
        Operations board {headline}
      </span>
    </section>
  );
}