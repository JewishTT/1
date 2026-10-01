import { toWorkStatus, type WorkStatus } from "../ui/status";
import type { ConnectorWire } from "./fabric";
import { connectorEcho, fabricRows } from "./fabric";
import type {
  BlockerRow,
  DuplicateDeliveryState,
  OpsServerState,
  QuarantineRow,
  SignalRow,
  SignalSeverity,
  WorkerPoolRow,
} from "./types";
import { unavailable } from "./types";

/**
 * Pure derivations for the operations surface (§46, §47, §48, §92, §192).
 *
 * Every function here is `(server payload) → rows the operator reads`. Nothing
 * here fetches, nothing here holds state, and every threshold is declared as a
 * named constant with the reason it has that value — which is what makes the
 * severity a *verdict about the pipeline* rather than a colour.
 *
 * §92 and the closed vocabulary: every `status` produced is a `WorkStatus`.
 * §99: `null` means the endpoint did not carry the field. It is never 0.
 */

/* ── Thresholds ─────────────────────────────────────────────────────── */

/**
 * Operational thresholds. Each names the consequence of crossing it, because a
 * threshold without a consequence is just a number in a different place.
 *
 * These are the UI's declared operating points, NOT the platform's SLOs — no
 * endpoint serves those. `thresholdMissing` on every row says so, so a reader
 * can tell "the platform says this is fine" from "nothing has said".
 */
export const THRESHOLDS = {
  /** Freshness lag above which data is behind the work it describes. */
  lagWatchSeconds: 30,
  lagAttentionSeconds: 120,
  /** A backlog that no longer drains within a normal working interval. */
  queueWatchCount: 10_000,
  queueAttentionCount: 100_000,
  /** Pool saturation above which there is no headroom for a burst. */
  saturationWatch: 0.8,
  saturationAttention: 0.95,
  /** Failures per active unit that indicates a broken pool rather than noise. */
  failureRateAttention: 0.25,
  /** Storage growth in bytes; a gigabyte per series per period is a real leak. */
  storageWatchBytes: 1_000_000_000,
  storageAttentionBytes: 10_000_000_000,
  /** Duplicate ratio above which deduplication is hiding a delivery problem. */
  duplicateAttentionRatio: 0.25,
} as const;

/* ── §160 release blockers ──────────────────────────────────────────── */

/**
 * §160's sixteen release blockers, verbatim in wording.
 *
 * Every row is `observable: false`, and that is the finding rather than an
 * omission: none of the sixteen can be settled from `/metrics`, `/metrics/pools`
 * or `/dlq`. The audit that settles each one is named instead, so the operator
 * can see where the answer actually lives and the audit trail stays reportable.
 *
 * Rendering sixteen green ticks from a payload carrying none of them would be
 * the exact failure §99 forbids — a UI claiming a guarantee it cannot observe.
 */
export const SECTION_160_BLOCKERS: ReadonlyArray<Omit<BlockerRow, "observable">> = [
  { id: "observation-id-random", blocker: "observation_id random", settledBy: "apps/shared/tests/unit/test_observation_identity.py" },
  { id: "event-id-random-replay", blocker: "event_id random for replay-sensitive events", settledBy: "apps/shared/tests/unit/test_observation_gate_identity.py" },
  { id: "raw-artifact-absent", blocker: "raw artifact absent", settledBy: "apps/acquisition/tests/unit/test_acquisition_artifact_sink.py" },
  { id: "observation-without-raw-lineage", blocker: "observation without raw lineage", settledBy: "apps/acquisition/tests/unit/test_acquisition_artifact_sink.py" },
  { id: "event-without-envelope", blocker: "event without canonical EventEnvelope", settledBy: "apps/acquisition/tests/unit/test_acquisition_worker.py" },
  { id: "tool-bypasses-policy", blocker: "tool bypasses policy", settledBy: "apps/acquisition/tests/unit/test_adapters_gate.py" },
  { id: "tenant-information-lost", blocker: "tenant information lost", settledBy: "apps/acquisition/tests/unit/test_acquisition_worker.py" },
  { id: "investigation-id-lost", blocker: "investigation_id lost", settledBy: "apps/acquisition/tests/unit/test_acquisition_worker.py" },
  { id: "consumer-cannot-replay", blocker: "consumer cannot replay", settledBy: "apps/acquisition/tests/unit/test_replay_journal.py" },
  { id: "pagination-loses-pages", blocker: "pagination loses pages", settledBy: "apps/acquisition/tests/unit/test_backpressure.py" },
  { id: "airbyte-state-as-evidence", blocker: "Airbyte STATE treated as evidence", settledBy: "apps/acquisition/tests/unit/test_airbyte_runtime.py" },
  { id: "donor-event-written-to-graph", blocker: "donor event written directly to graph", settledBy: "apps/acquisition/tests/unit/test_bbot_runtime.py" },
  { id: "secret-in-logs", blocker: "secret appears in logs/events", settledBy: "apps/acquisition/tests/unit/test_acquisition_worker.py" },
  { id: "live-source-never-executed", blocker: "live source never actually executed", settledBy: "apps/acquisition/tests/unit/test_live_loop.py" },
  { id: "redpanda-path-not-exercised", blocker: "Redpanda path not exercised", settledBy: "apps/acquisition/tests/unit/test_browser_fabric.py" },
  { id: "downstream-consumer-not-exercised", blocker: "downstream consumer not exercised", settledBy: "apps/acquisition/tests/unit/test_loop_closed.py" },
];

export function blockerRows(): ReadonlyArray<BlockerRow> {
  return SECTION_160_BLOCKERS.map((entry) => ({ ...entry, observable: false as const }));
}

/* ── Worker pools ───────────────────────────────────────────────────── */

export interface PoolWire {
  healthy: boolean;
  active: number;
  capacity: number;
  failures: number;
}

/**
 * One pool row.
 *
 * `healthy` is the platform's boolean and is kept as-is; the closed-vocabulary
 * status is derived from the four numbers because a pool can report `healthy:
 * true` while sitting at 97% saturation with three failures, and an operator
 * reading only the boolean would miss it.
 *
 * The interesting case is `capacity === 0`: 0/0 is not 0% saturation, it is an
 * unconfigured pool, and it must not render as a healthy idle one.
 */
export function poolRows(pools: Readonly<Record<string, PoolWire>>): WorkerPoolRow[] {
  return Object.entries(pools)
    .map(([pool, value]) => {
      const saturation = value.capacity > 0 ? value.active / value.capacity : null;
      const failureRate = value.active > 0 ? value.failures / value.active : null;

      let status: WorkStatus;
      if (!value.healthy) status = "Failed";
      else if (value.capacity === 0) status = "Blocked";
      else if (saturation !== null && saturation >= THRESHOLDS.saturationAttention) status = "Queued";
      else if (value.failures > 0) status = "Paused";
      else status = "Healthy";

      let action: string | null = null;
      if (!value.healthy) {
        action = `${value.failures} failure(s) reported — the pool reports itself unhealthy. Restart it or inspect the failing work before queueing more.`;
      } else if (value.capacity === 0) {
        action = "Capacity is zero, so nothing can be dispatched to this pool. Raise its capacity before queueing work.";
      } else if (saturation !== null && saturation >= THRESHOLDS.saturationWatch) {
        action = `At ${(saturation * 100).toFixed(0)}% of capacity there is no headroom for a burst. Expect queue growth until it drains.`;
      } else if (value.failures > 0) {
        action = `${value.failures} failure(s) recorded against ${value.active} active unit(s). Watch before adding load.`;
      }

      return {
        pool,
        active: value.active,
        capacity: value.capacity,
        failures: value.failures,
        status,
        action,
        saturation,
        failureRate,
      } satisfies WorkerPoolRow;
    })
    // Worst first: a failed pool is a bigger problem than a saturated one, and a
    // saturated one than a noisy one. Sorting by status means the row needing
    // attention is at the top without the operator scanning for it.
    .sort((a, b) => severityRank(b.status) - severityRank(a.status) || a.pool.localeCompare(b.pool));
}

function severityRank(status: WorkStatus): number {
  switch (status) {
    case "Failed":
      return 5;
    case "Blocked":
      return 4;
    case "Queued":
      return 3;
    case "Paused":
      return 2;
    case "Unknown":
      return 1;
    default:
      return 0;
  }
}

/* ── Signals ────────────────────────────────────────────────────────── */

function signal(
  key: string,
  value: number,
  unit: SignalRow["unit"],
  severity: SignalSeverity,
  meaning: string,
  action: string | null,
): SignalRow {
  return {
    key,
    value,
    unit,
    severity,
    status: severity === "attention" ? "Blocked" : severity === "watch" ? "Paused" : "Healthy",
    meaning,
    action,
    // The platform serves no threshold, so every row says so rather than
    // implying a number here came from an SLO.
    thresholdMissing: true,
  };
}

/** Freshness lag per stage hop. Seconds; lower is better, so the verdict inverts. */
export function lagRows(lags: Readonly<Record<string, number>>): SignalRow[] {
  return finiteEntries(lags)
    .map(([key, value]) => {
      const severity: SignalSeverity =
        value >= THRESHOLDS.lagAttentionSeconds
          ? "attention"
          : value >= THRESHOLDS.lagWatchSeconds
            ? "watch"
            : "nominal";
      return signal(
        key,
        value,
        "seconds",
        severity,
        `${key}: how far behind the newest input this stage is reading.`,
        severity === "nominal"
          ? null
          : `${value.toFixed(1)}s behind. Data on this hop is describing a past moment; widen the time range or wait for the hop to drain before drawing a conclusion from it.`,
      );
    })
    .sort((a, b) => b.value - a.value);
}

/** Queue depth per named queue. Count; higher is worse. */
export function queueRows(queues: Readonly<Record<string, number>>): SignalRow[] {
  return finiteEntries(queues)
    .map(([key, value]) => {
      const severity: SignalSeverity =
        value >= THRESHOLDS.queueAttentionCount
          ? "attention"
          : value >= THRESHOLDS.queueWatchCount
            ? "watch"
            : "nominal";
      return signal(
        key,
        value,
        "count",
        severity,
        `${key}: work accepted and waiting for capacity.`,
        severity === "nominal"
          ? null
          : `${value.toLocaleString()} item(s) waiting. The scheduler is behind intake — check pool saturation above before assuming the consumers are at fault.`,
      );
    })
    .sort((a, b) => b.value - a.value);
}

/** Storage growth per series. Bytes; higher is worse. */
export function storageRows(storage: Readonly<Record<string, number>>): SignalRow[] {
  return finiteEntries(storage)
    .map(([key, value]) => {
      const severity: SignalSeverity =
        value >= THRESHOLDS.storageAttentionBytes
          ? "attention"
          : value >= THRESHOLDS.storageWatchBytes
            ? "watch"
            : "nominal";
      return signal(
        key,
        value,
        "bytes",
        severity,
        `${key}: bytes accumulated by this series.`,
        severity === "nominal"
          ? null
          : `${formatBytes(value)} accumulated. Growth at this scale is a retention decision, not a bug — confirm the retention window covers it.`,
      );
    })
    .sort((a, b) => b.value - a.value);
}

/** Throughput. Observations per second; a zero here with work queued is the tell. */
export function throughputRow(throughput: number | null, queued: number): SignalRow | null {
  if (throughput === null) return null;
  const severity: SignalSeverity = throughput === 0 && queued > 0 ? "attention" : "nominal";
  return signal(
    "throughput",
    throughput,
    "per_second",
    severity,
    "Observations per second across the whole pipeline, tenant-wide — not this investigation's count.",
    severity === "attention"
      ? `Zero throughput with ${queued.toLocaleString()} item(s) queued: the pipeline is blocked, not idle. Start at the worker pools above.`
      : null,
  );
}

/** Discovery yield. Ratio 0–1; higher is better. */
export function discoveryYieldRow(yield_: number | null): SignalRow | null {
  if (yield_ === null) return null;
  const severity: SignalSeverity = yield_ === 0 ? "watch" : "nominal";
  return signal(
    "discovery yield",
    yield_,
    "ratio",
    severity,
    "Share of collected material that became new knowledge rather than a repeat.",
    severity === "nominal"
      ? null
      : "Nothing collected became new knowledge. Check the duplicate ratio before assuming the sources are exhausted.",
  );
}

/** Browser pool utilisation. Ratio 0–1; higher is worse. */
export function utilisationRow(browserUtilisation: number | null, pools: Readonly<Record<string, PoolWire>>): SignalRow | null {
  if (browserUtilisation === null) return null;
  const browser = pools["browser"];
  const poolStatus = browser ? poolRows({ browser })[0]?.status ?? "Unknown" : "Unknown";
  const severity: SignalSeverity =
    browserUtilisation >= THRESHOLDS.saturationAttention
      ? "attention"
      : browserUtilisation >= THRESHOLDS.saturationWatch
        ? "watch"
        : "nominal";
  return signal(
    "browser utilisation",
    browserUtilisation,
    "ratio",
    severity,
    "Share of the browser pool in use. The pool itself reports as " + poolStatus.toLowerCase() + ".",
    severity === "nominal"
      ? null
      : `${(browserUtilisation * 100).toFixed(0)}% of browser capacity in use. Browser-bound recon is the first thing to slow down when this saturates.`,
  );
}

/* ── Duplicate delivery (§192) ──────────────────────────────────────── */

/**
 * §192 — a delivery that was deduplicated must be *visible* as deduplicated,
 * not indistinguishable from one that arrived once.
 *
 * `/metrics` serves `duplicate_ratio`, a platform-wide aggregate. That is real
 * evidence that deduplication is running, and it is the only evidence this
 * surface can reach: it proves deduplication happens but cannot say WHICH
 * delivery was suppressed. The gap is stated rather than smoothed over, and the
 * endpoint that would close it is named.
 */
export function duplicateDeliveryState(metrics: {
  duplicate_ratio?: number;
  useful_observations?: number;
}): DuplicateDeliveryState {
  const ratio = typeof metrics.duplicate_ratio === "number" ? metrics.duplicate_ratio : null;
  const severityNote =
    ratio !== null && ratio >= THRESHOLDS.duplicateAttentionRatio
      ? " At or above the declared attention point, deduplication is masking intake that is arriving repeatedly — treat it as a delivery fault, not a saving."
      : null;

  return {
    ratio,
    usefulObservations: typeof metrics.useful_observations === "number" ? metrics.useful_observations : null,
    unreported: ratio === null,
    mechanism:
      "Observations are content-addressed (§11: OBS-{digest128} over tenant, capture, locator and record digest), and the quarantine store preserves idempotently by payload fingerprint. A redelivery therefore collides with an existing identity instead of creating a second one." +
      (severityNote ?? ""),
    perDeliveryProof: unavailable(
      "The served ratio is platform-wide; no endpoint names which delivery was suppressed or against which prior one",
      "GET /observations/{id}/redeliveries (the suppression record for one observation)",
    ),
  };
}

/* ── Quarantine (§47) ───────────────────────────────────────────────── */

export interface QuarantineWire {
  record_id: string;
  reason: string;
  topic: string;
  partition: number;
  preserved: boolean;
  fingerprint: string;
}

/**
 * One quarantined row.
 *
 * The §47 table asks for Time / Source / Runtime / Object / Reason / Attempts /
 * Status / Replayable. `/dlq` serves exactly one of those eight: the reason.
 * The other seven are `null` with the endpoint named, and `degraded: true` marks
 * the row so the table header can say so once instead of per-cell.
 *
 * REPLAYABILITY IS DERIVED FROM `preserved`, and that derivation is the whole
 * point of the surface. §107/§108 forbid dropping malformed output; the bytes
 * survive in quarantine, which is what makes replay possible. When `preserved`
 * is false the bytes are gone, so `replayable` is false and the Replay button
 * must not be rendered — a button that 404s is §69's dead end.
 */
export function quarantineRows(records: ReadonlyArray<QuarantineWire>): QuarantineRow[] {
  return records
    .map((record) => {
      const { digest, payloadPrefix } = splitFingerprint(record.fingerprint);
      const replayable = record.preserved;
      return {
        recordId: record.record_id,
        reason: record.reason,
        topic: record.topic,
        partition: record.partition,
        preserved: record.preserved,
        digest,
        payloadPrefix,
        recordedAt: null,
        sourceId: null,
        runtimeRef: null,
        objectRef: null,
        attempts: null,
        status: toWorkStatus(record.preserved ? "QUARANTINED" : "REJECTED"),
        preservedRaw: record.preserved,
        replayable,
        replayBlockedReason: replayable
          ? null
          : "The preserved bytes are gone, so there is nothing to replay. Re-evaluation is also unavailable: both read the payload, so the record can only be read as evidence that a delivery failed.",
        degraded: true,
      } satisfies QuarantineRow;
    })
    .sort((a, b) => a.recordId.localeCompare(b.recordId));
}

/**
 * `fingerprint` is `base64(payload)[:12] + ":" + sha256(payload)[:12]`.
 *
 * The left half is payload BYTES, not an identifier. Rendering it in a table
 * would put untrusted, possibly-binary content into the DOM as text; so the
 * catalogue renders the digest half and keeps the payload half out of the
 * markup. Splitting them here is what makes that guarantee testable.
 */
export function splitFingerprint(fingerprint: string): { digest: string; payloadPrefix: string | null } {
  const separator = fingerprint.indexOf(":");
  if (separator === -1) return { digest: fingerprint, payloadPrefix: null };
  const payloadPrefix = fingerprint.slice(0, separator);
  const digest = fingerprint.slice(separator + 1);
  // A fingerprint with no digest half is malformed; say so rather than show "".
  return { digest: digest === "" ? "not reported" : digest, payloadPrefix };
}

/* ── Assembly ───────────────────────────────────────────────────────── */

/**
 * Build the whole operations state from the served payloads.
 *
 * `silent` is a distinct state from "nominal": `/metrics` answering with all
 * zeroes and `/metrics/pools` answering with no pools is a hermetic or
 * unseeded deployment, and a dashboard that renders that as a wall of zeros
 * reads as "the pipeline is fine and empty", which is a claim the payload does
 * not make.
 */
export function buildOpsState(input: {
  metrics: Record<string, unknown> | null;
  pools: Record<string, PoolWire> | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}): OpsServerState {
  const metrics = input.metrics ?? {};
  const rawPools = input.pools ?? {};
  const pools = poolRows(rawPools);
  const queues = queueRows(asNumberRecord(metrics["queues"]));
  const lags = lagRows(asNumberRecord(metrics["lags_s"]));
  const storage = storageRows(asNumberRecord(metrics["storage_growth_b"]));
  const throughput = throughputRow(asNumber(metrics["throughput_per_s"]), sumValues(asNumberRecord(metrics["queues"])));
  const discoveryYield = discoveryYieldRow(asNumber(metrics["discovery_yield"]));
  const utilisation = utilisationRow(asNumber(metrics["browser_utilization"]), rawPools);
  const duplicateDelivery = duplicateDeliveryState(metrics as { duplicate_ratio?: number; useful_observations?: number });

  const attention = [throughput, discoveryYield, utilisation, ...queues, ...lags, ...storage]
    .filter((row): row is SignalRow => row !== null && row.severity !== "nominal")
    .sort(
      (a, b) =>
        severityOrder(b.severity) - severityOrder(a.severity) ||
        // Within one severity, order by consequence, not by magnitude — see
        // CONSEQUENCE_RANK for why comparing a count with a ratio is meaningless.
        consequenceRank(a) - consequenceRank(b) ||
        // Same unit, so magnitude is finally comparable: worst value first.
        b.value - a.value,
    );

  const answered = input.metrics !== null || input.pools !== null;
  const silent = answered && pools.length === 0 && queues.length === 0 && lags.length === 0;

  return {
    loading: input.loading,
    error: input.error,
    refetch: input.refetch,
    pools,
    queues,
    lags,
    storage,
    throughput,
    discoveryYield,
    duplicateDelivery,
    blockers: blockerRows(),
    attention,
    loaded: answered ? ["/metrics", "/metrics/pools"] : [],
    missing: [
      "GET /metrics/thresholds (the platform publishes no SLO, so every severity here is a declared operating point)",
      "GET /quarantine (a count and an age distribution, so the surface does not have to sum the whole list to know whether quarantine is growing)",
      "GET /dlq/{id}/attempts (how many times a delivery was retried before it was refused)",
      "GET /observations/{id}/redeliveries (per-delivery duplicate-suppression evidence, §192)",
    ],
    silent,
  };
}

function severityOrder(severity: SignalSeverity): number {
  switch (severity) {
    case "attention":
      return 2;
    case "watch":
      return 1;
    default:
      return 0;
  }
}

/**
 * Order within one severity, by CONSEQUENCE rather than by magnitude.
 *
 * Sorting attention rows by raw value is the bug this replaces: `500000` queue
 * items and `400` seconds of lag and `0` obs/s are different quantities, so
 * "largest number first" is not a meaningful comparison — it would rank a 500k
 * backlog above a pipeline that has stopped moving, when the stalled pipeline is
 * what explains the backlog.
 *
 * The order below is a DECLARED EDITORIAL CHOICE, stated as such rather than
 * derived from the numbers, because the platform publishes no SLO to derive it
 * from (§92). Read top to bottom as: is anything moving, how much is outstanding,
 * how old is what I have, and then the quality and cost ratios.
 */
const CONSEQUENCE_RANK: Record<SignalRow["unit"], number> = {
  // A pipeline that is not moving at all explains every backlog below it.
  per_second: 0,
  // Backlog depth is what an operator can act on directly (add capacity).
  count: 1,
  // Staleness changes what the data can be used to conclude, and follows from
  // the backlog above it.
  seconds: 2,
  // Ratios describe quality or cost, which matter but do not unblock work.
  ratio: 3,
  bytes: 4,
  currency: 5,
};

function consequenceRank(row: SignalRow): number {
  return CONSEQUENCE_RANK[row.unit];
}

/** Drop non-finite entries from a served series, at the row builder rather than the caller. */
function finiteEntries(record: Readonly<Record<string, number>>): Array<[string, number]> {
  return Object.entries(record).filter(
    (entry): entry is [string, number] => typeof entry[1] === "number" && Number.isFinite(entry[1]),
  );
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asNumberRecord(value: unknown): Record<string, number> {
  if (typeof value !== "object" || value === null) return {};
  const out: Record<string, number> = {};
  for (const [key, entry] of Object.entries(value as Record<string, unknown>)) {
    if (typeof entry === "number" && Number.isFinite(entry)) out[key] = entry;
  }
  return out;
}

function sumValues(record: Record<string, number>): number {
  return Object.values(record).reduce((total, value) => total + value, 0);
}

/** Bytes as a human-readable string. Binary units, because storage is bytes. */
export function formatBytes(bytes: number): string {
  if (bytes >= 1_000_000_000_000) return `${(bytes / 1_000_000_000_000).toFixed(1)} TB`;
  if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(1)} GB`;
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(1)} kB`;
  return `${bytes} B`;
}

export { fabricRows, connectorEcho };
export type { ConnectorWire };