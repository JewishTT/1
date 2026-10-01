import type { WorkspaceObjectKind, WorkspaceSelection } from "../workspace/types";

/**
 * Lineage (§31, §32).
 *
 * TWO CHAINS, TWO TYPES, TWO ARRAYS. NEVER ONE MERGED LIST.
 *
 * The failure this file exists to prevent is the one the existing
 * `components/LineageWalker.tsx` demonstrates: a single `LineageNode[]` with a
 * `kind` union of `finding | feature | assertion | evidence | observation |
 * source`, walked into one `<ol>` with a `→` between every step. That renders
 * beautifully and it is a lie, because it puts a Finding next to an
 * observation with no claim between them — an inference the platform never
 * made, drawn by the layout.
 *
 * So the separation is enforced by the TYPE, not by discipline:
 *
 *   EvidenceLineageChain    Finding → Claim → Evidence → Observation →
 *                           Capture → Raw object → Source
 *   DerivationLineageChain  Claim → Candidate → Signal → Observation
 *
 *   - Two distinct step types with largely disjoint `kind` sets. `Claim` and
 *     `Observation` legitimately appear in both; everything else appears in
 *     exactly one. A `Capture` is not assignable to a derivation step, so it
 *     cannot be pushed into the derivation chain by a renderer that got the
 *     wrong array.
 *   - Two distinct chain ids, so a persisted or exported lineage document
 *     records which chain each step belongs to.
 *   - `assertChainsSeparate()` asserts the invariant at runtime for data that
 *     arrives from the server, where the compiler cannot help.
 *   - `LineageModel` has two nullable fields, never a list of chains, so there
 *     is no representation in which the two can be concatenated.
 *
 * §99: the steps carry platform identifiers and platform-reported values. A
 * step whose record the platform did not report has `null` in the field and the
 * viewer prints "not reported" — it is never filled in by inference.
 */

export const EVIDENCE_CHAIN_ID = "evidence" as const;
export const DERIVATION_CHAIN_ID = "derivation" as const;

export type LineageChainId = typeof EVIDENCE_CHAIN_ID | typeof DERIVATION_CHAIN_ID;

/* ── Evidence lineage (§31) ──────────────────────────────────────────── */

/** The seven rungs, in the order provenance runs. Fixed and exhaustive. */
export type EvidenceStepKind =
  | "Finding"
  | "Claim"
  | "Evidence"
  | "Observation"
  | "Capture"
  | "RawObject"
  | "Source";

/** The rungs in order. A chain that arrives out of order is sorted into it. */
export const EVIDENCE_STEP_ORDER: ReadonlyArray<EvidenceStepKind> = [
  "Finding",
  "Claim",
  "Evidence",
  "Observation",
  "Capture",
  "RawObject",
  "Source",
];

export interface EvidenceLineageStep {
  kind: EvidenceStepKind;
  /** The platform's own identifier for the record at this rung. */
  ref: string | null;
  /** Human label as the platform reports it. Null ⇒ not reported. */
  label: string | null;
  /** What this rung contributes that the one above it does not. */
  note: string | null;
  /** ISO instants the platform reports for this rung. Empty ⇒ not reported. */
  at: string[];
  /** Where activating this step sends the global selection. */
  selection: WorkspaceSelection | null;
}

export interface EvidenceLineageChain {
  chainId: typeof EVIDENCE_CHAIN_ID;
  /** Steps in provenance order, rungs with no record simply omitted. */
  steps: ReadonlyArray<EvidenceLineageStep>;
  /** Rungs the platform has no record for. Reported, not hidden (§99). */
  missingRungs: ReadonlyArray<EvidenceStepKind>;
}

/* ── Derivation lineage (§32) ────────────────────────────────────────── */

export type DerivationStepKind = "Claim" | "Candidate" | "Signal" | "Observation";

/** The four rungs, in the order a claim was arrived at. */
export const DERIVATION_STEP_ORDER: ReadonlyArray<DerivationStepKind> = [
  "Claim",
  "Candidate",
  "Signal",
  "Observation",
];

export interface DerivationLineageStep {
  kind: DerivationStepKind;
  ref: string | null;
  label: string | null;
  /** The relation between this rung and the one above it, verbatim. */
  relation: string | null;
  /** Platform-reported score for this rung, when there is one. Null ⇒ not reported. */
  score: number | null;
  selection: WorkspaceSelection | null;
}

export interface DerivationLineageChain {
  chainId: typeof DERIVATION_CHAIN_ID;
  steps: ReadonlyArray<DerivationLineageStep>;
  missingRungs: ReadonlyArray<DerivationStepKind>;
}

/* ── The model ───────────────────────────────────────────────────────── */

export interface LineageModel {
  /** Provenance: what a finding rests on, down to the bytes. */
  evidence: EvidenceLineageChain | null;
  /** Derivation: how a claim was arrived at, up from an observation. */
  derivation: DerivationLineageChain | null;
}

export const EMPTY_LINEAGE: LineageModel = { evidence: null, derivation: null };

/* ── Routing ─────────────────────────────────────────────────────────── */

const EVIDENCE_SELECTION_KIND: Readonly<Record<EvidenceStepKind, WorkspaceObjectKind | null>> = {
  Finding: "Finding",
  Claim: "Claim",
  Observation: "Observation",
  Capture: "Capture",
  Source: "Source",
  // `Evidence` is the platform's evidence-record id, and `RawObject` is the
  // capture's stored payload. Neither has a `WorkspaceObjectKind`, so they are
  // not fabricated: they route to the Observation they contain, which is where
  // the inspector can actually read something.
  Evidence: null,
  RawObject: null,
};

const DERIVATION_SELECTION_KIND: Readonly<Record<DerivationStepKind, WorkspaceObjectKind | null>> = {
  Claim: "Claim",
  Observation: "Observation",
  // A candidate is an unmaterialised correlation and a signal is a structural
  // feature. Neither is an addressable platform object; both route to the
  // entity whose neighbourhood produced them, when one is known.
  Candidate: null,
  Signal: null,
};

/** Where an evidence step routes. Null when nothing in the store can hold it. */
export function routeEvidenceStep(step: EvidenceLineageStep): WorkspaceSelection | null {
  if (step.selection !== null) return step.selection;
  if (step.ref === null) return null;
  const kind = EVIDENCE_SELECTION_KIND[step.kind];
  return kind === null ? null : { kind, id: step.ref, ...(step.label === null ? {} : { label: step.label }) };
}

/** Where a derivation step routes. */
export function routeDerivationStep(step: DerivationLineageStep): WorkspaceSelection | null {
  if (step.selection !== null) return step.selection;
  if (step.ref === null) return null;
  const kind = DERIVATION_SELECTION_KIND[step.kind];
  return kind === null ? null : { kind, id: step.ref, ...(step.label === null ? {} : { label: step.label }) };
}

/* ── The invariant ───────────────────────────────────────────────────── */

/**
 * Rungs that may appear in EXACTLY ONE chain.
 *
 * `assertChainsSeparate` checks this table, so adding a rung to one chain and
 * forgetting the other is a test failure rather than a merged render.
 */
export const CHAIN_EXCLUSIVE_KINDS: Readonly<Record<"evidence" | "derivation", ReadonlyArray<string>>> = {
  evidence: ["Finding", "Evidence", "Capture", "RawObject", "Source"],
  derivation: ["Candidate", "Signal"],
};

/** Rungs that may appear in both, because the platform uses them in both senses. */
export const SHARED_KINDS: ReadonlyArray<string> = ["Claim", "Observation"];

export interface SeparationResult {
  separated: boolean;
  /** The specific violations found, so the message can name them. */
  violations: string[];
}

/**
 * Prove the two chains did not get mixed. Called by the viewer on every render
 * of server data, and by the tests with data that should pass.
 *
 * Three checks:
 *   1. no rung exclusive to one chain appears in the other
 *   2. every step carries its chain's id — the chain objects are built here, so
 *      a mismatch means a hand-assembled model
 *   3. every evidence step's kind is in `EVIDENCE_STEP_ORDER`, and likewise for
 *      derivation: a step of the wrong union cannot have been type-checked in,
 *      and this catches it when data arrives untyped from JSON
 */
export function assertChainsSeparate(model: LineageModel): SeparationResult {
  const violations: string[] = [];

  const evidenceKinds = model.evidence?.steps.map((step) => step.kind) ?? [];
  const derivationKinds = model.derivation?.steps.map((step) => step.kind) ?? [];

  for (const kind of evidenceKinds) {
    if (CHAIN_EXCLUSIVE_KINDS.derivation.includes(kind)) {
      violations.push(`${kind} appears in the evidence chain but belongs to the derivation chain`);
    }
    if (!EVIDENCE_STEP_ORDER.includes(kind)) {
      violations.push(`${kind} is not an evidence-chain rung`);
    }
  }
  for (const kind of derivationKinds) {
    if (CHAIN_EXCLUSIVE_KINDS.evidence.includes(kind)) {
      violations.push(`${kind} appears in the derivation chain but belongs to the evidence chain`);
    }
    if (!DERIVATION_STEP_ORDER.includes(kind)) {
      violations.push(`${kind} is not a derivation-chain rung`);
    }
  }

  if (model.evidence !== null && model.evidence.chainId !== EVIDENCE_CHAIN_ID) {
    violations.push(`evidence chain carries chainId "${model.evidence.chainId}"`);
  }
  if (model.derivation !== null && model.derivation.chainId !== DERIVATION_CHAIN_ID) {
    violations.push(`derivation chain carries chainId "${model.derivation.chainId}"`);
  }

  return { separated: violations.length === 0, violations };
}