import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TimelineView } from "./TimelineView";

const ENTRIES = [
  { id: "OBS-1001", label: "report.html", at: "2026-01-01T00:00:00Z" },
  { id: "OBS-1002", label: "ledger.html", at: "2026-01-03T00:00:00Z" },
  { id: "OBS-1003", label: "contacts.html", at: "2026-01-06T00:00:00Z" },
];

describe("TimelineView", () => {
  it("renders an empty message when there are no entries", () => {
    render(<TimelineView entries={[]} />);
    expect(screen.getByTestId("entity-timeline")).toHaveTextContent("No timeline observed.");
  });

  it("draws markers and a time window when timestamps are present", () => {
    render(<TimelineView entries={ENTRIES} metrics={{ burstiness: 0.7, events_per_day: 0.5 }} />);
    expect(screen.getByTestId("timeline-svg")).toBeInTheDocument();
    expect(screen.getAllByTestId("timeline-marker")).toHaveLength(3);
    expect(screen.getByTestId("entity-timeline")).toHaveTextContent("OBS-1001");
    expect(screen.getByTestId("timeline-metrics")).toHaveTextContent("burstiness 0.70");
  });

  it("falls back to sequence order without timestamps", () => {
    render(
      <TimelineView
        entries={[
          { id: "A", label: "x" },
          { id: "B", label: "y" },
        ]}
      />,
    );
    expect(screen.getByTestId("entity-timeline")).toHaveTextContent("sequence order");
  });
});