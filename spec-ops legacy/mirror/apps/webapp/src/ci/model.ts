import { toWorkStatus, type WorkStatus } from "../ui/status";
import type {
  AbilityRow,
  AbilityState,
  CampaignRow,
  CiScope,
  CiServerState,
  ForensicsComparisonRow,
  SubjectInvariantRow,
} from "./types";

/**
 * Pure derivations for the CI/SpecOps department (Feature 027, T007).
 *
 * No fetching, no store writes — every function here is `wire → row`, so the
 * panels render from tested derivations and the hooks stay thin. Status mapping
 * reuses the closed `WorkStatus` vocabulary (§92): a donor spelling this module
 * does not recognise becomes `Unknown`, never a new state.
 */

/** Donor ability state → the department's closed ability vocabulary. */
export function toAbilityState(raw: string | null | undefined): AbilityState {
  switch ((raw ?? "").trim().toLowerCase()) {
    case "executed":
    case "success":
    case "ran":
      return "executed";
    case "failed":
    case "error":
      return "failed";
    case "skipped":
    case "unfinished":
      return "skipped";
    case "planned":
    case "queued":
    case "pending":
      return "planned";
    default:
      // Unknown donor spelling: shown as `planned` would be a lie, so it maps to
      // the neutral `skipped` slot AND its WorkStatus is `Unknown` (below).
      return "skipped";
  }
}

/** Closed-vocabulary status for an ability, from its (already-mapped) state. */
export function abilityStatus(state: AbilityState): WorkStatus {
  switch (state) {
    case "executed":
      return "Completed";
    case "failed":
      return "Failed";
    case "planned":
      return "Queued";
    case "skipped":
      return "Unknown";
  }
}

/** Raw donor ability → row, with an explicit `Unknown` fallback. */
export function abilityRow(raw: {
  ability_id: string;
  technique?: string;
  tactic?: string;
  executor?: string;
  state?: string | null;
  expected_telemetry?: string[];
}): AbilityRow {
  const state = toAbilityState(raw.state);
  return {
    ability_id: raw.ability_id,
    technique: raw.technique ?? "unknown",
    tactic: raw.tactic ?? "unknown",
    executor: raw.executor ?? "unknown",
    state,
    status: abilityStatus(state),
    expected_telemetry: raw.expected_telemetry ?? [],
  };
}

/**
 * An invariant is supported only when it carries evidence. An empty evidence
 * list is rendered as unsupported — never asserted (FR-008). Confidence stays
 * `null` when unserved rather than defaulting to a number.
 */
export function subjectInvariant(raw: {
  kind: SubjectInvariantRow["kind"];
  value: string;
  confidence?: number | null;
  evidence_refs?: string[];
}): SubjectInvariantRow {
  const evidence = raw.evidence_refs ?? [];
  return {
    kind: raw.kind,
    value: raw.value,
    confidence: raw.confidence ?? null,
    evidence_refs: evidence,
    supported: evidence.length > 0,
  };
}

/** Campaign → row. `captured_credentials_count` is pinned to 0 (FR-006). */
export function campaignRow(raw: {
  campaign_id: string;
  state: CampaignRow["state"];
  roe_status: CampaignRow["roe_status"];
  roster?: string[];
  engagement?: Partial<CampaignRow["engagement"]>;
  attack_mapping?: string[];
}): CampaignRow {
  const e = raw.engagement ?? {};
  return {
    campaign_id: raw.campaign_id,
    state: raw.state,
    roe_status: raw.roe_status,
    roster: raw.roster ?? [],
    engagement: {
      sent: e.sent ?? 0,
      opened: e.opened ?? 0,
      clicked: e.clicked ?? 0,
      submitted: e.submitted ?? 0,
    },
    attack_mapping: raw.attack_mapping ?? [],
    captured_credentials_count: 0,
  };
}

/**
 * Forensics comparison: an expected telemetry item with ≥1 matching observation
 * is `corroborated`; with none it is a `gap` and is listed, never dropped
 * (FR-010).
 */
export function forensicsComparison(raw: {
  ability_id: string;
  technique?: string;
  expected: string;
  actual?: string[];
}): ForensicsComparisonRow {
  const actual = raw.actual ?? [];
  return {
    ability_id: raw.ability_id,
    technique: raw.technique ?? "unknown",
    expected: raw.expected,
    actual,
    status: actual.length > 0 ? "corroborated" : "gap",
  };
}

/** Wrap a hook's raw result into the common envelope with named absences. */
export function ciServerState(args: {
  loading: boolean;
  error: string | null;
  refetch: () => void;
  scope: CiScope;
  loaded: string[];
  missing: string[];
  silent?: boolean;
}): CiServerState {
  return {
    loading: args.loading,
    error: args.error,
    refetch: args.refetch,
    scope: args.scope,
    loaded: args.loaded,
    missing: args.missing,
    silent: args.silent ?? false,
  };
}

/** Re-export so panels map a donor status string in one place. */
export { toWorkStatus };
