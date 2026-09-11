import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FindingViewPage, FindingView } from "./FindingViewPage";

const FINDING: FindingView = {
  finding_id: "FND-5001",
  status: "open",
  why_detected: "loop + velocity spike",
  structural_evidence: [{ feature_id: "FEAT-42", kind: "tda_loop" }],
  semantic_evidence: [{ kind: "named_entity", value: "Yard" }],
  supporting_graph_region: { subgraph: "Yard cluster", diameter: 3 },
  supporting_assertions: ["ASR-9001"],
  observations: [
    { observation_id: "OBS-1001", uri: "http://fixtures.local/report.html", immutable: true },
  ],
  sources: ["http://fixtures.local/report.html"],
  evidence_resolves: true,
};

const LINEAGE = [
  { id: "L1", kind: "finding" as const, label: "FND-5001" },
  { id: "L2", kind: "observation" as const, label: "OBS-1001" },
  { id: "L3", kind: "source" as const, label: "http://fixtures.local/report.html" },
];

const LINEAGE_WITH_ASSERTION = [
  ...LINEAGE,
  { id: "ASR-9001", kind: "assertion" as const, label: "Account X → Yard" },
];

describe("FindingViewPage", () => {
  it("renders reason, region, observations and lineage", () => {
    render(<FindingViewPage finding={FINDING} lineage={LINEAGE} />);
    expect(screen.getByTestId("finding-view")).toHaveAttribute("data-finding-id", "FND-5001");
    expect(screen.getByTestId("reason")).toHaveTextContent("loop + velocity spike");
    expect(screen.getByTestId("graph-region")).toHaveTextContent("Yard cluster");
    expect(screen.getByTestId("observation-sources")).toHaveTextContent("fixtures.local");
    expect(screen.getByTestId("lineage-walker")).toBeInTheDocument();
  });

  it("reports resolving evidence", () => {
    render(<FindingViewPage finding={FINDING} lineage={LINEAGE} />);
    expect(screen.getByTestId("resolves")).toHaveTextContent("immutable observations");
  });

  it("renders lineage chain nodes", () => {
    render(<FindingViewPage finding={FINDING} lineage={LINEAGE} />);
    expect(screen.getByTestId("node-finding")).toHaveTextContent("Finding");
    expect(screen.getByTestId("node-source")).toHaveTextContent("Raw source");
  });

  it("shows no review decisions initially", () => {
    render(<FindingViewPage finding={FINDING} lineage={LINEAGE_WITH_ASSERTION} />);
    expect(screen.getByTestId("review-status")).toHaveTextContent("No review decisions yet.");
  });

  it("wires review buttons to the review API as provenance (FR-006)", async () => {
    const reviewApi = vi.fn().mockResolvedValue({ ok: true, review_id: "RV-1" });
    render(
      <FindingViewPage finding={FINDING} lineage={LINEAGE_WITH_ASSERTION} reviewApi={reviewApi} />,
    );
    fireEvent.click(screen.getByTestId("review-accept"));
    await waitFor(() =>
      expect(reviewApi).toHaveBeenCalledWith("ASR-9001", "ACCEPT", "assertion"),
    );
    await waitFor(() =>
      expect(screen.getByTestId("review-status-ASR-9001")).toHaveTextContent("ACCEPT"),
    );
  });

  it("does not record provenance when review API fails", async () => {
    const reviewApi = vi.fn().mockResolvedValue({ ok: false });
    render(
      <FindingViewPage finding={FINDING} lineage={LINEAGE_WITH_ASSERTION} reviewApi={reviewApi} />,
    );
    fireEvent.click(screen.getByTestId("review-reject"));
    await waitFor(() => expect(reviewApi).toHaveBeenCalled());
    expect(screen.getByTestId("review-status")).toHaveTextContent("No review decisions yet.");
  });
});
