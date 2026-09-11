import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CoverageView, HypothesisWithCoverage, RankedOpportunity } from "../lib/science/types";
import { HypothesesPage } from "./HypothesesPage";

const hyp: HypothesisWithCoverage = {
  hypothesis_id: "H-1",
  project_id: "P-science",
  text: "High-degree hubs are the most probable spreaders",
  status: "proposed",
  evidence_count: 2,
  decisions: [],
};

const coverage: CoverageView = { project_id: "P-science", alive: 3, covered: 2, ratio: 0.67 };

const opportunity: RankedOpportunity = {
  opportunity_id: "OP-1",
  expected_gain: 0.31,
  discriminates: [],
};

describe("HypothesesPage", () => {
  it("renders hypotheses with coverage", () => {
    render(<HypothesesPage hypotheses={[hyp]} plan={[]} coverage={coverage} />);
    expect(screen.getByTestId("hyp-list")).toBeInTheDocument();
    expect(screen.getByTestId("hyp-item-H-1").textContent).toContain("High-degree hubs");
    expect(screen.getByTestId("coverage").textContent).toContain("0.67");
  });

  it("shows empty state", () => {
    render(<HypothesesPage hypotheses={[]} plan={[]} coverage={null} />);
    expect(screen.getByTestId("no-hypotheses")).toBeInTheDocument();
    expect(screen.getByTestId("no-plan")).toBeInTheDocument();
  });

  it("proposes a hypothesis via callback", async () => {
    const onRegister = vi.fn(async () => undefined);
    render(<HypothesesPage hypotheses={[]} plan={[]} coverage={null} onRegister={onRegister} />);
    fireEvent.change(screen.getByTestId("project-input"), { target: { value: "P-2" } });
    fireEvent.change(screen.getByTestId("hyp-text"), {
      target: { value: "Traffic density explains outage spread" },
    });
    fireEvent.click(screen.getByTestId("register-btn"));
    await waitFor(() =>
      expect(onRegister).toHaveBeenCalledWith("P-2", "Traffic density explains outage spread"),
    );
  });

  it("discards a hypothesis via callback", async () => {
    const onDiscard = vi.fn(async () => undefined);
    render(
      <HypothesesPage hypotheses={[hyp]} plan={[]} coverage={coverage} onDiscard={onDiscard} />,
    );
    fireEvent.click(screen.getByTestId("discard-H-1"));
    expect(onDiscard).toHaveBeenCalledWith("H-1");
  });

  it("renders information-gain plan", () => {
    render(<HypothesesPage hypotheses={[]} plan={[opportunity]} coverage={coverage} />);
    expect(screen.getByTestId("plan-list")).toBeInTheDocument();
    expect(screen.getByTestId("plan-item-OP-1").textContent).toContain("0.3100");
  });
});
