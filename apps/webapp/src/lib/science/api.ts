/** Scientific Intelligence Fabric — API client (T138, US7).

Thin wrappers over the ``/api/science`` REST surface (contracts/science-api.md).
Containers adapt these raw payloads into the page prop shapes in ``types.ts``.
*/

/* eslint-disable @typescript-eslint/no-explicit-any */

import type {
  CausalModelRecord,
  ClaimRecord,
  ClaimReviewView,
  CommunityResult,
  CoverageView,
  DiagramFeaturesResult,
  ExperimentRun,
  GraphEdgeInput,
  HypergraphResult,
  HypothesisRecord,
  InvariantParams,
  InvariantResult,
  NetworkMeasuresResult,
  PhodmsResult,
  RankedOpportunity,
  ReproductionResult,
  RobustnessReport,
  StructureAnalyzeResult,
  TemporalPathsResult,
} from "./types";

const SCIENCE_BASE = "/api/science";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${SCIENCE_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail ?? res.statusText),
    );
  }
  return res.json();
}

export interface RankedOpportunityDto {
  opportunity_id: string;
  expected_gain: number;
  discriminating_pair?: [string, string];
}

export const scienceApi = {
  // ── Claims + review (US1, US7) ────────────────────────────────
  listClaims(): Promise<{ claims: ClaimRecord[] }> {
    return request<{ claims: ClaimRecord[] }>("/claims");
  },

  getReview(claimId: string): Promise<ClaimReviewView> {
    return request<ClaimReviewView>(`/review/${encodeURIComponent(claimId)}`);
  },

  comment(claimId: string, actor: string, body: string): Promise<{ event_id: string }> {
    return request<{ event_id: string }>(`/review/${encodeURIComponent(claimId)}/comment`, {
      method: "POST",
      body: JSON.stringify({ actor, body }),
    });
  },

  changeStatus(
    claimId: string,
    actor: string,
    toStatus: string,
    comment?: string | null,
  ): Promise<{ event_id: string }> {
    return request<{ event_id: string }>(`/review/${encodeURIComponent(claimId)}/status`, {
      method: "POST",
      body: JSON.stringify({ actor, to_status: toStatus, comment }),
    });
  },

  // ── Robustness + experiments (US6) ────────────────────────────
  listRobustness(): Promise<{ reports: RobustnessReport[] }> {
    return request<{ reports: RobustnessReport[] }>("/robustness");
  },

  analyzeRobustness(body: {
    claim_id: string;
    evidence: Array<{ link_id: string; observation_id: string; direction: string; weight: number }>;
    missing_fraction?: number[];
    label_flip?: number[];
    biased_subsample?: number[];
  }): Promise<RobustnessReport> {
    return request<RobustnessReport>("/robustness", { method: "POST", body: JSON.stringify(body) });
  },

  recordExperiment(body: {
    input_refs: string[];
    output_refs: string[];
    seed: number;
    pipeline_version: string;
    dependency_freeze?: Record<string, string>;
    tolerance?: number;
  }): Promise<{ run_id: string; pipeline_version: string; tolerance: number }> {
    return request<{ run_id: string; pipeline_version: string; tolerance: number }>(
      "/experiments",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    );
  },

  listExperiments(): Promise<{ runs: ExperimentRun[] }> {
    return request<{ runs: ExperimentRun[] }>("/experiments");
  },

  reproduce(runId: string): Promise<ReproductionResult> {
    return request<ReproductionResult>("/experiments/reproduce", {
      method: "POST",
      body: JSON.stringify({ run_id: runId }),
    });
  },

  // ── Hypotheses (US2) ───────────────────────────────────────────
  listHypotheses(projectId?: string): Promise<{ hypotheses: HypothesisRecord[] }> {
    const params = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return request<{ hypotheses: HypothesisRecord[] }>(`/hypotheses${params}`);
  },

  proposeHypothesis(
    projectId: string,
    text: string,
  ): Promise<{ hypothesis_id: string; status: string }> {
    return request<{ hypothesis_id: string; status: string }>("/hypotheses", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, text }),
    });
  },

  attachEvidence(
    hypothesisId: string,
    body: {
      observation_id: string;
      direction: "supports" | "refutes";
      weight: number;
    },
  ): Promise<{ hypothesis_id: string; evidence_links: number }> {
    return request<{ hypothesis_id: string; evidence_links: number }>(
      `/hypotheses/${encodeURIComponent(hypothesisId)}/evidence`,
      {
        method: "POST",
        body: JSON.stringify({ hypothesis_id: hypothesisId, link_id: `L-${Date.now()}`, ...body }),
      },
    );
  },

  discardHypothesis(
    hypothesisId: string,
    actor: string,
    reason: string,
  ): Promise<{ hypothesis_id: string; status: string }> {
    return request<{ hypothesis_id: string; status: string }>(
      `/hypotheses/${encodeURIComponent(hypothesisId)}/discard`,
      { method: "POST", body: JSON.stringify({ hypothesis_id: hypothesisId, actor, reason }) },
    );
  },

  planCollection(
    projectId: string,
    opportunities: Array<{
      opportunity_id: string;
      description: string;
      likelihoods: Record<string, number>;
    }>,
  ): Promise<{
    project_id: string;
    plan: RankedOpportunityDto[];
  }> {
    return request<{ project_id: string; plan: RankedOpportunityDto[] }>("/hypotheses/plan", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, opportunities }),
    });
  },

  coverage(projectId: string): Promise<CoverageView> {
    return request<CoverageView>(
      `/hypotheses/coverage?project_id=${encodeURIComponent(projectId)}`,
    );
  },

  // ── Topological invariant (011/FR-009) ─────────────────────────
  invariant(body: InvariantParams): Promise<InvariantResult> {
    return request<InvariantResult>("/invariant", { method: "POST", body: JSON.stringify(body) });
  },

  // ── Structure (network graph analysis — science_structure) ─────
  structureAnalyze(body: {
    graph_ref: string;
    edges: GraphEdgeInput[];
    kind?: "spectral" | "motif";
    max_ops?: number;
    max_permutations?: number;
    n_permutations?: number;
    seed?: number;
  }): Promise<StructureAnalyzeResult> {
    return request<StructureAnalyzeResult>("/structure/analyze", { method: "POST", body: JSON.stringify(body) });
  },

  structureResult(resultId: string): Promise<StructureAnalyzeResult> {
    return request<StructureAnalyzeResult>(`/structure/results/${encodeURIComponent(resultId)}`);
  },

  // ── Temporal (change-point science — science_temporal) ─────────
  temporalBuildSeries(
    variable: string,
    samples: Array<{ time: string; value: number }>,
  ): Promise<{ series_id: string; variable: string; values: number[]; timestamps: string[]; change_points: number[] }> {
    return request<any>("/temporal/series", {
      method: "POST",
      body: JSON.stringify({ variable, samples }),
    });
  },

  temporalChangePoints(
    seriesId: string,
    window = 5,
    minShift = 1.0,
  ): Promise<{ series_id: string; variable: string; values: number[]; timestamps: string[]; change_points: number[] }> {
    return request<any>("/temporal/change-points", {
      method: "POST",
      body: JSON.stringify({ series_id: seriesId, window, min_shift: minShift }),
    });
  },

  temporalSeries(seriesId: string): Promise<{ series_id: string; values: number[]; timestamps: string[]; change_points: number[] }> {
    return request<any>(`/temporal/series/${encodeURIComponent(seriesId)}`);
  },

  // ── Causal DAGs (science_causal) ────────────────────────────────
  causalClassify(body: {
    outcome_attribute: string;
    evidence?: Array<Record<string, unknown>>;
    model_id?: string | null;
    possible_confounders?: string[];
  }): Promise<Record<string, unknown>> {
    return request<Record<string, unknown>>("/causal/classify", { method: "POST", body: JSON.stringify(body) });
  },

  causalRegisterModel(body: {
    model_id: string;
    graph: Record<string, string[]>;
    confounders?: string[];
    assumptions?: string[];
    scope_decl?: string[];
  }): Promise<{ model_id: string; scope_decl: string[] }> {
    return request<{ model_id: string; scope_decl: string[] }>("/causal/models", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  causalListModels(): Promise<{ models: Array<{ model_id: string; scope_decl: string[] }> }> {
    return request<{ models: Array<{ model_id: string; scope_decl: string[] }> }>("/causal/models");
  },

  causalModel(modelId: string): Promise<CausalModelRecord> {
    return request<CausalModelRecord>(`/causal/models/${encodeURIComponent(modelId)}`);
  },
};

const NETWORK_BASE = "/api/v1/network";

async function requestV1(path: string, init?: RequestInit): Promise<any> {
  const res = await fetch(`${NETWORK_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail ?? res.statusText),
    );
  }
  return res.json();
}

/** /api/v1/network — projection-plane network & TDA features surface. */
export const networkApi = {
  measures(edges: GraphEdgeInput[]): Promise<NetworkMeasuresResult> {
    return requestV1("/measures", { method: "POST", body: JSON.stringify({ edges }) });
  },

  communities(edges: GraphEdgeInput[]): Promise<CommunityResult> {
    return requestV1("/communities", { method: "POST", body: JSON.stringify({ edges }) });
  },

  hypergraph(observations: Record<string, string[]>, minDegree = 1): Promise<HypergraphResult> {
    return requestV1("/hypergraph", {
      method: "POST",
      body: JSON.stringify({ observations, min_degree: minDegree }),
    });
  },

  temporal(
    edges: Array<{ source: string; target: string; t: number; edge_id?: string }>,
    source?: string,
    target?: string,
  ): Promise<TemporalPathsResult> {
    return requestV1("/temporal", {
      method: "POST",
      body: JSON.stringify({ edges, source, target }),
    });
  },

  diagramFeatures(body: {
    entity_id: string;
    series: number[];
    lag?: number;
    embed_dim?: number;
    max_dim?: number;
    budget?: number;
    metric?: string;
    prev_diagrams?: Record<string, Array<[number, number | null]>>;
  }): Promise<DiagramFeaturesResult> {
    return requestV1("/diagram-features", { method: "POST", body: JSON.stringify(body) });
  },

  phodms(body: {
    clouds: number[][][];
    thresholds?: number[];
  }): Promise<PhodmsResult> {
    return requestV1("/phodms", { method: "POST", body: JSON.stringify(body) });
  },
};

export function toRankedOpportunities(dtos: RankedOpportunityDto[]): RankedOpportunity[] {
  return dtos.map((d) => ({
    opportunity_id: d.opportunity_id,
    expected_gain: d.expected_gain,
    discriminates: [],
  }));
}
