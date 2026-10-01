import { describe, expect, it } from "vitest";

import {
  THRESHOLDS,
  blockerRows,
  buildOpsState,
  discoveryYieldRow,
  duplicateDeliveryState,
  formatBytes,
  lagRows,
  poolRows,
  queueRows,
  quarantineRows,
  splitFingerprint,
  storageRows,
  throughputRow,
  utilisationRow,
} from "./model";
import type { QuarantineWire } from "./model";

const NO_ERROR = { loading: false, error: null, refetch: () => undefined };

describe("§46 — worker pools become actionable rows, not gauges", () => {
  it("reports a healthy idle pool with no action", () => {
    const [row] = poolRows({ browser: { healthy: true, active: 2, capacity: 8, failures: 0 } });
    expect(row.status).toBe("Healthy");
    expect(row.action).toBeNull();
    expect(row.saturation).toBe(0.25);
  });

  it("surfaces a pool that reports itself unhealthy above everything else", () => {
    const rows = poolRows({
      healthy_pool: { healthy: true, active: 1, capacity: 4, failures: 0 },
      broken_pool: { healthy: false, active: 0, capacity: 4, failures: 3 },
      saturated: { healthy: true, active: 4, capacity: 4, failures: 0 },
    });
    expect(rows.map((row) => row.pool)).toEqual(["broken_pool", "saturated", "healthy_pool"]);
    expect(rows[0].status).toBe("Failed");
    expect(rows[0].action).toMatch(/unhealthy/i);
  });

  it("does not report a zero-capacity pool as a healthy idle one", () => {
    // 0/0 is not 0% saturation; it is a pool nothing can be dispatched to.
    const [row] = poolRows({ browser: { healthy: true, active: 0, capacity: 0, failures: 0 } });
    expect(row.status).toBe("Blocked");
    expect(row.saturation).toBeNull();
    expect(row.action).toMatch(/capacity is zero/i);
  });

  it("warns on a saturated pool even when it reports healthy", () => {
    const [row] = poolRows({ browser: { healthy: true, active: 10, capacity: 10, failures: 0 } });
    expect(row.status).toBe("Queued");
    expect(row.action).toMatch(/headroom/i);
  });

  it("leaves the failure rate null when nothing is active, rather than 0%", () => {
    const [row] = poolRows({ browser: { healthy: true, active: 0, capacity: 4, failures: 0 } });
    expect(row.failureRate).toBeNull();
  });
});

describe("§46 — lag, queues and storage carry a consequence", () => {
  it("marks a fresh hop nominal and a stale one as needing a decision", () => {
    const rows = lagRows({
      "dispatcher->interpretation": 8.4,
      "interpretation->projection": 340,
    });
    expect(rows[0].severity).toBe("attention");
    expect(rows[1].severity).toBe("nominal");
    expect(rows[0].action).toMatch(/behind/i);
    expect(rows[1].action).toBeNull();
  });

  it("uses the declared operating point as the watch boundary", () => {
    const rows = lagRows({ hop: THRESHOLDS.lagWatchSeconds });
    expect(rows[0].severity).toBe("watch");
  });

  it("orders queues by depth so the worst is first", () => {
    const rows = queueRows({ frontier: 24_318, tiny: 3, backfill: 250_000 });
    expect(rows.map((row) => row.key)).toEqual(["backfill", "frontier", "tiny"]);
    expect(rows[0].severity).toBe("attention");
  });

  it("points a large queue at pool saturation rather than blaming consumers", () => {
    const [row] = queueRows({ frontier: 250_000 });
    expect(row.action).toMatch(/pool saturation/i);
  });

  it("formats storage in binary units because the unit is bytes", () => {
    expect(formatBytes(512_000_000)).toBe("512.0 MB");
    expect(formatBytes(12_000_000_000)).toBe("12.0 GB");
    expect(formatBytes(900)).toBe("900 B");
  });

  it("treats storage growth as a retention decision, not a bug", () => {
    const [row] = storageRows({ observations: 20_000_000_000 });
    expect(row.action).toMatch(/retention/i);
  });

  it("flags zero throughput with work queued as blocked, not idle", () => {
    // The failure this catches: 0/s on a dashboard with a big queue reads as
    // "the pipeline is fine and quiet" when it is in fact stalled.
    const row = throughputRow(0, 24_318);
    expect(row?.severity).toBe("attention");
    expect(row?.action).toMatch(/blocked, not idle/i);
  });

  it("treats zero throughput with nothing queued as nominal", () => {
    expect(throughputRow(0, 0)?.severity).toBe("nominal");
  });

  it("returns null for a throughput the endpoint did not send", () => {
    expect(throughputRow(null, 1000)).toBeNull();
    expect(discoveryYieldRow(null)).toBeNull();
  });

  it("ties browser utilisation to the browser pool's own status", () => {
    const row = utilisationRow(0.98, { browser: { healthy: true, active: 4, capacity: 4, failures: 0 } });
    expect(row?.severity).toBe("attention");
    expect(row?.meaning).toMatch(/reports as queued/i);
  });
});

describe("§92 — every status is drawn from the closed vocabulary", () => {
  it("emits only WorkStatus values from every derivation", () => {
    const legal = new Set([
      "Healthy",
      "Running",
      "Queued",
      "Paused",
      "Completed",
      "Failed",
      "Blocked",
      "Unknown",
    ]);
    const state = buildOpsState({
      metrics: { throughput_per_s: 0, queues: { frontier: 500_000 }, duplicate_ratio: 0.4 },
      pools: { browser: { healthy: false, active: 0, capacity: 0, failures: 1 } },
      ...NO_ERROR,
    });
    const statuses = [
      ...state.pools.map((row) => row.status),
      ...[...state.queues, ...state.lags, ...state.storage].map((row) => row.status),
      ...state.blockers.map(() => "Unknown" as const),
    ];
    for (const status of statuses) expect(legal.has(status)).toBe(true);
  });
});

describe("§160 — the blocker list is the directive's, and nothing is claimed clear", () => {
  it("lists all sixteen blockers", () => {
    expect(blockerRows()).toHaveLength(16);
  });

  it("marks every blocker unobservable, because no served endpoint settles one", () => {
    // The finding, not an omission: rendering sixteen green ticks from a payload
    // carrying none of them is §99's exact failure.
    for (const row of blockerRows()) {
      expect(row.observable, row.blocker).toBe(false);
      expect(row.settledBy, row.blocker).toMatch(/\.py$/);
    }
  });

  it("names the four well-known blockers the directive leads with", () => {
    const names = blockerRows().map((row) => row.blocker);
    expect(names).toContain("observation_id random");
    expect(names).toContain("event_id random for replay-sensitive events");
    expect(names).toContain("observation without raw lineage");
    expect(names).toContain("event without canonical EventEnvelope");
  });

  it("gives every blocker a unique id", () => {
    const ids = blockerRows().map((row) => row.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe("§192 — a deduplicated delivery must be visible as deduplicated", () => {
  it("reports the served ratio and calls it tenant-wide", () => {
    const state = duplicateDeliveryState({ duplicate_ratio: 0.12, useful_observations: 1_048_576 });
    expect(state.ratio).toBe(0.12);
    expect(state.usefulObservations).toBe(1_048_576);
    expect(state.unreported).toBe(false);
    expect(state.mechanism).toMatch(/content-addressed/i);
  });

  it("says plainly that per-delivery proof is unavailable", () => {
    // An aggregate ratio without this caveat is a false reassurance: it proves
    // deduplication happens but not which delivery was suppressed.
    const state = duplicateDeliveryState({ duplicate_ratio: 0.12 });
    expect(state.perDeliveryProof.reason).toMatch(/platform-wide/i);
    expect(state.perDeliveryProof.endpoint).toContain("/redeliveries");
  });

  it("marks the ratio unreported rather than zero when the endpoint omits it", () => {
    const state = duplicateDeliveryState({});
    expect(state.ratio).toBeNull();
    expect(state.unreported).toBe(true);
  });

  it("escalates a high ratio to a delivery fault, not a saving", () => {
    const state = duplicateDeliveryState({ duplicate_ratio: 0.5 });
    expect(state.mechanism).toMatch(/delivery fault/i);
  });
});

describe("§47 — a quarantined row says honestly what it cannot do", () => {
  const RECORD: QuarantineWire = {
    record_id: "DLQ-1",
    reason: "parse-failure",
    topic: "cognitive-events--t-default-tenant",
    partition: 0,
    preserved: true,
    fingerprint: "bW9jaw==bW9jaw:deadbeefcafe",
  };

  it("offers replay for a preserved record", () => {
    const [row] = quarantineRows([RECORD]);
    expect(row.replayable).toBe(true);
    expect(row.replayBlockedReason).toBeNull();
    expect(row.status).toBe("Blocked");
  });

  it("withholds replay when the bytes are gone, and says why", () => {
    // §69: a button that 404s is a dead end. The absence of a control is stated.
    const [row] = quarantineRows([{ ...RECORD, preserved: false }]);
    expect(row.replayable).toBe(false);
    expect(row.replayBlockedReason).toMatch(/nothing to replay/i);
    expect(row.status).toBe("Blocked");
    expect(row.preservedRaw).toBe(false);
  });

  it("marks every row degraded, because /dlq serves six fields and §47 names eight columns", () => {
    for (const row of quarantineRows([RECORD])) {
      expect(row.degraded).toBe(true);
      expect(row.recordedAt).toBeNull();
      expect(row.sourceId).toBeNull();
      expect(row.runtimeRef).toBeNull();
      expect(row.objectRef).toBeNull();
      expect(row.attempts).toBeNull();
    }
  });

  it("splits the fingerprint so payload bytes never reach the markup", () => {
    const [row] = quarantineRows([RECORD]);
    expect(row.digest).toBe("deadbeefcafe");
    expect(row.payloadPrefix).toBe("bW9jaw==bW9jaw");
  });

  it("handles a fingerprint with no separator", () => {
    expect(splitFingerprint("deadbeef")).toEqual({ digest: "deadbeef", payloadPrefix: null });
  });

  it("does not render an empty digest as if it were a value", () => {
    expect(splitFingerprint("bW9jaw==:").digest).toBe("not reported");
  });

  it("sorts by record id so the queue order is stable", () => {
    const rows = quarantineRows([
      { ...RECORD, record_id: "DLQ-3" },
      { ...RECORD, record_id: "DLQ-1" },
      { ...RECORD, record_id: "DLQ-2" },
    ]);
    expect(rows.map((row) => row.recordId)).toEqual(["DLQ-1", "DLQ-2", "DLQ-3"]);
  });
});

describe("§90 — silent is a distinct state from nominal", () => {
  it("reports silent when the endpoints answered with no series at all", () => {
    // A dashboard that renders all-zeroes as "the pipeline is fine and empty"
    // makes a claim the payload does not make.
    const state = buildOpsState({ metrics: {}, pools: {}, ...NO_ERROR });
    expect(state.silent).toBe(true);
  });

  it("is not silent when a pool is reporting", () => {
    const state = buildOpsState({
      metrics: {},
      pools: { browser: { healthy: true, active: 0, capacity: 4, failures: 0 } },
      ...NO_ERROR,
    });
    expect(state.silent).toBe(false);
  });

  it("collects the off-nominal signals into one attention list, worst first", () => {
    const state = buildOpsState({
      metrics: {
        throughput_per_s: 0,
        queues: { frontier: 500_000, small: 5 },
        lags_s: { "a->b": 400, "c->d": 1 },
        storage_growth_b: {},
      },
      pools: { browser: { healthy: true, active: 1, capacity: 4, failures: 0 } },
      ...NO_ERROR,
    });
    expect(state.attention.map((row) => row.key)).toEqual(["throughput", "frontier", "a->b"]);
    // Nominal series are excluded: the attention list is what needs a decision.
    expect(state.attention.map((row) => row.key)).not.toContain("small");
    expect(state.attention.map((row) => row.key)).not.toContain("c->d");
  });

  it("names the endpoints that are missing so the gap is a closable list", () => {
    const state = buildOpsState({ metrics: { throughput_per_s: 1 }, pools: {}, ...NO_ERROR });
    expect(state.missing.length).toBeGreaterThan(0);
    for (const endpoint of state.missing) expect(endpoint).toMatch(/^GET /);
    // §192's gap must be named, not just noted in prose.
    expect(state.missing.some((entry) => entry.includes("redeliveries"))).toBe(true);
  });

  it("reports which endpoints answered", () => {
    const state = buildOpsState({ metrics: {}, pools: {}, ...NO_ERROR });
    expect(state.loaded).toEqual(["/metrics", "/metrics/pools"]);
  });

  it("ignores non-numeric values in a series rather than rendering NaN", () => {
    const rows = lagRows({ good: 5, bad: Number.NaN } as Record<string, number>);
    expect(rows.map((row) => row.key)).toEqual(["good"]);
  });
});
