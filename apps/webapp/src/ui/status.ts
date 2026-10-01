/**
 * Closed status vocabulary (§92).
 *
 * The UI may not invent states. Anything the backend reports that is not in
 * this list maps to `Unknown` at the adapter boundary — it is never passed
 * through as a new colour.
 *
 *   Healthy     a component is serving and idle
 *   Running     work is in flight right now
 *   Queued      accepted, waiting for capacity
 *   Paused      deliberately stopped, resumable
 *   Completed   finished successfully
 *   Failed      errored — this is where red is legitimate
 *   Blocked     cannot proceed, needs a decision or an external change
 *   Unknown     not reported, or reported in a form this UI does not model
 */
export const WORK_STATUSES = [
  "Healthy",
  "Running",
  "Queued",
  "Paused",
  "Completed",
  "Failed",
  "Blocked",
  "Unknown",
] as const;

export type WorkStatus = (typeof WORK_STATUSES)[number];

/** CSS modifier for StatusDot / Badge. `Unknown` is deliberately neutral. */
export function statusTone(status: WorkStatus): string {
  switch (status) {
    case "Healthy":
    case "Running":
      return "accent";
    case "Queued":
      return "steel";
    case "Paused":
      return "gold";
    case "Completed":
      return "strong";
    case "Failed":
    case "Blocked":
      return "danger";
    case "Unknown":
      return "dim";
  }
}

/**
 * Adapter from a backend-reported status string to the closed vocabulary.
 * Unknown spellings collapse to `Unknown` rather than reaching a colour.
 */
export function toWorkStatus(raw: string | null | undefined): WorkStatus {
  if (!raw) return "Unknown";
  const key = raw.trim().toUpperCase();
  switch (key) {
    case "HEALTHY":
    case "ACTIVE":
    case "ENABLED":
    case "MATERIALIZED":
      return "Healthy";
    case "RUNNING":
    case "ADVANCING":
    case "IN_PROGRESS":
      return "Running";
    case "QUEUED":
    case "REGISTERED":
    case "PLANNED":
    case "PENDING":
    case "OPEN":
      return "Queued";
    case "PAUSED":
    case "SUSPENDED":
      return "Paused";
    case "COMPLETED":
    case "DONE":
    case "ARCHIVED":
      return "Completed";
    case "FAILED":
    case "ERROR":
      return "Failed";
    case "BLOCKED":
    case "DISABLED":
    case "REJECTED":
    case "QUARANTINED":
      return "Blocked";
    default:
      return "Unknown";
  }
}