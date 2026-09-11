/** Scientific Intelligence Fabric — webapp types (T138, US7).

Mirrors the science-API payloads returned by ``apps/control-plane`` at
``/api/science`` (contracts/science-api.md). Kept intentionally separate from
``lib/api.ts`` (the ``/api/v1`` investigation surface) because the science
fabric carries its own prefix and record shapes.
*/

export interface CredenceDistribution {
  states: string[];
  labels: string[];
  probs: number[];
  method: string;
  calibration_ref?: string | null;
}

export interface EvidenceLink {
  link_id: string;
  observation_id: string;
  raw_sha256: string;
  direction: "supports" | "refutes" | "discriminates";
  weight: number;
}

export interface ClaimRecord {
  claim_id: string;
  project_id: string;
  statement: string;
  status: string;
  model_id: string;
  distribution?: CredenceDistribution;
  producer_run?: string | null;
}

export interface LadderGates {
  calibrated: boolean;
  null_model: boolean;
  robustness: boolean;
  reproduction: boolean;
}

export interface ReviewEvent {
  event_id: string;
  claim_id: string;
  actor: string;
  kind: "comment" | "status_change" | "ladder_change";
  body?: string | null;
  from_status?: string | null;
  to_status?: string | null;
  at: string;
}

export interface ClaimReviewView {
  claim_id: string;
  statement: string;
  status: string;
  model_id: string;
  distribution_ref?: string | null;
  gates: LadderGates;
  ladder_position: number | null;
  top_rung: number;
  review_state: "review_pending" | "in_review" | "confirmed";
  events: ReviewEvent[];
}

export interface RobustnessReport {
  report_id: string;
  claim_ref: string;
  perturbations: Array<{ family: string; levels: number[] }>;
  flip_rates: Record<string, number>;
  sensitivity_summary: Record<string, number>;
  noise_regions: Array<{ family: string; level: number; flipped: boolean; margin: number }>;
  downgraded_to_uncertain?: boolean;
}

export interface ExperimentRun {
  run_id: string;
  seed: number;
  pipeline_version: string;
  tolerance: number;
  reproductions: string[];
}

export interface ReproductionResult {
  run_id: string;
  reproduced: boolean;
  tolerance: number;
  mismatches: Array<Record<string, unknown>>;
}

export interface HypothesisRecord {
  hypothesis_id: string;
  project_id: string;
  text: string;
  status: string;
  evidence_count?: number;
  decisions: Array<{ actor: string; reason: string }>;
  gain_priority?: number | null;
}

export interface HypothesisWithCoverage extends HypothesisRecord {
  coverage?: { project_id: string; alive: number; covered: number; ratio: number } | null;
}

export interface RankedOpportunity {
  opportunity_id: string;
  description?: string;
  expected_gain: number;
  discriminates: Array<{ a: string; b: string }>;
}

export interface CoverageView {
  project_id: string;
  alive: number;
  covered: number;
  ratio: number;
}
