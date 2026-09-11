import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OpsDashboardPage, OpsMetrics } from "./OpsDashboardPage";

const METRICS: OpsMetrics = {
  throughput_per_s: 142.3,
  useful_observations: 1048576,
  discovery_yield: 0.41,
  duplicate_ratio: 0.12,
  browser_utilization: 0.25,
  lags_s: { "dispatcher->interpretation": 8.4 },
  queues: { frontier: 24318 },
  storage_growth_b: { observations: 512000000 },
  cost_per_1m_obs: 3.75,
  pools: {
    http: { healthy: true, active: 4, capacity: 4, failures: 0 },
    tda: { healthy: false, active: 0, capacity: 2, failures: 3 },
  },
};

describe("OpsDashboardPage", () => {
  it("renders throughput, knowledge, cost and utilization tiles", () => {
    render(<OpsDashboardPage metrics={METRICS} />);
    expect(screen.getByTestId("ops-dashboard")).toBeInTheDocument();
    expect(screen.getByTestId("op-throughput")).toHaveTextContent(/142/);
    expect(screen.getByTestId("op-useful obs")).toHaveTextContent(/1\s?048\s?576/);
    expect(screen.getByTestId("op-cost / 1M obs")).toHaveTextContent("$3.75");
  });

  it("renders lags, queues and storage", () => {
    render(<OpsDashboardPage metrics={METRICS} />);
    expect(screen.getByTestId("lag")).toHaveTextContent("8.4s");
    expect(screen.getByTestId("queues")).toHaveTextContent(/24\s?318/);
    expect(screen.getByTestId("storage")).toHaveTextContent(/512\.0 MB/);
  });

  it("flags unhealthy worker pools (isolation)", () => {
    render(<OpsDashboardPage metrics={METRICS} />);
    const pools = screen.getAllByTestId("pool");
    const tda = pools.find((p) => p.getAttribute("data-healthy") === "false");
    expect(tda).toBeTruthy();
    expect(tda!.textContent).toContain("UNHEALTHY");
    const http = pools.find((p) => p.getAttribute("data-healthy") === "true");
    expect(http!.textContent).toContain("healthy");
  });

  it("fires refresh", () => {
    const onRefresh = vi.fn();
    render(<OpsDashboardPage metrics={METRICS} onRefresh={onRefresh} />);
    fireEvent.click(screen.getByTestId("refresh-btn"));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
