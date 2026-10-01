import type { FindingView } from "../lib/api";
import type { ClaimRecord, ObservationRecord } from "../workspace/inspector/types";
import {
  DERIVATION_CHAIN_ID,
  DERIVATION_STEP_ORDER,
  EVIDENCE_CHAIN_ID,
  EVIDENCE_STEP_ORDER,
  type DerivationLineageChain,
  type DerivationLineageStep,
  type DerivationStepKind,
  type EvidenceLineageChain,
  type EvidenceLineageStep,
  type EvidenceStepKind,
  type LineageModel,
} from "./lineage";

/**
 * Building the two chains from what the platform reports (§31, §32, §99).
 *
 * The two builders are SEPARATE FUNCTIONS with separate inputs. That is the
 * second half of the separation: not only can the two chains not be merged, but
 * they cannot be *derived* from one another. A derivation chain needs the
 * assertion/candidate trail, which is not part of a provenance walk, so asking
 * for both from one input would be asking for a model the platform does not
 * have.
 *
 * A rung with no record is OMITTED from `steps` and reported in `missingRungs`.
 * It is never rendered as an empty box, and never filled in by guessing what
 * the missing record would have said.
 */

export interface EvidenceChainInput {
  finding: FindingView | null;
  claim: ClaimRecord | null;
  observation: ObservationRecord | null;
  /** The capture the observation was extracted from, when loaded. */
  capture: { capture_id: string; target_uri: string | null; content_digest: string | null } | null;
  /** The raw stored payload for the capture, when loaded. */
  rawObject: { ref: string; digest: string | null; bytes: number | null } | null;
  source: { source_id: string; name: string | null; kind: string | null } | null;
}

/**
 * Evidence lineage: Finding → Claim → Evidence → Observation → Capture →
 * Raw object → Source.
 *
 * Built from `EvidenceChainInput`, walked in the fixed rung order. Each rung
 * contributes AT MOST ONE step, because this is a provenance spine, not a
 * fan-out — the multi-valued rungs (a claim's many observations) belong in the
 * derivation chain or in the evidence list, and flattening them into the spine
 * would misrepresent the structure.
 */
export function buildEvidenceChain(input: EvidenceChainInput): EvidenceLineageChain {
  const steps: EvidenceLineageStep[] = [];
  const missing: EvidenceStepKind[] = [];

  const add = (kind: EvidenceStepKind, step: EvidenceLineageStep | null): void => {
    if (step === null) {
      missing.push(kind);
      return;
    }
    steps.push({ ...step, kind });
  };

  add(
    "Finding",
    input.finding === null
      ? null
      : {
          kind: "Finding",
          ref: input.finding.finding_id,
          label: input.finding.finding_id,
          note: input.finding.why_detected,
          at: [],
          selection: { kind: "Finding", id: input.finding.finding_id },
        },
  );

  add(
    "Claim",
    input.claim === null
      ? null
      : {
          kind: "Claim",
          ref: input.claim.relation_id,
          label: input.claim.relation_type,
          note: input.claim.evidence_grade,
          at: compact([input.claim.observed_at, input.claim.published_at, input.claim.valid_from]),
          selection: { kind: "Claim", id: input.claim.relation_id },
        },
  );

  // The evidence rung is the platform's evidence-record id. It has no
  // `WorkspaceObjectKind`, so it routes to the observation it contains.
  const evidenceId = input.observation?.record_digest ?? input.finding?.structural_evidence?.[0]?.["evidence_id"];
  add(
    "Evidence",
    typeof evidenceId === "string" && evidenceId !== ""
      ? {
          kind: "Evidence",
          ref: evidenceId,
          label: typeof evidenceId === "string" ? evidenceId.slice(0, 16) : null,
          note: input.observation?.content_type ?? null,
          at: compact([input.observation?.collected_at]),
          selection:
            input.observation === null
              ? null
              : { kind: "Observation", id: input.observation.observation_id },
        }
      : null,
  );

  add(
    "Observation",
    input.observation === null
      ? null
      : {
          kind: "Observation",
          ref: input.observation.observation_id,
          label: input.observation.uri,
          note: input.observation.locator,
          at: compact([input.observation.collected_at]),
          selection: { kind: "Observation", id: input.observation.observation_id },
        },
  );

  add(
    "Capture",
    input.capture === null
      ? null
      : {
          kind: "Capture",
          ref: input.capture.capture_id,
          label: input.capture.target_uri,
          note: input.capture.content_digest,
          at: [],
          selection: { kind: "Capture", id: input.capture.capture_id },
        },
  );

  add(
    "RawObject",
    input.rawObject === null
      ? null
      : {
          kind: "RawObject",
          ref: input.rawObject.ref,
          label: input.rawObject.digest,
          note: input.rawObject.bytes === null ? null : `${input.rawObject.bytes} bytes`,
          at: [],
          selection:
            input.observation === null
              ? null
              : { kind: "Observation", id: input.observation.observation_id },
        },
  );

  add(
    "Source",
    input.source === null
      ? null
      : {
          kind: "Source",
          ref: input.source.source_id,
          label: input.source.name,
          note: input.source.kind,
          at: [],
          selection: { kind: "Source", id: input.source.source_id },
        },
  );

  return {
    chainId: EVIDENCE_CHAIN_ID,
    steps: sortEvidenceSteps(steps),
    missingRungs: EVIDENCE_STEP_ORDER.filter((kind) => missing.includes(kind)),
  };
}

export interface DerivationChainInput {
  claim: ClaimRecord | null;
  /** The unmaterialised candidate the claim was derived from. */
  candidate: { ref: string; score: number | null; reasons: ReadonlyArray<string> } | null;
  /** The structural or semantic signal that fired on the candidate. */
  signal: { ref: string; name: string; score: number | null } | null;
  observation: ObservationRecord | null;
  /** The entity whose neighbourhood the candidate belongs to. */
  originEntityId: string | null;
}

/**
 * Derivation lineage: Claim → Candidate → Signal → Observation.
 *
 * Four rungs, read in the order the claim was ARRIVED AT — which is the reverse
 * of how provenance reads. The viewer renders this chain bottom-up with its own
 * direction arrow, precisely so it cannot be mistaken for a continuation of the
 * provenance spine.
 */
export function buildDerivationChain(input: DerivationChainInput): DerivationLineageChain {
  const steps: DerivationLineageStep[] = [];
  const missing: DerivationStepKind[] = [];

  const add = (kind: DerivationStepKind, step: DerivationLineageStep | null): void => {
    if (step === null) {
      missing.push(kind);
      return;
    }
    steps.push({ ...step, kind });
  };

  add(
    "Claim",
    input.claim === null
      ? null
      : {
          kind: "Claim",
          ref: input.claim.relation_id,
          label: input.claim.relation_type,
          relation: `${input.claim.subject_ref} → ${input.claim.object_ref}`,
          score: input.claim.confidence,
          selection: { kind: "Claim", id: input.claim.relation_id },
        },
  );

  add(
    "Candidate",
    input.candidate === null
      ? null
      : {
          kind: "Candidate",
          ref: input.candidate.ref,
          label: input.candidate.reasons.join(", ") || "not reported",
          relation: "derived from",
          score: input.candidate.score,
          // A candidate is not an addressable object. It routes to the entity
          // whose neighbourhood produced it — the only place the platform can
          // say anything about it.
          selection:
            input.originEntityId === null ? null : { kind: "Entity", id: input.originEntityId },
        },
  );

  add(
    "Signal",
    input.signal === null
      ? null
      : {
          kind: "Signal",
          ref: input.signal.ref,
          label: input.signal.name,
          relation: "fired on",
          score: input.signal.score,
          selection:
            input.originEntityId === null ? null : { kind: "Entity", id: input.originEntityId },
        },
  );

  add(
    "Observation",
    input.observation === null
      ? null
      : {
          kind: "Observation",
          ref: input.observation.observation_id,
          label: input.observation.uri,
          relation: "read",
          score: null,
          selection: { kind: "Observation", id: input.observation.observation_id },
        },
  );

  return {
    chainId: DERIVATION_CHAIN_ID,
    steps: sortDerivationSteps(steps),
    missingRungs: DERIVATION_STEP_ORDER.filter((kind) => missing.includes(kind)),
  };
}

function sortEvidenceSteps(steps: EvidenceLineageStep[]): EvidenceLineageStep[] {
  return [...steps].sort(
    (a, b) => EVIDENCE_STEP_ORDER.indexOf(a.kind) - EVIDENCE_STEP_ORDER.indexOf(b.kind),
  );
}

function sortDerivationSteps(steps: DerivationLineageStep[]): DerivationLineageStep[] {
  return [...steps].sort(
    (a, b) => DERIVATION_STEP_ORDER.indexOf(a.kind) - DERIVATION_STEP_ORDER.indexOf(b.kind),
  );
}

function compact(values: ReadonlyArray<string | null | undefined>): string[] {
  return values.filter((value): value is string => typeof value === "string" && value !== "");
}

/** Build both chains. Two calls, two inputs, no shared accumulator. */
export function buildLineageModel(
  evidenceInput: EvidenceChainInput,
  derivationInput: DerivationChainInput,
): LineageModel {
  return {
    evidence: buildEvidenceChain(evidenceInput),
    derivation: buildDerivationChain(derivationInput),
  };
}

/** Chain counts for the tab label, so the tab can say "2 of 7 rungs present". */
export function chainSummary(chain: EvidenceLineageChain | DerivationLineageChain | null): string {
  if (chain === null) return "no record";
  return `${chain.steps.length}/${chain.steps.length + chain.missingRungs.length} rungs`;
}