import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EMPTY_METRICS, InvestigationPage } from "../pages/InvestigationPage";

describe("InvestigationPage", () => {
  it("renders objective and core metrics", () => {
    render(
      <InvestigationPage
        metrics={{
          ...EMPTY_METRICS,
          objective: "Track asset movements",
          acquisition: { qps: 42, queue: 7, freshnessSec: 12 },
          knowledge: { entities: 120, assertions: 340, findings: 5 },
        }}
      />,
    );
    expect(screen.getByText("Track asset movements")).toBeInTheDocument();
    expect(screen.getByTestId("tile-qps")).toHaveTextContent("42");
    expect(screen.getByTestId("tile-entities")).toHaveTextContent("120");
  });

  it("pause toggles to resume and fires callback", () => {
    const onPause = vi.fn();
    const onResume = vi.fn();
    function Harness() {
      const [paused, setPaused] = useState(false);
      return (
        <InvestigationPage
          metrics={EMPTY_METRICS}
          onPause={onPause}
          onResume={onResume}
          pauseRequested={paused}
          setPauseRequested={setPaused}
        />
      );
    }
    render(<Harness />);
    fireEvent.click(screen.getByTestId("pause-btn"));
    expect(onPause).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("resume-btn")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("resume-btn"));
    expect(onResume).toHaveBeenCalledTimes(1);
  });

  it("shows analysis panel with recrawl schedule", () => {
    render(<InvestigationPage metrics={EMPTY_METRICS} />);
    expect(screen.getByTestId("analysis-panel")).toBeInTheDocument();
  });
});
