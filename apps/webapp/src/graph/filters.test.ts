import { describe, expect, it } from "vitest";

import { EMPTY_GRAPH_FACETS, applyFacets, matchesTimeRange, nodeMatchesFacets, edgeMatchesFacets, toggleFacetValue, activeFacetIds, type GraphFacets } from "./filters";
import { buildGraphModel, projectAdmission, type GraphInput } from "./model";
import type { GraphModel, GraphNode } from "./types";

/**
 * Facet tests (§22).
 *
 * The claims under test, in order of how badly they would hurt if false:
 *   1. facets COMBINE — narrowing by two things narrows by both
 *   2. a time range hides a dated node OUTSIDE the window, and KEEPS one with no
 *      date at all, because "unknown when" is not "outside"
 *   3. an edge is dropped when EITHER endpoint is, so the canvas never renders a
 *      dangling edge
 *   4. an unreported admission is `unknown` and never `admitted`
 */

const INPUT: GraphInput = {
  entities: [
    {
      entity_id: "ENT-1",
      label: "acme.example",
      timeline: [
        { observation_id: "OBS-A", uri: "https://acme.example/a", immutable: true, observed_at: "2026-01-10T00:00:00Z" },
        { observation_id: "OBS-B", uri: "https://acme.example/b", immutable: false, observed_at: "2026-02-20T00:00:00Z" },
      ],
      evidence: [{ evidence_id: "EV-A", observation_id: "OBS-C", immutable: true }],
      sourceIds: ["acme.example"],
    },
    {
      entity_id: "ENT-2",
      label: "beta.example",
      timeline: [{ observation_id: "OBS-D", uri: "https://beta.example/d", immutable: true, observed_at: "2026-03-01T00:00:00Z" }],
      evidence: [],
      sourceIds: ["beta.example"],
      relationships: [{ target: "ENT-1", type: "works_for" }],
    },
  ],
  findings: [
    {
      finding_id: "FND-1",
      status: "OPEN",
      why_detected: "burst",
      structural_evidence: [{}],
      semantic_evidence: [],
      supporting_graph_region: {},
      supporting_assertions: [],
      observations: [{ observation_id: "OBS-B", uri: "https://acme.example/b", immutable: false }],
      sources: ["acme.example"],
      evidence_resolves: true,
    },
  ],
  correlations: [],
  claims: [],
};

function model(): GraphModel {
  return buildGraphModel(INPUT);
}

function node(model_: GraphModel, id: string): GraphNode {
  const found = model_.nodeIndex.get(id);
  if (found === undefined) throw new Error(`no node ${id}`);
  return found;
}

describe("§22 — facets combine", () => {
  it("applies two facets as AND, not as a union of either one alone", () => {
    const m = model();
    const byKind = applyFacets(m, { ...EMPTY_GRAPH_FACETS, kinds: ["Finding"] });
    const bySource = applyFacets(m, { ...EMPTY_GRAPH_FACETS, sourceIds: ["beta.example"] });
    const both = applyFacets(m, {
      ...EMPTY_GRAPH_FACETS,
      kinds: ["Finding"],
      sourceIds: ["beta.example"],
    });

    // Each facet alone admits a set; the combination admits only their
    // intersection. The one finding comes from acme.example and the
    // beta.example rows are not findings, so the intersection is empty.
    expect(byKind.nodes.length).toBeGreaterThan(0);
    expect(bySource.nodes.length).toBeGreaterThan(0);
    expect(both.nodes).toEqual([]);
    expect(both.nodes.length).toBeLessThan(Math.min(byKind.nodes.length, bySource.nodes.length));
    expect(both.hiddenNodeCount).toBe(m.nodes.length);
  });

  it("combines as AND when the intersection is non-empty", () => {
    const m = model();
    const both = applyFacets(m, {
      ...EMPTY_GRAPH_FACETS,
      kinds: ["Observation"],
      sourceIds: ["acme.example"],
    });
    expect(both.nodes.map((n) => n.identifier).sort()).toEqual(["OBS-A", "OBS-B", "OBS-C"]);
    // And it is narrower than either facet alone.
    const kindOnly = applyFacets(m, { ...EMPTY_GRAPH_FACETS, kinds: ["Observation"] });
    const sourceOnly = applyFacets(m, { ...EMPTY_GRAPH_FACETS, sourceIds: ["acme.example"] });
    expect(both.nodes.length).toBeLessThan(kindOnly.nodes.length);
    expect(both.nodes.length).toBeLessThan(sourceOnly.nodes.length);
  });

  it("toggles values inside one facet without disturbing the others", () => {
    expect(toggleFacetValue(["a"], "a")).toEqual([]);
    expect(toggleFacetValue(["a"], "b")).toEqual(["a", "b"]);
    // Immutability: the caller's array is untouched.
    const original = ["a"];
    toggleFacetValue(original, "b");
    expect(original).toEqual(["a"]);
  });

  it("reports which facets are active, so the toolbar can count them", () => {
    const facets: GraphFacets = { ...EMPTY_GRAPH_FACETS, kinds: ["Entity"], query: "acme" };
    expect(activeFacetIds(facets)).toEqual(["kinds", "query"]);
    expect(activeFacetIds(EMPTY_GRAPH_FACETS)).toEqual([]);
  });

  it("an empty facet admits everything — that is what 'no filter' means", () => {
    const m = model();
    const all = applyFacets(m, EMPTY_GRAPH_FACETS);
    expect(all.nodes.length).toBe(m.nodes.length);
    expect(all.hiddenNodeCount).toBe(0);
  });
});

describe("§22 — a time range hides dated objects and keeps undated ones", () => {
  it("excludes a node whose every instant falls outside the window", () => {
    const january = node(model(), "Observation:OBS-A");
    expect(
      nodeMatchesFacets(january, {
        ...EMPTY_GRAPH_FACETS,
        timeRange: { from: "2026-01-01T00:00:00Z", to: "2026-01-31T23:59:59Z" },
      }),
    ).toBe(true);

    const february = node(model(), "Observation:OBS-B");
    expect(
      nodeMatchesFacets(february, {
        ...EMPTY_GRAPH_FACETS,
        timeRange: { from: "2026-01-01T00:00:00Z", to: "2026-01-31T23:59:59Z" },
      }),
    ).toBe(false);
  });

  it("keeps a node that reports NO instant, because unknown is not outside", () => {
    const undated = node(model(), "Observation:OBS-C");
    expect(undated.observedAt).toEqual([]);
    expect(
      nodeMatchesFacets(undated, {
        ...EMPTY_GRAPH_FACETS,
        timeRange: { from: "2026-01-01T00:00:00Z", to: "2026-01-02T00:00:00Z" },
      }),
    ).toBe(true);
  });

  it("treats an open bound as open in that direction only", () => {
    expect(matchesTimeRange(["2026-05-01T00:00:00Z"], { from: null, to: null })).toBe(true);
    expect(matchesTimeRange(["2026-05-01T00:00:00Z"], { from: "2026-06-01T00:00:00Z", to: null })).toBe(false);
    expect(matchesTimeRange(["2026-05-01T00:00:00Z"], { from: null, to: "2026-04-01T00:00:00Z" })).toBe(false);
    expect(matchesTimeRange(["2026-05-01T00:00:00Z"], { from: "2026-04-01T00:00:00Z", to: null })).toBe(true);
  });

  it("keeps a node with at least one instant inside the window", () => {
    const spanning = { ...node(model(), "Observation:OBS-A"), observedAt: ["2026-01-05T00:00:00Z", "2026-03-05T00:00:00Z"] };
    expect(
      nodeMatchesFacets(spanning, {
        ...EMPTY_GRAPH_FACETS,
        timeRange: { from: "2026-03-01T00:00:00Z", to: "2026-03-31T00:00:00Z" },
      }),
    ).toBe(true);
  });
});

describe("§22 — filtering never leaves a dangling edge", () => {
  it("drops an edge when one endpoint is filtered out", () => {
    const m = model();
    const filtered = applyFacets(m, { ...EMPTY_GRAPH_FACETS, sourceIds: ["beta.example"] });
    for (const edge of filtered.edges) {
      expect(filtered.nodes.some((n) => n.id === edge.source)).toBe(true);
      expect(filtered.nodes.some((n) => n.id === edge.target)).toBe(true);
    }
  });

  it("does not filter edges by endpoint kind — that would delete relations between two visible things", () => {
    const m = model();
    const edgesOnly = applyFacets(m, { ...EMPTY_GRAPH_FACETS, kinds: ["Entity"] });
    expect(edgesOnly.edges.length).toBeGreaterThan(0);
  });

  it("reports how many edges the facets removed instead of applying them silently", () => {
    const m = model();
    const filtered = applyFacets(m, { ...EMPTY_GRAPH_FACETS, relations: ["possible"] });
    expect(filtered.edges).toEqual([]);
    expect(filtered.hiddenEdgeCount).toBe(m.edges.length);
  });
});

describe("§16 — admission is conservative", () => {
  it("maps only recognised platform statuses, and collapses everything else to unknown", () => {
    expect(projectAdmission("ADMITTED")).toBe("admitted");
    expect(projectAdmission("MATERIALIZED")).toBe("admitted");
    expect(projectAdmission("PROVISIONAL")).toBe("provisional");
    expect(projectAdmission("REJECTED")).toBe("rejected");
    expect(projectAdmission("WHAT_IS_THIS")).toBe("unknown");
    expect(projectAdmission(null)).toBe("unknown");
    expect(projectAdmission("")).toBe("unknown");
  });

  it("never paints an unreported status as admitted", () => {
    expect(projectAdmission("admitted")).toBe("admitted");
    // The permissive direction is the dangerous one: an unrecognised string
    // must not reach the accent.
    expect(projectAdmission("ADMITED")).toBe("unknown");
    expect(projectAdmission("approved_by_someone")).toBe("unknown");
  });

  it("marks every hypothesis provisional and every materialised entity not", () => {
    const m = buildGraphModel({
      entities: [{ entity_id: "ENT-9", label: "e", evidence: [] }],
      findings: [],
      correlations: [
        {
          edge_id: "E1",
          candidate_a: "ENT-9",
          candidate_b: "CAND-1",
          kind: "possible_match",
          raw_pair_score: 0.4,
          collective_score: 0.4,
          reasons: ["name"],
          state: "OPEN",
          origin_entity: "ENT-9",
        },
      ],
    });
    const hypothesis = m.nodeIndex.get("Hypothesis:CAND-1");
    expect(hypothesis).toBeDefined();
    expect(hypothesis?.provisional).toBe(true);
    expect(hypothesis?.admission).toBe("provisional");
    expect(m.nodeIndex.get("Entity:ENT-9")?.provisional).toBe(false);
  });
});

describe("§99 — the projection invents nothing", () => {
  it("creates no Claim node from a relationship row", () => {
    const m = model();
    // The entity carries a `works_for` relationship row with no claim id. The
    // canvas must render an EDGE, not a Claim the platform never reported.
    expect(m.nodes.filter((n) => n.kind === "Claim")).toEqual([]);
    const asserted = m.edges.filter((e) => e.family === "asserts");
    expect(asserted.length).toBe(1);
    expect(asserted[0]?.claimId).toBeNull();
  });

  it("emits no Source or Capture node — those are peers of the graph, not subgraphs", () => {
    const m = model();
    expect(m.nodes.some((n) => n.kind === ("Source" as never))).toBe(false);
    expect(m.edges.some((e) => e.source.includes("Source") || e.target.includes("Source"))).toBe(false);
  });

  it("falls back to the identifier when the platform reports no label", () => {
    const m = buildGraphModel({ entities: [{ entity_id: "ENT-X" }], findings: [], correlations: [] });
    expect(m.nodeIndex.get("Entity:ENT-X")?.label).toBe("ENT-X");
  });

  it("is deterministic: the same records produce byte-identical ids and order", () => {
    const a = model();
    const b = model();
    expect(a.nodes.map((n) => n.id)).toEqual(b.nodes.map((n) => n.id));
    expect(a.edges.map((e) => e.id)).toEqual(b.edges.map((e) => e.id));
  });

  it("deduplicates an observation named by two entities into ONE record", () => {
    const m = buildGraphModel({
      entities: [
        { entity_id: "E1", evidence: [{ evidence_id: "v1", observation_id: "OBS-SHARED", immutable: true }] },
        { entity_id: "E2", evidence: [{ evidence_id: "v2", observation_id: "OBS-SHARED", immutable: true }] },
      ],
      findings: [],
      correlations: [],
    });
    expect(m.nodes.filter((n) => n.kind === "Observation")).toHaveLength(1);
    expect(m.edges.filter((e) => e.family === "observes")).toHaveLength(2);
  });

  it("reports a source facet only from what the model carries", () => {
    const m = model();
    expect(edgeMatchesFacets(m.edges[0] as never, EMPTY_GRAPH_FACETS)).toBe(true);
  });
});