/** Scientific Intelligence Fabric — API client (T138, US7).

Thin wrappers over the ``/api/science`` REST surface (contracts/science-api.md).
Containers adapt these raw payloads into the page prop shapes in ``types.ts``.
*/

/* eslint-disable @typescript-eslint/no-explicit-any */

import type {
  ClaimRecord,
  ClaimReviewView,
  CoverageView,
  ExperimentRun,
  HypothesisRecord,
  InvariantParams,
  InvariantResult,
  RankedOpportunity,
  ReproductionResult,
  RobustnessReport,
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
};

export function toRankedOpportunities(dtos: RankedOpportunityDto[]): RankedOpportunity[] {
  return dtos.map((d) => ({
    opportunity_id: d.opportunity_id,
    expected_gain: d.expected_gain,
    discriminates: [],
  }));
}
