import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { scienceApi } from "../lib/science/api";
import type { RobustnessReport } from "../lib/science/types";
import { ScienceContainer } from "./ScienceContainer";

vi.mock("../lib/science/api", () => ({
  scienceApi: {
    listClaims: vi.fn(),
    listRobustness: vi.fn(),
    getReview: vi.fn(),
    comment: vi.fn(),
    invariant: vi.fn(),
  },
}));

const review = {
  claim_id: "SC-1",
  project_id: "P-science",
  statement: "Hub degree predicts recovery time",
  status: "uncertain",
  model_id: "binomial-kde@1.0",
  gates: { calibrated: true, null_model: true, robustness: true, reproduction: false },
  ladder_position: 3,
  top_rung: 4,
  review_state: "review_pending" as const,
  events: [],
};

const report: RobustnessReport = {
  report_id: "RB-1",
  claim_ref: "SC-1",
  perturbations: [],
  flip_rates: { missing: 0.1, flip: 0.2, biased_subsample: 0.0 },
  sensitivity_summary: {},
  noise_regions: [],
  downgraded_to_uncertain: true,
};

describe("ScienceContainer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(scienceApi.listClaims).mockResolvedValue({ claims: [{ ...review }] });
    vi.mocked(scienceApi.getReview).mockResolvedValue(review);
    vi.mocked(scienceApi.listRobustness).mockResolvedValue({ reports: [report] });
    vi.mocked(scienceApi.comment).mockResolvedValue({ event_id: "EV-1" });
  });

  it("loads claims and robustness reports into the page", async () => {
    render(<ScienceContainer />);
    expect(await screen.findByTestId("ladder-table")).toBeInTheDocument();
    expect(screen.getByTestId("claim-statement").textContent).toContain("Hub degree");
    expect(screen.getByTestId("report-list")).toBeInTheDocument();
    expect(screen.getByText(/downgraded to UNCERTAIN/)).toBeInTheDocument();
  });

  it("tolerates a missing review (proof stage has no artifacts)", async () => {
    vi.mocked(scienceApi.getReview).mockRejectedValue(new Error("no review"));
    render(<ScienceContainer />);
    expect(await screen.findByTestId("ladder-table")).toBeInTheDocument();
    expect(screen.getByTestId("ladder-position").textContent).toContain("—");
  });

  it("posts a comment through the API and reloads", async () => {
    render(<ScienceContainer />);
    await screen.findByTestId("ladder-table");
    fireEvent.change(screen.getByTestId("comment-input-SC-1"), {
      target: { value: "needs reproduction" },
    });
    fireEvent.click(screen.getByTestId("comment-btn-SC-1"));
    await waitFor(() =>
      expect(scienceApi.comment).toHaveBeenCalledWith("SC-1", "webapp", "needs reproduction"),
    );
  });

  it("surfaces load errors", async () => {
    vi.mocked(scienceApi.listClaims).mockRejectedValue(new Error("boom"));
    render(<ScienceContainer />);
    expect(await screen.findByTestId("error-view")).toBeInTheDocument();
  });

  it("runs the topological invariant from the panel and renders barcode stats", async () => {
    vi.mocked(scienceApi.invariant).mockResolvedValue({
      entity_id: "ENT-2001",
      provider: "vr-z2-science",
      structural_only: true,
      series_len: 48,
      embedding: { lag: 2, embed_dim: 2, points: [[0, 1]] },
      diagrams: { "0": [[0, 1.5]] },
      stats: { "0": { num_bars: 1, mean_persistence: 1.5, max_persistence: 1.5, total_persistence: 1.5 } },
      digest: "af2ef693b83e6f7d1f1d200bc57e2c5ba19d51f3f22ac49f9d0ab25c1d248b17",
    });
    render(<ScienceContainer />);
    await screen.findByTestId("ladder-table");
    fireEvent.click(screen.getByTestId("run-topology-btn"));
    await waitFor(() => expect(screen.getByTestId("topology-result")).toBeInTheDocument());
    expect(screen.getByTestId("structural-badge")).toHaveTextContent("STRUCTURAL ONLY");
    expect(screen.getByTestId("barcode-dim-0")).toBeInTheDocument();
    expect(scienceApi.invariant).toHaveBeenCalledWith(
      expect.objectContaining({ entity_id: "ENT-2001", lag: 2, embed_dim: 2, max_dim: 1 }),
    );
  });
});
