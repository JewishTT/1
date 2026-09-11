/**
 * COGNITIVE Control-Plane API client (T024, T050–T068).
 *
 * Typed wrappers around the FastAPI REST surface mounted at /api/v1/.
 * Every function returns the raw JSON payload; adaptation to UI shapes
 * happens in the container components.
 */

/* eslint-disable @typescript-eslint/no-explicit-any */

const API_BASE = "/api/v1";

// ── Core async helper ────────────────────────────────────────────

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ── Shared types ─────────────────────────────────────────────────

export type ReviewDecision = "ACCEPT" | "REJECT" | "UNCERTAIN";
export type ReviewTargetType = "candidate" | "assertion" | "correlation_edge" | "finding";

export interface SearchResult {
  doc_id: string;
  score: number;
  backends: string[];
  observation_ids: string[];
  evidence: Array<{
    backend: string;
    kind: string;
    observation: { observation_id: string; uri: string; immutable: boolean } | null;
    source_id: string | null;
    reason: string;
  }>;
}

export interface SearchResponse {
  query: string;
  mode: string;
  tenant_id: string;
  results: SearchResult[];
}

export interface Correlation {
  edge_id: string;
  candidate_a: string;
  candidate_b: string;
  kind: string;
  raw_pair_score: number;
  collective_score: number;
  reasons: string[];
  state: string;
}

export interface EntityView {
  entity_id: string;
  canonical_identity: Record<string, string>;
  current_state: Record<string, unknown>;
  historical_versions: Array<Record<string, unknown>>;
  aliases: string[];
  relationships: Array<Record<string, string>>;
  supporting_assertions: string[];
  evidence: Array<{ evidence_id: string; observation_id: string; immutable: boolean }>;
  timeline: Array<{ observation_id: string; uri: string; immutable: boolean }>;
  structural_signals: Array<Record<string, unknown>>;
  correlations?: Correlation[];
  map_points?: Array<{ lat: number; lon: number; label?: string }>;
}

export interface FindingView {
  finding_id: string;
  status: string;
  why_detected: string;
  structural_evidence: Array<Record<string, unknown>>;
  semantic_evidence: Array<Record<string, unknown>>;
  supporting_graph_region: Record<string, unknown>;
  supporting_assertions: string[];
  observations: Array<{ observation_id: string; uri: string; immutable: boolean }>;
  sources: string[];
  evidence_resolves: boolean;
}

export type LineageKind =
  "finding" | "feature" | "assertion" | "evidence" | "observation" | "source";

export interface LineageNode {
  id: string;
  kind: LineageKind;
  label: string;
}

export interface InvestigationView {
  investigation_id: string;
  name: string;
  tenant_id: string;
  objective: Record<string, unknown>;
  seeds: string[];
  scope: Record<string, unknown>;
  policy_id: string | null;
  state: string;
  created_at: string;
}

export interface WorkerPoolStatus {
  healthy: boolean;
  active: number;
  capacity: number;
  failures: number;
}

export interface ReviewRecord {
  review_id: string;
  target_type: string;
  target_id: string;
  decision: string;
  analyst_id: string;
  reasoning: string;
  reviewed_at: string;
  tenant_id: string;
  provenance: Record<string, unknown>;
  replayed: boolean;
}

/** Resolution queue pair record (feature 005 US2/US6 — control-plane resolutions route). */
export interface ResolutionPair {
  pair_key: string;
  review_id: string;
  decision: string;
  reviewer_id: string;
  reviewed_at: string;
  reasoning: string;
}

export interface OpsMetrics {
  throughput_per_s: number;
  useful_observations: number;
  discovery_yield: number;
  duplicate_ratio: number;
  browser_utilization: number;
  lags_s: Record<string, number>;
  queues: Record<string, number>;
  storage_growth_b: Record<string, number>;
  cost_per_1m_obs: number;
  pools?: Record<string, WorkerPoolStatus>;
}

/** Connector registry (T026, FR-008) — SpiderFoot-style source connectors. */
export interface Connector {
  connector_id: string;
  name: string;
  tenant_id: string;
  source_types: string[];
  capabilities: Record<string, unknown>;
  policy_id: string;
  version: string;
  status: "REGISTERED" | "ACTIVE" | "DISABLED";
  contract_compliant: boolean;
}

/** Recon plan (T026, FR-009) — reNgine-style recon orchestration. */
export interface ReconPlan {
  plan_id: string;
  investigation_id: string;
  tenant_id: string;
  strategy: Record<string, unknown>;
  task_ids: string[];
  status: "PLANNED" | "RUNNING" | "COMPLETED" | "FAILED";
  started_at: string;
  finished_at: string;
}

/** Quarantined message record (T065, FR-023). */
export interface QuarantineRecord {
  record_id: string;
  reason: string;
  topic: string;
  partition: number;
  preserved: boolean;
  fingerprint: string;
}

export interface ReplayResponse {
  record_id: string;
  base64_payload: string;
  replayed_from_quarantine: boolean;
}

// ── Endpoints ────────────────────────────────────────────────────

export const api = {
  /** Search (T051, US2) — hybrid query with optional source/investigation filters. */
  search(
    query: string,
    options?: {
      mode?: "lexical" | "semantic" | "hybrid";
      source_ids?: string;
      investigation_id?: string;
      limit?: number;
    },
  ): Promise<SearchResponse> {
    const params = new URLSearchParams({ q: query });
    if (options?.mode) params.set("mode", options.mode);
    if (options?.source_ids) params.set("source_ids", options.source_ids);
    if (options?.investigation_id) params.set("investigation_id", options.investigation_id);
    if (options?.limit) params.set("limit", String(options.limit));
    return request<SearchResponse>(`/search?${params.toString()}`);
  },

  /** Entity detail (T052, US2). */
  getEntity(entityId: string): Promise<EntityView & { tenant_id: string }> {
    return request<EntityView & { tenant_id: string }>(`/entities/${encodeURIComponent(entityId)}`);
  },

  /** Correlation edges for an entity (T020, FR-004) — no merge implied. */
  getCorrelations(entityId: string): Promise<{ entity_id: string; correlations: Correlation[] }> {
    return request<{ entity_id: string; correlations: Correlation[] }>(
      `/entities/${encodeURIComponent(entityId)}/correlations`,
    );
  },

  /** Submit analyst review (FR-006, Vitni pattern). */
  submitReview(
    targetId: string,
    decision: ReviewDecision,
    targetType: ReviewTargetType,
    reasoning = "",
  ): Promise<{ review: ReviewRecord; event: string }> {
    return request<{ review: ReviewRecord; event: string }>(
      `/entities/${encodeURIComponent(targetId)}/review`,
      {
        method: "POST",
        body: JSON.stringify({ decision, reasoning, target_type: targetType }),
      },
    );
  },

  /** List analyst reviews for a target. */
  listReviews(targetId: string): Promise<{ target_id: string; reviews: ReviewRecord[] }> {
    return request<{ target_id: string; reviews: ReviewRecord[] }>(
      `/entities/${encodeURIComponent(targetId)}/reviews`,
    );
  },

  /** Resolution review queue for an investigation (feature 005 US6). */
  listResolutions(investigationId: string): Promise<{
    investigation_id: string;
    tenant_id: string;
    pairs: ResolutionPair[];
  }> {
    return request<{
      investigation_id: string;
      tenant_id: string;
      pairs: ResolutionPair[];
    }>(`/investigations/${encodeURIComponent(investigationId)}/resolutions`);
  },

  /** Record an analyst decision on one candidate pair (append-only, US6). */
  decideResolution(
    investigationId: string,
    pairKey: string,
    decision: ReviewDecision,
    reasoning = "",
  ): Promise<{
    investigation_id: string;
    pair_key: string;
    review: ReviewRecord;
    candidate_state: string;
    event: string;
  }> {
    return request<{
      investigation_id: string;
      pair_key: string;
      review: ReviewRecord;
      candidate_state: string;
      event: string;
    }>(`/investigations/${encodeURIComponent(investigationId)}/resolutions/decide`, {
      method: "POST",
      body: JSON.stringify({ pair_key: pairKey, decision, reasoning }),
    });
  },

  /** Finding detail (T053, US2). */
  getFinding(findingId: string): Promise<FindingView & { tenant_id: string }> {
    return request<FindingView & { tenant_id: string }>(
      `/findings/${encodeURIComponent(findingId)}`,
    );
  },

  /** Finding lineage chain (FR-032). */
  findingLineage(findingId: string): Promise<{ finding_id: string; chain: LineageNode[] }> {
    return request<{ finding_id: string; chain: Array<{ kind: string; label: string }> }>(
      `/findings/${encodeURIComponent(findingId)}/lineage`,
    ).then((res) => ({
      finding_id: res.finding_id,
      chain: res.chain.map((node) => ({
        id: node.label,
        kind: node.kind as LineageKind,
        label: node.label,
      })),
    }));
  },

  /** List investigations (FR-003). */
  listInvestigations(): Promise<{ investigations: InvestigationView[] }> {
    return request<{ investigations: InvestigationView[] }>("/investigations");
  },

  /** Single investigation (FR-003). */
  getInvestigation(investigationId: string): Promise<InvestigationView> {
    return request<InvestigationView>(`/investigations/${encodeURIComponent(investigationId)}`);
  },

  /** Create investigation (FR-003). */
  createInvestigation(body: {
    name: string;
    objective?: Record<string, unknown>;
    seeds?: string[];
    scope?: Record<string, unknown>;
    policy_id?: string | null;
  }): Promise<{
    investigation_id: string;
    name: string;
    state: string;
    event: string;
    tenant_id: string;
  }> {
    return request<{
      investigation_id: string;
      name: string;
      state: string;
      event: string;
      tenant_id: string;
    }>("/investigations", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** Pause investigation (FR-003 state machine). */
  pauseInvestigation(investigationId: string): Promise<InvestigationView> {
    return request<InvestigationView>(
      `/investigations/${encodeURIComponent(investigationId)}/pause`,
      { method: "POST" },
    );
  },

  /** Resume investigation (FR-003 state machine). */
  resumeInvestigation(investigationId: string): Promise<InvestigationView> {
    return request<InvestigationView>(
      `/investigations/${encodeURIComponent(investigationId)}/resume`,
      { method: "POST" },
    );
  },

  /** Complete investigation (FR-003 state machine). */
  completeInvestigation(investigationId: string): Promise<InvestigationView> {
    return request<InvestigationView>(
      `/investigations/${encodeURIComponent(investigationId)}/complete`,
      { method: "POST" },
    );
  },

  /** Archive investigation (FR-003 state machine). */
  archiveInvestigation(investigationId: string): Promise<InvestigationView> {
    return request<InvestigationView>(
      `/investigations/${encodeURIComponent(investigationId)}/archive`,
      { method: "POST" },
    );
  },

  /** Update investigation (PATCH — objective/scope/policy_id). */
  updateInvestigation(
    investigationId: string,
    body: {
      objective?: Record<string, unknown>;
      scope?: Record<string, unknown>;
      policy_id?: string | null;
    },
  ): Promise<InvestigationView> {
    return request<InvestigationView>(`/investigations/${encodeURIComponent(investigationId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },

  /** Operational metrics (T068, US3). */
  getOpsMetrics(): Promise<OpsMetrics> {
    return request<OpsMetrics>("/metrics");
  },

  /** Worker-pool health + capacity (T068, US3). */
  getWorkerPools(): Promise<{ pools: Record<string, WorkerPoolStatus>; healthy: string[] }> {
    return request<{ pools: Record<string, WorkerPoolStatus>; healthy: string[] }>(
      "/metrics/pools",
    );
  },

  // ── Connectors & recon plans (T026, FR-008/FR-009) ──────────────

  /** List registered connectors for the tenant. */
  listConnectors(): Promise<{ connectors: Connector[] }> {
    return request<{ connectors: Connector[] }>("/connectors");
  },

  /** List recon plans for the tenant (FR-009). */
  listReconPlans(): Promise<{ plans: ReconPlan[] }> {
    return request<{ plans: ReconPlan[] }>("/connectors/recon-plans");
  },

  /** Register a new connector (fails 409 on duplicate name). */
  registerConnector(body: {
    name: string;
    source_types?: string[];
    policy_id?: string;
    version?: string;
  }): Promise<{ connector: Connector; event: string }> {
    return request<{ connector: Connector; event: string }>("/connectors/register", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** Activate a registered connector (gated on AcquisitionWorker compliance). */
  activateConnector(name: string): Promise<{ connector: Connector; event: string }> {
    return request<{ connector: Connector; event: string }>(
      `/connectors/${encodeURIComponent(name)}/activate`,
      { method: "POST" },
    );
  },

  /** Create a recon plan against a connector for an investigation (FR-009). */
  createReconPlan(
    connectorName: string,
    body: { investigation_id: string; strategy?: Record<string, unknown> },
  ): Promise<{ plan: ReconPlan; event: string }> {
    return request<{ plan: ReconPlan; event: string }>(
      `/connectors/${encodeURIComponent(connectorName)}/recon-plans`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  // ── Quarantine / DLQ (T065, FR-023) ─────────────────────────────

  /** List preserved dead-letter records (optional topic filter). */
  listQuarantine(topic?: string): Promise<{ tenant_id: string; records: QuarantineRecord[] }> {
    const params = topic ? `?topic=${encodeURIComponent(topic)}` : "";
    return request<{ tenant_id: string; records: QuarantineRecord[] }>(`/dlq${params}`);
  },

  /** Fetch one quarantined record (base64 payload available on replay responses). */
  getQuarantined(recordId: string): Promise<ReplayResponse> {
    return request<ReplayResponse>(`/dlq/${encodeURIComponent(recordId)}`);
  },

  /** Replay a quarantined message back into the pipeline (payload byte-for-byte). */
  replayQuarantined(recordId: string): Promise<ReplayResponse> {
    return request<ReplayResponse>(`/dlq/${encodeURIComponent(recordId)}/replay`, {
      method: "POST",
    });
  },

  /** Re-evaluate a quarantined record (rejects malformed, accepts otherwise). */
  reEvaluateQuarantined(
    recordId: string,
  ): Promise<{ record_id: string; re_evaluated: "rejected" | "accepted"; tenant_id: string }> {
    return request<{ record_id: string; re_evaluated: "rejected" | "accepted"; tenant_id: string }>(
      `/dlq/${encodeURIComponent(recordId)}/re-evaluate`,
      { method: "POST" },
    );
  },
};

/**
 * Combined ops-metrics fetch: merges /metrics and /metrics/pools into a single
 * payload for the Operations dashboard.
 */
export async function fetchOpsMetrics(): Promise<OpsMetrics> {
  const [metrics, pools] = await Promise.all([api.getOpsMetrics(), api.getWorkerPools()]);
  return { ...metrics, pools: pools.pools };
}

export { scienceApi } from "./science/api";
