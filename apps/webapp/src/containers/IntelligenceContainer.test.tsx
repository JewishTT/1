import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Correlation, EntityView } from "../lib/api";
import { buildIntelGraph } from "../lib/intelGraph";

describe("intel graph assembler", () => {
  const ENTITY: EntityView = {
    entity_id: "ENT-2001",
    canonical_identity: { account: "Yard" },
    current_state: {},
    historical_versions: [],
    aliases: ["Yard"],
    relationships: [{ type: "candidate_of", target: "ENT-2003" }],
    supporting_assertions: ["ASR-9001"],
    evidence: [],
    timeline: [],
    structural_signals: [],
  };

  const CORR: Correlation = {
    edge_id: "CE-200001",
    candidate_a: "ENT-2001",
    candidate_b: "ENT-2002",
    kind: "possible_match",
    raw_pair_score: 0.72,
    collective_score: 0.74,
    reasons: ["email"],
    state: "OPEN",
  };

  beforeEach(() => vi.clearAllMocks());

  it("builds entity + correlate + relationship node kinds", () => {
    const graph = buildIntelGraph({ "ENT-2001": ENTITY }, { "ENT-2001": [CORR] });
    const ids = graph.nodes.map((n) => [n.id, n.kind]);
    expect(ids).toContainEqual(["ENT-2001", "entity"]);
    expect(ids).toContainEqual(["ENT-2002", "correlate"]);
    expect(ids).toContainEqual(["ENT-2003", "relationship"]);
    expect(graph.edges).toContainEqual(
      expect.objectContaining({ id: "CE-200001", kind: "possible_match" }),
    );
    expect(graph.edges).toContainEqual(
      expect.objectContaining({ id: "REL-ENT-2001-ENT-2003", kind: "relationship" }),
    );
  });

  it("labels a correlate that becomes materialised as entity", () => {
    const materialised = { ...ENTITY, entity_id: "ENT-2002", canonical_identity: { account: "Acct" } };
    const graph = buildIntelGraph(
      { "ENT-2001": ENTITY, "ENT-2002": materialised },
      { "ENT-2001": [CORR] },
    );
    const node = graph.nodes.find((n) => n.id === "ENT-2002");
    expect(node?.kind).toBe("entity");
    expect(node?.materialized).toBe(true);
    expect(node?.label).toBe("Acct");
  });

  it("dedupes nodes by id", () => {
    const graph = buildIntelGraph({ "ENT-2001": ENTITY }, {
      "ENT-2001": [CORR, { ...CORR, edge_id: "CE-200002" }],
    });
    expect(graph.nodes.filter((n) => n.id === "ENT-2002")).toHaveLength(1);
    expect(graph.edges).toHaveLength(3); // 2 correlation edges + 1 relationship
  });
});

// ── Container integration ───────────────────────────────────────────
vi.mock("../lib/api", () => ({
  api: {
    getEntity: vi.fn(async (id: string) => {
      if (id === "ENT-2001") {
        return {
          entity_id: "ENT-2001",
          canonical_identity: { account: "Yard" },
          current_state: {},
          historical_versions: [],
          aliases: ["Yard", "yard-account"],
          relationships: [],
          supporting_assertions: ["ASR-9001"],
          evidence: [{ evidence_id: "E-1", observation_id: "OBS-1001", immutable: true }],
          timeline: [{ observation_id: "OBS-1001", uri: "http://fixtures.local/report.html", immutable: true }],
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

vi.mock("cytoscape", () => ({
  default: () => ({ on: vi.fn(), fit: vi.fn(), destroy: vi.fn(), ready: vi.fn() }),
}));

async function renderIntel(initialEntry = "/intel?entity=ENT-2001") {
  const { IntelligenceContainer } = await import("./IntelligenceContainer");
  return (
    <MemoryRouter initialEntries={[initialEntry]}>
      <IntelligenceContainer />
    </MemoryRouter>
  );
}

describe("IntelligenceContainer (Maltego-style)", () => {
  it("materialises a deep-link seed into the graph and seed bank", async () => {
    render(await renderIntel());
    await waitFor(() => expect(screen.getByTestId("seed-node-ENT-2001")).toBeInTheDocument());
    expect(screen.getByTestId("intel-board")).toBeInTheDocument();
    expect(screen.getByTestId("intel-seedbank")).toHaveTextContent("Yard");
    expect(screen.queryByTestId("intel-empty")).not.toBeInTheDocument();
  });

  it("selects a seed and opens the node inspector", async () => {
    render(await renderIntel());
    await waitFor(() => expect(screen.getByTestId("seed-node-ENT-2001")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("seed-node-ENT-2001"));
    expect(screen.getByTestId("intel-inspector")).toBeInTheDocument();
    expect(screen.getByTestId("inspector-id")).toHaveTextContent("Yard");
    expect(screen.getByTestId("inspector-expand")).toBeInTheDocument();
  });

  it("adds a seed via the seed bank form", async () => {
    render(await renderIntel("/intel"));
    await waitFor(() => expect(screen.getByTestId("seed-empty")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("seed input"), { target: { value: "ENT-2001" } });
    fireEvent.submit(screen.getByTestId("seed-form"));
    await waitFor(() => expect(screen.getByTestId("seed-node-ENT-2001")).toBeInTheDocument());
  });

  it("keeps the SSE feed idle without events in a jsdom runtime", async () => {
    render(await renderIntel());
    await waitFor(() => expect(screen.getByTestId("intel-feed")).toBeInTheDocument());
    expect(screen.getByText(/SSE link idle/)).toBeInTheDocument();
  });
});