/**
 * Query keys, in one place, because a react-query key is an identity claim.
 *
 * Four hooks fetched the same two payloads -- the entity projection and the finding list --
 * under keys that differed only in their first segment: `["graph", …]`, `["objects", …]`,
 * `["timeline", …]`, `["evidence", …]`. That is eight cache entries for two payloads, and
 * because react-query caches by key, mounting the graph view next to its docked timeline
 * issued four HTTP round-trips for the same two responses. Nothing was wrong with any of the
 * four; they simply could not see each other's work.
 *
 * The keys live here rather than inline so that "does this component refetch what another one
 * already has?" has a single answer to read. Adding a fifth consumer now costs a cache entry
 * of zero.
 */

/** The whole entity graph for one investigation. */
export const entityProjectionKey = (investigationId: string | null | undefined) =>
  ["entity-projection", investigationId ?? ""] as const;

/** Findings for one investigation. Same payload for every surface that shows them. */
export const findingsKey = (investigationId: string | null | undefined) =>
  ["findings", investigationId ?? ""] as const;

/** Ops metrics and worker pools, polled by useOpsState and read by four other surfaces. */
export const opsMetricsKey = () => ["ops", "metrics"] as const;
export const workerPoolsKey = () => ["ops", "pools"] as const;
export const quarantineKey = (topic: string) => ["ops", "dlq", topic] as const;
export const connectorsKey = () => ["ops", "connectors"] as const;

/** One investigation's header state. Read by the shell, the workspace and the inspector. */
export const investigationKey = (investigationId: string | null | undefined) =>
  ["investigation", investigationId ?? ""] as const;

/** One entity and its correlations, for the inspector and the three entity surfaces. */
export const entityRecordKey = (entityId: string | null | undefined) =>
  ["entity", entityId ?? ""] as const;
