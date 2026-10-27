import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DesignSystemPage } from "./DesignSystemPage";

describe("DesignSystemPage", () => {
  it("renders the public component-library catalogue and active primitives", () => {
    render(<DesignSystemPage />);
    expect(screen.getByRole("heading", { name: "Component library" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Buttons" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Primary action" })).toBeInTheDocument();
    expect(screen.getByRole("tablist", { name: "Component library sections" })).toBeInTheDocument();
  });

  it("demonstrates filterable, keyboard-selectable tabular data", () => {
    render(<DesignSystemPage />);
    fireEvent.click(screen.getByRole("tab", { name: /Data & state/ }));

    const table = screen.getByRole("table", { name: "Design system sample observations" });
    expect(within(table).getAllByRole("row")).toHaveLength(5);
    fireEvent.click(screen.getByTestId("row-DEMO-ENT-0108"));
    expect(screen.getByTestId("ui-kit-selected-id")).toHaveTextContent("DEMO-ENT-0108");

    fireEvent.change(screen.getByLabelText("Filter rows"), { target: { value: "DOES-NOT-EXIST" } });
    expect(screen.getByText("No matching records")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Design system sample observations" })).not.toBeInTheDocument();
  });

  it("shows consistent empty, loading and error feedback primitives", () => {
    render(<DesignSystemPage />);
    fireEvent.click(screen.getByRole("tab", { name: /Feedback/ }));
    expect(screen.getByText("No entities selected")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Refreshing evidence projection");
    expect(screen.getByRole("alert")).toHaveTextContent("Source gateway returned a bounded, retryable error.");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  });
});
