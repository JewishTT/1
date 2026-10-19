/**
 * COGNITIVE Control-Plane API client (T024, T050–T068).
 *
 * Typed wrappers around the FastAPI REST surface mounted at /api/v1/.
 * Every function returns the raw JSON payload; adaptation to UI shapes
 * happens in the container components.
 */

import { clientFor } from "./http";

const API_BASE = "/api/v1";

// ── Core async helper ────────────────────────────────────────────

// One shared implementation: four copies of this helper had drifted into three
// error contracts, and all four merged `headers` before `...init`, which silently
// dropped `Content-Type` whenever a caller passed its own headers. See lib/http.ts.
const request = clientFor(API_BASE);

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

/**
 * Atomic-entity invariant projection (backend services/catalog.py): the entity
 * id is the stable anchor while the asserted identity is carried forward across
 * versions. Rendered verbatim by the intel board and entity page.
 */
export interface IdentityInvariant {
  status: "MATERIALIZED" | string;
  continuity: "PERSISTENT" | string;
  version: number;
  history_depth: number;
  identity_digest: string;
  first_seen: string | null;
  last_seen: string | null;
}

export interface EntityView {
  entity_id: string;
  canonical_identity: Record<string, string>;
  current_state: Record<string, unknown>;
  identity_invariant?: IdentityInvariant;
  historical_versions: Array<Record<string, unknown>>;
  aliases: string[];
  relationships: Array<Record<string, string>>;
  supporting_assertions: string[];
  evidence: Array<{ evidence_id: string; observation_id: string; immutable: boolean }>;
  timeline: Array<{
    observation_id: string;
    uri: string;
    immutable: boolean;
    observed_at?: string;
  }>;
  structural_signals: Array<Record<string, unknown>>;
  correlations?: Correlation[];
  map_points?: Array<{ lat: number; lon: number; label?: string }>;
}

export interface TemporalWindowView {
  window_start: string;
  window_end: string;
  lifecycle: string;
  event_count: number;
  first_seen: string | null;
  last_seen: string | null;
  source_record_ids: string[];
  observation_refs: string[];
}

export interface TemporalHistoryView {
  tenant_id: string;
  entity_id: string;
  publication: {
    publication_id: string;
    source_cut: { cut_id: string; coverage_start: string; coverage_end: string };
    revisions: Array<{
      revision_id: string;
      revision_number: number;
      window: TemporalWindowView;
      window_fingerprint: string;
      source_cut_id: string;
    }>;
    integrity_fingerprint: string;
    projection_generation: number;
  };
  status?: string;
  is_latest_valid?: boolean;
}

export interface TemporalFeatureView {
  feature_name: string;
  value: string | number | null;
  available: boolean;
  structural_only: boolean;
  source_record_ids: string[];
  feature_fingerprint: string;
}

export interface TemporalMaterializationHealth {
  runs: Array<Record<string, unknown>>;
  tenant_id: string;
}

/** One normalized Common Crawl capture observation (L1 extract output). */
export interface CcTemporalityCapture {
  url: string;
  observed_at: string; // ISO-UTC
  status: number;
  digest: string;
}

/** Final payload of POST /entities/{id}/cc-temporality. */
export interface CcTemporalityPayload {
  entity_id: string;
  plan: {
    kind: string;
    url_query: string;
    match_type: string;
    surt_prefix: string | null;
    limit: number;
  } | null;
  captures: CcTemporalityCapture[];
  series: Array<{ t: string; count: number }>;
  metrics: { burstiness: number | null; events_per_day: number | null };
  notes: string[];
  tenant_id?: string;
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

// ── SpecOps (entity graph + Maltego-style tools) ───────────────────

/** One node in the SpecOps entity graph; entity_type is an uppercase label like "EMAIL". */
export interface SpecOpsGraphNode {
  id: string;
  label: string;
  entity_type: string;
  properties: Record<string, string>;
}

/** One edge in the SpecOps entity graph. */
export interface SpecOpsGraphEdge {
  id: string;
  source: string;
  target: string;
  kind: string;
}

/** GET /entities/graph payload — whole-graph projection, Maltego-style. */
export interface SpecOpsGraphResponse {
  nodes: SpecOpsGraphNode[];
  edges: SpecOpsGraphEdge[];
}

/** Registered Maltego-style tool available against entity types. */
export interface ToolSpec {
  tool_id: string;
  name: string;
  category: string;
  entity_types: string[];
  method: string;
  source: string;
  license: string;
  attribution: string;
  run_mode: string;
  command_template: string[];
  description: string;
}

/** Enqueued tool run (POST /tools/{tool_id}/enqueue). */
export interface ToolRun {
  tool_id: string;
  entity_type: string;
  entity_value: string;
  entity_id?: string;
  status: string;
  command: string[];
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
  getTemporalHistory(entityId: string): Promise<TemporalHistoryView> {
    return request<TemporalHistoryView>(
      `/entities/${encodeURIComponent(entityId)}/temporal-history/current`,
    );
  },

  getTemporalFeatures(
    entityId: string,
  ): Promise<{ features: TemporalFeatureView[]; source_cut: { cut_id: string } }> {
    return request(`/entities/${encodeURIComponent(entityId)}/temporal-features`);
  },

  getTemporalHealth(): Promise<TemporalMaterializationHealth> {
    return request<TemporalMaterializationHealth>("/temporal-materializations/health");
  },

  getEntityInvariant(
    entityId: string,
  ): Promise<{ entity_id: string; invariant: Record<string, unknown> }> {
    return request(`/entities/${encodeURIComponent(entityId)}/invariant`);
  },

  getEntityStream(
    entityId: string,
  ): Promise<{ entity_id: string; records: Array<Record<string, unknown>> }> {
    return request(`/entities/${encodeURIComponent(entityId)}/stream`);
  },

  getEntityMaterializationStatus(entityId: string): Promise<Record<string, unknown>> {
    return request(`/entities/${encodeURIComponent(entityId)}/materialization-status`);
  },

  getCorrelations(entityId: string): Promise<{ entity_id: string; correlations: Correlation[] }> {
    return request<{ entity_id: string; correlations: Correlation[] }>(
      `/entities/${encodeURIComponent(entityId)}/correlations`,
    );
  },

  /** Pull the entity's Common Crawl temporality (CC-TEMPORALITY v1).
   *  Synchronous bounded pull: plan → CC index → series; empty data ⇒ honest notes. */
  ccTemporality(entityId: string): Promise<CcTemporalityPayload> {
    return request<CcTemporalityPayload>(
      `/entities/${encodeURIComponent(entityId)}/cc-temporality`,
      { method: "POST" },
    );
  },

  /** Create a new atomic entity (dynamic invariant — persistent identity, versioned, evidence-anchored). */
  createEntity(body: {
    canonical_identity: Record<string, string>;
    aliases?: string[];
    label?: string;
  }): Promise<{ entity: EntityView & { tenant_id: string }; event: string }> {
    return request<{ entity: EntityView & { tenant_id: string }; event: string }>("/entities", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** Link an entity to another candidate via possible_match — no identity merge. */
  linkEntities(
    entityId: string,
    body: {
      candidate_b: string;
      kind?: string;
      raw_pair_score?: number;
      reasons?: string[];
    },
  ): Promise<{ edge: Correlation; event: string }> {
    return request<{ edge: Correlation; event: string }>(
      `/entities/${encodeURIComponent(entityId)}/correlations`,
      { method: "POST", body: JSON.stringify(body) },
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

  listFindings(): Promise<{ findings: Array<FindingView & { tenant_id: string }> }> {
    return request<{ findings: Array<FindingView & { tenant_id: string }> }>("/findings");
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

  // ── SpecOps (entity graph + Maltego-style tools) ──────────────────

  /** Whole-graph projection of entities plus their edges, Maltego-style. */
  specOpsGraph(): Promise<SpecOpsGraphResponse> {
    return request<SpecOpsGraphResponse>("/entities/graph");
  },

  /** List registered tools, optionally scoped to one entity type. */
  listTools(entityType?: string): Promise<{ tools: ToolSpec[] }> {
    const params = entityType ? `?entity_type=${encodeURIComponent(entityType)}` : "";
    return request<{ tools: ToolSpec[] }>(`/tools${params}`);
  },

  /** Enqueue a tool run against one entity value. */
  enqueueTool(
    toolId: string,
    body: { entity_type: string; entity_value: string; entity_id?: string },
  ): Promise<{ run: ToolRun; event: string }> {
    return request<{ run: ToolRun; event: string }>(
      `/tools/${encodeURIComponent(toolId)}/enqueue`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  // ── CI/SpecOps department (Feature 027) ──────────────────────────────
  // Thin typed wrappers over /api/v1/specops/* (contracts/specops-api.md).
  // Named-absence discipline: an unserved field arrives as null + the source
  // named in `missing`, never a zero (FR-012). The RoE gate is enforced
  // server-side, so a 409 here is the gate refusing, not a client error.

  /** Record a rules-of-engagement sign-off (supervisor). */
  recordRoe(body: {
    target_ref: string;
    scope: string;
    approved_by: string;
    expires_at?: string | null;
  }): Promise<CiRoeView> {
    return request<CiRoeView>("/specops/roe", { method: "POST", body: JSON.stringify(body) });
  },

  /** Read a sign-off's status. */
  getRoe(roeId: string): Promise<CiRoeView> {
    return request<CiRoeView>(`/specops/roe/${encodeURIComponent(roeId)}`);
  },

  /** List ATT&CK emulation plans from the donor libraries. */
  listEmulationPlans(): Promise<CiEnvelope<{ plans: CiPlanWire[] }>> {
    return request("/specops/emulation/plans");
  },

  /** One plan's abilities + expected telemetry. */
  getEmulationPlan(planId: string): Promise<CiEnvelope<{ plan: CiPlanDetailWire }>> {
    return request(`/specops/emulation/plans/${encodeURIComponent(planId)}`);
  },

  /** Launch an operation. Blocked (409 RoEError) without a confirmed roe_id. */
  launchOperation(body: {
    plan_id: string;
    lab_fixture: string;
    roe_id: string;
  }): Promise<CiEnvelope<{ operation: CiOperationWire }>> {
    return request("/specops/emulation/operations", { method: "POST", body: JSON.stringify(body) });
  },

  /** Live + post-run operation state (per-ability planned vs executed). */
  getOperation(operationId: string): Promise<CiEnvelope<{ operation: CiOperationWire }>> {
    return request(`/specops/emulation/operations/${encodeURIComponent(operationId)}`);
  },

  /** Create a draft phishing campaign (no send). */
  createCampaign(body: {
    name: string;
    template_source: string;
    roster: string[];
    attack_mapping?: string[];
  }): Promise<CiEnvelope<{ campaign: CiCampaignWire }>> {
    return request("/specops/phishing/campaigns", { method: "POST", body: JSON.stringify(body) });
  },

  /** Send a campaign. Blocked (409 RoEError / 422 RosterError) when not authorized. */
  launchCampaign(
    campaignId: string,
    body: { roe_id: string },
  ): Promise<CiEnvelope<{ campaign: CiCampaignWire }>> {
    return request(`/specops/phishing/campaigns/${encodeURIComponent(campaignId)}/launch`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** Read a campaign (engagement metrics; captured_credentials_count always 0). */
  getCampaign(campaignId: string): Promise<CiEnvelope<{ campaign: CiCampaignWire }>> {
    return request(`/specops/phishing/campaigns/${encodeURIComponent(campaignId)}`);
  },

  /** A counterintelligence subject + its invariants (each with evidence refs). */
  getSubject(subjectId: string): Promise<CiEnvelope<{ subject: CiSubjectWire }>> {
    return request(`/specops/counterintel/subjects/${encodeURIComponent(subjectId)}`);
  },

  /** Run a social-reaction projection over a modeled population. */
  runProjection(body: {
    population_ref: string;
    narrative_input: string;
    horizon: number;
  }): Promise<CiEnvelope<{ projection: CiProjectionWire }>> {
    return request("/specops/social/projections", { method: "POST", body: JSON.stringify(body) });
  },

  /** Forensics for a completed operation: expected vs actual + gaps + coverage. */
  getForensics(operationId: string): Promise<CiEnvelope<{ forensics: CiForensicsWire }>> {
    return request(`/specops/forensics/operations/${encodeURIComponent(operationId)}`);
  },

  // ── GhostLine (Feature 031) ─────────────────────────────────────────────
  // Voice-borne social engineering, served from /api/v1/specops/ghostline/*
  // (contracts/ghostline-api.md). One method per GhostLine CLI verb, so the UI owns
  // the whole control surface and the CLI is a convenience rather than a gate.
  // The RoE gate is server-side: a 409 here is the gate refusing an unauthorised
  // dial, and a 424 is a setup fact (a missing credential, an uninstalled donor
  // dependency) — the two read differently and the panels keep them apart.

  /** Everything the runtime panel renders: donor, providers, runtime, absences. */
  ghostlineStatus(): Promise<CiEnvelope<GlStatusWire>> {
    return request("/specops/ghostline/status");
  },

  /** The donor's playbook library. */
  listGhostlinePlaybooks(): Promise<CiEnvelope<GlPlaybookListWire>> {
    return request("/specops/ghostline/playbooks");
  },

  /** One playbook: every stage, its persona, the platform's ATT&CK mapping. */
  getGhostlinePlaybook(playbookId: string): Promise<CiEnvelope<GlPlaybookDetailWire>> {
    return request(`/specops/ghostline/playbooks/${encodeURIComponent(playbookId)}`);
  },

  /** Re-read the donor's playbook tree after a scenario was edited on disk. */
  reloadGhostlinePlaybooks(): Promise<CiEnvelope<{ playbook_count: number }>> {
    return request("/specops/ghostline/playbooks/reload", { method: "POST" });
  },

  /** Dry-run the donor's stage machine over a scripted transcript. */
  simulateGhostlinePlaybook(
    playbookId: string,
    utterances: string[],
  ): Promise<CiEnvelope<{ simulation: GlSimulationWire }>> {
    return request(`/specops/ghostline/playbooks/${encodeURIComponent(playbookId)}/simulate`, {
      method: "POST",
      body: JSON.stringify({ utterances }),
    });
  },

  /** Registered voices (cloned or premade). */
  listGhostlineVoices(): Promise<CiEnvelope<GlVoiceListWire>> {
    return request("/specops/ghostline/voices");
  },

  /** Record a voice id the operator already holds (the free-tier path). */
  registerGhostlineVoice(body: {
    voice_id: string;
    name: string;
    origin?: string;
    notes?: string;
  }): Promise<CiEnvelope<{ voice: GlVoiceWire }>> {
    return request("/specops/ghostline/voices", { method: "POST", body: JSON.stringify(body) });
  },

  /** Clone a voice from a sample (the donor CLI's `clone`). */
  cloneGhostlineVoice(body: {
    name: string;
    sample_ref?: string;
    sample_base64?: string;
    sample_filename?: string;
  }): Promise<CiEnvelope<{ voice: GlVoiceWire }>> {
    return request("/specops/ghostline/voices/clone", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** Forget a voice. 409 while a running runtime is pinned to it. */
  forgetGhostlineVoice(voiceId: string): Promise<CiEnvelope<{ removed: string }>> {
    return request(`/specops/ghostline/voices/${encodeURIComponent(voiceId)}`, {
      method: "DELETE",
    });
  },

  /** Bring the runtime up (the donor CLI's `serve`). 424 with named blockers. */
  startGhostlineRuntime(body: {
    voice_id: string;
    playbook_id: string;
    port?: number | null;
  }): Promise<CiEnvelope<{ runtime: GlRuntimeWire }>> {
    return request("/specops/ghostline/runtime/start", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** Tear the runtime down and close the tunnel. Idempotent. */
  stopGhostlineRuntime(): Promise<CiEnvelope<{ runtime: GlRuntimeWire }>> {
    return request("/specops/ghostline/runtime/stop", { method: "POST" });
  },

  /** Place an outbound call (the donor CLI's `call`). 409 RoEError / 422 RosterError. */
  dialGhostline(body: {
    target: string;
    campaign: string;
    persona: string;
    roe_id: string;
    approved_roster: string[];
    playbook_id?: string | null;
  }): Promise<CiEnvelope<GlDialWire>> {
    return request("/specops/ghostline/calls", { method: "POST", body: JSON.stringify(body) });
  },

  /** Recent calls, most recent first. Transcripts are not inlined. */
  listGhostlineCalls(limit = 50): Promise<CiEnvelope<{ calls: GlCallWire[] }>> {
    return request(`/specops/ghostline/calls?limit=${limit}`);
  },

  /** One call with its redacted transcript. */
  getGhostlineCall(callId: string): Promise<CiEnvelope<{ call: GlCallDetailWire }>> {
    return request(`/specops/ghostline/calls/${encodeURIComponent(callId)}`);
  },

  /** Append a turn to a call. Redacted server-side before it is stored. */
  logGhostlineTurn(
    callId: string,
    body: {
      role: string;
      content: string;
      stage?: string | null;
      playbook_id?: string | null;
      sentiment_score?: number | null;
      interest_level?: number | null;
      objection_type?: string | null;
      trigger_used?: string | null;
    },
  ): Promise<CiEnvelope<{ message: GlMessageWire }>> {
    return request(`/specops/ghostline/calls/${encodeURIComponent(callId)}/turns`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** Close a call with its outcome. */
  completeGhostlineCall(
    callId: string,
    body: { outcome: string; notes?: string | null },
  ): Promise<CiEnvelope<{ call: GlCallWire }>> {
    return request(`/specops/ghostline/calls/${encodeURIComponent(callId)}/complete`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** Stage distribution, outcome split, campaign rollups. */
  ghostlineAnalytics(
    campaign?: string | null,
  ): Promise<CiEnvelope<{ analytics: GlAnalyticsWire }>> {
    const query = campaign ? `?campaign=${encodeURIComponent(campaign)}` : "";
    return request(`/specops/ghostline/analytics${query}`);
  },

  /** The donor's `analytics` export, served rather than written to a file. */
  exportGhostlineAnalytics(
    format: "csv" | "json" = "csv",
    campaign?: string | null,
  ): Promise<CiEnvelope<{ export: GlExportWire }>> {
    const params = new URLSearchParams({ format });
    if (campaign) params.set("campaign", campaign);
    return request(`/specops/ghostline/analytics/export?${params.toString()}`);
  },

  // ── Engagement fabric (Feature 032) ───────────────────────────────────────
  // One lifecycle for every channel. The email and voice channels both report into
  // this log, which is what makes the cross-campaign subject view answerable at all.
  // Two tracks are returned — the adversarial funnel and training compliance — and
  // never merged; see `GlCampaignFunnelWire`.

  /** The closed event vocabulary, the ladder, and what was refused from the donor. */
  engagementTaxonomy(): Promise<CiEnvelope<GlTaxonomyWire>> {
    return request("/specops/engagement/taxonomy");
  },

  /** The whole board: per-campaign funnels plus cross-campaign subject profiles. */
  engagementBoard(): Promise<CiEnvelope<{ projection: GlBoardWire }>> {
    return request("/specops/engagement/board");
  },

  /** One campaign's funnel, its events, and its subjects. */
  engagementCampaign(campaignId: string): Promise<CiEnvelope<GlCampaignWire>> {
    return request(`/specops/engagement/campaigns/${encodeURIComponent(campaignId)}`);
  },

  /** The cross-channel event timeline, most recent first. */
  engagementTimeline(limit = 100): Promise<CiEnvelope<{ events: GlEngagementEventWire[] }>> {
    return request(`/specops/engagement/timeline?limit=${limit}`);
  },

  /** Every subject across every campaign. */
  engagementSubjects(): Promise<CiEnvelope<{ subjects: GlSubjectWire[] }>> {
    return request("/specops/engagement/subjects");
  },

  /** Record an event. 422 PayloadRefused for a credential-bearing payload. */
  recordEngagementEvent(body: {
    campaign_id: string;
    channel: string;
    kind: string;
    subject_ref?: string | null;
    metadata?: Record<string, unknown>;
    anonymized?: boolean;
  }): Promise<CiEnvelope<{ event: GlEngagementEventWire }>> {
    return request("/specops/engagement/events", { method: "POST", body: JSON.stringify(body) });
  },

  /** Strip identity from a campaign's events, keeping the counts exact. */
  anonymizeEngagementCampaign(
    campaignId: string,
  ): Promise<CiEnvelope<{ campaign_id: string; anonymized: number }>> {
    return request("/specops/engagement/anonymize", {
      method: "POST",
      body: JSON.stringify({ campaign_id: campaignId }),
    });
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

// ── CI/SpecOps wire types (Feature 027) ────────────────────────────────
// The shapes the /api/v1/specops/* endpoints serve, kept next to the client that
// calls them (contracts/specops-api.md). `served`/`missing` carry the named-
// absence contract: a field the endpoint does not serve is named in `missing`,
// never defaulted here.

export type CiEnvelope<T> = {
  served: string[];
  missing: string[];
  scope: "tenant-wide" | "investigation-scoped";
} & T;

export interface CiRoeView {
  roe_id: string;
  target_ref: string;
  scope: string;
  approved_by: string;
  signed_at: string;
  expires_at: string | null;
  status: "unconfirmed" | "confirmed" | "expired";
}

export interface CiPlanWire {
  plan_id: string;
  name: string;
  source_donor: string;
  target_techniques: string[];
  lab_fixture: string;
}

export interface CiAbilityWire {
  ability_id: string;
  technique: string;
  tactic: string;
  executor: string;
  state?: string | null;
  expected_telemetry?: string[];
}

export interface CiPlanDetailWire {
  plan_id: string;
  abilities: CiAbilityWire[];
  expected_telemetry: string[];
  lab_fixture: string;
}

export interface CiOperationWire {
  operation_id: string;
  plan_id: string;
  lab_fixture: string;
  roe_status: "unconfirmed" | "confirmed" | "expired";
  state: "planned" | "running" | "halted" | "complete";
  abilities: CiAbilityWire[];
  agent_beacons?: unknown[];
  pivot_paths?: unknown[];
  started_at: string | null;
  halted_reason: string | null;
}

export interface CiCampaignWire {
  campaign_id: string;
  state: "draft" | "ready" | "sending" | "complete" | "refused";
  roe_status: "unconfirmed" | "confirmed" | "expired";
  roster: string[];
  engagement_metrics: { sent: number; opened: number; clicked: number; submitted: number };
  attack_mapping: string[];
  captured_credentials_count: number;
}

export interface CiSubjectWire {
  subject_id: string;
  kind: string;
  display: string;
  invariants: Array<{
    kind: string;
    value: string;
    confidence?: number | null;
    evidence_refs?: string[];
  }>;
  relations?: Array<{ to: string; kind: string; evidence_refs?: string[] }>;
}

export interface CiProjectionWire {
  projection_id: string;
  trajectories: Array<{ t: number; reach: number; polarization: number }>;
  phase_transition_risk: { indicator: number; threshold_crossed: boolean };
  confidence: "low" | "medium" | "high";
  artifacts_ref: string | null;
}

export interface CiForensicsWire {
  operation_id: string;
  comparison: Array<{
    ability_id: string;
    technique?: string;
    expected: string;
    actual?: string[];
  }>;
  gaps: Array<{ gap_id: string; ability_id: string; expected_telemetry: string }>;
}

// ── GhostLine wire types (Feature 031) ────────────────────────────────────────
// The shapes /api/v1/specops/ghostline/* serves (contracts/ghostline-api.md). They
// sit next to the client that calls them, and they keep the two disciplines the
// rest of this file keeps: an unserved field is `null` plus a `missing[]` entry, and
// `credentials_captured` is a number the server pins to 0 — rendered so the
// invariant is visible where the credential would otherwise be.

/** Whether one external provider is usable, and what would make it so. */
export interface GlProviderWire {
  name: string;
  configured: boolean;
  env_var: string;
  detail: string;
}

/** The donor's voice-pipeline shape, from its own capability detector. */
export interface GlCapabilitiesWire {
  model: string;
  /** text | realtime | hybrid_stt | hybrid_tts */
  modality: string;
  native_stt: boolean;
  native_tts: boolean;
  needs_deepgram: boolean;
  needs_elevenlabs: boolean;
  /** litellm | registry | env_override | default | platform-fallback */
  source: string;
}

export interface GlDonorWire {
  donor_id: string;
  repo: string;
  license: string;
  root: string;
  present: boolean;
  playbooks_root: string;
  stage_engine: { ready: string[]; absent: string[] };
  live_edges: { ready: string[]; absent: string[] };
  roles: Record<string, string>;
}

export interface GlRuntimeWire {
  /** stopped | blocked | running */
  state: string;
  voice_id: string | null;
  voice_name: string | null;
  playbook_id: string | null;
  playbook_name: string | null;
  model: string | null;
  capabilities: Partial<GlCapabilitiesWire>;
  ws_url: string | null;
  public_url: string | null;
  tunnel_provider: string | null;
  port: number | null;
  started_at: string | null;
  media_route_served: boolean;
  blockers: string[];
  missing: string[];
}

export interface GlStatusWire {
  donor: GlDonorWire;
  config: {
    model: string;
    litellm_api_base: string | null;
    tts_model: string;
    stt_model: string;
    stt_language: string;
    samples_root: string;
    playbooks_root: string;
    ledger_path: string;
    log_level: string;
  };
  providers: GlProviderWire[];
  blockers: string[];
  runtime: GlRuntimeWire;
  counts: { playbooks: number; playbooks_valid: number; voices: number; calls: number };
  playbook_validation_errors: Record<string, string>;
  missing: string[];
}

export interface GlTechniqueWire {
  id: string;
  reason: string;
}

export interface GlPlaybookSummaryWire {
  playbook_id: string;
  name: string;
  author: string | null;
  version: number;
  culture: string | null;
  description: string | null;
  stage_count: number;
  first_stage: string;
  stage_names: string[];
  has_branching: boolean;
  persona_name: string;
  techniques: GlTechniqueWire[];
  /** Always "platform-declared": GhostLine carries no ATT&CK data of its own. */
  mapping_source: string;
  source_path: string;
  valid: boolean;
  invalid_reason: string | null;
  missing: string[];
}

export interface GlStageWire {
  stage: string;
  position: number;
  persona: string | null;
  has_custom_prompt: boolean;
  custom_prompt: string | null;
  success_regex: string | null;
  goto_on_success: string | null;
  goto_on_fail: string | null;
  max_cycles: number;
  silent_until: number | null;
  ambient_ratio: number | null;
  language_hint: string | null;
  operator_note: string | null;
  /** null when the donor taxonomy module is not importable — named, not empty. */
  psych_triggers: string[] | null;
  default_prompt: string | null;
  checkin_line: string | null;
  captures_credential: boolean;
}

export interface GlPersonaWire {
  name: string;
  background: string;
  voice: string;
  persuasion_principles: string[];
  do: string[];
  dont: string[];
}

export interface GlPlaybookDetailWire {
  playbook: GlPlaybookSummaryWire;
  stages: GlStageWire[];
  persona: GlPersonaWire | null;
  defaults: Record<string, unknown> | null;
}

export interface GlPlaybookListWire {
  playbooks: GlPlaybookSummaryWire[];
  invalid: Record<string, string>;
}

export interface GlSimulationStepWire {
  index: number;
  /** Already redacted server-side: what the operator sees, not what they typed. */
  utterance: string;
  stage_before: string;
  stage_after: string;
  success: boolean;
  cycles_remaining: number;
  /** The matched span, or its redaction kind when the match was a credential. */
  matched_pattern: string | null;
  next_line: string | null;
  exited: boolean;
}

export interface GlSimulationWire {
  playbook_id: string;
  playbook_name: string;
  steps: GlSimulationStepWire[];
  final_stage: string | null;
  outcome: string | null;
  outcome_reason: string | null;
  capture_passwords: boolean;
  credentials_captured: number;
  redaction_kinds: string[];
  missing: string[];
}

export interface GlVoiceWire {
  voice_id: string;
  name: string;
  /** cloned | premade */
  origin: string;
  created_at: string;
  sample_ref: string | null;
  sample_bytes: number | null;
  notes: string | null;
}

export interface GlVoiceListWire {
  voices: GlVoiceWire[];
}

export interface GlMessageWire {
  call_id: string;
  role: string;
  content: string;
  stage: string | null;
  timestamp: string;
  /** Which credential shapes were removed from this turn. */
  redaction_kinds: string[];
  sentiment_score: number | null;
  interest_level: number | null;
  objection_type: string | null;
  trigger_used: string | null;
}

export interface GlCallWire {
  call_id: string;
  sid: string | null;
  target: string;
  campaign: string;
  persona: string;
  playbook_id: string | null;
  roe_id: string | null;
  started_at: string;
  ended_at: string | null;
  outcome: string | null;
  capture_passwords: boolean;
  credentials_captured: number;
  notes: string | null;
  message_count: number;
  final_stage: string | null;
}

export interface GlCallDetailWire extends GlCallWire {
  messages: GlMessageWire[];
}

export interface GlDialWire {
  call: GlCallWire;
  placed: {
    sid: string;
    to_number: string;
    from_number: string;
    ws_url: string;
  };
  authorisation: { authorized: boolean; roe_id: string; target_count: number };
  capture_passwords: boolean;
  credentials_captured: number;
}

export interface GlAnalyticsWire {
  campaign: string | null;
  call_count: number;
  completed_count: number;
  in_progress_count: number;
  turn_count: number;
  stage_counts: Record<string, number>;
  outcomes: Record<string, number>;
  by_campaign: Record<string, number>;
  redaction_kinds: Record<string, number>;
  capture_passwords: boolean;
  credentials_captured: number;
  /** null when no call has completed — never a fabricated 0. */
  conversion_rate: number | null;
}

export interface GlExportWire {
  format: string;
  filename: string;
  payload: string | Record<string, unknown>;
}

// ── Engagement fabric wire types (Feature 032) ─────────────────────────────────
// Note the shape of a campaign: `reached` (the adversarial ladder) and `training` are
// SEPARATE fields, and there is no combined one. That is the donor's best idea
// reproduced structurally rather than by convention — there is simply nowhere for a
// meaningless merged score to be rendered from.

export interface GlEventDefinitionWire {
  kind: string;
  track: "phishing" | "training" | "lifecycle";
  stage: number;
  display: string;
  credential_bearing: boolean;
}

export interface GlFunnelStageWire {
  key: string;
  stage: number;
  intent: string;
}

export interface GlTaxonomyWire {
  events: GlEventDefinitionWire[];
  stages: GlFunnelStageWire[];
  dont_heritage: string[];
  log_path: string;
}

export interface GlEngagementEventWire {
  event_id: string;
  campaign_id: string;
  channel: string;
  kind: string;
  display: string;
  occurred_at: string;
  /** null once the campaign has been anonymised. */
  subject_ref: string | null;
  /** Stable pseudonym — this is what keeps linkage after anonymisation. */
  pseudonym: string | null;
  stage: number;
  track: string;
  metadata: Record<string, unknown>;
  ip: string | null;
  user_agent: string | null;
  anonymized: boolean;
}

export interface GlCampaignFunnelWire {
  campaign_id: string;
  channels: string[];
  /** stage key -> subject count, each subject at its DEEPEST position only. */
  reached: Record<string, number>;
  subject_count: number;
  event_count: number;
  event_counts: Record<string, number>;
  /** The training track. Never added into `reached`. */
  training: { assigned: number; completed: number };
  resisted: number;
}

export interface GlSubjectWire {
  subject_ref: string | null;
  pseudonym: string | null;
  deepest_stage: number;
  campaigns: string[];
  channels: string[];
  events: number;
  repeat_engaged: number;
  conceded_campaigns: string[];
  resisted_campaigns: string[];
  trainings_completed: number;
}

export interface GlBoardWire {
  campaigns: GlCampaignFunnelWire[];
  subjects: GlSubjectWire[];
  outcome_split: Record<string, number>;
  stages: GlFunnelStageWire[];
  missing: string[];
}

export interface GlCampaignWire {
  campaign: GlCampaignFunnelWire;
  events: GlEngagementEventWire[];
}
