import { describe, expect, it } from "vitest";

import type { EntityView } from "./api";
import { buildEntityGraphElements } from "./entityGraph";

const ENTITY: EntityView = {
  entity_id: "ENT-2001",
  canonical_identity: { account: "Yard" },
  current_state: {},
  historical_versions: [],
  aliases: [],
  relationships: [],
  supporting_assertions: [],
  evidence: [],
  timeline: [],
  structural_signals: [],
  correlations: [
    {
      edge_id: "CE-200001",
      candidate_a: "ENT-2001",
      candidate_b: "ENT-2002",
      kind: "possible_match",
      raw_pair_score: 0.72,
      collective_score: 0.74,
      reasons: ["email"],
      state: "OPEN",
    },
  ],
};

describe("buildEntityGraphElements", () => {
  it("emits the focal entity plus counterpart nodes and a correlation edge", () => {
    const elements = buildEntityGraphElements(ENTITY, ENTITY.correlations ?? []);
    const ids = elements.filter((e) => e.kind === "node").map((e) => e.id);
    expect(ids).toContain("ENT-2001");
    expect(ids).toContain("ENT-2002");
    const edges = elements.filter((e) => e.kind === "edge");
    expect(edges).toHaveLength(1);
    expect(edges[0]).toMatchObject({ source: "ENT-2001", target: "ENT-2002" });
    expect(edges[0].label).toContain("possible_match");
  });

  it("skips correlation edges that do not touch the entity", () => {
    const foreign: EntityView = { ...ENTITY, correlations: [] };
    const elements = buildEntityGraphElements(foreign, [
      {
        edge_id: "CE-9",
        candidate_a: "ENT-900",
        candidate_b: "ENT-901",
        kind: "possible_match",
        raw_pair_score: 0.5,
        collective_score: 0.5,
        reasons: [],
        state: "OPEN",
      },
    ]);
    expect(elements.filter((e) => e.kind === "node").map((e) => e.id)).toEqual(["ENT-2001"]);
    expect(elements.filter((e) => e.kind === "edge")).toHaveLength(0);
  });

  it("dedupes nodes and keeps ids unique across edges", () => {
    const elements = buildEntityGraphElements(ENTITY, [
      ...(ENTITY.correlations ?? []),
      {
        edge_id: "CE-200002",
        candidate_a: "ENT-2001",
        candidate_b: "ENT-2002",
        kind: "possible_match",
        raw_pair_score: 0.6,
        collective_score: 0.6,
        reasons: ["handle"],
        state: "OPEN",
      },
    ]);
    const nodeIds = elements.filter((e) => e.kind === "node").map((e) => e.id);
    expect(new Set(nodeIds).size).toBe(nodeIds.length);
    const allIds = elements.map((e) => e.id);
    expect(new Set(allIds).size).toBe(allIds.length);
  });

  it("is deterministic — the same entity yields identical elements twice", () => {
    const first = buildEntityGraphElements(ENTITY, ENTITY.correlations ?? []);
    const second = buildEntityGraphElements(ENTITY, ENTITY.correlations ?? []);
    expect(first.map((e) => `${e.kind}:${e.id}`)).toEqual(second.map((e) => `${e.kind}:${e.id}`));
  });

  it("is order-invariant — swapped correlation order produces identical edge ids", () => {
    const correlations = [
      ...(ENTITY.correlations ?? []),
      {
        edge_id: "CE-200002",
        candidate_a: "ENT-2001",
        candidate_b: "ENT-2002",
        kind: "possible_match",
        raw_pair_score: 0.6,
        collective_score: 0.6,
        reasons: ["handle"],
        state: "OPEN",
      },
    ];
    const forward = buildEntityGraphElements(ENTITY, correlations).filter((e) => e.kind === "edge");
    const backward = buildEntityGraphElements(ENTITY, [...correlations].reverse()).filter((e) => e.kind === "edge");
    expect(forward.map((e) => e.id)).toEqual(backward.map((e) => e.id));
  });
});