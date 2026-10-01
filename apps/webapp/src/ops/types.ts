import type { WorkStatus } from "../ui/status";

/**
 * Operations, quarantine and source-catalogue row vocabulary (§46, §47, §48,
 * §92, §99).
 *
 * Everything here is a *row the platform can be asked for*, not a metric we
 * invented. Where the served endpoint does not carry a field, the row says so
 * through `null` and the surface renders "not served" with the endpoint named —
 * never a zero, never a guess (§90, §91).
 *
 * §92: every status field in this file is a `WorkStatus`. The closed vocabulary
 * lives in `src/ui/status.ts` and this module never widens it. A platform string
 * it does not recognise arrives as `Unknown`, which is the honest answer, not a
 * new colour.
 *
 * §99: `null` and `notReported` mean exactly one thing — *the endpoint that
 * answers this field is not the one being read*. The distinction matters because
 * "the record has no source" and "we were never told the record's source" are
 * different facts about different systems.
 */

/** A value the served endpoints do not carry, with the endpoint that would. */
export interface Unavailable {
  /** Rendered verbatim as the reason, and never as a zero or an empty cell. */
  readonly reason: string;
  /** The endpoint (or field) whose absence causes this. Named so it can be closed. */
  readonly endpoint: string;
}

export function unavailable(reason: string, endpoint: string): Unavailable {
  return { reason, endpoint };
}

/* ── Worker health (§46) ────────────────────────────────────────────── */

export interface WorkerPoolRow {
  /** Pool name as `/metrics/pools` reports it, e.g. `browser`. Never renamed. */
  readonly pool: string;
  readonly active: number;
  readonly capacity: number;
  readonly failures: number;
  /** Closed-vocabulary verdict derived in `model.ts` from the four numbers above. */
  readonly status: WorkStatus;
  /** One sentence naming the operator action, or null when nothing is needed. */
  readonly action: string | null;
  /** Saturation 0–1, or null when capacity is zero (0/0 is not 0%). */
  readonly saturation: number | null;
  /** Failure ratio of active work, or null when nothing is active. */
  readonly failureRate: number | null;
}

/* ── Queues, lag, resource utilisation (§46) ────────────────────────── */

export type SignalSeverity = "attention" | "watch" | "nominal";

/**
 * One named signal with a number and a verdict.
 *
 * A signal is never just a number. §70 forbids a wall of gauges and §8 forbids
 * decorative telemetry: each of these rows states what the number means for the
 * operator and what to do about it.
 */
export interface SignalRow {
  /** The series key exactly as the server sent it, e.g. `frontier`. */
  readonly key: string;
  readonly value: number;
  /** Unit as the platform means it: `count`, `seconds`, `bytes`, `ratio`. */
  readonly unit: "count" | "seconds" | "bytes" | "ratio" | "per_second" | "currency";
  readonly severity: SignalSeverity;
  /** Closed-vocabulary status alongside the severity, so colour is not the only signal. */
  readonly status: WorkStatus;
  /** What this number means operationally. Never empty. */
  readonly meaning: string;
  /** The operator action, or null when the signal is nominal. */
  readonly action: string | null;
  /** True when the endpoint answered but the platform reports no threshold. */
  readonly thresholdMissing: boolean;
}

/* ── Duplicate delivery (§192) ──────────────────────────────────────── */

/**
 * Duplicate delivery must be *visible*, not merely absent.
 *
 * §192's requirement is that an operator can tell a deduplicated delivery from
 * a single one. `GET /metrics` serves `duplicate_ratio`, a platform-wide
 * aggregate — which proves deduplication is happening but cannot name which
 * delivery was suppressed. That gap is stated on the surface rather than papered
 * over, and the endpoint that would close it is named.
 */
export interface DuplicateDeliveryState {
  /** Platform-wide ratio in 0–1, or null when `/metrics` did not serve it. */
  readonly ratio: number | null;
  /** Observations counted as useful after deduplication, when served. */
  readonly usefulObservations: number | null;
  /** True when the platform reports no ratio at all. */
  readonly unreported: boolean;
  /** How deduplication is actually achieved, with its source. */
  readonly mechanism: string;
  /** Per-delivery proof (which delivery was suppressed, against which prior one). */
  readonly perDeliveryProof: Unavailable;
}

/* ── §160 release-blocker audit ─────────────────────────────────────── */

/**
 * One §160 blocker and whether this UI can observe it.
 *
 * The list is the directive's, verbatim in wording. None of it is served by the
 * endpoints this surface reads, so the honest column is `not observable here`
 * plus the endpoint that would settle it. Rendering sixteen green ticks from a
 * payload that carries none of them would be §99's exact failure.
 */
export interface BlockerRow {
  readonly id: string;
  readonly blocker: string;
  readonly observable: false;
  /** The audit that settles it, and where it lives. */
  readonly settledBy: string;
}

/* ── Quarantine (§47) ───────────────────────────────────────────────── */

export type QuarantineRowStatus = WorkStatus;

/**
 * One quarantined delivery.
 *
 * `/dlq` serves exactly six fields: `record_id`, `reason`, `topic`, `partition`,
 * `preserved`, `fingerprint`. Everything this row needs beyond that is `null`
 * with the endpoint named, which is why the §47 table's first column is `null`
 * for most rows today and why the table says so in its header.
 */
export interface QuarantineRow {
  readonly recordId: string;
  /** Server-reported rejection reason. The one narrative field that is served. */
  readonly reason: string;
  /** The stream the message came off. Names the platform stream, NOT the source. */
  readonly topic: string;
  readonly partition: number;
  /** Whether the bytes are retained. This is what decides replayability. */
  readonly preserved: boolean;
  /** Digest half of the server fingerprint. See `digestHalf` below. */
  readonly digest: string;
  /** The fingerprint's base64 half — payload bytes, deliberately not rendered. */
  readonly payloadPrefix: string | null;

  readonly recordedAt: string | null;
  readonly sourceId: string | null;
  readonly runtimeRef: string | null;
  readonly objectRef: string | null;
  readonly attempts: number | null;
  readonly status: QuarantineRowStatus;
  /** The platform's raw `preserved` flag, shown beside the derived status. */
  readonly preservedRaw: boolean;

  /**
   * Whether Replay can work, and why not when it cannot.
   *
   * §69: a button that fails is a dead end. `replayable: false` renders no
   * button at all — the cell states the reason instead.
   */
  readonly replayable: boolean;
  readonly replayBlockedReason: string | null;

  /** True when the fields the §47 table names are absent from the served payload. */
  readonly degraded: boolean;
}

export const QUARANTINE_UNAVAILABLE: ReadonlyArray<Unavailable> = [
  unavailable("DLQRecord carries no timestamp, and record ids are random", "GET /dlq (add `recorded_at`)"),
  unavailable(
    "The served record names the platform stream, not the Source it came from",
    "GET /dlq (add `source_id`)",
  ),
  unavailable(
    "§97: provenance is never inferred from runtime_ref, so a topic name is not a runtime",
    "GET /dlq (add `producer` / `runtime_ref`)",
  ),
  unavailable("No subject or entity id is served on the record", "GET /dlq (add `subject_id`)"),
  unavailable(
    "QuarantineStore is idempotent by payload fingerprint and counts no attempt",
    "GET /dlq (add `attempts`)",
  ),
];

/* ── Source catalogue (§48) ─────────────────────────────────────────── */

/**
 * One row of the acquisition fabric (§48).
 *
 * §48 requires SearXNG, Airbyte, Maigret, BBOT and SpiderFoot to appear as
 * items of ONE fabric with their real `runtime_ref` and capabilities — not five
 * bespoke cards. So a row carries the runtime's own vocabulary verbatim and the
 * catalogue renders them through one table shape.
 */
export interface FabricRow {
  /** Platform source name. Exactly what the acquisition registry calls it. */
  readonly source: string;
  /** §14's `runtime_ref` — the executable identity, not a display label. */
  readonly runtimeRef: string;
  /** §14's `execution_class` — the coarser deployment grouping. */
  readonly executionClass: string;
  /** The runtime's own `capabilities()` list, verbatim and unordered-as-declared. */
  readonly capabilities: ReadonlyArray<string>;
  /** The Python module that declares this row, so the mirror cannot drift unnoticed. */
  readonly declaredBy: string;
  /** Runtime readiness. `null` unless an endpoint serves it — see `health`. */
  readonly health: WorkStatus | null;
  readonly version: string | null;
  readonly lastRunAt: string | null;
  /** Successful / attempted, as the platform reports it. `null` when unserved. */
  readonly successRate: number | null;
  readonly runsTotal: number | null;
  /** What this source is known to reach, from the served source_types or the runtime contract. */
  readonly coverage: ReadonlyArray<string>;
  /** Everything `null` above, as named absences. Rendered as the row's coverage note. */
  readonly gaps: ReadonlyArray<Unavailable>;
  /** Set when the tenant has registered a connector for this runtime. */
  readonly connector: ConnectorEcho | null;
}

/** What `/connectors` says about a registered connector, when one exists. */
export interface ConnectorEcho {
  readonly connectorId: string;
  readonly name: string;
  readonly status: WorkStatus;
  readonly rawStatus: string;
  readonly version: string;
  readonly policyId: string;
  readonly sourceTypes: ReadonlyArray<string>;
  /** §157: AcquisitionWorker compliance, as the control plane reports it. */
  readonly contractCompliant: boolean;
  /**
   * Runtime this connector's NAME declares, e.g. `maigret-sites` → `maigret`.
   *
   * Derived from the name and never from `capabilities` (§13 forbids inferring
   * the worker from what it can do). `null` when the name implies none of the
   * five, which is the honest answer for a generic HTTP connector.
   */
  readonly runtimeRefHint: string | null;
}

/* ── Composite server state ─────────────────────────────────────────── */

export interface OpsServerState {
  readonly loading: boolean;
  readonly error: string | null;
  readonly refetch: () => void;
  readonly pools: ReadonlyArray<WorkerPoolRow>;
  readonly queues: ReadonlyArray<SignalRow>;
  readonly lags: ReadonlyArray<SignalRow>;
  readonly storage: ReadonlyArray<SignalRow>;
  readonly throughput: SignalRow | null;
  readonly discoveryYield: SignalRow | null;
  readonly duplicateDelivery: DuplicateDeliveryState;
  readonly blockers: ReadonlyArray<BlockerRow>;
  /** Rows needing an operator, worst first. Empty is a real state, not an omission. */
  readonly attention: ReadonlyArray<SignalRow>;
  /** Endpoints that answered. */
  readonly loaded: ReadonlyArray<string>;
  /** Endpoints this surface needs and the platform does not expose. */
  readonly missing: ReadonlyArray<string>;
  /** True when nothing at all came back — a different state from "everything is nominal". */
  readonly silent: boolean;
}