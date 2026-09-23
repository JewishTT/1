import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Layout } from "./Layout";

function renderLayout(initialPath = "/intel") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="*" element={<Layout />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Layout (NEXUS shell)", () => {
  it("defaults to the OSINT module and shows its sub-navigation", () => {
    renderLayout();
    expect(screen.getByTestId("module-nav")).toBeInTheDocument();
    expect(screen.getByTestId("section-nav")).toHaveTextContent("Intel Board");
    expect(screen.getByTestId("section-nav")).toHaveTextContent("Science Console");
    expect(screen.getByTestId("section-nav")).toHaveTextContent("Connectors");
    expect(screen.getByTestId("nexus-shell")).toHaveAttribute("data-module", "osint");
  });

  it("switches to the ECONOMICS module (matri-glen accent)", () => {
    renderLayout();
    fireEvent.click(screen.getByRole("tab", { name: /ECON/ }));
    expect(screen.getByTestId("nexus-shell")).toHaveAttribute("data-module", "economic");
    expect(screen.getByTestId("section-nav")).toHaveTextContent("Intelligence Economy");
    expect(screen.queryByText("Intel Board")).not.toBeInTheDocument();
  });

  it("switches to the SPECOPS module (crimson accent)", () => {
    renderLayout("/ops");
    expect(screen.getByTestId("nexus-shell")).toHaveAttribute("data-module", "specops");
    expect(screen.getByTestId("section-nav")).toHaveTextContent("SpecOps Console");
    expect(screen.getByTestId("section-nav")).toHaveTextContent("Entity Graph");
    expect(screen.getByTestId("section-nav")).toHaveTextContent("Quarantine / DLQ");
  });

  it("derives the active module from the URL on navigation", () => {
    renderLayout("/экономика-seed");
    fireEvent.click(screen.getByRole("tab", { name: /SPEC/ }));
    expect(screen.getByTestId("nexus-shell")).toHaveAttribute("data-module", "specops");
  });
});