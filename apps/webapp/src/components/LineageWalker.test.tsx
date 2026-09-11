import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LineageWalker } from "./LineageWalker";

const NODES = [
  { id: "f1", kind: "finding" as const, label: "Money movement" },
  { id: "ft1", kind: "feature" as const, label: "loop 2.3" },
  { id: "a1", kind: "assertion" as const, label: "Account X → Yard" },
  { id: "e1", kind: "evidence" as const, label: "transfer record" },
  { id: "o1", kind: "observation" as const, label: "obs-123" },
  { id: "s1", kind: "source" as const, label: "https://src" },
];

const EDGES = [
  { from: "f1", to: "ft1", relation: "uses" },
  { from: "ft1", to: "a1", relation: "supports" },
  { from: "a1", to: "e1", relation: "backed by" },
  { from: "e1", to: "o1", relation: "derived from" },
  { from: "o1", to: "s1", relation: "acquired from" },
];

describe("LineageWalker", () => {
  it("walks from finding to raw source", () => {
    render(<LineageWalker nodes={NODES} edges={EDGES} />);
    expect(screen.getByTestId("lineage-walker")).toBeInTheDocument();
    expect(screen.getByTestId("lineage-chain")).toBeInTheDocument();
    expect(screen.getByTestId("node-finding")).toHaveTextContent("Finding");
    expect(screen.getByTestId("node-source")).toHaveTextContent("Raw source");
  });

  it("renders empty state when no nodes", () => {
    render(<LineageWalker nodes={[]} edges={[]} />);
    expect(screen.getByText("No lineage yet.")).toBeInTheDocument();
  });

  it("emits review decisions for assertion nodes (Vitni pattern)", () => {
    const onReview = vi.fn();
    render(<LineageWalker nodes={NODES} edges={EDGES} onReview={onReview} />);
    expect(screen.getByTestId("review-control")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("review-accept"));
    expect(onReview).toHaveBeenCalledWith("ACCEPT", NODES[2]);
    fireEvent.click(screen.getByTestId("review-uncertain"));
    expect(onReview).toHaveBeenCalledWith("UNCERTAIN", NODES[2]);
  });

  it("renders review buttons without a handler (no crash)", () => {
    render(<LineageWalker nodes={NODES} edges={EDGES} />);
    expect(screen.getByTestId("review-reject")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("review-reject")); // no onReview → noop
  });

  it("renders confidence label + colour for scored nodes (Vitni port)", () => {
    const nodes = [{ ...NODES[0], confidence: 0.85 }, ...NODES.slice(1)];
    render(<LineageWalker nodes={nodes} edges={EDGES} />);
    const badge = screen.getByTestId("confidence-f1");
    expect(badge).toHaveTextContent("Verified");
    expect(badge).toHaveStyle({ color: "#2e7d4f" });
  });

  it("labels edges via the donor taxonomy (relationshipTypes)", () => {
    const edges = [{ from: "ft1", to: "a1", relation: "associated_with" }, ...EDGES];
    render(<LineageWalker nodes={NODES} edges={edges} />);
    expect(screen.getByText("Associated With")).toBeInTheDocument();
  });

  it("renders per-subject fact lists grouped and date-ordered (005 US6)", () => {
    render(
      <LineageWalker
        nodes={NODES}
        edges={EDGES}
        factsBySubject={{
          a1: [
            { id: "fact-2", label: "later transfer", at: "2026-03-02" },
            { id: "fact-1", label: "first mention", at: "2026-01-15" },
          ],
        }}
      />,
    );
    expect(screen.getByTestId("lineage-facts")).toBeInTheDocument();
    const group = screen.getByTestId("facts-a1");
    expect(group).toHaveTextContent("Account X → Yard");
    const times = group.querySelectorAll("time");
    expect(times[0]).toHaveAttribute("datetime", "2026-01-15");
    expect(times[1]).toHaveAttribute("datetime", "2026-03-02");
  });

  it("renders review-status badges from the vitni status map (005 US6)", () => {
    render(
      <LineageWalker
        nodes={NODES}
        edges={EDGES}
        nodeReviewStatuses={
          new Map([["a1", { reviewTone: "conflict", evidenceTone: "gap" }]])
        }
      />,
    );
    const badge = screen.getByTestId("review-status-a1");
    expect(badge).toHaveTextContent("needs attention");
    expect(badge).toHaveTextContent("evidence gap");
  });
});
