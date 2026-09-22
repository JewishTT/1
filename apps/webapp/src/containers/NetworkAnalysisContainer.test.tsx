import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { networkApi } from "../lib/science/api";

// ── Backend stubs (containers drive honest payloads, tests assert contract) ──
vi.mock("../lib/api", () => ({
  api: {
    getEntity: vi.fn(async (id: string) => {
      if (id === "ENT-2001") {
        return {
          entity_id: "ENT-2001",
          canonical_identity: { account: "Yard" },
          current_state: {},
          historical_versions: [],
          aliases: ["Yard"],
          relationships: [],
          supporting_assertions: ["ASR-9001"],
          evidence: [{ evidence_id: "E-1", observation_id: "OBS-1001", immutable: true }],
          timeline: [
            { observation_id: "OBS-1001", uri: "http://fixtures.local/a.html", immutable: true, observed_at: "2026-09-01T03:00:00Z" },
            { observation_id: "OBS-1002", uri: "http://fixtures.local/b.html", immutable: true, observed_at: "2026-09-03T10:00:00Z" },
            { observation_id: "OBS-1003", uri: "http://fixtures.local/c.html", immutable: true, observed_at: "2026-09-05T22:00:00Z" },
          ],
          structural_signals: [],
          tenant_id: "t",
        };
      }
      if (id === "ENT-9009") {
        // Entity with observation timeline that carries no temporal anchors (I-3).
        return {
          entity_id: "ENT-9009",
          canonical_identity: { account: "Silent" },
          current_state: {},
          historical_versions: [],
          aliases: ["Silent"],
          relationships: [],
          supporting_assertions: [],
          evidence: [{ evidence_id: "E-9", observation_id: "OBS-9001", immutable: true }],
          timeline: [
            { observation_id: "OBS-9001", uri: "http://fixtures.local/snapshot.json", immutable: true },
          ],
          structural_signals: [],
          tenant_id: "t",
        };
      }
      throw new Error(`entity not found: ${id}`);
    }),
    getCorrelations: vi.fn(async (id: string) => ({
      entity_id: id,
      correlations: [
        {
          edge_id: "CE-200001",
          candidate_a: "ENT-2001",
          candidate_b: "ENT-2002",
          kind: "possible_match",
          raw_pair_score: 0.72,
          collective_score: 0.74,
          reasons: ["email", "handle"],
          state: "OPEN",
        },
      ],
    })),
  },
}));

vi.mock("../lib/science/api", () => ({
  networkApi: {
    measures: vi.fn(async () => ({
      n_nodes: 2, n_edges: 1, density: 1, avg_degree: 1, max_degree: 1,
      avg_clustering: 0, transitivity: 0, assortativity: 0, degree_gini: 1,
      power_law_alpha: null, power_law_x_min: null, avg_shortest_path: 1,
      small_world_sigma: null, degree_distribution: {}, degree_centrality: { "ENT-2001": 1 },
      structural_only: true,
    })),
    communities: vi.fn(async () => ({
      structural_only: true, n_nodes: 2, n_edges: 1, community_count: 1,
      modularity_q: 0, communities: { "0": ["ENT-2001", "ENT-2002"] },
    })),
    hypergraph: vi.fn(async () => ({
      num_nodes: 2, num_edges: 1, order: 1, edge_sizes: {}, hyperedge_sizes: {},
      degree_distribution: {}, average_node_degree: 1, incidence_density: 1,
      connected_pairs: 1, node_degrees: {}, structural_only: true,
    })),
    temporal: vi.fn(async () => ({
      structural_only: true, n_nodes: 2, n_edges: 1, nodes: ["ENT-2001", "ENT-2002"],
      distance_matrix: { "ENT-2001": { "ENT-2001": 0, "ENT-2002": 1 } },
      motifs: { out_star: 1, in_star: 0, relay: 0 },
      timeline: [[0, ["ENT-2001"]]],
    })),
    diagramFeatures: vi.fn(async () => ({
      entity_id: "ENT-2001", provider: "vr-z2-science", structural_only: true,
      series_len: 5,
      diagrams: { "0": [[0, null]], "1": [] } as Record<string, Array<[number, number | null]>>,
      features: { structural_only: true, dimensions: {} },
      features_digest: "sha256:beef0001",
    })),
    phodms: vi.fn(async () => ({
      structural_only: true, n_times: 1, n_points: 3, n_thresholds: 2,
      betti_zero_surface: [[[]]], rank_invariant: {
        s1: 1, t1: 1, t2: 2, s2: 1, t3: 2, t4: 3, dim: 0, rank: 1, verdict: "stable",
      },
    })),
  },
}));

async function renderNet(initialEntry = "/network?e=ENT-2001") {
  const { NetworkAnalysisContainer } = await import("./NetworkAnalysisContainer");
  return (
    <MemoryRouter initialEntries={[initialEntry]}>
      <NetworkAnalysisContainer />
    </MemoryRouter>
  );
}

describe("NetworkAnalysisContainer (projection-plane /api/v1/network)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("materialises a deep-link seed and derives correlation edges", async () => {
    render(await renderNet());
    await waitFor(() => expect(screen.getByTestId("net-board")).toBeInTheDocument());
    expect(screen.getByTestId("net-seedbank")).toHaveTextContent("Yard");
    expect(screen.getByTestId("net-seedbank")).toHaveTextContent("1 EDGES");
  });

  it("adds an entity with a silent timeline and keeps series honest", async () => {
    render(await renderNet("/network"));
    await waitFor(() => expect(screen.getByTestId("net-seed-empty")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("seed input"), { target: { value: "ENT-9009" } });
    fireEvent.submit(screen.getByTestId("net-seed-form"));
    await waitFor(() => expect(screen.getAllByText("Silent").length).toBeGreaterThan(0));
    expect(screen.getByText(/NO SERIES/)).toBeInTheDocument();
  });

  it("runs measures and shows the structural-only result", async () => {
    render(await renderNet());
    await waitFor(() => expect(screen.getByTestId("net-board")).toBeInTheDocument());
    fireEvent.click(
      screen.getByText(/NETWORK MEASURES/).closest(".panel")!.querySelector("button")!,
    );
    await waitFor(() => expect(screen.getByTestId("measures-result")).toBeInTheDocument());
    expect(screen.getByTestId("measures-result")).toHaveTextContent("density");
    expect(vi.mocked(networkApi.measures)).toHaveBeenCalledTimes(1);
  });

  it("runs communities, hypergraph, temporal from the same edge set", async () => {
    render(await renderNet());
    await waitFor(() => expect(screen.getByTestId("net-board")).toBeInTheDocument());
    fireEvent.click(screen.getByText(/COMMUNITIES/).closest(".panel")!.querySelector("button")!);
    fireEvent.click(screen.getByText(/HYPERGRAPH/).closest(".panel")!.querySelector("button")!);
    fireEvent.click(screen.getByText(/TEMPORAL PATHS/).closest(".panel")!.querySelector("button")!);
    await waitFor(() => expect(screen.getByTestId("communities-result")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("hypergraph-result")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("temporal-result")).toBeInTheDocument());
    expect(vi.mocked(networkApi.communities)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(networkApi.hypergraph)).toHaveBeenCalledTimes(1);
  });

  it("runs diagram features and phodms from the honest timeline series", async () => {
    render(await renderNet());
    await waitFor(() => expect(screen.getByTestId("net-board")).toBeInTheDocument());
    fireEvent.click(
      screen.getByText(/DIAGRAM FEATURES/).closest(".panel")!.querySelector("button")!,
    );
    fireEvent.click(
      screen.getByText(/PHODMS INVARIANT/).closest(".panel")!.querySelector("button")!,
    );
    await waitFor(() => expect(screen.getByTestId("diagram-features-result")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("phodms-result")).toBeInTheDocument());
    const series = vi.mocked(networkApi.diagramFeatures).mock.calls[0][0].series;
    expect(series).toEqual([1, 0, 1, 0, 1]);
  });

  it("defers diagram features honestly for an entity with no temporal data", async () => {
    render(await renderNet("/network"));
    await waitFor(() => expect(screen.getByTestId("net-seed-empty")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("seed input"), { target: { value: "ENT-9009" } });
    fireEvent.submit(screen.getByTestId("net-seed-form"));
    await waitFor(() => expect(screen.getAllByText("Silent").length).toBeGreaterThan(0));
    fireEvent.click(
      screen.getByText(/DIAGRAM FEATURES/).closest(".panel")!.querySelector("button")!,
    );
    await waitFor(() => expect(screen.getByText(/insufficient temporal data/)).toBeInTheDocument());
    expect(vi.mocked(networkApi.diagramFeatures)).not.toHaveBeenCalled();
  });
});