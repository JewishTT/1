import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { AppShell } from "../AppShell";
import { TopNav } from "./TopNav";
import {
  NAV_MODULES,
  NAV_SECTIONS,
  isNavItemActive,
  resolveFindingsPath,
  resolveModule,
  resolveTitle,
} from "./nav";

function renderAt(path: string, withShell = false) {
  const inner = (
    <Routes>
      <Route path="*" element={<div data-testid="page">page</div>} />
    </Routes>
  );
  const tree = withShell ? <AppShell>{inner}</AppShell> : <TopNav />;
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={new QueryClient()}>
        {tree}
        {withShell ? null : inner}
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("persistent field navigation", () => {
  it("keeps the full route index visible without opening a modal deck", () => {
    renderAt("/investigations");
    expect(screen.getByTestId("topnav")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Operational domains" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "osint workspaces" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Investigations/i })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByTestId("nav-deck")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-deck-trigger")).not.toBeInTheDocument();
  });

  it("shows all three operational domains as direct destinations", () => {
    renderAt("/investigations");
    for (const module of NAV_MODULES) {
      expect(screen.getByTestId(`nav-module-${module.key}`)).toBeInTheDocument();
      expect(screen.getByTestId(`nav-module-${module.key}`)).toHaveAttribute("href", module.landing);
    }
    const activeDomain = screen.getByTestId("nav-module-osint");
    expect(activeDomain).toHaveAttribute("data-active", "true");
    expect(activeDomain).toHaveAttribute("aria-current", "location");
    expect(screen.getByTestId("nav-module-specops")).not.toHaveAttribute("aria-current");
  });

  it("keeps destination groups visible for the active domain", () => {
    renderAt("/investigations");
    const nav = screen.getByRole("navigation", { name: "osint workspaces" });
    expect(nav).toHaveTextContent("COLLECT");
    expect(nav).toHaveTextContent("INVESTIGATE");
    expect(nav).toHaveTextContent("ANALYZE");
    expect(nav).toHaveTextContent("Science Console");
    expect(nav).toHaveTextContent("Research Cases");
  });

  it("switches destination sets when the domain route changes", () => {
    renderAt("/investigations");
    fireEvent.click(screen.getByTestId("nav-module-specops"));
    expect(screen.getByRole("navigation", { name: "specops workspaces" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "specops workspaces" })).toHaveTextContent("Pipeline Operations");
    expect(screen.queryByRole("navigation", { name: "osint workspaces" })).not.toBeInTheDocument();
  });

  it("marks the active domain and exact destination", () => {
    renderAt("/specops/connectors");
    expect(screen.getByTestId("nav-module-specops")).toHaveAttribute("aria-current", "location");
    const active = screen.getByRole("link", { name: /Connectors/i });
    expect(active).toHaveAttribute("data-active", "true");
    expect(active).toHaveAttribute("aria-current", "page");
  });

  it("keeps the tenant-wide graph out of the SpecOps section", () => {
    renderAt("/specops");
    expect(screen.queryByText("Tenant Graph")).not.toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "specops workspaces" })).toHaveTextContent("Pipeline Operations");
  });

  it("retains the consolidated investigation graph destination", () => {
    renderAt("/investigations");
    const destinations = screen.getByRole("navigation", { name: "osint workspaces" });
    expect(destinations).toHaveTextContent("Investigations");
    expect(destinations).not.toHaveTextContent("Tenant Graph");
    expect(destinations).not.toHaveTextContent("Investigation Graph");
    expect(destinations).not.toHaveTextContent("Intel Board");
  });

  it("handles query-specific destinations without lighting up a path-only sibling", () => {
    const item = { to: "/intel?entity=ENT-1", label: "Entities", icon: "view-objects" } as const;
    expect(isNavItemActive("/intel", item)).toBe(false);
    expect(isNavItemActive("/intel", item, "?entity=ENT-1")).toBe(true);
    expect(isNavItemActive("/intel", item, "?entity=ENT-2")).toBe(false);
  });

  it("matches nested paths but not siblings", () => {
    const item = { to: "/investigations", label: "Investigations", icon: "view-graph" } as const;
    expect(isNavItemActive("/investigations/INV-1", item)).toBe(true);
    expect(isNavItemActive("/investigationsx", item)).toBe(false);
  });

  it("renders nothing outside a router rather than throwing", () => {
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <AppShell>bare</AppShell>
      </QueryClientProvider>,
    );
    expect(container.querySelector(".ui-primary-nav")).toBeNull();
    expect(screen.getByTestId("app-shell")).toBeInTheDocument();
  });

  it("keeps the app shell's main workspace as a separate flex region", () => {
    const { container } = renderAt("/investigations", true);
    expect(screen.getByTestId("shell-main")).toBeInTheDocument();
    expect(container.querySelector(".ui-primary-nav + .ui-shell-main")).not.toBeNull();
  });
});

describe("navigation data", () => {
  it("routes paths to their module", () => {
    expect(resolveModule("/intel")).toBe("osint");
    expect(resolveModule("/specops")).toBe("specops");
    expect(resolveModule("/specops/quarantine")).toBe("specops");
    expect(resolveModule("/specops/connectors")).toBe("specops");
    expect(resolveModule("/economic")).toBe("economic");
    expect(resolveModule("/quarantine")).toBe("osint");
  });

  it("titles the longest matching prefix", () => {
    expect(resolveTitle("/ops")).toBe("SpecOps Console");
    expect(resolveTitle("/investigations")).toBe("Investigation");
    expect(resolveTitle("/investigations/graph")).toBe("Investigation");
  });

  it("keeps findings navigation on the list route instead of inventing an id", () => {
    const items = NAV_SECTIONS.osint.flatMap((section) => section.items);
    expect(items.find((item) => item.label === "Findings")?.to).toBe("/findings");
    expect(resolveFindingsPath([])).toBeNull();
    expect(resolveFindingsPath(["", "FND-42"])).toBe("/findings/FND-42");
  });
});
