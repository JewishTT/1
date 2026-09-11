import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GraphPanel } from "./GraphPanel";

describe("GraphPanel", () => {
  it("is a panel, not the main interface", () => {
    render(<GraphPanel elements={[]} />);
    expect(screen.getByTestId("graph-panel")).toBeInTheDocument();
    expect(screen.getByText("No graph region to render.")).toBeInTheDocument();
  });

  it("renders a canvas container when elements are provided", () => {
    render(
      <GraphPanel
        elements={[
          { id: "n1", label: "Yard", kind: "node" },
          { id: "n2", label: "Acct", kind: "node" },
        ]}
      />,
    );
    expect(screen.getByTestId("graph-canvas")).toBeInTheDocument();
  });

  it("uses a supplied title", () => {
    render(<GraphPanel elements={[]} title="Neighbourhood" />);
    expect(screen.getByText("Neighbourhood")).toBeInTheDocument();
  });
});
