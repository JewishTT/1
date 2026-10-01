import { describe, expect, it } from "vitest";

import {
  arityOf,
  EDGE_ARITY,
  EdgeFormationData,
  fnv1a,
  formEdges,
  layoutSeed,
  makeEdgeId,
  makeObservationId,
  orderNodeIds,
  pairwiseCliqueProjection,
} from "./edgeFormation";

function edgesById(data: EdgeFormationData) {
  return formEdges(["ENT-1", "ENT-2", "ENT-3", "OBS-1"], data).edges.map((e) => e.id);
}

describe("EDGE_ARITY", () => {
  it("declares co_occurrence undirected and every other kind directed", () => {
    expect(arityOf("co_occurrence")).toBe("undirected");
    expect(arityOf("relationship")).toBe("directed");
    expect(arityOf("assertion")).toBe("directed");
    expect(arityOf("evidence")).toBe("directed");
    expect(arityOf("possible_match")).toBe("directed");
    expect(arityOf("source_host")).toBe("directed");
    expect(Object.keys(EDGE_ARITY).sort()).toEqual([
      "assertion",
      "co_occurrence",
      "evidence",
      "possible_match",
      "relationship",
      "source_host",
    ]);
  });
});

describe("makeEdgeId", () => {
  it("is stable across calls and URL-safe", () => {
    const id = makeEdgeId("ENT-1", "ENT-2", "possible_match", "CE-1");
    expect(id).toMatch(/^UI-[0-9a-f]{32}$/);
    expect(makeEdgeId("ENT-1", "ENT-2", "possible_match", "CE-1")).toBe(id);
  });

  it("is order-sensitive for directed kinds — a→b and b→a are different relations", () => {
    for (const kind of ["relationship", "assertion", "evidence", "possible_match", "source_host"] as const) {
      expect(makeEdgeId("ENT-1", "ENT-2", kind, "SRC-1")).not.toBe(
        makeEdgeId("ENT-2", "ENT-1", kind, "SRC-1"),
      );
    }
  });

  it("is order-insensitive for undirected kinds — a→b and b→a are one relation", () => {
    expect(makeEdgeId("ENT-1", "ENT-2", "co_occurrence", "OBS-9")).toBe(
      makeEdgeId("ENT-2", "ENT-1", "co_occurrence", "OBS-9"),
    );
    expect(makeEdgeId("B", "A", "co_occurrence", "OBS-7")).toBe(makeEdgeId("A", "B", "co_occurrence", "OBS-7"));
  });

  it("separates kind and source (provenance-derived identity)", () => {
    const base = makeEdgeId("ENT-1", "ENT-2", "possible_match", "CE-1");
    expect(makeEdgeId("ENT-1", "ENT-2", "assertion", "CE-1")).not.toBe(base);
    expect(makeEdgeId("ENT-1", "ENT-2", "possible_match", "CE-2")).not.toBe(base);
  });

  it("pins the documented 128-bit identity vector, replacing the 32-bit one", () => {
    // ADR-0023: the 32-bit `e:1d374e53` identity vector is replaced. This digest
    // is sha256('{"mode":"directed","object":"ENT-2","source":"CE-1",'
    // + '"subject":"ENT-1","type":"possible_match"}')[:32], computed by the
    // Python donor's relation_identity.digest128 over canonical_material.
    expect(makeEdgeId("ENT-1", "ENT-2", "possible_match", "CE-1")).toBe(
      "UI-a3a1b4281e7cc32d98e597d7ef31621f",
    );
  });

  it("hashes UTF-8 bytes, so a non-ASCII id is stable and width-correct", () => {
    const id = makeEdgeId("ИВАН", "ОРГАНИЗАЦИЯ", "relationship", "works_for");
    expect(id).toMatch(/^UI-[0-9a-f]{32}$/);
    expect(id).toBe(makeEdgeId("ИВАН", "ОРГАНИЗАЦИЯ", "relationship", "works_for"));
    expect(id).not.toBe(makeEdgeId("ИВАН", "ОРГАНИЗАЦИЯ", "relationship", "employed_by"));
  });
});

describe("fnv1a", () => {
  it("still satisfies its golden vector for the empty string (retired for identity only)", () => {
    expect(fnv1a("")).toBe(0x811c9dc5);
    expect((fnv1a("") >>> 0).toString(16).padStart(8, "0")).toBe("811c9dc5");
  });

  it("is no longer an edge-identity function", () => {
    expect(fnv1a("ENT-1")).not.toBe(makeEdgeId("ENT-1", "ENT-2", "possible_match", "CE-1"));
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

  it("is stable across repeated calls for the same node set", () => {
    const nodes = ["ENT-1", "ENT-2", "ENT-3"];
    expect(layoutSeed(nodes)).toBe(layoutSeed(nodes));
    expect(layoutSeed(nodes)).toBe(layoutSeed([...nodes]));
    expect(layoutSeed(["ENT-1", "ENT-2"])).not.toBe(layoutSeed(["ENT-1", "ENT-2", "ENT-3"]));
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
    expect(first.edges.map((e) => e.id)).toEqual(second.edges.map((e) => e.id));
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
    expect(edgesById(data)).toEqual(edgesById(swapped));
    const left = formEdges(["ENT-1", "ENT-2", "ENT-3"], data);
    const right = formEdges(["ENT-1", "ENT-2", "ENT-3"], swapped);
    expect(left.observations.map((o) => o.id)).toEqual(right.observations.map((o) => o.id));
    expect(left.observations).toEqual(right.observations);
  });

  it("rejects self-loops", () => {
    const data: EdgeFormationData = {
      observations: [],
      seeds: [{ a: "ENT-1", b: "ENT-1", kind: "possible_match", source: "CE-1" }],
    };
    expect(formEdges(["ENT-1"], data).edges).toHaveLength(0);
  });

  it("dedupes identical primitives by edge id", () => {
    const data: EdgeFormationData = {
      observations: [],
      seeds: [
        { a: "ENT-1", b: "ENT-2", kind: "possible_match", source: "CE-1" },
        { a: "ENT-1", b: "ENT-2", kind: "possible_match", source: "CE-1" },
        { a: "ENT-1", b: "ENT-2", kind: "possible_match", source: "CE-1", reason: "email" },
      ],
    };
    expect(formEdges(["ENT-1", "ENT-2"], data).edges).toHaveLength(1);
  });

  it("keeps a directed pair and its reverse as two distinct oriented edges", () => {
    const seeds: EdgeFormationData["seeds"] = [
      { a: "ENT-1", b: "ENT-2", kind: "relationship", source: "works_for", reason: "works_for" },
      { a: "ENT-2", b: "ENT-1", kind: "relationship", source: "works_for", reason: "works_for" },
    ];
    const { edges } = formEdges(["ENT-1", "ENT-2"], { observations: [], seeds });
    expect(edges).toHaveLength(2);
    const forward = edges.find((e) => e.source === "ENT-1");
    const reverse = edges.find((e) => e.source === "ENT-2");
    expect(forward).toEqual({
      id: makeEdgeId("ENT-1", "ENT-2", "relationship", "works_for"),
      source: "ENT-1",
      target: "ENT-2",
      kind: "relationship",
      reason: "works_for",
    });
    expect(reverse).toEqual({
      id: makeEdgeId("ENT-2", "ENT-1", "relationship", "works_for"),
      source: "ENT-2",
      target: "ENT-1",
      kind: "relationship",
      reason: "works_for",
    });
    expect(forward?.id).not.toBe(reverse?.id);
  });

  it("collapses a reversed undirected pair into one edge with a canonical orientation", () => {
    const reversed: EdgeFormationData = {
      observations: [{ observation_id: "OBS-9", nodes: ["ENT-2", "ENT-1"] }],
      seeds: [
        { a: "ENT-2", b: "ENT-1", kind: "co_occurrence", source: "OBS-9" },
        { a: "ENT-1", b: "ENT-2", kind: "co_occurrence", source: "OBS-9" },
      ],
    };
    const { edges } = formEdges(["ENT-1", "ENT-2"], reversed, { pairwiseProjection: true });
    expect(edges).toHaveLength(1);
    expect(edges[0]).toEqual({
      id: makeEdgeId("ENT-1", "ENT-2", "co_occurrence", "OBS-9"),
      source: "ENT-1",
      target: "ENT-2",
      kind: "co_occurrence",
      reason: "OBS-9",
      derivedFrom: makeObservationId("co_occurrence", ["ENT-1", "ENT-2"], "OBS-9"),
    });
  });

  it("preserves an N-ary observation as one record and never expands it implicitly", () => {
    const data: EdgeFormationData = {
      observations: [{ observation_id: "OBS-1", nodes: ["ENT-3", "ENT-1", "ENT-2"] }],
      seeds: [],
    };
    const { edges, observations } = formEdges(["ENT-1", "ENT-2", "ENT-3"], data);
    expect(edges).toHaveLength(0);
    expect(observations).toEqual([
      {
        id: makeObservationId("co_occurrence", ["ENT-1", "ENT-2", "ENT-3"], "OBS-1"),
        kind: "co_occurrence",
        participants: ["ENT-1", "ENT-2", "ENT-3"],
        source: "OBS-1",
        reason: "OBS-1",
      },
    ]);
  });

  it("derives the pairwise clique only when the caller opts in, and traces it to its record", () => {
    const data: EdgeFormationData = {
      observations: [{ observation_id: "OBS-1", nodes: ["ENT-1", "ENT-2", "ENT-3"] }],
      seeds: [],
    };
    const record = formEdges(["ENT-1", "ENT-2", "ENT-3"], data).observations[0];
    const projected = formEdges(["ENT-1", "ENT-2", "ENT-3"], data, { pairwiseProjection: true });

    // The record survives the projection unchanged — the view is derived, not a replacement.
    expect(projected.observations).toEqual([record]);
    expect(projected.edges).toHaveLength(3);
    for (const edge of projected.edges) {
      expect(edge.derivedFrom).toBe(record.id);
      expect(edge.id).not.toBe(record.id);
      expect(record.participants).toContain(edge.source);
      expect(record.participants).toContain(edge.target);
    }
    expect(projected.edges.map((e) => [e.source, e.target])).toEqual(
      pairwiseCliqueProjection(record).map((s) => [s.a, s.b]),
    );
  });

  it("drops an observation that has fewer than two known distinct participants", () => {
    const data: EdgeFormationData = {
      observations: [
        { observation_id: "OBS-1", nodes: ["ENT-1", "ENT-1"] },
        { observation_id: "OBS-2", nodes: ["ENT-1", "GHOST"] },
        { observation_id: "OBS-3", nodes: ["ENT-1", "ENT-2"] },
      ],
      seeds: [],
    };
    const { observations } = formEdges(["ENT-1", "ENT-2"], data);
    expect(observations.map((o) => o.source)).toEqual(["OBS-3"]);
  });

  it("is order-invariant in the payload — a duplicate id cannot last-writer-win its reason", () => {
    const forward: EdgeFormationData = {
      observations: [],
      seeds: [
        { a: "ENT-1", b: "ENT-2", kind: "possible_match", source: "CE-1", reason: "aaa" },
        { a: "ENT-1", b: "ENT-2", kind: "possible_match", source: "CE-1", reason: "zzz" },
      ],
    };
    const reversed: EdgeFormationData = { ...forward, seeds: [...forward.seeds].reverse() };
    const left = formEdges(["ENT-1", "ENT-2"], forward);
    const right = formEdges(["ENT-1", "ENT-2"], reversed);
    expect(left.edges).toHaveLength(1);
    expect(left.edges).toEqual(right.edges);
    expect(left.edges[0].reason).toBe("aaa");
  });

  it("canonicalises the orientation of an undirected duplicate so the payload cannot flip", () => {
    const forward: EdgeFormationData = {
      observations: [],
      seeds: [
        { a: "ENT-1", b: "ENT-2", kind: "co_occurrence", source: "OBS-1" },
        { a: "ENT-2", b: "ENT-1", kind: "co_occurrence", source: "OBS-1" },
      ],
    };
    const reversed: EdgeFormationData = { ...forward, seeds: [...forward.seeds].reverse() };
    expect(formEdges(["ENT-1", "ENT-2"], forward).edges).toEqual(
      formEdges(["ENT-1", "ENT-2"], reversed).edges,
    );
    expect(formEdges(["ENT-1", "ENT-2"], forward).edges[0]).toMatchObject({
      source: "ENT-1",
      target: "ENT-2",
    });
  });

  it("drops edges whose endpoints are not known nodes", () => {
    const data: EdgeFormationData = {
      observations: [],
      seeds: [{ a: "ENT-1", b: "GHOST", kind: "possible_match", source: "CE-1" }],
    };
    expect(formEdges(["ENT-1", "ENT-2"], data).edges).toHaveLength(0);
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
    const { observations } = formEdges(["ENT-1", "ENT-2", "ENT-3"], data);
    expect([...observations.map((o) => o.id)].sort()).toEqual(observations.map((o) => o.id));
  });
});
