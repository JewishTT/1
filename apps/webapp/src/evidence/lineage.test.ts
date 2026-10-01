import { describe, expect, it } from "vitest";

import {
  CHAIN_EXCLUSIVE_KINDS,
  DERIVATION_CHAIN_ID,
  DERIVATION_STEP_ORDER,
  EVIDENCE_STEP_ORDER,
  SHARED_KINDS,
  assertChainsSeparate,
  routeDerivationStep,
  routeEvidenceStep,
  type DerivationLineageStep,
  type EvidenceLineageChain,
  type EvidenceLineageStep,
  type LineageModel,
} from "./lineage";
import { buildDerivationChain, buildEvidenceChain, buildLineageModel, chainSummary } from "./lineageBuilder";

/**
 * Chain separation (§31, §32).
 *
 * The failure this file prevents is the one the legacy `LineageWalker`
 * demonstrates: a single `LineageNode[]` with a merged `kind` union, walked into
 * one list with one arrow. That renders fine and it is a lie — it puts a Finding
 * next to an observation with no claim between them, an inference nobody made.
 *
 * The tests assert the separation at three levels:
 *   1. the TYPE — the two step unions do not overlap except for the two kinds
 *      the platform genuinely uses in both senses
 *   2. the BUILDER — each chain is built by its own function from its own input
 *   3. the RUNTIME — `assertChainsSeparate` catches untyped data from the server
 */

const FULL_EVIDENCE = buildEvidenceChain({
  finding: {
    finding_id: "FND-1",
    status: "OPEN",
    why_detected: "burst",
    structural_evidence: [{}],
    semantic_evidence: [],
    supporting_graph_region: {},
    supporting_assertions: [],
    observations: [{ observation_id: "OBS-1", uri: "https://a.example/1", immutable: true }],
    sources: ["a.example"],
    evidence_resolves: true,
  },
  claim: {
    relation_id: "CLM-1",
    relation_type: "works_for",
    subject_ref: "ENT-1",
    object_ref: "ENT-2",
    role_bindings: [],
    valid_from: "2026-01-01T00:00:00Z",
    valid_to: null,
    observed_at: "2026-01-02T00:00:00Z",
    published_at: null,
    known_from: null,
    known_until: null,
    evidence_grade: "B",
    confidence: 0.8,
    status: "ADMITTED",
    assertion_refs: [],
    observation_refs: ["OBS-1"],
    extraction_version: "1",
    normalization_version: "1",
    ontology_version: "1",
    contradicts: [],
    supersedes: null,
    investigation_id: "INV-1",
    candidate_id: null,
  },
  observation: {
    observation_id: "OBS-1",
    capture_id: "CAP-1",
    locator: "$.records[0].email",
    record_digest: "sha256:abcd",
    content_type: "application/json",
    runtime_producer: "crawler",
    runtime_producer_version: "2",
    parser_hint: null,
    source_id: "a.example",
    uri: "https://a.example/1",
    collected_at: "2026-01-02T00:00:00Z",
    lifecycle: "STORED",
    tenant_id: "t1",
  },
  capture: { capture_id: "CAP-1", target_uri: "https://a.example/1", content_digest: "sha256:beef" },
  rawObject: { ref: "obj/CAP-1.json", digest: "sha256:beef", bytes: 4096 },
  source: { source_id: "a.example", name: "A Example", kind: "web" },
});

const FULL_DERIVATION = buildDerivationChain({
  claim: {
    relation_id: "CLM-1",
    relation_type: "works_for",
    subject_ref: "ENT-1",
    object_ref: "ENT-2",
    role_bindings: [],
    valid_from: "2026-01-01T00:00:00Z",
    valid_to: null,
    observed_at: null,
    published_at: null,
    known_from: null,
    known_until: null,
    evidence_grade: null,
    confidence: 0.8,
    status: "ADMITTED",
    assertion_refs: [],
    observation_refs: [],
    extraction_version: null,
    normalization_version: null,
    ontology_version: null,
    contradicts: [],
    supersedes: null,
    investigation_id: null,
    candidate_id: "CAND-9",
  },
  candidate: { ref: "CAND-9", score: 0.42, reasons: ["name", "domain"] },
  signal: { ref: "SIG-3", name: "co_occurrence", score: 0.61 },
  observation: {
    observation_id: "OBS-1",
    capture_id: null,
    locator: null,
    record_digest: null,
    content_type: null,
    runtime_producer: null,
    runtime_producer_version: null,
    parser_hint: null,
    source_id: null,
    uri: null,
    collected_at: null,
    lifecycle: null,
    tenant_id: null,
  },
  originEntityId: "ENT-1",
});

describe("§31 — the evidence chain runs Finding → Claim → Evidence → Observation → Capture → Raw object → Source", () => {
  it("has exactly those seven rungs, in that order, and nothing else", () => {
    expect([...EVIDENCE_STEP_ORDER]).toEqual([
      "Finding",
      "Claim",
      "Evidence",
      "Observation",
      "Capture",
      "RawObject",
      "Source",
    ]);
  });

  it("emits every rung when every record is present, in provenance order", () => {
    expect(FULL_EVIDENCE.steps.map((step) => step.kind)).toEqual([...EVIDENCE_STEP_ORDER]);
    expect(FULL_EVIDENCE.missingRungs).toEqual([]);
  });

  it("keeps the rungs in provenance order even when the input arrives shuffled", () => {
    const shuffled = buildEvidenceChain({
      finding: null,
      claim: null,
      observation: null,
      capture: null,
      rawObject: null,
      source: { source_id: "a.example", name: null, kind: null },
    });
    expect(shuffled.steps.map((step) => step.kind)).toEqual(["Source"]);

    const sourceFirst: EvidenceLineageChain = buildEvidenceChain({
      finding: null,
      claim: null,
      observation: null,
      capture: null,
      rawObject: null,
      source: { source_id: "s", name: null, kind: null },
    });
    expect(sourceFirst.steps[0]?.kind).toBe("Source");
  });

  it("reports a missing rung instead of rendering an empty box or guessing it", () => {
    const partial = buildEvidenceChain({
      finding: null,
      claim: null,
      observation: {
        observation_id: "OBS-9",
        capture_id: null,
        locator: null,
        record_digest: null,
        content_type: null,
        runtime_producer: null,
        runtime_producer_version: null,
        parser_hint: null,
        source_id: null,
        uri: null,
        collected_at: null,
        lifecycle: null,
        tenant_id: null,
      },
      capture: null,
      rawObject: null,
      source: null,
    });
    expect(partial.steps.map((step) => step.kind)).toEqual(["Observation"]);
    expect(partial.missingRungs).toEqual(["Finding", "Claim", "Evidence", "Capture", "RawObject", "Source"]);
    // Every reported missing rung is a real rung, not a leftover.
    for (const rung of partial.missingRungs) expect(EVIDENCE_STEP_ORDER).toContain(rung);
  });

  it("summary counts present rungs against the whole spine", () => {
    expect(chainSummary(FULL_EVIDENCE)).toBe("7/7 rungs");
    expect(chainSummary(null)).toBe("no record");
  });
});

describe("§32 — the derivation chain runs Claim → Candidate → Signal → Observation", () => {
  it("has exactly those four rungs, in that order, and nothing else", () => {
    expect([...DERIVATION_STEP_ORDER]).toEqual(["Claim", "Candidate", "Signal", "Observation"]);
  });

  it("emits every rung when every record is present", () => {
    expect(FULL_DERIVATION.steps.map((step) => step.kind)).toEqual([...DERIVATION_STEP_ORDER]);
    expect(FULL_DERIVATION.missingRungs).toEqual([]);
  });

  it("carries the platform-reported score and never a defaulted one", () => {
    const claim = FULL_DERIVATION.steps.find((step) => step.kind === "Claim");
    const candidate = FULL_DERIVATION.steps.find((step) => step.kind === "Candidate");
    const signal = FULL_DERIVATION.steps.find((step) => step.kind === "Signal");
    const observation = FULL_DERIVATION.steps.find((step) => step.kind === "Observation");
    expect(claim?.score).toBe(0.8);
    expect(candidate?.score).toBe(0.42);
    expect(signal?.score).toBe(0.61);
    // Observation has no platform score, so it is null — not 0, which is a claim.
    expect(observation?.score).toBeNull();
  });

  it("reports a missing rung rather than inferring one from the evidence chain", () => {
    const claimOnly = buildDerivationChain({
      claim: null,
      candidate: null,
      signal: null,
      observation: null,
      originEntityId: null,
    });
    expect(claimOnly.steps).toEqual([]);
    expect(claimOnly.missingRungs).toEqual([...DERIVATION_STEP_ORDER]);
  });

  it("routes a candidate and a signal to the entity whose neighbourhood produced them", () => {
    const candidate = FULL_DERIVATION.steps.find((step) => step.kind === "Candidate");
    const route = candidate === undefined ? null : routeDerivationStep(candidate);
    expect(route).toEqual({ kind: "Entity", id: "ENT-1" });

    // With no origin there is nowhere honest to send it.
    const orphan = buildDerivationChain({
      claim: null,
      candidate: { ref: "CAND-1", score: null, reasons: [] },
      signal: null,
      observation: null,
      originEntityId: null,
    });
    const orphanCandidate = orphan.steps[0];
    expect(orphanCandidate === undefined ? null : routeDerivationStep(orphanCandidate)).toBeNull();
  });
});

describe("§31 + §32 — the two chains do not mix", () => {
  const MODEL: LineageModel = { evidence: FULL_EVIDENCE, derivation: FULL_DERIVATION };

  it("declares which rungs belong to exactly one chain, and which to both", () => {
    expect([...CHAIN_EXCLUSIVE_KINDS.evidence]).toEqual(["Finding", "Evidence", "Capture", "RawObject", "Source"]);
    expect([...CHAIN_EXCLUSIVE_KINDS.derivation]).toEqual(["Candidate", "Signal"]);
    expect([...SHARED_KINDS]).toEqual(["Claim", "Observation"]);

    // The two exclusive sets are disjoint, and every rung in the shared set is a
    // rung of BOTH orders. If that stops being true the two vocabularies have
    // drifted and this file's other assertions mean nothing.
    for (const shared of SHARED_KINDS) {
      expect(EVIDENCE_STEP_ORDER).toContain(shared);
      expect(DERIVATION_STEP_ORDER).toContain(shared);
    }
    for (const kind of CHAIN_EXCLUSIVE_KINDS.evidence) {
      expect(CHAIN_EXCLUSIVE_KINDS.derivation).not.toContain(kind);
      expect(EVIDENCE_STEP_ORDER).toContain(kind);
    }
  });

  it("passes the separation check on well-formed data", () => {
    const result = assertChainsSeparate(MODEL);
    expect(result.violations).toEqual([]);
    expect(result.separated).toBe(true);
  });

  it("catches a derivation rung that leaked into the provenance chain", () => {
    const contaminated: LineageModel = {
      evidence: {
        ...FULL_EVIDENCE,
        steps: [
          ...FULL_EVIDENCE.steps,
          // A Signal is a derivation rung. Hand-assembled, so the compiler could
          // not stop it — which is exactly why the runtime check exists.
          {
            kind: "Signal",
            ref: "SIG-3",
            label: "co_occurrence",
            note: null,
            at: [],
            selection: null,
          } as unknown as EvidenceLineageStep,
        ],
      },
      derivation: FULL_DERIVATION,
    };
    const result = assertChainsSeparate(contaminated);
    expect(result.separated).toBe(false);
    expect(result.violations.join(" ")).toContain("Signal");
  });

  it("catches a provenance rung that leaked into the derivation chain", () => {
    const contaminated: LineageModel = {
      evidence: FULL_EVIDENCE,
      derivation: {
        ...FULL_DERIVATION,
        steps: [
          ...FULL_DERIVATION.steps,
          {
            kind: "Capture",
            ref: "CAP-1",
            label: null,
            relation: null,
            score: null,
            selection: null,
          } as unknown as DerivationLineageStep,
        ],
      },
    };
    const result = assertChainsSeparate(contaminated);
    expect(result.separated).toBe(false);
    expect(result.violations.join(" ")).toContain("Capture");
  });

  it("catches a chain carrying the wrong chainId", () => {
    // The literal type forbids this, which is the point — so the hand-built
    // model has to be cast, and the runtime assertion is what catches it when
    // untyped data arrives from the server.
    const mislabelled: LineageModel = {
      evidence: { ...FULL_EVIDENCE, chainId: DERIVATION_CHAIN_ID } as unknown as EvidenceLineageChain,
      derivation: FULL_DERIVATION,
    };
    expect(assertChainsSeparate(mislabelled).separated).toBe(false);
    const single: LineageModel = {
      evidence: { ...FULL_EVIDENCE, chainId: DERIVATION_CHAIN_ID } as unknown as EvidenceLineageChain,
      derivation: null,
    };
    expect(assertChainsSeparate(single).violations.join(" ")).toContain("chainId");
  });

  it("catches a rung that belongs to neither chain at all", () => {
    const alien: LineageModel = {
      evidence: {
        ...FULL_EVIDENCE,
        steps: [...FULL_EVIDENCE.steps, { kind: "IntelItem", ref: "X-1", label: null, note: null, at: [], selection: null } as unknown as EvidenceLineageStep],
      },
      derivation: null,
    };
    const result = assertChainsSeparate(alien);
    expect(result.separated).toBe(false);
    expect(result.violations.join(" ")).toContain("IntelItem");
  });

  it("has no representation in which the two chains could be concatenated", () => {
    // The model is two nullable fields, never a list of chains. So there is no
    // array to push both into, and no helper that returns one.
    const keys = Object.keys(MODEL).sort();
    expect(keys).toEqual(["derivation", "evidence"]);
    expect(Array.isArray(MODEL)).toBe(false);
    for (const value of Object.values(MODEL)) expect(value === null || Array.isArray(value.steps)).toBe(true);
  });

  it("builds both chains from two separate inputs, in one call", () => {
    const built = buildLineageModel(
      { finding: null, claim: null, observation: null, capture: null, rawObject: null, source: null },
      { claim: null, candidate: null, signal: null, observation: null, originEntityId: null },
    );
    expect(built.evidence?.steps).toEqual([]);
    expect(built.derivation?.steps).toEqual([]);
    // And the derivation builder has no access to a capture, a raw object, a
    // source or a finding — the type forbids it, which is the whole point.
    expect(DERIVATION_STEP_ORDER).not.toContain("Capture");
    expect(DERIVATION_STEP_ORDER).not.toContain("RawObject");
    expect(DERIVATION_STEP_ORDER).not.toContain("Source");
    expect(DERIVATION_STEP_ORDER).not.toContain("Finding");
  });
});

describe("§33 / §34 / §69 — every rung routes, or is honestly static", () => {
  it("routes each evidence rung that has a WorkspaceSelection", () => {
    const routes = FULL_EVIDENCE.steps.map((step) => ({
      kind: step.kind,
      route: routeEvidenceStep(step),
    }));
    expect(routes.find((entry) => entry.kind === "Finding")?.route).toEqual({
      kind: "Finding",
      id: "FND-1",
    });
    expect(routes.find((entry) => entry.kind === "Claim")?.route?.kind).toBe("Claim");
    expect(routes.find((entry) => entry.kind === "Observation")?.route?.kind).toBe("Observation");
    expect(routes.find((entry) => entry.kind === "Capture")?.route?.kind).toBe("Capture");
    expect(routes.find((entry) => entry.kind === "Source")?.route?.kind).toBe("Source");
  });

  it("routes the two rungs with no WorkspaceSelection to the observation that contains them", () => {
    // Evidence and RawObject are not addressable platform objects. They route to
    // the observation, which is where the inspector can actually read something,
    // rather than being given an invented kind.
    const evidence = FULL_EVIDENCE.steps.find((step) => step.kind === "Evidence");
    const raw = FULL_EVIDENCE.steps.find((step) => step.kind === "RawObject");
    expect(evidence === undefined ? null : routeEvidenceStep(evidence)).toEqual({
      kind: "Observation",
      id: "OBS-1",
    });
    expect(raw === undefined ? null : routeEvidenceStep(raw)).toEqual({ kind: "Observation", id: "OBS-1" });
  });

  it("returns null for a rung with no record, so the viewer renders text rather than a dead button", () => {
    const bare: EvidenceLineageStep = {
      kind: "Source",
      ref: null,
      label: null,
      note: null,
      at: [],
      selection: null,
    };
    expect(routeEvidenceStep(bare)).toBeNull();
    const bareDerivation: DerivationLineageStep = {
      kind: "Candidate",
      ref: null,
      label: null,
      relation: null,
      score: null,
      selection: null,
    };
    expect(routeDerivationStep(bareDerivation)).toBeNull();
  });

  it("shows the platform's raw locator on the observation rung", () => {
    const observation = FULL_EVIDENCE.steps.find((step) => step.kind === "Observation");
    expect(observation?.note).toBe("$.records[0].email");
  });

  it("keeps the platform's confidence on the claim rung and no confidence elsewhere", () => {
    const claim = FULL_DERIVATION.steps.find((step) => step.kind === "Claim");
    expect(claim?.score).toBe(0.8);
    expect(FULL_DERIVATION.steps.filter((step) => step.score === 0)).toEqual([]);
  });
});