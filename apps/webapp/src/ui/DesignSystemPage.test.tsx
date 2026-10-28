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
    expect(screen.getByTestId("ui-kit-panel")).toHaveAttribute("data-variant", "flat");
    expect(screen.getByRole("region", { name: "Navigation & selected state" })).toBeInTheDocument();
  });

  it("provides labelled multiline text and checkbox controls", () => {
    render(<DesignSystemPage />);

    const context = screen.getByLabelText("Investigation context");
    expect(context.tagName).toBe("TEXTAREA");
    fireEvent.change(context, { target: { value: "Illustrative context only" } });
    expect(context).toHaveValue("Illustrative context only");

    const includeRejected = screen.getByLabelText("Include rejected evidence");
    expect(includeRejected).toBeChecked();
    fireEvent.click(includeRejected);
    expect(includeRejected).not.toBeChecked();
    expect(context).toHaveAttribute("aria-describedby");
    expect(includeRejected).toHaveAttribute("aria-describedby");
  });

  it("previews all three density modes locally without changing workspace settings", () => {
    render(<DesignSystemPage />);
    const page = screen.getByTestId("ui-kit-page");
    expect(page).toHaveAttribute("data-density", "standard");

    fireEvent.click(screen.getByLabelText(/Compact/));
    expect(page).toHaveAttribute("data-density", "compact");
    expect(screen.getByLabelText(/Compact/)).toBeChecked();

    fireEvent.click(screen.getByLabelText(/Comfortable/));
    expect(page).toHaveAttribute("data-density", "comfortable");
    expect(screen.getByLabelText(/Comfortable/)).toBeChecked();
  });

  it("demonstrates filterable, keyboard-selectable tabular data", () => {
    render(<DesignSystemPage />);
    fireEvent.click(screen.getByRole("tab", { name: /Data & state/ }));

    const table = screen.getByRole("table", { name: "Design system sample observations" });
    expect(within(table).getAllByRole("row")).toHaveLength(5);

    const identifierHeader = within(table).getByRole("columnheader", { name: /Identifier/ });
    fireEvent.click(within(identifierHeader).getByRole("button", { name: "Sort by Identifier" }));
    expect(identifierHeader).toHaveAttribute("aria-sort", "ascending");
    expect(within(table).getAllByTestId(/^row-/).map((row) => row.getAttribute("data-row-id"))).toEqual([
      "DEMO-ENT-0108",
      "DEMO-FND-0006",
      "DEMO-OBS-0042",
      "DEMO-SRC-0027",
    ]);

    fireEvent.click(screen.getByTestId("row-DEMO-ENT-0108"));
    expect(screen.getByTestId("ui-kit-selected-id")).toHaveTextContent("DEMO-ENT-0108");

    fireEvent.change(screen.getByLabelText("Filter rows"), { target: { value: "DOES-NOT-EXIST" } });
    expect(screen.getByText("No matching records")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Design system sample observations" })).not.toBeInTheDocument();
  });

  it("previews modal focus behavior and dismissible toast announcements", () => {
    render(<DesignSystemPage />);
    fireEvent.click(screen.getByRole("tab", { name: /Feedback/ }));

    const trigger = screen.getByRole("button", { name: "Open modal preview" });
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Acquisition preview" })).toHaveAttribute("aria-modal", "true");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Acquisition preview" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();

    fireEvent.click(screen.getByRole("button", { name: "Preview success toast" }));
    expect(screen.getByTestId("ui-kit-toast")).toHaveAttribute("role", "status");
    expect(screen.getByTestId("ui-kit-toast")).toHaveTextContent("Design-system preview only");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
    expect(screen.queryByTestId("ui-kit-toast")).not.toBeInTheDocument();
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
