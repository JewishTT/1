import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { RobustnessReport } from "../lib/science/types";
import { ScienceClaim, SciencePage } from "./SciencePage";

const claim: ScienceClaim = {
  claim_id: "CL-abc123",
  project_id: "P-science",
  statement: "Degrees in the street network predict recovery time",
  status: "uncertain",
  model_id: "binomial-kde@1.0",
  review: {
    claim_id: "CL-abc123",
    statement: "Degrees in the street network predict recovery time",
    status: "uncertain",
    model_id: "binomial-kde@1.0",
    gates: { calibrated: true, null_model: true, robustness: true, reproduction: false },
    ladder_position: 3,
    top_rung: 4,
    review_state: "review_pending",
    events: [],
  },
};

const report: RobustnessReport = {
  report_id: "RB-1",
  claim_ref: "CL-abc123",
  perturbations: [{ family: "flip", levels: [0.5, 0.9] }],
  sensitivity_summary: { flip: 0.9 },
  flip_rates: { missing: 0.4, flip: 0.9, biased_subsample: 0.2 },
  noise_regions: [],
  downgraded_to_uncertain: true,
};

describe("SciencePage", () => {
  it("renders claims with ladder gates and review state", () => {
    render(<SciencePage claims={[claim]} reports={[]} />);
    expect(screen.getByTestId("ladder-table")).toBeInTheDocument();
    expect(screen.getByTestId("claim-statement").textContent).toContain(
      "Degrees in the street network",
    );
    expect(screen.getByTestId("ladder-position").textContent).toContain("3 / 4");
    expect(screen.getByTestId("gate-null_model").textContent).toContain("✔");
    expect(screen.getByTestId("gate-reproduction").textContent).toContain("—");
    expect(screen.getByTestId("review-state").textContent).toContain("REVIEW_PENDING");
  });

  it("shows empty states", () => {
    render(<SciencePage claims={[]} reports={[]} />);
    expect(screen.getByTestId("no-claims")).toBeInTheDocument();
    expect(screen.getByTestId("no-reports")).toBeInTheDocument();
  });

  it("lists robustness reports with downgrade note", () => {
    render(<SciencePage claims={[claim]} reports={[report]} />);
    expect(screen.getByTestId("report-list")).toBeInTheDocument();
    expect(screen.getByText(/flip rates/)).toBeInTheDocument();
    expect(screen.getByText(/downgraded to UNCERTAIN/)).toBeInTheDocument();
  });

  it("posts a review comment via callback", async () => {
    const onComment = vi.fn(async () => undefined);
    render(<SciencePage claims={[claim]} reports={[]} onComment={onComment} />);
    fireEvent.change(screen.getByTestId("comment-input-CL-abc123"), {
      target: { value: "needs null badge" },
    });
    fireEvent.click(screen.getByTestId("comment-btn-CL-abc123"));
    await waitFor(() => expect(onComment).toHaveBeenCalledWith("CL-abc123", "needs null badge"));
  });
});
