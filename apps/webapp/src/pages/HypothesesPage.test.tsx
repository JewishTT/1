import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { HypothesisWithCoverage, RankedOpportunity } from "../lib/science/types";
import { HypothesesPage } from "./HypothesesPage";

const hyp: HypothesisWithCoverage = {
  hypothesis_id: "H-1",
  project_id: "P-science",
  text: "High-degree hubs are the most probable spreaders",
  status: "proposed",
  evidence_count: 2,
  decisions: [],
};

const coverage = { project_id: "P-science", alive: 3, covered: 2, ratio: 0.67 };

const opportunity: RankedOpportunity = {
  opportunity_id: "OP-1",
  expected_gain: 0.31,
  discriminates: [],
};

/**
 * The exact payload `GET /api/science/hypotheses` and `.../coverage` return against a
 * tenant with no hypotheses. Captured from the running control-plane, not written by
 * hand: `ratio` and `covered` are ABSENT, and the coverage body carries `with_evidence`
 * instead. This is the payload that blanked the page.
 */
const liveEmptyPayload = {
  hypotheses: { hypotheses: [] },
  coverage: {
    project_id: "P-science",
    hypotheses: 0,
    alive: 0,
    dead: 0,
    with_evidence: 0,
    without_evidence: 0,
    evidence_links: 0,
    direction_counts: { supports: 0, refutes: 0, discriminates: 0 },
    requirements_covered: [],
  },
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

  // ── The defect ──────────────────────────────────────────────────────────
  // `coverage.ratio.toFixed(2)` threw "Cannot read properties of undefined (reading
  // 'toFixed')" on the live payload, because the endpoint does not serve `ratio`.
  // React unmounted the tree and `#root` was left empty.

  it("does not throw on the live empty payload and shows an honest empty state", () => {
    expect(() =>
      render(
        <HypothesesPage
          hypotheses={liveEmptyPayload.hypotheses.hypotheses}
          plan={[]}
          coverage={liveEmptyPayload.coverage}
        />,
      ),
    ).not.toThrow();

    expect(screen.getByTestId("hypotheses-page")).toBeInTheDocument();
    expect(screen.getByTestId("no-hypotheses")).toBeInTheDocument();
    expect(screen.getByTestId("no-plan")).toBeInTheDocument();
  });

  it("claims no coverage the payload does not carry", () => {
    // `alive` is 0 and there is no `ratio`. Rendering "coverage 0.00 (0/0 covered)"
    // would state a measurement nobody took; `0/0` is not a ratio at all.
    render(<HypothesesPage hypotheses={[]} plan={[]} coverage={liveEmptyPayload.coverage} />);
    expect(screen.queryByTestId("coverage")).not.toBeInTheDocument();
  });

  it("reads coverage off with_evidence when the payload uses that name", () => {
    render(
      <HypothesesPage
        hypotheses={[]}
        plan={[]}
        coverage={{ project_id: "P", alive: 4, with_evidence: 3 }}
      />,
    );
    expect(screen.getByTestId("coverage").textContent).toContain("(3/4 covered)");
  });

  it("survives a payload missing every optional field on every record", () => {
    expect(() =>
      render(
        <HypothesesPage
          hypotheses={
            [
              { project_id: "P", text: "", status: "", decisions: [] },
              { hypothesis_id: "H-2", project_id: "P", decisions: [] },
            ] as unknown as HypothesisWithCoverage[]
          }
          plan={
            [{ opportunity_id: "OP-9", discriminates: [] }, {}] as unknown as RankedOpportunity[]
          }
          coverage={{}}
        />,
      ),
    ).not.toThrow();
  });

  it("does not render a gain the plan did not report", () => {
    render(
      <HypothesesPage
        hypotheses={[]}
        plan={[{ opportunity_id: "OP-9", discriminates: [] } as unknown as RankedOpportunity]}
        coverage={null}
      />,
    );
    expect(screen.getByTestId("plan-item-OP-9").textContent).toContain(
      "expected gain not reported",
    );
  });

  it("does not render a link count the record did not carry", () => {
    // `evidence_count` used to be defaulted to 0 in the container, which printed
    // "(0 links)" for a hypothesis nobody had measured.
    render(
      <HypothesesPage
        hypotheses={[{ ...hyp, evidence_count: undefined }]}
        plan={[]}
        coverage={null}
      />,
    );
    expect(screen.getByTestId("hyp-item-H-1").textContent).not.toContain("links");
  });

  // ── behaviour ────────────────────────────────────────────────────────────

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
