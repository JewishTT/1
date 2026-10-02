import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { QuarantineRecord } from "../lib/api";
import { OpsCanvas } from "./OpsCanvas";
import { QuarantineWorkspace } from "./QuarantineWorkspace";
import { OperationsWorkspace } from "./OperationsWorkspace";

/**
 * The Ops surfaces, mounted as the workspace's Ops view (T130, FR-109).
 *
 * `src/ops/` shipped three finished surfaces — 3 462 lines, 54 tests — and none
 * of them was reachable: `/ops` rendered the pre-UI-2.0 `OpsDashboardPage`, and no
 * workspace view mounted any of them. The work was done and unconnected.
 *
 * Two things are asserted here that a per-surface unit test could not:
 *
 *   1. **The mutation round trip.** `replay` and `reEvaluate` both call
 *      `queryClient.invalidateQueries({ queryKey: ["ops", "quarantine"] })`. That
 *      is correct, and it was correct before — but it was never exercised through
 *      a mounted surface, so "correct" was a claim about code that no test
 *      reached. Re-evaluation REMOVES the record; a missing invalidation would
 *      leave a row on screen for a record that no longer exists, which is a false
 *      statement about the pipeline's state.
 *   2. **That the workspace's `onOpenQuarantine` reaches the board.** The
 *      Operations surface only renders "Check quarantine" when a host passes the
 *      handler, because §69 forbids a control that cannot succeed. No host ever
 *      did, so the affordance was correctly absent and the surface was
 *      unreachable from the place an operator would look for it.
 */

vi.mock("../lib/api", () => ({
  api: {
    listQuarantine: vi.fn(),
    replayQuarantined: vi.fn(),
    reEvaluateQuarantined: vi.fn(),
    getOpsMetrics: vi.fn(),
    getWorkerPools: vi.fn(),
    listConnectors: vi.fn(),
  },
}));

const { api } = await import("../lib/api");

// `vi.mocked` for the same reason as the objects tests: the factory's `vi.fn()`
// has no `.mockResolvedValue` in its type, so without this the file fails `tsc`
// while the runtime behaviour is fine.
const listQuarantine = vi.mocked(api.listQuarantine);
const replayQuarantined = vi.mocked(api.replayQuarantined);
const reEvaluateQuarantined = vi.mocked(api.reEvaluateQuarantined);
const getOpsMetrics = vi.mocked(api.getOpsMetrics);
const getWorkerPools = vi.mocked(api.getWorkerPools);
const listConnectors = vi.mocked(api.listConnectors);

/** Nominal metrics: the board must never render a fabricated zero. */
const METRICS = {
  throughput_per_s: 12,
  useful_observations: 40,
  discovery_yield: 0.2,
  duplicate_ratio: 0.1,
  browser_utilization: 0.1,
  lags_s: { "dispatcher->interpretation": 2 },
  queues: { frontier: 3 },
  storage_growth_b: { observations: 1024 },
  cost_per_1m_obs: 1,
} as never;

/** Metrics refused, pools fine — the error path the retry assertion needs. */
const METRICS_DOWN = new Error("502 from /metrics");
const POOLS = { pools: {}, healthy: [] } as never;
const NO_CONNECTORS = { connectors: [] } as never;

/** The three ops endpoints answer. Called from `beforeEach` so no test forgets. */
function opsUp() {
  getOpsMetrics.mockResolvedValue(METRICS);
  getWorkerPools.mockResolvedValue(POOLS);
  listConnectors.mockResolvedValue(NO_CONNECTORS);
}

/** Metrics refused. The board's error state, with its retry. */
function opsError() {
  getOpsMetrics.mockRejectedValue(METRICS_DOWN);
  getWorkerPools.mockResolvedValue(POOLS);
  listConnectors.mockResolvedValue(NO_CONNECTORS);
}

function record(id: string, overrides: Partial<QuarantineRecord> = {}): QuarantineRecord {
  return {
    record_id: id,
    reason: "schema mismatch",
    topic: "cognitive-events--t-obs",
    partition: 0,
    preserved: true,
    // The donor's own shape: base64(payload)[:12] + ":" + sha256(payload)[:12].
    // `model.splitFingerprint` enforces that only the digest half is rendered.
    fingerprint: "aGVsbG8gd29ybGQ=:deadbeefcafe",
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    queryClient,
    ...render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listQuarantine.mockResolvedValue({ tenant_id: "t", records: [record("DLQ-1"), record("DLQ-2")] });
  replayQuarantined.mockResolvedValue({
    record_id: "DLQ-1",
    base64_payload: "aGVsbG8gd29ybGQ=",
    replayed_from_quarantine: true,
  });
  reEvaluateQuarantined.mockResolvedValue({ record_id: "DLQ-1", accepted: false, purged: true } as never);
});

/* ── The mutations ────────────────────────────────────────────────────── */

describe("T130 — QuarantineWorkspace's mutations invalidate the quarantine query", () => {
  it("replay posts the record and invalidates the query it belongs to", async () => {
    renderWithClient(<QuarantineWorkspace />);
    await screen.findByTestId("quar-row-DLQ-1");

    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    fireEvent.click(screen.getByTestId("quar-replay-DLQ-1"));

    await waitFor(() => expect(replayQuarantined).toHaveBeenCalledWith("DLQ-1"));
    // The prefix key, not the exact one: the topic-filtered variants
    // (`["ops", "quarantine", topic]`) are the same data, so a replay under one
    // filter must refresh the list under every other.
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["ops", "quarantine"] }),
    );
    invalidate.mockRestore();
  });

  it("replay re-reads the list, so a record the pipeline re-queued appears", async () => {
    const { queryClient } = renderWithClient(<QuarantineWorkspace />);
    await screen.findByTestId("quar-row-DLQ-1");

    // The server now serves a third record. A mutation without invalidation
    // leaves the stale list on screen, and the operator is looking at a queue
    // that does not exist.
    listQuarantine.mockResolvedValue({
      tenant_id: "t",
      records: [record("DLQ-1"), record("DLQ-2"), record("DLQ-3")],
    });
    fireEvent.click(screen.getByTestId("quar-replay-DLQ-1"));

    await waitFor(() => expect(screen.getByTestId("quar-row-DLQ-3")).toBeInTheDocument());
    expect(queryClient.getQueryData(["ops", "quarantine", ""])).toBeDefined();
  });

  it("re-evaluate posts the record and invalidates, and the removed row leaves the list", async () => {
    renderWithClient(<QuarantineWorkspace />);
    const row = await screen.findByTestId("quar-row-DLQ-1");
    fireEvent.click(row);

    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    // Re-evaluation REMOVES the record, so the row must disappear rather than
    // linger as a claim about a record the pipeline no longer holds.
    listQuarantine.mockResolvedValue({ tenant_id: "t", records: [record("DLQ-2")] });

    fireEvent.click(screen.getByTestId("quar-detail-reevaluate"));

    await waitFor(() => expect(reEvaluateQuarantined).toHaveBeenCalledWith("DLQ-1"));
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["ops", "quarantine"] }),
    );
    await waitFor(() => expect(screen.queryByTestId("quar-row-DLQ-1")).not.toBeInTheDocument());
    invalidate.mockRestore();
  });

  it("offers re-evaluation only where it can succeed, and says why where it cannot", async () => {
    listQuarantine.mockResolvedValue({
      tenant_id: "t",
      records: [record("DLQ-1"), record("DLQ-2", { preserved: false, fingerprint: "AAAA:111111111111" })],
    });
    renderWithClient(<QuarantineWorkspace />);

    fireEvent.click(await screen.findByTestId("quar-row-DLQ-1"));
    expect(screen.getByTestId("quar-detail-reevaluate")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("quar-row-DLQ-2"));
    expect(screen.queryByTestId("quar-detail-reevaluate")).not.toBeInTheDocument();
    expect(screen.getByTestId("quar-not-replayable-DLQ-2")).toHaveTextContent(/not replayable/i);
  });
});

/* ── The Ops view ─────────────────────────────────────────────────────── */

describe("T130 — Ops is a workspace view, mounting all three surfaces", () => {
  it("mounts the operations board and states its scope", async () => {
    opsUp();
    renderWithClient(<OpsCanvas />);
    // `operations-workspace` is on the LOADING branch too, so waiting for it would
    // assert against a skeleton. The scope line only exists once the board has
    // real numbers, which is the state this assertion is about.
    expect(await screen.findByTestId("ops-scope")).toHaveTextContent(
      /not scoped to one investigation/i,
    );
    expect(screen.getByTestId("ops-canvas")).toHaveAttribute("data-panel", "operations");
  });

  it("wires 'Check quarantine' to the quarantine panel, so the affordance exists", async () => {
    opsError();

    renderWithClient(<OpsCanvas />);
    const quarantine = await screen.findByTestId("ops-error-quarantine");

    fireEvent.click(quarantine);
    expect(screen.getByTestId("quarantine-workspace")).toBeInTheDocument();
    expect(screen.getByTestId("ops-canvas")).toHaveAttribute("data-panel", "quarantine");
  });

  it("carries the scope statement on the tab bar, where the numbers are read", async () => {
    opsError();

    renderWithClient(<OpsCanvas />);
    expect(
      screen.getByText(/tenant-wide · not scoped to one investigation/i),
    ).toBeInTheDocument();
  });

  it("mounts the source fabric on its own panel", async () => {
    opsError();

    renderWithClient(<OpsCanvas />);
    fireEvent.click(await screen.findByTestId("tab-sources"));
    // The fabric is a registry rendered from the runtime mirror plus `/connectors`
    // — it must name the runtimes even with no connectors registered, because an
    // empty catalogue reads as "this platform has no sources".
    expect(screen.getByTestId("source-catalog")).toBeInTheDocument();
  });

  it("keeps the board and the quarantine table on independent query keys (§68)", async () => {
    opsError();

    const { queryClient } = renderWithClient(<OpsCanvas />);
    await screen.findByTestId("ops-error-quarantine");

    // An ops refresh must not refetch the graph's data and vice versa. Every
    // request this view makes sits under one prefix, and nothing else is
    // touched: that is the whole of §68's query half.
    const prefixes = queryClient.getQueryCache().getAll().map((query) => query.queryKey[0]);
    expect(prefixes).toContain("ops");
    expect(prefixes.every((prefix) => prefix === "ops")).toBe(true);
  });
});

/* ── The board's own honesty contract ─────────────────────────────────── */

describe("T130 — OperationsWorkspace reports its scope and its gaps", () => {
  it("reports the scope on the loaded board, not a number it cannot source", async () => {
    opsUp();

    renderWithClient(<OperationsWorkspace />);
    // `operations-workspace` is ALSO on the loading branch, so waiting for it
    // would assert against a skeleton. The scope line only exists once the board
    // has real numbers, which is the state this assertion is about.
    expect(await screen.findByTestId("ops-scope")).toHaveTextContent(/tenant-wide/i);
    expect(screen.getByTestId("ops-title")).toBeInTheDocument();
  });

  it("retries the failed endpoint when the metrics call is refused", async () => {
    opsError();

    renderWithClient(<OperationsWorkspace />);
    const retry = await screen.findByTestId("ops-error-retry");

    getOpsMetrics.mockClear();
    fireEvent.click(retry);
    await waitFor(() => expect(getOpsMetrics).toHaveBeenCalled());
  });
});
