import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, ResolutionPair } from "../lib/api";
import { ReviewContainer, pairsToReviewAssertions } from "./ReviewContainer";

vi.mock("../lib/api", () => ({
  api: {
    listResolutions: vi.fn(),
    decideResolution: vi.fn(),
  },
}));

const PAIRS: ResolutionPair[] = [
  {
    pair_key: "ENT-1::ENT-3",
    review_id: "rev-1",
    decision: "UNCERTAIN",
    reviewer_id: "analyst-1",
    reviewed_at: "2026-02-01T10:00:00Z",
    reasoning: "",
  },
  {
    pair_key: "ENT-2::ENT-4",
    review_id: "rev-2",
    decision: "ACCEPT",
    reviewer_id: "analyst-1",
    reviewed_at: "2026-01-10T10:00:00Z",
    reasoning: "",
  },
  {
    pair_key: "ENT-5::ENT-7",
    review_id: "rev-3",
    decision: "OPEN",
    reviewer_id: "analyst-1",
    reviewed_at: "2026-01-15T10:00:00Z",
    reasoning: "",
  },
];

function listResolutions() {
  return { investigation_id: "inv-1", tenant_id: "tenant-1", pairs: PAIRS };
}

describe("ReviewContainer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listResolutions).mockResolvedValue(listResolutions());
    vi.mocked(api.decideResolution).mockResolvedValue({
      investigation_id: "inv-1",
      pair_key: "ENT-5::ENT-7",
      review: {
        review_id: "rev-4",
        target_type: "candidate",
        target_id: "ENT-5::ENT-7",
        decision: "REJECT",
        analyst_id: "analyst-1",
        reasoning: "",
        reviewed_at: "2026-03-01T00:00:00Z",
        tenant_id: "tenant-1",
        provenance: {},
        replayed: false,
      },
      candidate_state: "rejected",
      event: "resolution.candidate_decided",
    });
  });

  it("tolerates an empty queue", async () => {
    vi.mocked(api.listResolutions).mockResolvedValue({
      investigation_id: "inv-1",
      tenant_id: "tenant-1",
      pairs: [],
    });
    render(<ReviewContainer investigationId="inv-1" />);
    expect(await screen.findByTestId("review-queue-empty")).toBeInTheDocument();
  });

  it("unreviewed-first sort puts pending pairs above decided ones", async () => {
    render(<ReviewContainer investigationId="inv-1" />);
    const items = await screen.findByTestId("review-queue-items");
    const keys = within(items).getAllByTestId("review-state-badge");
    expect(keys[0]).toHaveTextContent("unreviewed");
    expect(keys[2]).toHaveTextContent("accepted");
  });

  it("renders derived badges: confidence, evidence, node tone", async () => {
    render(<ReviewContainer investigationId="inv-1" />);
    await screen.findByTestId("review-queue-items");
    expect(screen.getByTestId("review-confidence-rev-1")).toHaveTextContent("Unverified");
    expect(screen.getByTestId("review-confidence-rev-2")).toHaveTextContent("Verified");
    expect(screen.getAllByTestId("review-evidence")).not.toHaveLength(0);
    expect(screen.getAllByTestId("review-tone")[0]).toHaveTextContent("evidence gap");
  });

  it("filters by review state via the filter select", async () => {
    render(<ReviewContainer investigationId="inv-1" />);
    await screen.findByTestId("review-queue-items");
    fireEvent.change(screen.getByLabelText("Review state"), {
      target: { value: "accepted" },
    });
    const items = screen.getByTestId("review-queue-items");
    const badges = within(items).getAllByTestId("review-state-badge");
    expect(badges).toHaveLength(1);
    expect(badges[0]).toHaveTextContent("accepted");
  });

  it("records a decision through the API and reloads the queue", async () => {
    render(<ReviewContainer investigationId="inv-1" />);
    await screen.findByTestId("review-queue-items");
    fireEvent.click(screen.getByTestId("decide-rev-3-reject"));
    await waitFor(() =>
      expect(api.decideResolution).toHaveBeenCalledWith("inv-1", "ENT-5::ENT-7", "REJECT"),
    );
    await waitFor(() => expect(api.listResolutions).toHaveBeenCalledTimes(2));
  });

  it("maps pairs to review assertions with date ordering signals", () => {
    const assertions = pairsToReviewAssertions(PAIRS);
    expect(assertions).toHaveLength(3);
    expect(assertions[0]).toMatchObject({
      id: "rev-1",
      subject_id: "ENT-1::ENT-3",
      path: "resolution-candidate",
      review_state: "disputed",
      confidence: "unverified",
    });
    expect(assertions[2]).toMatchObject({ review_state: "unreviewed" });
    expect(assertions[0]!.created_at).toBeGreaterThan(assertions[1]!.created_at);
  });
});