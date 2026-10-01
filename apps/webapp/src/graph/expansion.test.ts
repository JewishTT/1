import { describe, expect, it } from "vitest";

import {
  DEFAULT_EXPANSION_BUDGET,
  HARD_NODE_CEILING,
  MAX_HOPS,
  collapse,
  expand,
  expansionChoices,
  normaliseHops,
  type ExpansionRequest,
} from "./expansion";
import { EMPTY_GRAPH_FACETS, type GraphFacets } from "./filters";
import { buildGraphModel, type GraphInput } from "./model";
import type { GraphModel } from "./types";

/**
 * Expansion bounds (§21).
 *
 * "Never dump the whole graph" is only a real constraint if something ENFORCES
 * it. This file is that something, and the tests below are the enforcement:
 *
 *   - hops clamp to 1–2, so there is no "expand to everything" gesture
 *   - a result is capped, and a capped result says so with a reason
 *   - an expansion respects the active facets rather than pulling filtered-out
 *     objects back in
 *   - expansion is reversible: collapse undoes it
 *
 * A star graph is used deliberately. It is the shape where an unbounded
 * expansion would genuinely return everything, so a regression that removed the
 * cap would fail here rather than on some convenient fixture.
 */

function starModel(leaves: number): GraphModel {
  const entities = [
    { entity_id: "ENT-HUB", label: "hub", evidence: [] },
    ...Array.from({ length: leaves }, (_value, index) => ({
      entity_id: `ENT-L${index}`,
      label: `leaf ${index}`,
      // Every leaf relates to the hub, so +1 hop from the hub reaches them all.
      relationships: [{ target: "ENT-HUB", type: "linked" }],
      evidence: [],
    })),
  ];
  const input: GraphInput = { entities, findings: [], correlations: [] };
  return buildGraphModel(input);
}

function ringModel(rings: number, perRing: number): GraphModel {
  const entities: Array<{ entity_id: string; label: string; evidence: []; relationships: Array<{ target: string; type: string }> }> = [
    { entity_id: "ENT-0", label: "root", evidence: [], relationships: [] },
  ];
  for (let ring = 1; ring <= rings; ring += 1) {
    for (let index = 0; index < perRing; index += 1) {
      const id = `ENT-${ring}-${index}`;
      const parent = ring === 1 ? "ENT-0" : `ENT-${ring - 1}-${index % perRing}`;
      entities.push({ entity_id: id, label: id, evidence: [], relationships: [{ target: parent, type: "linked" }] });
    }
  }
  return buildGraphModel({ entities, findings: [], correlations: [] });
}

describe("§21 — hops are clamped, so no expansion can mean 'everything'", () => {
  it("clamps a request for more than two hops to two", () => {
    expect(normaliseHops(1)).toBe(1);
    expect(normaliseHops(2)).toBe(2);
    expect(normaliseHops(3)).toBe(MAX_HOPS);
    expect(normaliseHops(99)).toBe(MAX_HOPS);
    expect(normaliseHops(0)).toBe(1);
    expect(normaliseHops(-5)).toBe(1);
    expect(normaliseHops(Number.NaN)).toBe(1);
    expect(MAX_HOPS).toBe(2);
  });

  it("+1 hop from the hub reaches only the hub's direct neighbours", () => {
    const model = ringModel(2, 3);
    const one = expand(model, ["Entity:ENT-0"], { kind: "hops", hops: 1 });
    expect(one.added.map((n) => n.id).sort()).toEqual(["Entity:ENT-1-0", "Entity:ENT-1-1", "Entity:ENT-1-2"]);
    // Nothing two rings out leaked in.
    expect(one.added.some((n) => n.id.startsWith("Entity:ENT-2-"))).toBe(false);
    expect(one.truncated).toBe(false);
  });

  it("+2 hops reaches exactly one ring further", () => {
    const model = ringModel(2, 3);
    const two = expand(model, ["Entity:ENT-0"], { kind: "hops", hops: 2 });
    expect(two.added).toHaveLength(6);
    expect(two.added.some((n) => n.id.startsWith("Entity:ENT-2-"))).toBe(true);
    expect(two.truncated).toBe(false);
  });

  it("a hop request of 50 is served as a two-hop request, not as a dump", () => {
    const model = starModel(500);
    const result = expand(model, ["Entity:ENT-HUB"], { kind: "hops", hops: 50 });
    // The star is one ring deep, so +2 and +50 coincide — but the RESULT is
    // still capped, which is the property under test.
    expect(result.added.length).toBeLessThanOrEqual(DEFAULT_EXPANSION_BUDGET);
  });
});

describe("§21 — the result is capped and the cap is reported", () => {
  it("truncates to the budget and states how many were dropped", () => {
    const model = starModel(400);
    const result = expand(model, ["Entity:ENT-HUB"], { kind: "hops", hops: 1 }, { budget: 10 });

    expect(result.truncated).toBe(true);
    expect(result.added).toHaveLength(10);
    expect(result.candidatesFound).toBe(400);
    expect(result.reason).toContain("400");
    // §69: a truncated expansion must offer the narrower next step.
    expect(result.reason).toContain("Narrow by relation, source or timeframe");
  });

  it("clamps a caller budget to the hard ceiling — the ceiling cannot be raised by a prop", () => {
    const model = starModel(HARD_NODE_CEILING + 50);
    const result = expand(model, ["Entity:ENT-HUB"], { kind: "hops", hops: 1 }, { budget: 1_000_000 });
    expect(result.added.length).toBeLessThanOrEqual(HARD_NODE_CEILING);
  });

  it("never returns a budget of zero or a negative budget", () => {
    const model = starModel(20);
    for (const budget of [0, -10, Number.NaN]) {
      const result = expand(model, ["Entity:ENT-HUB"], { kind: "hops", hops: 1 }, { budget });
      expect(result.added.length).toBeGreaterThan(0);
    }
  });

  it("is deterministic: the same seed and request yield the same objects in the same order", () => {
    const model = starModel(120);
    const request: ExpansionRequest = { kind: "hops", hops: 1 };
    const a = expand(model, ["Entity:ENT-HUB"], request, { budget: 25 });
    const b = expand(model, ["Entity:ENT-HUB"], request, { budget: 25 });
    expect(a.added.map((n) => n.id)).toEqual(b.added.map((n) => n.id));
  });
});

describe("§21 — constrained expansions add only what matches the constraint", () => {
  const model = buildGraphModel({
    entities: [
      {
        entity_id: "ENT-1",
        label: "one",
        evidence: [{ evidence_id: "v1", observation_id: "OBS-1", immutable: true }],
        relationships: [
          { target: "ENT-2", type: "works_for" },
          { target: "ENT-3", type: "registered_to" },
        ],
      },
      { entity_id: "ENT-2", label: "two", evidence: [{ evidence_id: "v2", observation_id: "OBS-2", immutable: true }] },
      { entity_id: "ENT-3", label: "three", evidence: [] },
    ],
    findings: [],
    correlations: [],
  });

  it("a specific relation adds only neighbours joined by that relation family", () => {
    const result = expand(model, ["Entity:ENT-1"], { kind: "relation", relation: "observes" });
    expect(result.added.map((n) => n.identifier)).toEqual(["OBS-1"]);
  });

  it("a specific relation that matches nothing returns nothing and says why it is not an error", () => {
    const result = expand(model, ["Entity:ENT-3"], { kind: "relation", relation: "supports" });
    expect(result.added).toEqual([]);
    expect(result.truncated).toBe(false);
    expect(result.reason).toBeNull();
  });

  it("a timeframe adds only edges whose validity falls inside the window", () => {
    const timed = buildGraphModel({
      entities: [
        {
          entity_id: "T-1",
          label: "t1",
          evidence: [],
          relationships: [{ target: "T-2", type: "works_for", valid_from: "2026-01-01T00:00:00Z" }],
        },
        {
          entity_id: "T-3",
          label: "t3",
          evidence: [],
          relationships: [{ target: "T-4", type: "works_for", valid_from: "2026-06-01T00:00:00Z" }],
        },
        { entity_id: "T-2", label: "t2", evidence: [] },
        { entity_id: "T-4", label: "t4", evidence: [] },
      ],
      findings: [],
      correlations: [],
    });

    const january = expand(timed, ["Entity:T-1"], {
      kind: "timeframe",
      range: { from: "2026-01-01T00:00:00Z", to: "2026-02-01T00:00:00Z" },
    });
    expect(january.added.map((n) => n.id)).toEqual(["Entity:T-2"]);

    const june = expand(timed, ["Entity:T-3"], {
      kind: "timeframe",
      range: { from: "2026-01-01T00:00:00Z", to: "2026-02-01T00:00:00Z" },
    });
    expect(june.added).toEqual([]);
  });

  it("returns only edges whose BOTH endpoints are in the result", () => {
    const result = expand(model, ["Entity:ENT-1"], { kind: "relation", relation: "observes" });
    const ids = new Set(["Entity:ENT-1", ...result.added.map((n) => n.id)]);
    for (const edge of result.edges) {
      expect(ids.has(edge.source)).toBe(true);
      expect(ids.has(edge.target)).toBe(true);
    }
  });
});

describe("§21 — expansion respects the active facets", () => {
  it("does not pull in an object the current facet hides", () => {
    const model = ringModel(1, 5);
    const allEntities: GraphFacets = { ...EMPTY_GRAPH_FACETS, kinds: ["Entity"] };
    const withFacets = expand(model, ["Entity:ENT-0"], { kind: "hops", hops: 1 }, { facets: allEntities });
    // Everything in this fixture is an Entity, so that facet admits the lot.
    expect(withFacets.added.length).toBe(5);

    // Narrowing to a kind nothing in the graph has must return nothing.
    const hidden: GraphFacets = { ...EMPTY_GRAPH_FACETS, kinds: ["Observation"] };
    expect(expand(model, ["Entity:ENT-0"], { kind: "hops", hops: 1 }, { facets: hidden }).added).toEqual([]);
  });

  it("reports when every seed is hidden rather than expanding from nothing", () => {
    const model = ringModel(1, 3);
    const hidden: GraphFacets = { ...EMPTY_GRAPH_FACETS, kinds: ["Observation"] };
    const result = expand(model, ["Entity:ENT-0"], { kind: "hops", hops: 1 }, { facets: hidden });
    expect(result.added).toEqual([]);
    expect(result.reason).toContain("hidden by the current filters");
  });

  it("refuses a seed the model does not contain", () => {
    const model = ringModel(1, 3);
    const result = expand(model, ["Entity:NOPE"], { kind: "hops", hops: 1 });
    expect(result.added).toEqual([]);
    expect(result.candidatesFound).toBe(0);
  });
});

describe("§21 — expansion is reversible", () => {
  it("collapses back to the seed set and counts what it removed", () => {
    const model = starModel(20);
    expect(model.nodes).toHaveLength(21);
    const grown = expand(model, ["Entity:ENT-HUB"], { kind: "hops", hops: 1 });
    expect(grown.added.length).toBe(20);

    // The seed survives; everything else is removed.
    const collapsed = collapse(model, ["Entity:ENT-HUB"]);
    expect(collapsed.removedNodeCount).toBe(20);
    expect(collapsed.removedEdgeCount).toBeGreaterThan(0);
  });

  it("collapsing to the whole model removes nothing, and says so", () => {
    const model = ringModel(1, 2);
    const collapsed = collapse(model, model.nodes.map((n) => n.id));
    expect(collapsed.removedNodeCount).toBe(0);
  });
});

describe("§15 — the toolbar's expansion menu is data, not markup", () => {
  it("offers the five shapes §21 names: 1 hop, 2 hops, a relation, a source, a timeframe", () => {
    const choices = expansionChoices(["acme.example"]);
    const kinds = new Set(choices.map((choice) => choice.request.kind));
    expect(kinds).toEqual(new Set(["hops", "relation", "source", "timeframe"]));
    expect(choices.filter((c) => c.request.kind === "hops")).toHaveLength(2);
    // Every choice names itself and explains itself — no bare affordance.
    for (const choice of choices) {
      expect(choice.label.length).toBeGreaterThan(0);
      expect(choice.hint.length).toBeGreaterThan(0);
    }
  });

  it("offers one source entry per known source, and none when there are none", () => {
    expect(expansionChoices(["a", "b"]).filter((c) => c.request.kind === "source")).toHaveLength(2);
    expect(expansionChoices().filter((c) => c.request.kind === "source")).toHaveLength(0);
  });

  it("offers no 'everything' entry, at any point", () => {
    const labels = expansionChoices(["x"]).map((choice) => choice.label.toLowerCase()).join(" ");
    for (const forbidden of ["all", "everything", "whole graph", "expand all"]) {
      expect(labels).not.toContain(forbidden);
    }
  });
});