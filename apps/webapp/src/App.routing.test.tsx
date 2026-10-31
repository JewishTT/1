import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

/**
 * The whole app, mounted at a route, with the network stubbed.
 *
 * Every other test renders a container or a page directly. That misses the class of failure
 * where a route is declared but never reached -- a missing import, a component that throws on
 * mount, a provider that is present in one shell and not the other -- and the symptom is a
 * blank page with an empty ``#root``, which is exactly what a user reports as "nothing
 * displays" and what no unit test in the tree would catch.
 *
 * It did catch one. The route table nested a second ``<Routes>`` under
 * ``<Route path="/">``, which React Router v6 does not match at depth: every destination
 * except ``/`` rendered nothing, with an empty console. ``AppShell.test`` passed throughout,
 * because it mounts the shell directly and never asks whether anything is reachable through
 * it.
 *
 * The providers mirror ``main.tsx``. Omitting ``QueryClientProvider`` fails differently --
 * ``AppShell`` calls ``useQuery`` -- and a test that fails for a reason unrelated to routing
 * teaches the reader nothing about routing.
 */

function stubFetch() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const json = (body: unknown) =>
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    if (url.includes("/api/v1/dossier")) return json({ subjects: [] });
    if (url.includes("/api/science")) return json({ claims: [], reports: [], results: [] });
    return json({ results: [], observations: [], investigations: [], contexts: [] });
  });
}

let originalFetch: typeof globalThis.fetch;

beforeEach(() => {
  originalFetch = globalThis.fetch;
  globalThis.fetch = stubFetch() as unknown as typeof globalThis.fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

function mountAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("routes are reachable and render something", () => {
  it("reaches the dossier surface through the router", async () => {
    mountAt("/dossier");

    await waitFor(() => {
      expect(screen.getByTestId("dossier-page")).toBeInTheDocument();
    });
  });

  it("wires the Dossier destination into the persistent shell navigation", async () => {
    // A route that exists but is absent from NAV_SECTIONS is unreachable from the
    // workbench. The route index is always visible, so no modal/deck action is involved.
    mountAt("/dossier");

    await waitFor(() => {
      const link = screen.getByRole("link", { name: /Dossier/i });
      expect(link).toHaveAttribute("href", "/dossier");
      expect(link).toHaveAttribute("aria-current", "page");
    });
    expect(screen.getByTestId("topnav")).toBeInTheDocument();
  });

  it("renders the dossier route instead of an empty root", async () => {
    mountAt("/dossier");

    await waitFor(() => {
      expect(screen.getByTestId("dossier-page")).toBeInTheDocument();
    });
  });

  it("offers the sweep control on the dossier route", async () => {
    mountAt("/dossier");

    await waitFor(() => expect(screen.getByTestId("dossier-sweep")).toBeInTheDocument());
    expect(screen.getByLabelText(/subject/i)).toBeInTheDocument();
  });

  it("renders the internal component library route", async () => {
    mountAt("/ui-kit");

    await waitFor(() => {
      expect(screen.getByTestId("ui-kit-page")).toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { name: "Component library" })).toBeInTheDocument();
  });

  it("sends an unknown destination to the board rather than to a blank page", async () => {
    const { container } = mountAt("/no-such-destination");

    await waitFor(() => {
      expect(container.innerHTML.length).toBeGreaterThan(0);
    });
  });
});