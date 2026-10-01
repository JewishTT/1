import { describe, expect, it } from "vitest";

import type { EntityView, FindingView, InvestigationView } from "../../lib/api";
import { buildInspectorModel, claimSections, observationSections, sectionOrder } from "./model";
import {
  EMPTY_INSPECTOR_DATA,
  type CaptureRecord,
  type ClaimRecord,
  type InspectorData,
  type ObservationRecord,
  type SourceRecord,
} from "./types";
import type { WorkspaceSelection } from "../types";

/**
 * Inspector object-driven dispatch tests (§33, §34).
 *
 * The point of these is that the inspector is *driven by the selected object*,
 * not by which page happens to be mounted, and that it never invents a value
 * it was not given.
 */

const OBSERVATION: ObservationRecord = {
  observation_id: "OBS-9001",
  capture_id: "CAP-abc",
  locator: "//article[3]/p[1]",
  record_digest: "sha256:deadbeef",
  content_type: "application/json",
  runtime_producer: "observation-gate",
  runtime_producer_version: "0.1.0",
  parser_hint: "json",
  source_id: "SRC-7",
  uri: "https://example.org/a.json",
  collected_at: "2026-02-01T10:00:00Z",
  lifecycle: "RUNNING",
  tenant_id: "tenant-1",
};

const CAPTURE: CaptureRecord = {
  capture_id: "CAP-abc",
  source_id: "SRC-7",
  source_family: "web",
  target_uri: "https://example.org/a.json",
  locator: "capture",
  content_digest: "sha256:deadbeef",
  media_type: "application/json",
  fetched_at: "2026-02-01T09:59:00Z",
  time_basis: "FETCH",
};

const SOURCE: SourceRecord = {
  source_id: "SRC-7",
  name: "example.org connector",
  kind: "http",
  tenant_id: "tenant-1",
};

const CLAIM: ClaimRecord = {
  relation_id: "REL-42",
  relation_type: "works_for",
  subject_ref: "ENT-1",
  object_ref: "ENT-2",
  role_bindings: [{ role: "employer", member_ref: "ENT-2" }],
  valid_from: "2024-01-01T00:00:00Z",
  valid_to: null,
  observed_at: "2025-06-01T00:00:00Z",
  published_at: "2025-06-02T00:00:00Z",
  known_from: "2025-06-02T00:00:00Z",
  known_until: null,
  evidence_grade: "CORROBORATED",
  confidence: 0.82,
  status: "ACTIVE",
  assertion_refs: ["CLM-1"],
  observation_refs: ["OBS-9001", "OBS-9002"],
  extraction_version: "ext-3",
  normalization_version: "norm-2",
  ontology_version: "onto-7",
  contradicts: ["REL-41"],
  supersedes: "REL-40",
  investigation_id: "INV-1",
  candidate_id: "CAND-3",
};

const ENTITY: EntityView = {
  entity_id: "ENT-182",
  canonical_identity: { account: "org-x" },
  current_state: {},
  historical_versions: [],
  aliases: ["Организация X", "OrgX"],
  relationships: [{ kind: "works_for", target: "ENT-2" }],
  supporting_assertions: ["REL-42"],
  evidence: [],
  timeline: [{ observation_id: "OBS-9001", uri: "https://example.org/a.json", immutable: true }],
  structural_signals: [],
};

const FINDING: FindingView = {
  finding_id: "FND-5",
  status: "OPEN",
  why_detected: "Two sources disagree on the affiliation window.",
  structural_evidence: [{ kind: "edge_count" }],
  semantic_evidence: [{ kind: "statement" }],
  supporting_graph_region: { nodes: ["ENT-1"] },
  supporting_assertions: ["REL-42"],
  observations: [{ observation_id: "OBS-9001", uri: "https://example.org/a.json", immutable: true }],
  sources: ["SRC-7"],
  evidence_resolves: false,
};

const INVESTIGATION: InvestigationView = {
  investigation_id: "42",
  name: "Operation Ledger",
  tenant_id: "tenant-1",
  objective: { goal: "monitor" },
  seeds: ["ENT-182"],
  scope: { regions: ["eu"] },
  policy_id: "policies/default",
  state: "RUNNING",
  created_at: "2026-01-01T00:00:00Z",
};

function data(overrides: Partial<InspectorData>): InspectorData {
  return { ...EMPTY_INSPECTOR_DATA, ...overrides };
}

function sel(kind: WorkspaceSelection["kind"], id: string): WorkspaceSelection {
  return { kind, id };
}

describe("inspector dispatch — selection drives the panel", () => {
  it("returns an empty model, not an error, when nothing is selected", () => {
    const model = buildInspectorModel(null, data({}));
    expect(model.kind).toBeNull();
    expect(model.sections).toEqual([]);
    expect(model.unavailable).toBe(false);
  });

  it("renders an observation when an observation is selected", () => {
    const model = buildInspectorModel(sel("Observation", "OBS-9001"), data({ observation: OBSERVATION }));
    expect(model.kind).toBe("Observation");
    expect(model.unavailable).toBe(false);
    expect(model.subtitle).toBe("OBS-9001");
    expect(model.sections.length).toBeGreaterThan(0);
  });

  it("renders a claim when a claim is selected, in the same panel", () => {
    const model = buildInspectorModel(sel("Claim", "REL-42"), data({ claim: CLAIM }));
    expect(model.kind).toBe("Claim");
    expect(model.unavailable).toBe(false);
  });

  it("renders an entity when an entity is selected", () => {
    const model = buildInspectorModel(sel("Entity", "ENT-182"), data({ entity: ENTITY }));
    expect(model.kind).toBe("Entity");
    expect(model.title).toBe("org-x");
  });

  it("renders a finding when a finding is selected", () => {
    const model = buildInspectorModel(sel("Finding", "FND-5"), data({ finding: FINDING }));
    expect(model.kind).toBe("Finding");
  });

  it("renders an investigation when an investigation is selected", () => {
    const model = buildInspectorModel(sel("Investigation", "42"), data({ investigation: INVESTIGATION }));
    expect(model.kind).toBe("Investigation");
    expect(model.title).toBe("Operation Ledger");
  });

  it("dispatches on kind alone: the same panel serves every record type", () => {
    const bundle = data({
      entity: ENTITY,
      observation: OBSERVATION,
      claim: CLAIM,
      finding: FINDING,
      investigation: INVESTIGATION,
    });
    for (const [kind, id] of [
      ["Entity", "ENT-182"],
      ["Observation", "OBS-9001"],
      ["Claim", "REL-42"],
      ["Finding", "FND-5"],
      ["Investigation", "42"],
    ] as const) {
      expect(buildInspectorModel(sel(kind, id), bundle).unavailable, kind).toBe(false);
    }
  });

  it("marks a selection whose record has not been fetched as unavailable, not empty", () => {
    const model = buildInspectorModel(sel("Observation", "OBS-NOPE"), data({ observation: OBSERVATION }));
    expect(model.unavailable).toBe(true);
    expect(model.id).toBe("OBS-NOPE");
  });

  it("does not show one kind's record under another kind's selection", () => {
    // An entity record is present, but an observation is selected.
    const model = buildInspectorModel(sel("Observation", "OBS-9001"), data({ entity: ENTITY }));
    expect(model.unavailable).toBe(true);
    expect(model.sections).toEqual([]);
  });
});

describe("§33 — an observation answers 'where did this come from?'", () => {
  const sections = observationSections(OBSERVATION, CAPTURE, SOURCE);
  const provenance = sections.find((entry) => entry.id === "provenance");

  it("shows all ten required fields", () => {
    const keys = provenance?.fields.map((entry) => entry.key) ?? [];
    expect(keys).toEqual([
      "observation-id",
      "capture",
      "source",
      "locator",
      "collected-at",
      "content-type",
      "digest",
      "runtime",
      "parser",
      "processing-state",
    ]);
  });

  it("shows the values the platform reported", () => {
    const byKey = Object.fromEntries((provenance?.fields ?? []).map((entry) => [entry.key, entry.value]));
    expect(byKey["observation-id"]).toBe("OBS-9001");
    expect(byKey.capture).toBe("CAP-abc");
    expect(byKey.source).toBe("SRC-7");
    expect(byKey.locator).toBe("//article[3]/p[1]");
    expect(byKey["collected-at"]).toBe("2026-02-01T10:00:00Z");
    expect(byKey["content-type"]).toBe("application/json");
    expect(byKey.digest).toBe("sha256:deadbeef");
    expect(byKey.runtime).toBe("observation-gate 0.1.0");
    expect(byKey.parser).toBe("json");
    expect(byKey["processing-state"]).toBe("RUNNING");
  });

  it("adds source and capture sections when those records were fetched", () => {
    expect(sectionOrder(sections)).toEqual(["provenance", "source", "capture"]);
  });

  it("omits the capture section when the capture was not fetched, rather than faking one", () => {
    const without = observationSections(OBSERVATION, null, null);
    expect(sectionOrder(without)).toEqual(["provenance"]);
  });

  it("renders an unreported field as null, never as an empty string or a guess", () => {
    const sparse = observationSections(
      { ...OBSERVATION, parser_hint: null, lifecycle: null, collected_at: null },
      null,
      null,
    );
    const provenance = sparse.find((entry) => entry.id === "provenance");
    const byKey = Object.fromEntries((provenance?.fields ?? []).map((entry) => [entry.key, entry.value]));
    expect(byKey.parser).toBeNull();
    expect(byKey["processing-state"]).toBeNull();
    expect(byKey["collected-at"]).toBeNull();
  });

  it("keeps the row present even when the value is unreported", () => {
    const sparse = observationSections({ ...OBSERVATION, parser_hint: null }, null, null);
    const provenance = sparse.find((entry) => entry.id === "provenance");
    expect(provenance?.fields).toHaveLength(10);
  });

  it("treats a whitespace-only value as unreported", () => {
    const blank = observationSections({ ...OBSERVATION, locator: "   " }, null, null);
    const provenance = blank.find((entry) => entry.id === "provenance");
    const byKey = Object.fromEntries((provenance?.fields ?? []).map((entry) => [entry.key, entry.value]));
    expect(byKey.locator).toBeNull();
  });
});

describe("§34 — a claim is not a boolean", () => {
  const sections = claimSections(CLAIM);

  it("names the predicate and both participants", () => {
    const assertion = sections.find((entry) => entry.id === "assertion");
    const byKey = Object.fromEntries((assertion?.fields ?? []).map((entry) => [entry.key, entry.value]));
    expect(byKey.predicate).toBe("works_for");
    expect(byKey.subject).toBe("ENT-1");
    expect(byKey.object).toBe("ENT-2");
  });

  it("shows temporal scope with an open bound spelled as an ellipsis, not a guess", () => {
    const temporal = sections.find((entry) => entry.id === "temporal");
    const byKey = Object.fromEntries((temporal?.fields ?? []).map((entry) => [entry.key, entry.value]));
    expect(byKey.validity).toBe("2024-01-01T00:00:00Z → …");
  });

  it("separates status/admission from validation", () => {
    const status = sections.find((entry) => entry.id === "status");
    const validation = sections.find((entry) => entry.id === "validation");
    const statusKeys = status?.fields.map((entry) => entry.key) ?? [];
    const validationKeys = validation?.fields.map((entry) => entry.key) ?? [];
    expect(statusKeys).toContain("status");
    expect(validationKeys).toEqual(["evidence-grade", "confidence"]);
  });

  it("reports evidence as counts and links through to the first observation", () => {
    const evidence = sections.find((entry) => entry.id === "evidence");
    const observations = evidence?.fields.find((entry) => entry.key === "observations");
    expect(observations?.value).toBe(2);
    expect(observations?.linkTo).toEqual({ kind: "Observation", id: "OBS-9001" });
  });

  it("reports derivation as the platform's own versions", () => {
    const derivation = sections.find((entry) => entry.id === "derivation");
    const byKey = Object.fromEntries((derivation?.fields ?? []).map((entry) => [entry.key, entry.value]));
    expect(byKey["extraction-version"]).toBe("ext-3");
    expect(byKey["normalization-version"]).toBe("norm-2");
    expect(byKey["ontology-version"]).toBe("onto-7");
  });

  it("marks a claim with recorded contradictions, and only that one", () => {
    const contradicted = buildInspectorModel(sel("Claim", "REL-42"), data({ claim: CLAIM }));
    expect(contradicted.badges.map((badge) => badge.label)).toContain("contradicted");

    const clean = buildInspectorModel(
      sel("Claim", "REL-43"),
      data({ claim: { ...CLAIM, relation_id: "REL-43", contradicts: [] } }),
    );
    expect(clean.badges.map((badge) => badge.label)).not.toContain("contradicted");
  });

  it("renders no evidence link when the claim rests on no observations", () => {
    const bare = claimSections({ ...CLAIM, observation_refs: [], assertion_refs: [] });
    const evidence = bare.find((entry) => entry.id === "evidence");
    const observations = evidence?.fields.find((entry) => entry.key === "observations");
    expect(observations?.value).toBe(0);
    expect(observations?.linkTo).toBeUndefined();
  });

  it("renders a fully unscoped claim as 'not reported' for validity", () => {
    const unscoped = claimSections({ ...CLAIM, valid_from: null, valid_to: null });
    const temporal = unscoped.find((entry) => entry.id === "temporal");
    const byKey = Object.fromEntries((temporal?.fields ?? []).map((entry) => [entry.key, entry.value]));
    expect(byKey.validity).toBeNull();
  });
});

describe("inspector — §99 no semantic invention", () => {
  it("labels the object kind from the platform's own record, not a UI synonym", () => {
    const bundle = data({ observation: OBSERVATION, claim: CLAIM, entity: ENTITY });
    expect(buildInspectorModel(sel("Observation", "OBS-9001"), bundle).badges[0].label).toBe("observation");
    expect(buildInspectorModel(sel("Claim", "REL-42"), bundle).badges[0].label).toBe("claim");
    expect(buildInspectorModel(sel("Entity", "ENT-182"), bundle).badges[0].label).toBe("entity");
  });

  it("does not present an observation as a claim or vice versa", () => {
    const bundle = data({ observation: OBSERVATION, claim: CLAIM });
    const obs = buildInspectorModel(sel("Observation", "OBS-9001"), bundle);
    const claim = buildInspectorModel(sel("Claim", "REL-42"), bundle);
    expect(obs.kind).toBe("Observation");
    expect(claim.kind).toBe("Claim");
    expect(obs.sections.map((s) => s.id)).not.toEqual(claim.sections.map((s) => s.id));
  });

  it("leaves acquisition kinds honestly unavailable at this stage", () => {
    const model = buildInspectorModel(sel("AcquisitionRun", "RUN-1"), data({}));
    expect(model.kind).toBe("AcquisitionRun");
    expect(model.unavailable).toBe(true);
  });
});

describe("inspector — ordering", () => {
  it("orders sections by their explicit order, not by insertion accident", () => {
    const order = sectionOrder([
      { id: "c", title: "C", order: 30, fields: [] },
      { id: "a", title: "A", order: 10, fields: [] },
      { id: "b", title: "B", order: 20, fields: [] },
    ]);
    expect(order).toEqual(["a", "b", "c"]);
  });
});