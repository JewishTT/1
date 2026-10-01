import { describe, expect, it } from "vitest";

import { FABRIC_DECLARATIONS, connectorEcho, fabricRows, runtimeHintFor, withRuntimeHints } from "./fabric";
import type { ConnectorWire } from "./fabric";

const MAIGRET: ConnectorWire = {
  connector_id: "CN-abc",
  name: "maigret",
  status: "ACTIVE",
  version: "0.6.6",
  policy_id: "policies/default",
  source_types: [],
  contract_compliant: true,
};

describe("§48 — the five acquisition runtimes are one fabric", () => {
  it("lists SearXNG, Airbyte, Maigret, BBOT and SpiderFoot", () => {
    expect(FABRIC_DECLARATIONS.map((entry) => entry.source).sort()).toEqual([
      "airbyte",
      "bbot",
      "maigret",
      "searxng",
      "spiderfoot",
    ]);
  });

  it("carries each runtime's real runtime_ref rather than a display label", () => {
    // §14: runtime_ref is the executable identity and must not be reworded.
    const refs = Object.fromEntries(FABRIC_DECLARATIONS.map((entry) => [entry.source, entry.runtimeRef]));
    expect(refs).toEqual({
      searxng: "searxng",
      airbyte: "airbyte",
      bbot: "bbot",
      maigret: "maigret",
      spiderfoot: "spiderfoot",
    });
  });

  it("carries the declared execution_class for each runtime", () => {
    const classes = Object.fromEntries(FABRIC_DECLARATIONS.map((entry) => [entry.source, entry.executionClass]));
    expect(classes).toEqual({
      searxng: "api/http",
      airbyte: "connector_protocol",
      bbot: "event_producing",
      // maigret and spiderfoot share one runtime, so they share its class.
      maigret: "external_process",
      spiderfoot: "external_process",
    });
  });

  it("carries each runtime's own capabilities(), verbatim", () => {
    const caps = Object.fromEntries(FABRIC_DECLARATIONS.map((entry) => [entry.source, entry.capabilities]));
    expect(caps["searxng"]).toEqual(["http", "search", "json-output", "paged"]);
    expect(caps["airbyte"]).toEqual(["connector-protocol", "stdio", "streaming", "stateful", "discover"]);
    expect(caps["bbot"]).toEqual(["recon", "event-stream", "passive", "dns", "subdomains", "streaming"]);
    expect(caps["maigret"]).toEqual(["process", "container-isolated", "streaming", "resource-bounded"]);
  });

  it("names the module that declares each row, so a drift is a bug here too", () => {
    for (const declaration of FABRIC_DECLARATIONS) {
      expect(declaration.declaredBy, declaration.source).toMatch(/^apps\/acquisition\/runtime\//);
    }
  });

  it("renders all five through ONE row shape", () => {
    // The §48 requirement is structural: five items of one fabric, not five cards.
    const rows = fabricRows([]);
    expect(rows).toHaveLength(5);
    const shapes = rows.map((row) => Object.keys(row).sort().join(","));
    expect(new Set(shapes).size).toBe(1);
  });
});

describe("§48 — the mirrored floor and the fetched truth", () => {
  it("shows the full fabric even when the tenant registered nothing", () => {
    // The finding that made this a mirror: an empty /connectors response must not
    // render an empty catalogue, because that reads as "no sources exist".
    const rows = fabricRows([]);
    expect(rows).toHaveLength(5);
    expect(rows.every((row) => row.connector === null)).toBe(true);
  });

  it("joins a connector whose name is exactly the runtime", () => {
    const rows = fabricRows(withRuntimeHints([MAIGRET]));
    const maigret = rows.find((row) => row.runtimeRef === "maigret");
    expect(maigret?.connector?.name).toBe("maigret");
    expect(maigret?.connector?.contractCompliant).toBe(true);
  });

  it("joins a connector whose name is prefixed by the runtime (maigret-sites)", () => {
    const rows = fabricRows(
      withRuntimeHints([{ ...MAIGRET, name: "maigret-sites", version: "0.7.0" }]),
    );
    const maigret = rows.find((row) => row.runtimeRef === "maigret");
    expect(maigret?.connector?.name).toBe("maigret-sites");
    // The tenant's version wins over the mirrored pin: the catalogue is about
    // what THIS tenant runs.
    expect(maigret?.version).toBe("0.7.0");
  });

  it("leaves other runtimes unclaimed rather than attaching a connector to the wrong row", () => {
    const rows = fabricRows(withRuntimeHints([MAIGRET]));
    const claimed = rows.filter((row) => row.connector !== null).map((row) => row.runtimeRef);
    expect(claimed).toEqual(["maigret"]);
  });

  it("folds the tenant's declared source types into coverage", () => {
    const rows = fabricRows(withRuntimeHints([{ ...MAIGRET, source_types: ["username", "site"] }]));
    const maigret = rows.find((row) => row.runtimeRef === "maigret");
    expect(maigret?.coverage).toContain("username");
    expect(maigret?.coverage).toContain("site");
  });
});

describe("§13 — the runtime hint comes from the name, never from capabilities", () => {
  it("reads a name that declares a runtime", () => {
    expect(runtimeHintFor("maigret")).toBe("maigret");
    expect(runtimeHintFor("maigret-sites")).toBe("maigret");
    expect(runtimeHintFor("spiderfoot_scan")).toBe("spiderfoot");
    expect(runtimeHintFor("BBOT")).toBe("bbot");
  });

  it("refuses to claim a generic connector that speaks HTTP", () => {
    // The §13 violation this prevents: a BBOT task reaching a generic HTTP worker
    // "because both speak HTTP". Capability inference is the same bug in another
    // spelling.
    expect(runtimeHintFor("subdomains-http")).toBeNull();
    expect(runtimeHintFor("rss-http")).toBeNull();
    expect(runtimeHintFor("maigreting")).toBeNull();
  });

  it("reports a null hint rather than a guess for an unclaimed connector", () => {
    expect(connectorEcho({ ...MAIGRET, name: "subdomains-http" }).runtimeRefHint).toBeNull();
  });
});

describe("§99 — the catalogue states what it cannot report", () => {
  it("leaves health, last run and success rate null rather than zero", () => {
    for (const row of fabricRows([])) {
      expect(row.health, row.runtimeRef).toBeNull();
      expect(row.lastRunAt, row.runtimeRef).toBeNull();
      expect(row.successRate, row.runtimeRef).toBeNull();
      expect(row.runsTotal, row.runtimeRef).toBeNull();
    }
  });

  it("names the endpoint that would close each gap", () => {
    const row = fabricRows([])[0];
    expect(row.gaps.length).toBeGreaterThan(0);
    for (const gap of row.gaps) {
      expect(gap.endpoint, row.runtimeRef).toMatch(/^(GET|POST) /);
      expect(gap.reason.length).toBeGreaterThan(0);
    }
  });

  it("does not claim a pinned version for a runtime that resolves it at run time", () => {
    const rows = fabricRows([]);
    // airbyte derives its version from the image digest at run time, so the
    // mirrored row must say so rather than pin a number it does not have.
    expect(rows.find((row) => row.runtimeRef === "airbyte")?.version).toBeNull();
    // spiderfoot's own definition declares version "unpinned".
    expect(rows.find((row) => row.runtimeRef === "spiderfoot")?.version).toBe("unpinned");
    expect(rows.find((row) => row.runtimeRef === "maigret")?.version).toBe("0.6.6");
  });
});