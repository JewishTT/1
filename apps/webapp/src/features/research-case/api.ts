/**
 * Research Case API client (Feature 034).
 *
 * Typed wrappers around the FastAPI REST surface mounted at /api/v1/research-cases/.
 * Every function returns the raw JSON payload; adaptation to UI shapes happens in
 * the container/components.
 */

import { clientFor } from "../../lib/http";

const API_BASE = "/api/v1/research-cases";
const request = clientFor(API_BASE);

// ── Types ──────────────────────────────────────────────────────────

export type LaunchProfile =
  | "PUBLIC_PROFESSIONAL"
  | "PUBLIC_ROLE_REVIEW"
  | "CONSENTED_RECORDS"
  | "AUTHORISED_CASE";

export type CaseState =
  | "DRAFT"
  | "AWAITING_APPROVAL"
  | "APPROVED"
  | "RUNNING"
  | "QUEUED"
  | "PAUSED"
  | "PARTIAL"
  | "COMPLETE"
  | "BLOCKED"
  | "CANCELLED"
  | "CLOSED";

export type ClaimFamily =
  | "public_name_as_published"
  | "public_professional_role"
  | "public_organization_affiliation"
  | "public_authorship_or_publication"
  | "public_statement_or_official_action"
  | "public_award_or_appointment"
  | "public_event_participation"
  | "public_registry_record"
  | "source_document_metadata";

export type Disposition = "satisfied" | "abandoned" | "blocked" | "superseded";

export interface SubjectAnchor {
  kind: "public_name" | "orcid" | "openalex_author_id" | "doi_author_record" | "official_profile_url";
  value: string;
  evidence_ref?: string;
}

export interface ValidTime {
  from: string | null;
  until: string | null;
  precision: "instant" | "day" | "month" | "year" | "unknown";
}

export interface ContextAmendment {
  amendment_id: string;
  ordinal: number;
  kind: "context" | "query_hint" | "constraint" | "question";
  body: string;
  rationale: string;
  created_by: string;
  created_at: string;
}

export interface DynamicInvariantAnchor {
  anchor_id: string;
  ordinal: number;
  kind: string;
  value: string;
  evidence_ref: string;
  note: string;
  state: "UNRESOLVED" | "REVIEWED" | "ADMITTED" | string;
  admitted_entity_id: string | null;
  created_by: string;
  created_at: string;
}

export interface CaseArtifact {
  artifact_id: string;
  case_id: string;
  capture_id: string;
  observation_id: string;
  raw_ref: string;
  content_digest: string;
  byte_length: number;
  content_type: string;
  filename: string;
  caption: string;
  artifact_kind: string;
  uploaded_by: string;
  created_at: string | null;
  download_path: string;
  processing_state?: string;
}

export interface CaseReportRef {
  report_id: string;
  report_digest: string;
  status: "COMPLETE" | "PARTIAL" | "BLOCKED" | string;
  created_at: string;
}

export interface ResearchCase {
  case_id: string;
  tenant_id: string;
  state: CaseState;
  purpose_code: string;
  purpose_text: string;
  basis_ref: string;
  launch_profile: LaunchProfile;
  subject_anchors: SubjectAnchor[];
  context_amendments?: ContextAmendment[];
  dynamic_invariant_anchors?: DynamicInvariantAnchor[];
  static_artifact_refs?: CaseArtifact[];
  latest_report_ref?: CaseReportRef | Record<string, unknown>;
  jurisdictions: string[];
  valid_time: ValidTime;
  claim_families: ClaimFamily[];
  allowed_source_ids: string[];
  denied_claim_families: string[];
  scope_digest: string;
  scope_revision: number;
  approved: boolean;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  budget_ref: string | null;
}

export interface CreateCaseRequest {
  purpose_code: string;
  purpose_text: string;
  basis_ref: string;
  launch_profile?: LaunchProfile;
  subject_anchors: SubjectAnchor[];
  jurisdictions?: string[];
  valid_time?: ValidTime;
  claim_families?: ClaimFamily[];
  allowed_source_ids?: string[];
  denied_claim_families?: string[];
  budget_ref?: string;
  expires_at?: string;
  questions?: string[];
}

export interface ApproveCaseRequest {
  scope_digest: string;
  scope_revision: number;
}

export interface ReviseScopeRequest extends CreateCaseRequest {
  purpose_code: string;
  purpose_text: string;
  basis_ref: string;
  subject_anchors: SubjectAnchor[];
}

export interface Obligation {
  obligation_id: string;
  question: string;
  claim_family?: string | null;
  claim_families?: string[];
  state: string;
  required_capabilities: string[];
  eligible_capabilities?: string[];
  satisfaction_condition?: string | string[];
  satisfaction_criteria?: string[];
  scope_condition?: string;
  rationale?: string;
  priority: number;
  priority_basis: string;
}

export interface CoverageItem {
  obligation_id: string;
  source_id: string | null;
  query_variant_id: string | null;
  state: string;
  attempts: number;
  records_received: number;
  raw_artifact_refs: string[];
  observation_refs: string[];
  started_at: string | null;
  finished_at: string | null;
  policy_digest: string;
  budget_reservation_id: string | null;
  reason_code: string | null;
  next_action_ref: string | null;
}

export interface CoverageLedger {
  case_id: string;
  scope_revision: number;
  overall_state: string;
  counts: Record<string, number>;
  items: CoverageItem[];
}

export interface Claim {
  claim_id: string;
  case_id: string;
  claim_family: string;
  subject_mention: string;
  predicate: string;
  object_payload: unknown;
  polarity: "positive" | "negative" | "unknown";
  epistemic_state?: "TRUE_ONLY" | "FALSE_ONLY" | "BOTH" | "NEITHER";
  state: "proposed" | "admitted" | "contested" | "retracted" | "superseded";
  valid_time: ValidTime;
  evidence_refs: string[];
  source_ref: string;
  extractor_ref: string;
  extractor_version: string;
}

export interface TimelineItem {
  claim_id: string;
  label: string;
  valid_time: ValidTime;
  source_time: { published_at: string | null; captured_at: string | null };
  epistemic_state: "TRUE_ONLY" | "FALSE_ONLY" | "BOTH" | "NEITHER";
  evidence_refs: string[];
  conflict_refs: string[];
  knowledge_time?: { from: string | null; until: string | null };
}

export interface GraphNode {
  id: string;
  kind: "PersonCandidate" | "AdmittedEntity" | "PublicOrganisation" | "PublicRole" | "PublicPublication" | "PublicEvent/Action" | "Claim" | "SourceDocument";
  label: string;
  identity_state: "UNRESOLVED" | "REVIEW_REQUIRED" | "ADMITTED" | "CONTESTED";
  claim_refs: string[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: "ASSERTS" | "SUPPORTED_BY" | "REFUTED_BY" | "HELD_PUBLIC_ROLE" | "AFFILIATED_WITH" | "AUTHORED" | "PARTICIPATED_IN_PUBLIC_EVENT" | "PUBLISHED_IN" | "POSSIBLE_MATCH";
  epistemic_state: "TRUE_ONLY" | "FALSE_ONLY" | "BOTH" | "NEITHER";
  valid_time: ValidTime;
  evidence_refs: string[];
  lineage_roots: string[];
  review_state: string;
  relation_type?: string;
}

export interface GraphProjection {
  case_id: string;
  scope_revision: number;
  projection_version: string;
  as_of: string;
  truncated: boolean;
  nodes: GraphNode[];
  edges: GraphEdge[];
  warnings: string[];
}

export interface IdentityReview {
  review_id: string;
  case_id: string;
  decision: "ACCEPT" | "REJECT" | "UNCERTAIN";
  rationale: string;
  reviewer: string;
  created_at: string;
}

export interface ClaimDispute {
  dispute_id: string;
  case_id: string;
  claim_id: string;
  action: "contest" | "retract" | "qualify";
  reason: string;
  actor: string;
  created_at: string;
}

export interface Report {
  report_id: string;
  case_id: string;
  sections: Array<{ heading: string; text: string; finding_ids: string[] }>;
  sentence_finding_refs: Array<{ sentence_index: number; finding_ids: string[] }>;
}

export interface RetentionAction {
  action_id: string;
  case_id: string;
  action: string;
  actor: string;
  created_at: string;
}

// ── Endpoints ──────────────────────────────────────────────────────

export interface CreatedResearchCase {
  case_id: string;
  tenant_id: string;
  state: "DRAFT";
  scope_digest: string;
  scope_revision: number;
  created_at: string;
  obligation_count: number;
}

export async function createCase(body: CreateCaseRequest): Promise<CreatedResearchCase> {
  return request("", { method: "POST", body: JSON.stringify(body) });
}

export async function getCase(caseId: string): Promise<ResearchCase> {
  return request(`/${encodeURIComponent(caseId)}`);
}

export async function proposeScopeRevision(
  caseId: string,
  body: ReviseScopeRequest,
): Promise<{ case_id: string; scope_revision: number; scope_digest: string; re_approval_required: boolean; stale_scope_behavior: string }> {
  return request(`/${encodeURIComponent(caseId)}/scope`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function approveCase(caseId: string, body: ApproveCaseRequest): Promise<{ case_id: string; state: string; scope_digest: string; scope_revision: number; approved_at: string }> {
  return request(`/${encodeURIComponent(caseId)}/approve`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface ResearchAction {
  action_id: string;
  obligation_id: string;
  proposed_method: string;
  runtime_ref: string;
  expected_information_gain: number;
  estimated_cost: number;
  priority: number;
  capability_requirements: string[];
  requires_operator_approval: boolean;
  status: "proposed" | "approved" | "rejected" | string;
  source_id: string;
  catalogue_source_id: string;
  query: string;
  parent_action_id: string;
  scope_digest: string;
  policy_digest: string;
  claim_family?: string;
}

export interface CaseActions {
  case_id: string;
  scope_digest: string;
  scope_revision: number;
  policy_digest: string;
  actions: ResearchAction[];
}

export interface CasePlan {
  case_id: string;
  tenant_id: string;
  scope_digest: string;
  scope_revision: number;
  policy_digest: string;
  obligations: Obligation[];
  actions: ResearchAction[];
  required_capabilities: string[];
  capabilities_preview: string[];
  capability_gaps: Array<{ obligation_id: string; claim_families?: string[]; detail: string; required?: string[] }>;
  rejected_catalogue_definitions: Record<string, string[]>;
  plan_state: "BLOCKED_CAPABILITY" | "BLOCKED_RUNTIME" | "BLOCKED_NO_ACTIONS" | "READY_FOR_REVIEW" | string;
  ready_to_dispatch: boolean;
  no_network_side_effects: boolean;
}

export async function planCase(caseId: string): Promise<CasePlan> {
  return request(`/${encodeURIComponent(caseId)}/plan`, { method: "POST" });
}

export interface RunCaseRequest {
  idempotency_key: string;
  approved_action_refs: string[];
}

export async function listActions(caseId: string): Promise<CaseActions> {
  return request(`/${encodeURIComponent(caseId)}/actions`);
}

export async function approveActions(
  caseId: string,
  action_refs: string[],
): Promise<{ case_id: string; approved_by: string; approved_action_refs: string[]; scope_digest: string; policy_digest: string }> {
  return request(`/${encodeURIComponent(caseId)}/actions/approve`, {
    method: "POST",
    body: JSON.stringify({ action_refs }),
  });
}

export async function runCase(caseId: string, body: RunCaseRequest): Promise<{ case_id: string; run_id: string; idempotency_key: string; state: string; dispatch_intent_created: boolean; dispatch?: Record<string, unknown> }> {
  return request(`/${encodeURIComponent(caseId)}/run`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function pauseCase(caseId: string): Promise<{ case_id: string; state: string }> {
  return request(`/${encodeURIComponent(caseId)}/pause`, { method: "POST" });
}

export async function listObligations(caseId: string): Promise<{ case_id: string; tenant_id: string; obligations: Obligation[] }> {
  return request(`/${encodeURIComponent(caseId)}/obligations`);
}

export async function getCoverage(caseId: string): Promise<CoverageLedger> {
  return request(`/${encodeURIComponent(caseId)}/coverage`);
}

export async function listClaims(caseId: string, limit = 50, cursor?: string): Promise<{ case_id: string; claims: Claim[]; next_cursor?: string | null; source_of_truth?: string }> {
  const qs = new URLSearchParams({ limit: String(limit) });
  if (cursor) qs.set("cursor", cursor);
  return request(`/${encodeURIComponent(caseId)}/claims?${qs}`);
}

export async function getTimeline(caseId: string, validFrom?: string, validUntil?: string, asOf?: string, limit = 50): Promise<{ case_id: string; timeline: TimelineItem[] }> {
  const qs = new URLSearchParams({ limit: String(limit) });
  if (validFrom) qs.set("valid_from", validFrom);
  if (validUntil) qs.set("valid_until", validUntil);
  if (asOf) qs.set("as_of", asOf);
  return request(`/${encodeURIComponent(caseId)}/timeline?${qs}`);
}

export async function getGraph(caseId: string, asOf?: string, depth = 1, kinds?: string[]): Promise<GraphProjection> {
  const qs = new URLSearchParams({ depth: String(depth) });
  if (asOf) qs.set("as_of", asOf);
  if (kinds?.length) qs.set("kinds", kinds.join(","));
  return request(`/${encodeURIComponent(caseId)}/graph?${qs}`);
}

export async function createIdentityReview(caseId: string, body: { decision: string; rationale: string }): Promise<{ review_id: string; event: string }> {
  return request(`/${encodeURIComponent(caseId)}/identity-reviews`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function createClaimDispute(caseId: string, body: { claim_id: string; action: string; reason: string }): Promise<{ dispute_id: string; event: string }> {
  return request(`/${encodeURIComponent(caseId)}/claim-disputes`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface CompletionReport {
  report_id: string;
  report_digest: string;
  status: "COMPLETE" | "PARTIAL" | "BLOCKED" | string;
  generated_at: string;
  summary: Record<string, number>;
  findings: Array<Record<string, unknown>>;
  relation_claims: Array<Record<string, unknown>>;
  obligations: Array<Record<string, unknown>>;
  source_inventory: Record<string, unknown>;
  coverage: CoverageLedger;
  processing: Array<Record<string, unknown>>;
  static_artifacts: CaseArtifact[];
  limitations: string[];
}

export async function generateReport(caseId: string): Promise<CompletionReport> {
  return request(`/${encodeURIComponent(caseId)}/report`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function getReport(caseId: string, reportId: string): Promise<CompletionReport> {
  return request(
    `/${encodeURIComponent(caseId)}/reports/${encodeURIComponent(reportId)}`,
  );
}

export async function appendContextAmendment(
  caseId: string,
  body: { body: string; rationale?: string; kind: ContextAmendment["kind"] },
): Promise<{ case_id: string; scope_revision: number; scope_digest: string; re_approval_required: boolean; extension: { kind: string; value: ContextAmendment }; stale_scope_behavior: string }> {
  return request(`/${encodeURIComponent(caseId)}/context/amendments`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function addDynamicInvariantAnchor(
  caseId: string,
  body: { kind: string; value: string; evidence_ref?: string; note?: string },
): Promise<{ case_id: string; scope_revision: number; scope_digest: string; re_approval_required: boolean; extension: { kind: string; value: DynamicInvariantAnchor }; stale_scope_behavior: string }> {
  return request(`/${encodeURIComponent(caseId)}/invariants`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listArtifacts(caseId: string): Promise<{ case_id: string; artifacts: CaseArtifact[]; count: number; source_of_truth: string }> {
  return request(`/${encodeURIComponent(caseId)}/artifacts`);
}

export async function uploadArtifact(
  caseId: string,
  file: File,
  caption = "",
): Promise<CaseArtifact> {
  return request(`/${encodeURIComponent(caseId)}/artifacts`, {
    method: "POST",
    body: file,
    headers: {
      "Content-Type": file.type || "application/octet-stream",
      "X-Artifact-Filename": encodeURIComponent(file.name),
      "X-Artifact-Caption": encodeURIComponent(caption),
    },
  });
}

export interface CloseCaseRequest {
  disposition: string;
  report?: Record<string, unknown>;
}

export async function closeCase(caseId: string, body: CloseCaseRequest): Promise<{ case_id: string; state: string; disposition: string; report: Record<string, unknown>; closed_at: string }> {
  return request(`/${encodeURIComponent(caseId)}/close`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function retentionAction(caseId: string, body: { action: string }): Promise<{ action_id: string; case_id: string }> {
  return request(`/${encodeURIComponent(caseId)}/retention-action`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}


/** Stable feature facade for components; named functions remain directly testable. */
export const api = {
  createCase,
  getCase,
  proposeScopeRevision,
  approveCase,
  planCase,
  listActions,
  approveActions,
  runCase,
  pauseCase,
  listObligations,
  getCoverage,
  listClaims,
  getTimeline,
  getGraph,
  appendContextAmendment,
  addDynamicInvariantAnchor,
  listArtifacts,
  uploadArtifact,
  generateReport,
  getReport,
  createIdentityReview,
  createClaimDispute,
  closeCase,
  retentionAction,
};
