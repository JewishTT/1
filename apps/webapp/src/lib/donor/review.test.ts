import { describe, expect, it } from "vitest";

import {
  DEFAULT_REVIEW_FILTERS,
  buildDerivedReviewAssertions,
  buildNodeReviewStatusMap,
  filterReviewAssertions,
  getAdjacentReviewAssertionId,
  getNextUnreviewedAssertionId,
  type DerivedReviewAssertion,
  type ReviewAssertion,
} from "./review";

function assertion(overrides: Partial<ReviewAssertion> = {}): ReviewAssertion {
  return {
    id: "a1",
    subject_id: "ENT-1",
    path: "owns",
    value: { account: "acme" },
    source_id: "src-1",
    review_state: "unreviewed",
    confidence: "unverified",
    created_at: 100,
    ...overrides,
  };
}

const SRC = {
  sources: [
    { id: "src-1", title: "First Report" },
    { id: "src-2", display_name: "Second Report" },
  ],
  graph: {
    nodes: [
      { id: "ENT-1", label: "Acme Corp" },
      { id: "ENT-2", label: null },
    ],
  },
};

describe("buildDerivedReviewAssertions", () => {
  it("groups identical values as corroboration and labels subjects/sources", () => {
    const items = buildDerivedReviewAssertions(
      [
        assertion({ id: "a1", source_id: "src-1" }),
        assertion({ id: "a2", source_id: "src-2" }),
      ],
      SRC.sources,
      SRC.graph,
    );
    const first = items[0]!;
    expect(first.subjectLabel).toBe("Acme Corp");
    expect(first.sourceTitle).toBe("First Report");
    expect(first.corroborationCount).toBe(1);
    expect(first.evidenceStatus).toBe("multiple");
    expect(first.conflictStatus).toBe("none");
  });

  it("flags conflicts within the same subject::path group", () => {
    const items = buildDerivedReviewAssertions(
      [
        assertion({ id: "a1", value: { account: "acme" } }),
        assertion({ id: "a2", value: { account: "acme-ltd" } }),
      ],
      SRC.sources,
      SRC.graph,
    );
    expect(items.every((i) => i.conflictStatus === "conflict")).toBe(true);
  });

  it("single source → evidenceStatus single; none → none", () => {
    const [alone] = buildDerivedReviewAssertions([assertion()], SRC.sources, SRC.graph);
    expect(alone.evidenceStatus).toBe("single");
    const [orphan] = buildDerivedReviewAssertions(
      [assertion({ source_id: null })],
      [],
      { nodes: [] },
    );
    expect(orphan.evidenceStatus).toBe("none");
    expect(orphan.subjectLabel).toBe("ENT-1");
  });

  it("summarises long values", () => {
    const long = { blob: "x".repeat(400) };
    const [item] = buildDerivedReviewAssertions(
      [assertion({ id: "a9", value: long })],
      [],
      { nodes: [] },
    );
    expect(item.valueSummary).toMatch(/^\{.*\.\.\.$/);
  });

  it("tolerates empty input", () => {
    expect(buildDerivedReviewAssertions([], [], { nodes: [] })).toEqual([]);
  });
});

describe("filterReviewAssertions", () => {
  const items: DerivedReviewAssertion[] = [
    { ...assertion({ id: "a1", created_at: 10, review_state: "accepted" }), subjectLabel: "A", sourceTitle: null, supportingSourceCount: 2, corroborationCount: 3, evidenceStatus: "multiple", conflictStatus: "none", valueSummary: "{\"account\":\"acme\"}" },
    { ...assertion({ id: "a2", created_at: 30, review_state: "unreviewed" }), subjectLabel: "B", sourceTitle: null, supportingSourceCount: 0, corroborationCount: 0, evidenceStatus: "none", conflictStatus: "none", valueSummary: "{\"v\":1}" },
    { ...assertion({ id: "a3", created_at: 20, review_state: "unreviewed" }), subjectLabel: "Acme", sourceTitle: "First Report", supportingSourceCount: 1, corroborationCount: 0, evidenceStatus: "single", conflictStatus: "conflict", valueSummary: "{\"v\":2}" },
  ];

  it("unreviewed-first sorts pending above decided, then evidence, then newest", () => {
    const ids = filterReviewAssertions(items, DEFAULT_REVIEW_FILTERS).map((i) => i.id);
    expect(ids).toEqual(["a2", "a3", "a1"]);
  });

  it("newest / oldest reorder by created_at", () => {
    expect(filterReviewAssertions(items, { ...DEFAULT_REVIEW_FILTERS, sort: "newest" }).map((i) => i.id))
      .toEqual(["a2", "a3", "a1"]);
    expect(filterReviewAssertions(items, { ...DEFAULT_REVIEW_FILTERS, sort: "oldest" }).map((i) => i.id))
      .toEqual(["a1", "a3", "a2"]);
  });

  it("weakest-evidence pushes evidence-less items first", () => {
    const ids = filterReviewAssertions(items, { ...DEFAULT_REVIEW_FILTERS, sort: "weakest_evidence" })
      .map((i) => i.id);
    expect(ids).toEqual(["a2", "a3", "a1"]);
  });

  it("evidence=weak keeps only non-multiple evidence", () => {
    const ids = filterReviewAssertions(items, { ...DEFAULT_REVIEW_FILTERS, evidence: "weak" }).map(
      (i) => i.id,
    );
    expect(ids).toEqual(["a2", "a3"]);
  });

  it("state filter narrows by review state", () => {
    const ids = filterReviewAssertions(
      items,
      { ...DEFAULT_REVIEW_FILTERS, reviewState: "accepted" },
    ).map((i) => i.id);
    expect(ids).toEqual(["a1"]);
  });

  it("query matches path, subject label, source title", () => {
    expect(filterReviewAssertions(items, { ...DEFAULT_REVIEW_FILTERS, query: "First Report" }).length)
      .toBe(1);
    expect(filterReviewAssertions(items, { ...DEFAULT_REVIEW_FILTERS, query: "acme" }).length)
      .toBeGreaterThanOrEqual(1);
  });

  it("empty input tolerated", () => {
    expect(filterReviewAssertions([], DEFAULT_REVIEW_FILTERS)).toEqual([]);
  });
});

describe("buildNodeReviewStatusMap", () => {
  it("conflict surfaces before review-attention before clear", () => {
    const map = buildNodeReviewStatusMap([
      { ...assertion({ id: "a1", subject_id: "ENT-1", review_state: "disputed" }), subjectLabel: "X", sourceTitle: null, supportingSourceCount: 0, corroborationCount: 0, evidenceStatus: "none", conflictStatus: "conflict", valueSummary: "1" },
      { ...assertion({ id: "a2", subject_id: "ENT-2", review_state: "unreviewed", source_id: null }), subjectLabel: "Y", sourceTitle: null, supportingSourceCount: 0, corroborationCount: 0, evidenceStatus: "none", conflictStatus: "none", valueSummary: "2" },
      { ...assertion({ id: "a3", subject_id: "ENT-3", review_state: "accepted" }), subjectLabel: "Z", sourceTitle: null, supportingSourceCount: 1, corroborationCount: 0, evidenceStatus: "single", conflictStatus: "none", valueSummary: "3" },
    ]);
    expect(map.get("ENT-1")).toEqual({ reviewTone: "conflict", evidenceTone: "gap" });
    expect(map.get("ENT-2")).toEqual({ reviewTone: "needs_review", evidenceTone: "gap" });
    expect(map.get("ENT-3")).toEqual({ reviewTone: "clear", evidenceTone: "supported" });
  });

  it("empty input → empty map", () => {
    expect(buildNodeReviewStatusMap([]).size).toBe(0);
  });
});

describe("navigation helpers", () => {
  const items: DerivedReviewAssertion[] = [
    { ...assertion({ id: "a1", created_at: 1, review_state: "accepted" }), subjectLabel: "A", sourceTitle: null, supportingSourceCount: 0, corroborationCount: 0, evidenceStatus: "none", conflictStatus: "none", valueSummary: "1" },
    { ...assertion({ id: "a2", created_at: 2, review_state: "unreviewed" }), subjectLabel: "B", sourceTitle: null, supportingSourceCount: 0, corroborationCount: 0, evidenceStatus: "none", conflictStatus: "none", valueSummary: "2" },
  ];

  it("wraps adjacency within the list", () => {
    expect(getAdjacentReviewAssertionId(items, null, "next")).toBe("a1");
    expect(getAdjacentReviewAssertionId(items, "a1", "next")).toBe("a2");
    expect(getAdjacentReviewAssertionId(items, "a2", "next")).toBe("a2");
    expect(getAdjacentReviewAssertionId(items, "a2", "previous")).toBe("a1");
    expect(getAdjacentReviewAssertionId([], "a1", "next")).toBeNull();
  });

  it("steps forward through unreviewed only", () => {
    expect(getNextUnreviewedAssertionId(items, null)).toBe("a2");
    expect(getNextUnreviewedAssertionId(items, "a2")).toBe("a2");
    expect(getNextUnreviewedAssertionId(items, "a1")).toBe("a2");
    expect(getNextUnreviewedAssertionId(items, "missing")).toBe("a2");
    expect(getNextUnreviewedAssertionId([], null)).toBeNull();
  });
});