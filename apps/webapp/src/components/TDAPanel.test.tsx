import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { InvariantResult } from "../lib/science/types";
import { TDAPanel } from "./TDAPanel";

const RESULT: InvariantResult = {
  entity_id: "ENT-2001",
  provider: "vr-z2-science",
  structural_only: true,
  series_len: 48,
  embedding: { lag: 2, embed_dim: 2, points: [[0, 1]] },
  diagrams: {
    "0": [
      [0, 1],
      [0.5, 2],
    ],
    "1": [[0.2, null]],
  },
  stats: {
    "0": { num_bars: 2, mean_persistence: 1.25, max_persistence: 2.0, total_persistence: 2.5 },
    "1": { num_bars: 1, mean_persistence: 0, max_persistence: 0, total_persistence: 0 },
  },
  digest: "af2ef693b83e6f7d1f1d200bc57e2c5ba19d51f3f22ac49f9d0ab25c1d248b17",
  drift: { metric: "diagram_sha256", changed: true, delta_max_persistence: 0.8 },
};

describe("TDAPanel", () => {
  it("emits serialized params through onRun", () => {
    const onRun = vi.fn();
    render(<TDAPanel entityId="ENT-2001" result={null} loading={false} error={null} onRun={onRun} />);
    fireEvent.click(screen.getByTestId("run-topology-btn"));
    expect(onRun).toHaveBeenCalledTimes(1);
    const params = onRun.mock.calls[0][0];
    expect(params.entity_id).toBe("ENT-2001");
    expect(params.series.length).toBe(48);
    expect(params.lag).toBe(2);
    expect(params.embed_dim).toBe(2);
    expect(params.prev_diagram).toBeUndefined();
  });

  it("re-uses a previous diagram as prev_diagram and shows drift", () => {
    const onRun = vi.fn();
    const { rerender } = render(
      <TDAPanel entityId="ENT-2001" result={RESULT} loading={false} error={null} onRun={onRun} />,
    );
    fireEvent.click(screen.getByTestId("run-topology-btn"));
    expect(onRun.mock.calls[0][0].prev_diagram).toEqual(RESULT.diagrams);
    rerender(<TDAPanel entityId="ENT-2001" result={RESULT} loading={false} error={null} onRun={onRun} />);
    expect(screen.getByTestId("structural-badge")).toHaveTextContent("STRUCTURAL ONLY");
    expect(screen.getByTestId("topology-result")).toHaveTextContent("sha256:af2ef693b83e…");
  });

  it("renders barcodes, infinite-bar arrowheads and per-dimension stats", () => {
    render(<TDAPanel entityId="ENT-2001" result={RESULT} loading={false} error={null} onRun={vi.fn()} />);
    expect(screen.getByTestId("barcode-dim-0")).toBeInTheDocument();
    expect(screen.getByTestId("barcode-dim-1")).toBeInTheDocument();
    expect(screen.getAllByTestId("barcode-bar-0").length).toBe(2);
    expect(screen.getAllByTestId("barcode-inf-1").length).toBe(1);
    expect(screen.getByTestId("stat-0")).toHaveTextContent("mean 1.250");
  });

  it("shows an empty state when no diagram exists", () => {
    render(
      <TDAPanel
        entityId="ENT-2001"
        result={{ ...RESULT, diagrams: {}, stats: {} }}
        loading={false}
        error={null}
        onRun={vi.fn()}
      />,
    );
    expect(screen.getByTestId("barcode-empty")).toBeInTheDocument();
  });

  it("surfaces errors instead of a result", () => {
    render(<TDAPanel entityId="E1" result={null} loading={false} error="boom" onRun={vi.fn()} />);
    expect(screen.getByTestId("topology-error")).toHaveTextContent("boom");
  });
});