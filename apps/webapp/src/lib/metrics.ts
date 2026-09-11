import { fetchOpsMetrics, OpsMetrics } from "./api";

/**
 * Fetch operational metrics from the control plane (T068, US3).
 * Merges /api/v1/metrics and /api/v1/metrics/pools into a single payload.
 */
export function getOpsMetrics(): Promise<OpsMetrics> {
  return fetchOpsMetrics();
}
