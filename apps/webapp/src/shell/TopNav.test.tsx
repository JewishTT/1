import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { TopNav } from "./TopNav";

function LocationText() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <TopNav />
      <LocationText />
    </MemoryRouter>,
  );
}

describe("navigation deck", () => {
  it("keeps the shell navigation compact until the operator opens it", () => {
    renderAt("/investigations");
    expect(screen.getByTestId("topnav")).toBeInTheDocument();
    expect(screen.getByTestId("nav-deck-trigger")).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("nav-deck")).not.toBeInTheDocument();
  });

  it("shows the three operational domains and grouped destinations", () => {
    renderAt("/investigations");
    fireEvent.click(screen.getByTestId("nav-deck-trigger"));
    expect(screen.getByRole("dialog", { name: "Navigation deck" })).toBeInTheDocument();
    expect(screen.getByTestId("nav-module-osint")).toBeInTheDocument();
    expect(screen.getByTestId("nav-module-economic")).toBeInTheDocument();
    expect(screen.getByTestId("nav-module-specops")).toBeInTheDocument();
    expect(screen.getByTestId("nav-deck-destinations")).toHaveTextContent("Investigations");
    expect(screen.getByTestId("nav-deck-destinations")).toHaveTextContent("Science Console");
  });

  it("changes the destination list by domain and navigates to the chosen route", () => {
    renderAt("/investigations");
    fireEvent.click(screen.getByTestId("nav-deck-trigger"));
    fireEvent.click(screen.getByTestId("nav-module-economic"));
    expect(screen.getByTestId("nav-deck-destinations")).toHaveTextContent("Intelligence Economy");
    fireEvent.click(screen.getByRole("link", { name: /Intelligence Economy/i }));
    expect(screen.getByTestId("location")).toHaveTextContent("/economic");
    expect(screen.queryByTestId("nav-deck")).not.toBeInTheDocument();
  });

  it("marks the exact current destination", () => {
    renderAt("/specops/connectors");
    fireEvent.click(screen.getByTestId("nav-deck-trigger"));
    const activeLink = screen.getByRole("link", { name: /Connectors/i });
    expect(activeLink).toHaveAttribute("aria-current", "page");
    expect(activeLink).toHaveAttribute("data-active", "true");
  });

  it("closes with Escape and restores focus to the trigger", () => {
    renderAt("/investigations");
    const trigger = screen.getByTestId("nav-deck-trigger");
    fireEvent.click(trigger);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("nav-deck")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("keeps the navigation absent outside a router", () => {
    render(<TopNav />);
    expect(screen.queryByTestId("topnav")).not.toBeInTheDocument();
  });
});
