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

/** Topological invariant payloads (011/FR-009 — apps/control-plane science_tda). */

export interface InvariantEmbedding {
  lag: number;
  embed_dim: number;
  points: number[][];
}

export interface DimensionPersistenceStats {
  num_bars: number;
  mean_persistence: number;
  max_persistence: number;
  total_persistence: number;
}

export interface InvariantDrift {
  metric: string;
  changed: boolean;
  delta_max_persistence: number;
}

export interface InvariantResult {
  entity_id: string;
  provider: string;
  structural_only: boolean;
  series_len: number;
  embedding: InvariantEmbedding;
  diagrams: Record<string, Array<[number, number | null]>>;
  stats: Record<string, DimensionPersistenceStats>;
  digest: string;
  drift?: InvariantDrift;
}

export interface InvariantParams {
  entity_id: string;
  series: number[];
  lag?: number;
  embed_dim?: number;
  max_dim?: number;
  budget?: number;
  prev_diagram?: Record<string, Array<[number, number | null]>>;
}

// ── Network analytics (projection plane via /api/v1/network) ──────────────

export interface GraphEdgeInput {
  source: string;
  target: string;
  edge_type?: string;
  properties?: Record<string, unknown>;
}

export interface NetworkMeasuresResult {
  n_nodes: number;
  n_edges: number;
  density: number;
  avg_degree: number;
  max_degree: number;
  avg_clustering: number;
  transitivity: number;
  assortativity: number;
  degree_gini: number;
  power_law_alpha: number | null;
  power_law_x_min: number | null;
  avg_shortest_path: number;
  small_world_sigma: number | null;
  degree_distribution: Record<string, number>;
  degree_centrality: Record<string, number>;
  structural_only: boolean;
}

export interface CommunityResult {
  structural_only: boolean;
  n_nodes: number;
  n_edges: number;
  community_count: number;
  modularity_q: number;
  communities: Record<string, string[]>;
}

export interface HypergraphResult {
  num_nodes: number;
  num_edges: number;
  order: number;
  edge_sizes: Record<string, number>;
  hyperedge_sizes: Record<string, number>;
  degree_distribution: Record<string, number>;
  average_node_degree: number;
  incidence_density: number;
  connected_pairs: number;
  node_degrees: Record<string, number>;
  structural_only: boolean;
}

export interface TimedEdgeInput {
  source: string;
  target: string;
  t: number;
  edge_id?: string;
}

export interface TemporalPathsResult {
  structural_only: boolean;
  n_nodes: number;
  n_edges: number;
  nodes: string[];
  distance_matrix: Record<string, Record<string, number>>;
  motifs: { out_star: number; in_star: number; relay: number };
  timeline: Array<[number, string[]]>;
  reachable_from?: string[];
  journey?: [Array<{ source: string; target: string; t: number; edge_id: string }>, number];
}

export interface DiagramFeatureCell {
  bottleneck_amplitude: number;
  wasserstein_amplitude: number;
  entropy: number;
  landscapes: number[][];
  betti: number[];
}

export interface DiagramFeaturesResult {
  entity_id: string;
  provider: string;
  structural_only: boolean;
  series_len: number;
  diagrams: Record<string, Array<[number, number | null]>>;
  features: { structural_only: boolean; dimensions: Record<string, DiagramFeatureCell> };
  features_digest: string;
  drift?: Record<string, { metric: string; q: number; value: number; changed: boolean; prev_hash: string; cur_hash: string }>;
}

export interface PhodmsResult {
  structural_only: boolean;
  n_times: number;
  n_points: number;
  n_thresholds: number;
  betti_zero_surface: number[][][];
  rank_invariant: {
    s1: number; t1: number; t2: number; s2: number; t3: number; t4: number;
    dim: number; rank: number; verdict: string;
  };
}

export interface StructureAnalyzeResult {
  result_id: string;
  graph_ref: string;
  kind: string;
  statistic: number;
  observed: number;
  mean_null: number;
  std_null: number;
  z_score: number | null;
  p_value: number | null;
  significant: boolean;
  deferred: boolean;
  summary: Record<string, unknown>;
}

export interface CausalModelRecord {
  model_id: string;
  scope_decl: string[];
  graph?: Record<string, string[]>;
  confounders?: string[];
  assumptions?: string[];
}
