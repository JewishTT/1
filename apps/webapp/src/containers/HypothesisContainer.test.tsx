import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { scienceApi } from "../lib/science/api";
import { HypothesisContainer } from "./HypothesisContainer";

vi.mock("../lib/science/api", () => ({
  scienceApi: {
    listHypotheses: vi.fn(),
    coverage: vi.fn(),
    proposeHypothesis: vi.fn(),
    attachEvidence: vi.fn(),
    discardHypothesis: vi.fn(),
    planCollection: vi.fn(),
  },
}));

describe("HypothesisContainer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(scienceApi.listHypotheses).mockResolvedValue({
      hypotheses: [
        {
          hypothesis_id: "H-1",
          project_id: "P-science",
          text: "Hubs spread fastest",
          status: "proposed",
          evidence_count: 1,
          decisions: [],
        },
      ],
    });
    vi.mocked(scienceApi.coverage).mockResolvedValue({
      project_id: "P-science",
      alive: 1,
      covered: 1,
      ratio: 1.0,
    });
    vi.mocked(scienceApi.proposeHypothesis).mockResolvedValue({
      hypothesis_id: "H-2",
      status: "proposed",
    });
    vi.mocked(scienceApi.attachEvidence).mockResolvedValue({
      hypothesis_id: "H-1",
      evidence_links: 2,
    });
    vi.mocked(scienceApi.discardHypothesis).mockResolvedValue({
      hypothesis_id: "H-1",
      status: "discarded",
    });
    vi.mocked(scienceApi.planCollection).mockResolvedValue({
      project_id: "P-science",
      plan: [{ opportunity_id: "OP-1", expected_gain: 0.31, discriminating_pair: ["H-1", "H-2"] }],
    });
  });

  it("loads hypotheses and coverage into the page", async () => {
    render(<HypothesisContainer />);
    expect(await screen.findByTestId("hyp-list")).toBeInTheDocument();
    expect(screen.getByTestId("hyp-item-H-1").textContent).toContain("Hubs spread fastest");
    expect(screen.getByTestId("coverage").textContent).toContain("1.0");
  });

  it("proposes a hypothesis through the API and reloads", async () => {
    render(<HypothesisContainer />);
    await screen.findByTestId("hyp-list");
    fireEvent.change(screen.getByTestId("hyp-text"), {
      target: { value: "Slow hubs accumulate risk" },
    });
    fireEvent.click(screen.getByTestId("register-btn"));
    await waitFor(() =>
      expect(scienceApi.proposeHypothesis).toHaveBeenCalledWith(
        "P-science",
        "Slow hubs accumulate risk",
      ),
    );
  });

  it("discards a hypothesis through the API", async () => {
    render(<HypothesisContainer />);
    await screen.findByTestId("hyp-list");
    fireEvent.click(screen.getByTestId("discard-H-1"));
    await waitFor(() =>
      expect(scienceApi.discardHypothesis).toHaveBeenCalledWith(
        "H-1",
        "webapp",
        expect.any(String),
      ),
    );
  });

  it("tolerates a missing coverage report", async () => {
    vi.mocked(scienceApi.coverage).mockRejectedValue(new Error("no coverage"));
    render(<HypothesisContainer />);
    expect(await screen.findByTestId("hyp-list")).toBeInTheDocument();
    expect(screen.queryByTestId("coverage")).not.toBeInTheDocument();
  });

  it("runs the information-gain plan", async () => {
    render(<HypothesisContainer />);
    await screen.findByTestId("hyp-list");
    fireEvent.click(screen.getByTestId("plan-btn"));
    expect(await screen.findByTestId("plan-item-OP-1")).toBeInTheDocument();
  });
});
