import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OpsMetrics } from "../lib/api";
import { EconomicsContainer } from "./EconomicsContainer";

vi.mock("../lib/api", () => ({
  fetchOpsMetrics: vi.fn(),
}));

import { fetchOpsMetrics } from "../lib/api";

const METRICS: OpsMetrics = {
  throughput_per_s: 4.2,
  useful_observations: 2_400_000,
  discovery_yield: 0.3,
  duplicate_ratio: 0.12,
  browser_utilization: 0.66,
  lags_s: { ingest: 1.2 },
  queues: { low: 12 },
  storage_growth_b: { parquet: 1_500_000_000 },
  cost_per_1m_obs: 1.5,
  pools: { "acq-1": { healthy: true, active: 3, capacity: 5, failures: 0 } },
};

describe("EconomicsContainer (matri-glen module)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the intelligence-economy ledger from ops metrics", async () => {
    vi.mocked(fetchOpsMetrics).mockResolvedValue(METRICS);
    render(<EconomicsContainer />);
    await waitFor(() => expect(screen.getByTestId("economic-dashboard")).toBeInTheDocument());
    expect(screen.getByTestId("eco-cost / 1M obs")).toHaveTextContent("$1.5");
    expect(screen.getByTestId("eco-running budget")).toHaveTextContent("$3.6");
    expect(screen.getByTestId("eco-pools")).toBeInTheDocument();
    expect(screen.getByTestId("eco-pool")).toHaveAttribute("data-healthy", "true");
  });

  it("refreshes the ledger on demand", async () => {
    vi.mocked(fetchOpsMetrics).mockResolvedValue(METRICS);
    render(<EconomicsContainer />);
    await waitFor(() => expect(screen.getByTestId("eco-refresh")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("eco-refresh"));
    await waitFor(() => expect(fetchOpsMetrics).toHaveBeenCalledTimes(2));
  });

  it("surfaces a load error with retry", async () => {
    vi.mocked(fetchOpsMetrics).mockRejectedValue(new Error("backend down"));
    render(<EconomicsContainer />);
    await waitFor(() => expect(screen.getByTestId("error-view")).toBeInTheDocument());
    vi.mocked(fetchOpsMetrics).mockResolvedValue(METRICS);
    fireEvent.click(screen.getByText("Retry"));
    await waitFor(() => expect(screen.getByTestId("economic-dashboard")).toBeInTheDocument());
  });
});