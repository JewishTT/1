import type { WorkStatus } from "../ui/status";

/**
 * CI/SpecOps department row vocabulary (Feature 027, §46/§92/§99).
 *
 * The department is a DIFFERENT subject from pipeline health: kill-chain
 * emulation, phishing/SAT, APT forensics, counterintelligence, social-reaction.
 * Nothing here is a throughput/queue/pool metric — those belong to the Ops view.
 *
 * Two rules carried verbatim from `src/ops/types.ts`, because the department
 * inherits the same discipline:
 *   §92  every status is a `WorkStatus`; an unrecognised donor spelling arrives
 *        as `Unknown`, never a new colour.
 *   §99  a field the endpoint does not serve is `null` + the endpoint name in a
 *        `missing[]` array — never a zero, never a default, never a guess.
 */

/** A value the served endpoints do not carry, with the endpoint that would. */
export interface Unavailable {
  readonly reason: string;
  readonly endpoint: string;
}

export function unavailable(reason: string, endpoint: string): Unavailable {
  return { reason, endpoint };
}

/** The department's panels — one subject each, one tab each on the canvas. */
export type CiPanel =
  | "operations"
  | "emulation"
  | "phishing"
  | "forensics"
  | "detection"
  | "counterintel"
  | "social";

/** Scope every panel declares on screen so a tenant-wide figure is never misread. */
export type CiScope = "tenant-wide" | "investigation-scoped";

/** Common server-state envelope each panel hook returns. */
export interface CiServerState {
  readonly loading: boolean;
  readonly error: string | null;
  readonly refetch: () => void;
  readonly scope: CiScope;
  /** Endpoints that answered. */
  readonly loaded: ReadonlyArray<string>;
  /** Endpoints this panel needs and the platform does not expose (named absence). */
  readonly missing: ReadonlyArray<string>;
  /** True when nothing at all came back — distinct from "everything nominal". */
  readonly silent: boolean;
}

/* ── Emulation (US2) ─────────────────────────────────────────────────── */

export type AbilityState = "planned" | "executed" | "failed" | "skipped";

export interface AbilityRow {
  readonly ability_id: string;
  readonly technique: string;
  readonly tactic: string;
  readonly executor: string;
  readonly state: AbilityState;
  /** Closed-vocabulary status derived from the donor's raw state. */
  readonly status: WorkStatus;
  readonly expected_telemetry: ReadonlyArray<string>;
}

export interface EmulationPlanRow {
  readonly plan_id: string;
  readonly name: string;
  readonly source_donor: string;
  readonly target_techniques: ReadonlyArray<string>;
  readonly lab_fixture: string;
}

export interface OperationRow {
  readonly operation_id: string;
  readonly plan_id: string;
  readonly lab_fixture: string;
  readonly roe_status: "unconfirmed" | "confirmed" | "expired";
  readonly state: "planned" | "running" | "halted" | "complete";
  readonly abilities: ReadonlyArray<AbilityRow>;
  readonly started_at: string | null;
  readonly halted_reason: string | null;
}

/* ── Phishing / SAT (US3) ────────────────────────────────────────────── */

export interface CampaignRow {
  readonly campaign_id: string;
  readonly state: "draft" | "ready" | "sending" | "complete" | "refused";
  readonly roe_status: "unconfirmed" | "confirmed" | "expired";
  readonly roster: ReadonlyArray<string>;
  readonly engagement: { sent: number; opened: number; clicked: number; submitted: number };
  readonly attack_mapping: ReadonlyArray<string>;
  /** Always 0 — credentials are never captured (FR-006). Rendered to prove it. */
  readonly captured_credentials_count: number;
}

/* ── Counterintelligence (US4) ───────────────────────────────────────── */

export type InvariantKind =
  | "belief-state"
  | "narrative-position"
  | "bias-profile"
  | "coordination-signature"
  | "phase-state";

export interface SubjectInvariantRow {
  readonly kind: InvariantKind;
  readonly value: string;
  readonly confidence: number | null;
  readonly evidence_refs: ReadonlyArray<string>;
  /** False when evidence_refs is empty — rendered as unsupported, never asserted. */
  readonly supported: boolean;
}

export interface SubjectRow {
  readonly subject_id: string;
  readonly kind: string;
  readonly display: string;
  readonly invariants: ReadonlyArray<SubjectInvariantRow>;
}

/* ── Social-reaction (US5) ───────────────────────────────────────────── */

export interface SocialProjectionRow {
  readonly projection_id: string;
  readonly trajectories: ReadonlyArray<{ t: number; reach: number; polarization: number }>;
  readonly phase_transition_risk: { indicator: number; threshold_crossed: boolean };
  readonly confidence: "low" | "medium" | "high";
  readonly artifacts_ref: string | null;
}

/* ── Forensics (US6) ─────────────────────────────────────────────────── */

export interface ForensicsComparisonRow {
  readonly ability_id: string;
  readonly technique: string;
  readonly expected: string;
  readonly actual: ReadonlyArray<string>;
  readonly status: "corroborated" | "gap";
}

export interface ForensicsRow {
  readonly operation_id: string;
  readonly comparison: ReadonlyArray<ForensicsComparisonRow>;
  readonly coverage: ReadonlyArray<{ technique: string; covered: boolean }>;
}
