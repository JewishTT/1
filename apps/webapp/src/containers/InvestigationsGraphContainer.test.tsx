import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InvestigationsGraphContainer } from "./InvestigationsGraphContainer";
import { entityProjectionKey, findingsKey } from "../lib/queryKeys";

/**
 * The Investigations screen, mounted as the app mounts it.
 *
 * Two things are asserted that nothing else in the tree asserts, and both are regressions
 * this screen actually suffered:
 *
 *   1. **The tenant scope is a scope.** `All investigations` is the default landing, and it
 *      used to land on the canvas's own "No investigation loaded" placeholder with nothing
 *      else on screen — a dead end that reads as "pick something first" while the switch
 *      above it says you do not have to. The screen must therefore carry its own content in
 *      tenant scope: the graph region plus a way to seed it.
 *   2. **The stream is still subscribed.** Intel Board was the only surface subscribing for
 *      graph purposes and it was deleted; without a subscription here, pipeline work lands
 *      in the database and the canvas keeps showing the projection from before. This test
 *      drives the REAL `usePipelineStream` through a stand-in `EventSource` — mocking the
 *      hook would assert that the container called a mock, which is true whether or not the
 *      subscription is wired at all.
 */

vi.mock("../lib/api", () => ({
  api: {
    listInvestigations: vi.fn(),
    createInvestigation: vi.fn(),
    createEntity: vi.fn(),
    specOpsGraph: vi.fn(),
    listFindings: vi.fn(),
  },
}));

const { api } = await import("../lib/api");

const listInvestigations = vi.mocked(api.listInvestigations);
const createInvestigation = vi.mocked(api.createInvestigation);
const createEntity = vi.mocked(api.createEntity);
const specOpsGraph = vi.mocked(api.specOpsGraph);
const listFindings = vi.mocked(api.listFindings);

/**
 * jsdom ships no `EventSource`, which is why `usePipelineStream` no-ops there. This stands
 * in for it: it records the listeners the hook registers and lets a test deliver a named
 * event the way the server would.
 */
class StubEventSource {
  static instances: StubEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  closed = false;
  private readonly listeners = new Map<string, Array<(event: MessageEvent) => void>>();

  constructor(readonly url: string) {
    StubEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void): void {
    const existing = this.listeners.get(type) ?? [];
    existing.push(listener);
    this.listeners.set(type, existing);
  }

  close(): void {
    this.closed = true;
  }

  /** Deliver one named SSE event, as `/api/v1/stream` would. */
  fire(type: string, payload: unknown): void {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ data: JSON.stringify(payload) } as MessageEvent);
    }
  }
}

let originalEventSource: typeof globalThis.EventSource | undefined;

beforeEach(() => {
  vi.clearAllMocks();
  StubEventSource.instances = [];
  originalEventSource = globalThis.EventSource;
  globalThis.EventSource = StubEventSource as unknown as typeof EventSource;

  listInvestigations.mockResolvedValue({
    investigations: [
      {
        investigation_id: "INV-1",
        name: "Nightjar",
        tenant_id: "t-1",
        objective: {},
        seeds: [],
        scope: {},
        policy_id: null,
        state: "ACTIVE",
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
  });
  specOpsGraph.mockResolvedValue({ nodes: [], edges: [] });
  listFindings.mockResolvedValue({ findings: [] });
  createEntity.mockResolvedValue({
    entity: { entity_id: "ENT-1" },
    event: "entity.created",
  } as never);
  createInvestigation.mockResolvedValue({
    investigation_id: "INV-2",
    name: "Kestrel",
    state: "ACTIVE",
    event: "investigation.created",
    tenant_id: "t-1",
  });
});

afterEach(() => {
  globalThis.EventSource = originalEventSource as typeof EventSource;
});

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <InvestigationsGraphContainer />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  };
}

describe("InvestigationsGraphContainer", () => {
  it("lands in tenant scope on the graph, not on the no-investigation placeholder", async () => {
    renderScreen();

    // No investigation is selected, and the graph region is still the surface.
    expect(await screen.findByTestId("graph-canvas")).toBeInTheDocument();
    expect(screen.getByTestId("scope-all")).toHaveClass("btn-primary");
    expect(screen.getByTestId("investigation-scope-label")).toHaveTextContent("all investigations");

    // The canvas placeholder is not the whole screen: there is a way to put something in
    // the graph, and it is reachable without navigating anywhere.
    expect(screen.getByTestId("seed-from-text")).toBeInTheDocument();
    expect(screen.getByTestId("seed-submit")).toBeInTheDocument();
    expect(screen.getByTestId("entity-seed")).toBeInTheDocument();
    const page = screen.getByTestId("investigations-page");
    expect(page.textContent ?? "").not.toBe(screen.getByTestId("graph-canvas").textContent);
  });

  it("refreshes the graph when the pipeline publishes", async () => {
    renderScreen();

    await waitFor(() => expect(specOpsGraph).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(listFindings).toHaveBeenCalledTimes(1));

    const source = StubEventSource.instances.at(-1);
    expect(source).toBeDefined();
    expect(source?.url).toBe("/api/v1/stream");

    act(() => {
      source?.fire("entity.updated", { entity_id: "ENT-9" });
    });

    // The projection and the finding list are the two payloads the canvas reads; both must
    // be re-read, or the canvas is showing records the pipeline has already moved past.
    await waitFor(() => expect(specOpsGraph).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(listFindings).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByTestId("investigations-last-event")).toHaveTextContent("entity.updated"),
    );

    // The keys it invalidates are the shared ones, so the workspace's graph, timeline and
    // evidence views come back with it rather than each holding a private copy.
    expect(entityProjectionKey(null)).toEqual(["entity-projection", ""]);
    expect(findingsKey(null)).toEqual(["findings", ""]);
  });

  it("seeds one entity per subject from free text and re-reads the graph", async () => {
    renderScreen();
    await screen.findByTestId("graph-canvas");
    await waitFor(() => expect(specOpsGraph).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByTestId("seed-text"), {
      target: { value: "example.com, ACME Holdings\nexample.com" },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("seed-submit"));
    });

    // Two subjects, not three: the repeated domain is the same subject.
    expect(createEntity).toHaveBeenCalledTimes(2);
    expect(createEntity).toHaveBeenNthCalledWith(1, {
      canonical_identity: { name: "example.com" },
      label: "example.com",
    });
    expect(createEntity).toHaveBeenNthCalledWith(2, {
      canonical_identity: { name: "ACME Holdings" },
      label: "ACME Holdings",
    });
    expect(await screen.findByTestId("seed-note")).toHaveTextContent("seeded 2 subjects");
    await waitFor(() => expect(specOpsGraph).toHaveBeenCalledTimes(2));
  });

  it("says which subjects were refused instead of reporting a whole-batch success", async () => {
    createEntity.mockRejectedValueOnce(new Error("409 conflict: identity already materialised"));
    renderScreen();
    await screen.findByTestId("graph-canvas");

    fireEvent.change(screen.getByTestId("seed-text"), {
      target: { value: "taken.example, fresh.example" },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("seed-submit"));
    });

    const note = await screen.findByTestId("seed-note");
    expect(note).toHaveTextContent("seeded 1 subject");
    expect(note).toHaveTextContent("taken.example");
    expect(note).toHaveTextContent("409 conflict");
  });
});
