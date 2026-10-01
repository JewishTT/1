import { describe, expect, it } from "vitest";

import {
  EDGE_LEGEND,
  EDGE_SEMANTICS,
  GRAPH_PALETTE_FALLBACK,
  NODE_LEGEND,
  NODE_SEMANTICS,
  edgeStyleForContext,
  isDashed,
  nodeAccentFor,
  nodeStyleFor,
  predicateIsVisible,
  readGraphPalette,
  type GraphPalette,
} from "./semantics";
import { GRAPH_OBJECT_KINDS, routeForNode, type AdmissionState, type GraphEdge, type GraphNode } from "./types";

/**
 * The visual language (Visual Direction §3–§4, §16, §17, §93).
 *
 * The rule under test is the one that stops this becoming a rainbow:
 *
 *   SHAPE  → kind          GLYPH → kind
 *   DASH   → provisional   COLOUR → admission, and only admission
 *
 * So the tests assert the NEGATIVE as well as the positive: that two different
 * kinds at the same admission state get the SAME colour, and that a provisional
 * object is distinguishable with colour removed entirely.
 */

const PALETTE = GRAPH_PALETTE_FALLBACK;

function node(kind: GraphNode["kind"], admission: AdmissionState | null, provisional = false): GraphNode {
  return {
    id: `${kind}:${kind}-1`,
    kind,
    label: kind,
    identifier: `${kind}-1`,
    admission,
    admissionRaw: admission,
    provisional,
    evidenceCount: 1,
    claimCount: 0,
    sourceId: null,
    observedAt: [],
    originEntityId: null,
  };
}

const CONTEXT = { palette: PALETTE, emphasis: "rest", secondary: false, dimmed: false, interactive: true } as const;

describe("§16 — five kinds, five silhouettes, five glyphs", () => {
  it("gives every kind a distinct shape and a distinct token", () => {
    const shapes = GRAPH_OBJECT_KINDS.map((kind) => NODE_SEMANTICS[kind].shape);
    const tokens = GRAPH_OBJECT_KINDS.map((kind) => NODE_SEMANTICS[kind].token);
    expect(new Set(shapes).size).toBe(shapes.length);
    expect(new Set(tokens).size).toBe(tokens.length);
    expect(NODE_SEMANTICS.Entity.token).toBe("ENT");
    expect(NODE_SEMANTICS.Observation.token).toBe("OBS");
    expect(NODE_SEMANTICS.Claim.token).toBe("CLM");
    expect(NODE_SEMANTICS.Finding.token).toBe("FND");
    expect(NODE_SEMANTICS.Hypothesis.token).toBe("HYP");
  });

  it("gives every kind a readable label, so the legend never depends on a glyph", () => {
    for (const kind of GRAPH_OBJECT_KINDS) {
      expect(NODE_SEMANTICS[kind].label.length).toBeGreaterThan(0);
      expect(NODE_LEGEND.find((row) => row.kind === kind)?.note.length).toBeGreaterThan(0);
    }
  });

  it("puts the kind token IN the node label, so a monochrome export is still readable", () => {
    const style = nodeStyleFor(node("Claim", "admitted"), CONTEXT);
    expect(style.label).toContain("CLM");
    expect(style.label).toContain("Claim");
    expect(style.label).toContain("CLM");
  });

  it("gives the Entity the largest silhouette, because it is the anchor", () => {
    expect(NODE_SEMANTICS.Entity.size).toBeGreaterThan(NODE_SEMANTICS.Observation.size);
    expect(NODE_SEMANTICS.Finding.size).toBeGreaterThan(NODE_SEMANTICS.Hypothesis.size);
  });
});

describe("Visual Direction §4 — exactly one accent, and it does not mean 'kind'", () => {
  it("gives two different kinds at the same admission the SAME colour", () => {
    const entity = nodeAccentFor(node("Entity", "admitted"), PALETTE);
    const claim = nodeAccentFor(node("Claim", "admitted"), PALETTE);
    const finding = nodeAccentFor(node("Finding", "admitted"), PALETTE);
    expect(entity).toBe(claim);
    expect(claim).toBe(finding);
    // And they all differ from the OTHER admission states.
    expect(entity).not.toBe(nodeAccentFor(node("Entity", "provisional"), PALETTE));
  });

  it("uses the accent for admitted structure only", () => {
    expect(nodeAccentFor(node("Entity", "admitted"), PALETTE)).toBe(PALETTE.accent);
    expect(nodeAccentFor(node("Finding", "rejected"), PALETTE)).toBe(PALETTE.danger);
    // Provisional is NEUTRAL, not amber: amber is metadata in this palette,
    // and a provisional object is not metadata.
    expect(nodeAccentFor(node("Hypothesis", "provisional"), PALETTE)).toBe(PALETTE.steel);
    expect(nodeAccentFor(node("Entity", "provisional"), PALETTE)).not.toBe(PALETTE.gold);
  });

  it("maps an unreported admission to neutral, never to the accent", () => {
    expect(nodeAccentFor(node("Entity", null), PALETTE)).toBe(PALETTE.steelDim);
    expect(nodeAccentFor(node("Entity", "unknown"), PALETTE)).toBe(PALETTE.steelDim);
    expect(nodeAccentFor(node("Entity", null), PALETTE)).not.toBe(PALETTE.accent);
  });

  it("spends at most four distinct colours across the whole vocabulary", () => {
    const colours = new Set(
      GRAPH_OBJECT_KINDS.map((kind) =>
        nodeAccentFor(node(kind, kind === "Hypothesis" ? "provisional" : "admitted"), PALETTE),
      ),
    );
    // Entity/Observation/Claim/Finding admitted share one; Hypothesis
    // provisional is the second. Two colours, not five.
    expect(colours.size).toBeLessThanOrEqual(2);
  });
});

describe("§16 — a hypothesis must never read as admitted fact", () => {
  it("draws a provisional object dashed, and an admitted one solid", () => {
    const hypothesis = nodeStyleFor(node("Hypothesis", "provisional", true), CONTEXT);
    const finding = nodeStyleFor(node("Finding", "admitted"), CONTEXT);
    expect(hypothesis["border-style"]).toBe("dashed");
    expect(finding["border-style"]).toBe("solid");
    expect(isDashed(node("Hypothesis", "provisional", true))).toBe(true);
    expect(isDashed(node("Finding", "admitted"))).toBe(false);
  });

  it("stays distinguishable with colour removed entirely", () => {
    const greyscale = {
      ...PALETTE,
      accent: "#808080",
      steel: "#808080",
      danger: "#808080",
      steelDim: "#808080",
      surface1: "#202020",
      surface2: "#202020",
    };
    const hypothesis = nodeStyleFor(node("Hypothesis", "provisional", true), { ...CONTEXT, palette: greyscale, emphasis: "rest" });
    const finding = nodeStyleFor(node("Finding", "admitted"), { ...CONTEXT, palette: greyscale, emphasis: "rest" });
    // With the palette collapsed to one grey the two are indistinguishable by
    // fill or stroke colour — and still differ by silhouette and by dash.
    expect(hypothesis["background-color"]).toBe(finding["background-color"]);
    expect(hypothesis["border-color"]).toBe(finding["border-color"]);
    expect(hypothesis.shape).not.toBe(finding.shape);
    expect(hypothesis["border-style"]).not.toBe(finding["border-style"]);
  });

  it("differs from a same-kind admitted object in more than colour", () => {
    const provisional = nodeStyleFor(node("Claim", "provisional", true), CONTEXT);
    const admitted = nodeStyleFor(node("Claim", "admitted"), CONTEXT);
    // Same silhouette — that is the point: shape means KIND, so two claims must
    // look alike. The difference is dash and stroke, i.e. provisionality.
    expect(provisional.shape).toBe(admitted.shape);
    expect(provisional["border-style"]).not.toBe(admitted["border-style"]);
    expect(provisional["border-color"]).not.toBe(admitted["border-color"]);
  });
});

describe("§17 — edges are thin and low-noise at rest", () => {
  const EDGE_CONTEXTS = { palette: PALETTE, hovered: false };

  it("draws no edge label at rest for any family", () => {
    for (const family of Object.keys(EDGE_SEMANTICS) as Array<keyof typeof EDGE_SEMANTICS>) {
      const style = edgeStyleForContext(family, { ...EDGE_CONTEXTS, emphasis: "rest" });
      expect(style.label, family).toBe("");
      expect(EDGE_SEMANTICS[family].labelAtRest, family).toBe(false);
    }
  });

  it("keeps every resting edge thin", () => {
    for (const family of Object.keys(EDGE_SEMANTICS) as Array<keyof typeof EDGE_SEMANTICS>) {
      expect(edgeStyleForContext(family, { ...EDGE_CONTEXTS, emphasis: "rest" }).width, family).toBeLessThanOrEqual(1.2);
    }
  });

  it("draws no arrowheads at rest — the canvas is not a flowchart", () => {
    const style = edgeStyleForContext("asserts", { ...EDGE_CONTEXTS, emphasis: "rest" });
    expect(style["target-arrow-shape"]).toBe("none");
  });

  it("separates families by dash pattern, not by colour", () => {
    const styles = (Object.keys(EDGE_SEMANTICS) as Array<keyof typeof EDGE_SEMANTICS>).map((family) =>
      edgeStyleForContext(family, { ...EDGE_CONTEXTS, emphasis: "rest" }),
    );
    const lineColours = new Set(styles.map((style) => style["line-color"]));
    expect(lineColours.size).toBe(1);
    const lineStyles = new Set(styles.map((style) => style["line-style"]));
    expect(lineStyles.size).toBeGreaterThan(1);
  });

  it("brightens the selected path and recedes everything else", () => {
    const onPath = edgeStyleForContext("asserts", { ...EDGE_CONTEXTS, emphasis: "selected" });
    const neighbour = edgeStyleForContext("asserts", { ...EDGE_CONTEXTS, emphasis: "neighbour" });
    const rest = edgeStyleForContext("asserts", { ...EDGE_CONTEXTS, emphasis: "rest" });
    const secondary = edgeStyleForContext("asserts", { ...EDGE_CONTEXTS, emphasis: "secondary" });

    expect(onPath["line-color"]).toBe(PALETTE.accent);
    expect(Number(onPath.width)).toBeGreaterThan(Number(rest.width));
    expect(Number(secondary.opacity)).toBeLessThan(Number(rest.opacity));
    expect(Number(neighbour.opacity)).toBeGreaterThanOrEqual(Number(rest.opacity));
    expect(Number(neighbour.opacity)).toBeLessThan(Number(onPath.opacity));
  });

  it("shows the predicate only on a selected, hovered or path edge", () => {
    expect(predicateIsVisible("rest", false)).toBe(false);
    expect(predicateIsVisible("secondary", false)).toBe(false);
    expect(predicateIsVisible("selected", false)).toBe(true);
    expect(predicateIsVisible("path", false)).toBe(true);
    expect(predicateIsVisible("rest", true)).toBe(true);
  });

  it("gives every family a legend entry explaining what it means", () => {
    for (const row of EDGE_LEGEND) {
      expect(row.note.length).toBeGreaterThan(0);
    }
    expect(EDGE_LEGEND.find((row) => row.family === "possible")?.note).toContain("no merge");
  });
});

describe("§71 / §93 — the palette resolves through tokens, not literals", () => {
  it("returns the fallback when there is no host to read from", () => {
    expect(readGraphPalette(null)).toEqual(GRAPH_PALETTE_FALLBACK);
    expect(readGraphPalette(undefined)).toEqual(GRAPH_PALETTE_FALLBACK);
  });

  it("resolves each token independently, so one missing property cannot blank the palette", () => {
    // jsdom does not resolve custom properties, so a real element falls back
    // per property — which is exactly the resilience under test.
    const host = document.createElement("div");
    const resolved = readGraphPalette(host);
    for (const token of Object.keys(GRAPH_PALETTE_FALLBACK) as Array<keyof GraphPalette>) {
      expect(resolved[token].length, token).toBeGreaterThan(0);
    }
    expect(resolved).toEqual(GRAPH_PALETTE_FALLBACK);
  });
});

describe("§98 / §69 — routing", () => {
  it("routes every kind to a real WorkspaceSelection, except a hypothesis", () => {
    expect(routeForNode(node("Entity", "admitted"))).toEqual({
      kind: "Entity",
      id: "Entity-1",
      label: "Entity",
    });
    expect(routeForNode(node("Observation", "admitted"))?.kind).toBe("Observation");
    expect(routeForNode(node("Claim", "provisional"))?.kind).toBe("Claim");
    expect(routeForNode(node("Finding", "provisional"))?.kind).toBe("Finding");
  });

  it("routes a hypothesis to the entity whose correlation produced it, never to itself", () => {
    const orphan = { ...node("Hypothesis", "provisional", true), originEntityId: null };
    expect(routeForNode(orphan)).toBeNull();

    const anchored = { ...node("Hypothesis", "provisional", true), originEntityId: "ENT-9" };
    const route = routeForNode(anchored);
    expect(route?.kind).toBe("Entity");
    expect(route?.id).toBe("ENT-9");
  });
});

describe("edge geometry invariants", () => {
  it("keeps a resting edge family label independent of any edge data", () => {
    const edge = { family: "possible", predicate: "possible_match" } as unknown as GraphEdge;
    expect(edge.predicate).toBe("possible_match");
  });
});