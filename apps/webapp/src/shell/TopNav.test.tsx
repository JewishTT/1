/**
 * Tests for the normalised navigation.
 *
 * These exist because the navbar was the visible symptom of a structural defect: the
 * router mounted the legacy `components/Layout` *around* the UI 2.0 workspace, so two
 * shells were live and the old navbar was always the one on screen. Nothing asserted
 * which shell owns the chrome, so the defect survived a complete UI 2.0 rebuild.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "../AppShell";
import { FindingsRoute } from "../containers/FindingsRoute";
import { TopNav } from "./TopNav";
import {
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
      {/* AppShell's work-state bar queries the API, so the shell needs a client. */}
      <QueryClientProvider client={new QueryClient()}>
        {tree}
        {withShell ? null : inner}
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("topnav", () => {
  it("renders the module tabs and the section navigation", () => {
    renderAt("/intel");
    expect(screen.getByTestId("topnav")).toBeInTheDocument();
    expect(screen.getByTestId("topnav-modules")).toBeInTheDocument();
    expect(screen.getByTestId("topnav-sections")).toBeInTheDocument();
  });

  it("separates module scope, active location and destination links into two rows", () => {
    renderAt("/investigations");
    const topnav = screen.getByTestId("topnav");
    expect(topnav.querySelector(".ui-topnav-primary")).toContainElement(screen.getByTestId("topnav-modules"));
    expect(topnav.querySelector(".ui-topnav-primary")).toContainElement(topnav.querySelector(".ui-topnav-trail"));
    expect(topnav.querySelector(".ui-topnav-sections")).not.toBeNull();
    expect(topnav.querySelector(".ui-topnav-primary")?.compareDocumentPosition(
      topnav.querySelector(".ui-topnav-sections")!,
    )).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(screen.getByTestId("topnav-sections")).toHaveAttribute("aria-label", "Section navigation");
  });

  it("shows the OSINT destinations by default", () => {
    renderAt("/investigations");
    const nav = screen.getByTestId("topnav-sections");
    expect(nav).not.toHaveTextContent("Connectors");
    expect(nav).toHaveTextContent("Science Console");
  });

  it("keeps the tenant-wide graph out of the SpecOps section", () => {
    renderAt("/specops");
    expect(screen.getByTestId("topnav-sections")).not.toHaveTextContent("Tenant Graph");
  });

  it("opens investigations on the graph, with scope as a filter not a destination", () => {
    // Two tabs whose labels both read "graph" were one destination offered twice: the
    // tenant-wide canvas and the same canvas narrowed to one investigation. The scope
    // switch on the page does that job, and a second tab made the analyst remember which
    // of the two they had meant.
    renderAt("/investigations");
    const nav = screen.getByTestId("topnav-sections");
    expect(nav).toHaveTextContent("Investigations");
    expect(nav).not.toHaveTextContent("Tenant Graph");
    expect(nav).not.toHaveTextContent("Investigation Graph");
  });

  it("has no Intel Board destination", () => {
    // The board was a second home for the same graph work the investigation workspace
    // already owns. Asserting its absence matters: a test that only checked the new labels
    // would still pass if someone re-added the tab later.
    renderAt("/investigations");
    expect(screen.getByTestId("topnav-sections")).not.toHaveTextContent("Intel Board");
  });

  it("switches section sets with the module", () => {
    renderAt("/specops");
    expect(screen.getByTestId("topnav-sections")).toHaveTextContent("Pipeline Operations");
    expect(screen.getByTestId("topnav-sections")).not.toHaveTextContent("Investigations");
  });

  it("marks the active module tab", () => {
    renderAt("/economic");
    const tab = document.querySelector('[data-module="economic"]');
    expect(tab).toHaveAttribute("data-active", "true");
  });

  it("marks the active destination and exposes aria-current", () => {
    renderAt("/specops/connectors");
    const link = screen.getByRole("link", { name: /Connectors/i });
    expect(link).toHaveAttribute("data-active", "true");
    expect(link).toHaveAttribute("aria-current", "page");
  });

  it("navigates when a module tab is pressed", () => {
    renderAt("/investigations");
    fireEvent.click(screen.getByRole("tab", { name: "SPECOPS" }));
    expect(screen.getByTestId("topnav-sections")).toHaveTextContent("Pipeline Operations");
  });

  it("renders the breadcrumb trail", () => {
    renderAt("/quarantine");
    expect(screen.getByTestId("topnav")).toHaveTextContent("Quarantine (DLQ)");
  });

  it("ships no question-mark glyph as iconography", () => {
    // The legacy brand mark was a literal "?"; the standard forbids a text glyph
    // standing in for a drawn icon.
    const { container } = renderAt("/intel", true);
    expect(container.querySelector(".brand-mark")).toBeNull();
    expect(container.querySelector(".ui-brand-mark")).not.toBeNull();
  });

  it("ships no connection status it cannot observe", () => {
    // "NEXUS LINK: ACTIVE" was a hardcoded string reporting a state that did not exist.
    const { container } = renderAt("/intel");
    expect(container.textContent).not.toMatch(/NEXUS LINK/i);
  });

  it("renders nothing outside a router rather than throwing", () => {
    // AppShell is mounted bare in tests and stories; navigation is meaningless there.
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <AppShell>bare</AppShell>
      </QueryClientProvider>,
    );
    expect(container.querySelector(".ui-topnav")).toBeNull();
    expect(screen.getByTestId("app-shell")).toBeInTheDocument();
  });
});

describe("nav data", () => {
  it("routes paths to their module", () => {
    expect(resolveModule("/intel")).toBe("osint");
    expect(resolveModule("/specops")).toBe("specops");
    expect(resolveModule("/specops/quarantine")).toBe("specops");
    expect(resolveModule("/specops/connectors")).toBe("specops");
    expect(resolveModule("/economic")).toBe("economic");
    // The retired bare paths resolve to OSINT here because the router redirects them before
    // the shell ever sees them. Asserted so the difference is deliberate: if this ever flips,
    // someone is matching on a path that no longer renders.
    expect(resolveModule("/quarantine")).toBe("osint");
  });

  it("titles the longest matching prefix, not the first", () => {
    // `/ops/graph` used to be its own destination with its own title. It is now a redirect
    // into `/investigations`, so the only prefix that can win for a SpecOps path is `/ops`.
    // The ordering rule this test protects -- longest prefix first -- is unchanged; what it
    // protects *about* is that no retired graph path can quietly claim a title again.
    expect(resolveTitle("/ops")).toBe("SpecOps Console");
    expect(resolveTitle("/investigations")).toBe("Investigation");
    expect(resolveTitle("/investigations/graph")).toBe("Investigation");
  });

  it("does not light up a query destination when only its path matches", () => {
    // "Intel Board" is /intel and "Entities" is /intel?entity=. react-router matches on
    // pathname alone, so without the query check both would render as current.
    const item = { to: "/intel?entity=ENT-1", label: "Entities", icon: "view-objects" } as const;
    expect(isNavItemActive("/intel", item)).toBe(false);
    expect(isNavItemActive("/intel", item, "?entity=ENT-1")).toBe(true);
    expect(isNavItemActive("/intel", item, "?entity=ENT-2")).toBe(false);
  });

  it("matches nested paths but not siblings", () => {
    const item = { to: "/investigations", label: "Investigations", icon: "view-overview" } as const;
    expect(isNavItemActive("/investigations/INV-1", item)).toBe(true);
    expect(isNavItemActive("/investigationsx", item)).toBe(false);
  });
});

describe("findings destination", () => {
  // The nav carried `{ to: "/findings/0" }`. "0" was never a finding id — it was a
  // placeholder in a real URL, and GET /api/v1/findings/0 answered 404 for every click.
  // A nav entry is static and a finding id is not, so the entry names the list and the
  // resolution happens where the ids are known.

  it("points the nav at the list, not at a placeholder id", () => {
    const items = NAV_SECTIONS.osint.flatMap((section) => section.items);
    const findings = items.find((item) => item.label === "Findings");
    expect(findings?.to).toBe("/findings");
  });

  it("carries no numeric segment in any nav destination", () => {
    // A guard rather than a one-off: a placeholder id in the nav is invisible in review
    // (it is just a string) and only fails at the endpoint, one click later.
    const allItems = Object.values(NAV_SECTIONS).flatMap((sections) =>
      sections.flatMap((section) => section.items),
    );
    for (const item of allItems) {
      expect(item.to, `${item.label} -> ${item.to}`).not.toMatch(/\/\d+(?:$|\?)/);
    }
  });

  it("resolves to a real finding id from the list", () => {
    expect(resolveFindingsPath(["FND-5001"])).toBe("/findings/FND-5001");
    // Head of the ordered list, not an arbitrary pick.
    expect(resolveFindingsPath(["FND-5001", "FND-5002"])).toBe("/findings/FND-5001");
  });

  it("returns null rather than inventing an id when there are no findings", () => {
    // An empty tenant is not a reason to fall back to a plausible-looking path.
    expect(resolveFindingsPath([])).toBeNull();
    expect(resolveFindingsPath(["", "  "])).toBeNull();
  });

  it("still titles a bookmarked placeholder path", () => {
    expect(resolveTitle("/findings/0")).toBe("Finding");
    expect(resolveTitle("/findings")).toBe("Finding");
    expect(resolveTitle("/findings/FND-5001")).toBe("Finding");
  });

  it("marks the destination active from a resolved finding path", () => {
    const item = { to: "/findings", label: "Findings", icon: "view-findings" } as const;
    expect(isNavItemActive("/findings/FND-5001", item)).toBe(true);
    expect(isNavItemActive("/findings", item)).toBe(true);
  });
});

describe("findings route", () => {
  // The live tenant has exactly one finding; an empty tenant is the other state worth
  // proving. Both are stubbed at the network boundary so the route is exercised through
  // the same `api.ts` client the app uses, not through a mocked module.
  const FINDING = {
    finding_id: "FND-5001",
    status: "open",
    why_detected: "persistent topological loop under account Yard",
    structural_evidence: [],
    semantic_evidence: [],
    supporting_graph_region: {},
    supporting_assertions: [],
    observations: [],
    sources: [],
    evidence_resolves: true,
    tenant_id: "default-tenant",
  };

  let findings: (typeof FINDING)[] = [];
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    findings = [FINDING];
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const json = (body: unknown, status = 200) =>
        new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        });
      if (url.endsWith("/api/v1/findings")) return json({ findings });
      if (url.includes("/lineage")) return json({ finding_id: "FND-5001", chain: [] });
      // Anything else is a detail fetch. "0" answers 404 exactly as the real endpoint
      // does — that is the state the redirect exists to leave behind.
      if (url.endsWith("/findings/0")) return json({ detail: "finding not found" }, 404);
      return json(FINDING);
    }) as unknown as typeof globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  // Mirrors App.tsx: one route for both forms.
  function mountAt(path: string) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <MemoryRouter initialEntries={[path]}>
        <QueryClientProvider client={client}>
          <Routes>
            <Route path="/findings/:id?" element={<FindingsRoute />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    );
  }

  it("lands a bookmarked placeholder id on a real finding", async () => {
    // The defect: `/findings/0` returned 404 because no record carried that id. It now
    // resolves, so a kept URL arrives at the finding it names rather than at an error.
    mountAt("/findings/0");
    const view = await screen.findByTestId("finding-view");
    expect(view).toHaveAttribute("data-finding-id", "FND-5001");
  });

  it("resolves the bare list destination to the head of the list", async () => {
    mountAt("/findings");
    const view = await screen.findByTestId("finding-view");
    expect(view).toHaveAttribute("data-finding-id", "FND-5001");
  });

  it("leaves a real id alone", async () => {
    mountAt("/findings/FND-5001");
    const view = await screen.findByTestId("finding-view");
    expect(view).toHaveAttribute("data-finding-id", "FND-5001");
  });

  it("states the absence rather than falling back to another destination", async () => {
    findings = [];
    mountAt("/findings");
    // An empty tenant must not be answered with "/investigations" — "no findings" and
    // "here are the investigations" are different claims, and only one of them is true.
    await waitFor(() => expect(screen.getByTestId("findings-empty")).toBeInTheDocument());
  });
});
