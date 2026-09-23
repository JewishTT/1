import { describe, expect, it } from "vitest";

import {
  EdgeFormationData,
  formEdges,
  layoutSeed,
  makeEdgeId,
  orderNodeIds,
} from "./edgeFormation";

function edgesById(data: EdgeFormationData) {
  return formEdges(["ENT-1", "ENT-2", "ENT-3", "OBS-1"], data).map((e) => e.id);
}

describe("makeEdgeId", () => {
  it("is stable across calls and URL-safe", () => {
    const id = makeEdgeId("ENT-1", "ENT-2", "possible_match", "CE-1");
    expect(id).toBe("e:1d374e53");
    expect(makeEdgeId("ENT-1", "ENT-2", "possible_match", "CE-1")).toBe(id);
  });

  it("is order-invariant — a→b and b→a produce the same id", () => {
    expect(makeEdgeId("ENT-1", "ENT-2", "possible_match", "CE-1")).toBe(
      makeEdgeId("ENT-2", "ENT-1", "possible_match", "CE-1"),
    );
    expect(makeEdgeId("B", "A", "evidence", "EV-7")).toBe(makeEdgeId("A", "B", "evidence", "EV-7"));
  });

  it("separates kind and source (provenance-derived identity)", () => {
    const base = makeEdgeId("ENT-1", "ENT-2", "possible_match", "CE-1");
    expect(makeEdgeId("ENT-1", "ENT-2", "assertion", "CE-1")).not.toBe(base);
    expect(makeEdgeId("ENT-1", "ENT-2", "possible_match", "CE-2")).not.toBe(base);
  });
});

describe("orderNodeIds", () => {
  it("is order-invariant and stable", () => {
    expect(orderNodeIds(["b", "a", "c"])).toEqual(["a", "b", "c"]);
    expect(orderNodeIds(["a", "c", "b"])).toEqual(["a", "b", "c"]);
  });
});

describe("layoutSeed", () => {
  it("derives deterministically from the node set, independent of order", () => {
    expect(layoutSeed(["ENT-1", "ENT-2", "ENT-3"])).toBe(layoutSeed(["ENT-3", "ENT-1", "ENT-2"]));
    expect(layoutSeed([])).toBe(0x5eed);
  });
});

describe("formEdges", () => {
  it("emits the same edge set and ids twice for the same input", () => {
    const data: EdgeFormationData = {
      observations: [{ observation_id: "OBS-1", nodes: ["ENT-1", "ENT-2", "ENT-3"] }],
      seeds: [
        { a: "ENT-1", b: "ENT-2", kind: "possible_match", source: "CE-1", reason: "possible_match (OPEN)" },
      ],
    };
    const first = formEdges(["ENT-1", "ENT-2", "ENT-3", "OBS-1"], data);
    const second = formEdges(["ENT-1", "ENT-2", "ENT-3", "OBS-1"], data);
    expect(first.map((e) => e.id)).toEqual(second.map((e) => e.id));
    expect(first).toEqual(second);
  });

  it("is order-invariant — swapping primitive input order yields identical ids", () => {
    const data: EdgeFormationData = {
      observations: [{ observation_id: "OBS-1", nodes: ["ENT-1", "ENT-2", "ENT-3"] }],
      seeds: [
        { a: "ENT-1", b: "ENT-2", kind: "possible_match", source: "CE-1" },
        { a: "ENT-2", b: "ENT-3", kind: "assertion", source: "CE-2" },
      ],
    };
    const swapped: EdgeFormationData = {
      observations: [{ observation_id: "OBS-1", nodes: ["ENT-3", "ENT-1", "ENT-2"] }],
      seeds: [
        { a: "ENT-2", b: "ENT-3", kind: "assertion", source: "CE-2" },
        { a: "ENT-1", b: "ENT-2", kind: "possible_match", source: "CE-1" },
      ],
    };
    expect(formEdges(["ENT-1", "ENT-2", "ENT-3"], data).map((e) => e.id)).toEqual(
      formEdges(["ENT-1", "ENT-2", "ENT-3"], swapped).map((e) => e.id),
    );
  });

  it("rejects self-loops", () => {
    const data: EdgeFormationData = {
      observations: [],
      seeds: [{ a: "ENT-1", b: "ENT-1", kind: "possible_match", source: "CE-1" }],
    };
    expect(formEdges(["ENT-1"], data)).toHaveLength(0);
  });

  it("dedupes identical primitives by edge id", () => {
    const data: EdgeFormationData = {
      observations: [],
      seeds: [
        { a: "ENT-1", b: "ENT-2", kind: "possible_match", source: "CE-1" },
        { a: "ENT-2", b: "ENT-1", kind: "possible_match", source: "CE-1" },
        { a: "ENT-1", b: "ENT-2", kind: "possible_match", source: "CE-1" },
      ],
    };
    const edges = formEdges(["ENT-1", "ENT-2"], data);
    expect(edges).toHaveLength(1);
  });

  it("forms co-occurrence edges with the observation anchor as source and the default kind", () => {
    const data: EdgeFormationData = {
      observations: [{ observation_id: "OBS-9", nodes: ["ENT-1", "ENT-2"] }],
      seeds: [],
    };
    const edges = formEdges(["ENT-1", "ENT-2"], data);
    expect(edges).toHaveLength(1);
    expect(edges[0].kind).toBe("co_occurrence");
    expect(edges[0].id).toBe(makeEdgeId("ENT-1", "ENT-2", "co_occurrence", "OBS-9"));
    expect(edges[0].reason).toBe("OBS-9");
  });

  it("drops edges whose endpoints are not known nodes", () => {
    const data: EdgeFormationData = {
      observations: [],
      seeds: [{ a: "ENT-1", b: "GHOST", kind: "possible_match", source: "CE-1" }],
    };
    expect(formEdges(["ENT-1", "ENT-2"], data)).toHaveLength(0);
  });

  it("emits in deterministic sorted-by-id order regardless of seed order", () => {
    const data: EdgeFormationData = {
      observations: [{ observation_id: "OBS-1", nodes: ["ENT-1", "ENT-2", "ENT-3"] }],
      seeds: [
        { a: "ENT-1", b: "ENT-3", kind: "assertion", source: "CE-3" },
        { a: "ENT-1", b: "ENT-2", kind: "possible_match", source: "CE-1" },
      ],
    };
    const ids = edgesById(data);
    expect([...ids].sort()).toEqual(ids);
  });

  it("provides the golden correlation edge id for persisted W5 payloads", () => {
    expect(makeEdgeId("ENT-1", "ENT-2", "possible_match", "CE-1")).toBe("e:1d374e53");
  });
});