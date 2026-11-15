import { describe, expect, it } from "vitest";

import type { SpecOpsGraphResponse } from "./api";
import {
  ENTITY_TYPE_STYLES,
  formatEntityValue,
  graphToCytoscape,
  toEntityTarget,
  typeStyle,
} from "./specopsGraph";

const GRAPH: SpecOpsGraphResponse = {
  nodes: [
    { id: "e-1", label: "alice@example.com", entity_type: "EMAIL", properties: { email: "alice@example.com" } },
    { id: "e-2", label: "", entity_type: "USERNAME", properties: { username: "bob" } },
    { id: "e-3", label: "10.0.0.1", entity_type: "IPV4", properties: {} },
    { id: "e-4", label: "mystery", entity_type: "GALAXY", properties: {} },
  ],
  edges: [{ id: "rel-1", source: "e-1", target: "e-2", kind: "related_to" }],
};

describe("typeStyle", () => {
  it("returns the mapped style for each known entity type", () => {
    expect(typeStyle("EMAIL")).toEqual(ENTITY_TYPE_STYLES.EMAIL);
    expect(typeStyle("USERNAME")).toMatchObject({ icon: "@", className: "so-username" });
    expect(typeStyle("PHONE")).toMatchObject({ icon: "☎" });
    expect(typeStyle("DOMAIN")).toMatchObject({ icon: "◉", className: "so-domain" });
    expect(typeStyle("URL")).toMatchObject({ icon: "⌕" });
    expect(typeStyle("NAME")).toMatchObject({ icon: "◈" });
    expect(typeStyle("ORG")).toMatchObject({ icon: "▤" });
    expect(typeStyle("LOCATION")).toMatchObject({ icon: "⌖" });
    expect(typeStyle("IPV4")).toMatchObject({ icon: "⛁", className: "so-ipv4" });
  });

  it("is case-insensitive and falls back for unknown types", () => {
    expect(typeStyle("email")).toEqual(ENTITY_TYPE_STYLES.EMAIL);
    expect(typeStyle(" Email ")).toEqual(ENTITY_TYPE_STYLES.EMAIL);
    expect(typeStyle("GALAXY")).toEqual(ENTITY_TYPE_STYLES.UNKNOWN);
    expect(typeStyle("")).toEqual(ENTITY_TYPE_STYLES.UNKNOWN);
  });

  it("is deterministic", () => {
    expect(typeStyle("EMAIL")).toBe(typeStyle("EMAIL"));
  });
});

describe("formatEntityValue", () => {
  it("prefers the backend label", () => {
    expect(formatEntityValue(GRAPH.nodes[0])).toBe("alice@example.com");
  });

  it("falls back to a property when the label is empty", () => {
    expect(formatEntityValue(GRAPH.nodes[1])).toBe("bob");
  });

  it("falls back to the id when nothing else is available", () => {
    expect(formatEntityValue(GRAPH.nodes[2])).toBe("10.0.0.1");
  });
});

describe("graphToCytoscape", () => {
  it("emits nodes with entity data and a classes token from typeStyle", () => {
    const elements = graphToCytoscape(GRAPH);
    const nodes = elements.filter((e) => e.data.source === undefined);
    expect(nodes).toHaveLength(4);
    const email = nodes.find((n) => n.data.id === "e-1");
    expect(email).toMatchObject({
      classes: "so-email",
      data: { id: "e-1", entity_type: "EMAIL", entity_value: "alice@example.com" },
    });
  });

  it("assigns the fallback class for unknown entity types", () => {
    const elements = graphToCytoscape(GRAPH);
    const galaxy = elements.find((e) => e.data.id === "e-4");
    expect(galaxy?.classes).toBe("so-unknown");
  });

  it("maps edges with source/target and label set to the edge kind", () => {
    const elements = graphToCytoscape(GRAPH);
    const edges = elements.filter((e) => e.data.source !== undefined);
    expect(edges).toHaveLength(1);
    expect(edges[0]).toMatchObject({
      data: { id: "rel-1", source: "e-1", target: "e-2", label: "related_to" },
    });
  });
});

describe("toEntityTarget", () => {
  it("shapes a graph node into a toolbar selection target", () => {
    const target = toEntityTarget(GRAPH.nodes[0]);
    expect(target).toEqual({
      id: "e-1",
      label: "alice@example.com",
      entity_type: "EMAIL",
      entity_value: "alice@example.com",
    });
  });
});