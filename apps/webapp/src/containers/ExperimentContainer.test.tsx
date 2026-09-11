import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { scienceApi } from "../lib/science/api";
import { ExperimentContainer } from "./ExperimentContainer";

vi.mock("../lib/science/api", () => ({
  scienceApi: {
    listExperiments: vi.fn(),
    recordExperiment: vi.fn(),
    reproduce: vi.fn(),
  },
}));

describe("ExperimentContainer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(scienceApi.listExperiments).mockResolvedValue({
      runs: [
        { run_id: "EX-1", seed: 7, pipeline_version: "0.1.0", tolerance: 1e-6, reproductions: [] },
      ],
    });
    vi.mocked(scienceApi.recordExperiment).mockResolvedValue({
      run_id: "EX-2",
      pipeline_version: "0.1.0",
      tolerance: 1e-6,
    });
    vi.mocked(scienceApi.reproduce).mockResolvedValue({
      run_id: "EX-1",
      reproduced: true,
      tolerance: 1e-6,
      mismatches: [],
    });
  });

  it("loads the experiment registry", async () => {
    render(<ExperimentContainer />);
    expect(await screen.findByTestId("run-item-EX-1")).toBeInTheDocument();
    expect(screen.getByTestId("run-item-EX-1").textContent).toContain("v0.1.0, seed 7");
  });

  it("records a run through the API and reloads", async () => {
    render(<ExperimentContainer />);
    await screen.findByTestId("run-item-EX-1");
    fireEvent.click(screen.getByTestId("record-btn"));
    await waitFor(() => expect(scienceApi.recordExperiment).toHaveBeenCalled());
    await waitFor(() => expect(scienceApi.listExperiments).toHaveBeenCalledTimes(2));
  });

  it("reproduce logs the outcome (SC-007)", async () => {
    render(<ExperimentContainer />);
    await screen.findByTestId("run-item-EX-1");
    fireEvent.click(screen.getByTestId("reproduce-EX-1"));
    expect(await screen.findByTestId("reproduction-item-EX-1")).toBeInTheDocument();
    expect(screen.getByTestId("reproduction-item-EX-1").getAttribute("data-reproduced")).toBe(
      "true",
    );
  });
});
