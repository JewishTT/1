import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TemporalMaterializationPanel } from "./TemporalMaterializationPanel";

const history = {
  tenant_id: "t1",
  entity_id: "e1",
  publication: {
    publication_id: "pub-1",
    source_cut: { cut_id: "cut-1", coverage_start: "2024-01-01T00:00:00Z", coverage_end: "2024-01-29T00:00:00Z" },
    revisions: [
      { revision_id: "wr-1", revision_number: 1, window: { window_start: "2024-01-01T00:00:00Z", window_end: "2024-01-08T00:00:00Z", lifecycle: "nasc…", event_count: 2, first_seen: null, last_seen: null, source_record_ids: [], observation_refs: [] }, window_fingerprint: "fp-1", source_cut_id: "cut-1" },
      { revision_id: "wr-2", revision_number: 2, window: { window_start: "2024-01-08T00:00:00Z", window_end: "2024-01-15T00:00:00Z", lifecycle: "dormant", event_count: 0, first_seen: null, last_seen: null, source_record_ids: [], observation_refs: [] }, window_fingerprint: "fp-2", source_cut_id: "cut-1" },
    ],
    integrity_fingerprint: "integrity-1",
    projection_generation: 1,
  },
};

describe("TemporalMaterializationPanel", () => {
  it("renders windows, source cut, and explicit dormant state", () => {
    render(<TemporalMaterializationPanel entityId="e1" history={history} features={[]} />);
    expect(screen.getByTestId("temporal-materialization-panel")).toBeInTheDocument();
    expect(screen.getByTestId("temporal-cut-id")).toHaveTextContent("cut-1");
    expect(screen.getByTestId("temporal-window")).toBeInTheDocument();
    expect(screen.getByTestId("temporal-window-dormant")).toHaveTextContent("dormant");
  });
});
