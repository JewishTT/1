import { useCallback, useMemo } from "react";
import { useQueries } from "@tanstack/react-query";

import { api, type SpecOpsGraphNode } from "../lib/api";
import {
  OBJECT_COVERAGE_MISSING,
  buildObjectModel,
  type ObjectFinding,
  type ProjectionEntity,
} from "./model";
import { emptyCounts } from "./model";
import type { ObjectRow, ObjectRowKind } from "./types";

/**
 * Server state for the objects table (§7, §25, §68).
 *
 * THE TWO RULES THIS HOOK EXISTS TO KEEP, identical to the graph's and the
 * evidence surface's:
 *
 *   1. Zustand and TanStack Query never mix. The selection, the type filter,
 *      the source filter, the query and the time range come from the workspace
 *      store; the records come from Query. They meet HERE, read-only. Nothing in
 *      this file writes a fetched payload into the store, and no action here
 *      mutates a server record.
 *   2. Fetch what the platform exposes, and NAME what it does not. Today that is
 *      the whole-graph entity projection and the finding list. `Claim` and
 *      `Capture` have no list endpoint, so their rows are zero and
 *      `coverage.missing` says exactly which endpoint would fill them.
 *
 * Query keys are keyed on the investigation, so switching investigations fetches
 * that investigation and nothing else (§68).
 */

export interface ObjectCoverage {
  /** Endpoints that answered. */
  loaded: string[];
  /** Endpoints this surface needs and the platform does not expose. */
  missing: string[];
}

// A mapped alias rather than an empty extending interface: the empty interface
// is structurally identical to its supertype while also promising members it does
// not have, and `no-empty-object-type` is right to reject it.
export type ObjectCounts = Record<ObjectRowKind, number>;

export interface ObjectServerState {
  rows: ObjectRow[];
  counts: ObjectCounts;
  loading: boolean;
  /** First error message, verbatim. Never swallowed (§91). */
  error: string | null;
  /** Refetch both endpoints. The error state's retry affordance. */
  refetch: () => void;
  coverage: ObjectCoverage;
}

const EMPTY_ROWS: ObjectRow[] = [];

export function useObjectRows(investigationId: string | null): ObjectServerState {
  const results = useQueries({
    queries: [
      {
        queryKey: ["objects", "entity-projection", investigationId],
        queryFn: () => api.specOpsGraph(),
        enabled: investigationId !== null,
        staleTime: 60_000,
      },
      {
        queryKey: ["objects", "findings", investigationId],
        queryFn: () => api.listFindings(),
        enabled: investigationId !== null,
        staleTime: 60_000,
      },
    ],
  });

  const [entitiesQuery, findingsQuery] = results;
  const loading = investigationId !== null && (entitiesQuery.isPending || findingsQuery.isPending);
  const firstError = [entitiesQuery.error, findingsQuery.error].find(Boolean);

  // One refetch for both. A retry that re-ran half the surface would be worse
  // than no retry at all: the counts would be internally inconsistent (§91).
  const refetch = useCallback(() => {
    void entitiesQuery.refetch();
    void findingsQuery.refetch();
  }, [entitiesQuery, findingsQuery]);

  return useMemo<ObjectServerState>(() => {
    if (investigationId === null) {
      return {
        rows: EMPTY_ROWS,
        counts: emptyCounts(),
        loading: false,
        error: null,
        refetch: () => undefined,
        coverage: { loaded: [], missing: [...OBJECT_COVERAGE_MISSING] },
      };
    }

    const built = buildObjectModel({
      investigationId,
      entities: adaptProjectionNodes((entitiesQuery.data?.nodes ?? []) as SpecOpsGraphNode[]),
      findings: (findingsQuery.data?.findings ?? []) as unknown as ObjectFinding[],
    });

    return {
      rows: built.rows,
      counts: built.counts,
      loading,
      error: firstError instanceof Error ? firstError.message : null,
      refetch,
      coverage: { loaded: ["/entities/graph", "/findings"], missing: [...OBJECT_COVERAGE_MISSING] },
    };
  }, [investigationId, entitiesQuery.data, findingsQuery.data, loading, firstError, refetch]);
}

/* ── Adapter ──────────────────────────────────────────────────────────── */

/**
 * The whole-graph projection arrives as `{ id, label, entity_type, properties }`
 * with the real record in `properties`. Both are read: a node whose properties
 * are missing still contributes an Entity with its label, because dropping it
 * would hide an object the server named.
 */
export function adaptProjectionNode(node: SpecOpsGraphNode): ProjectionEntity {
  const properties = node.properties ?? {};
  const entityId = properties["entity_id"] ?? node.id;
  return {
    entity_id: entityId,
    label: node.label || properties["label"] || undefined,
    canonical_identity: recordOfStrings(properties["canonical_identity"]),
    relationships: relationshipRows(properties["relationships"]),
    evidence: evidenceRows(properties["evidence"]),
    timeline: timelineRows(properties["timeline"]),
    source_ids: properties["source_ids"],
    invariant_status: properties["invariant_status"] ?? (node.entity_type === "ENTITY" ? "MATERIALIZED" : undefined),
    invariant_continuity: properties["invariant_continuity"],
    invariant_first_seen: properties["invariant_first_seen"],
    invariant_last_seen: properties["invariant_last_seen"],
    invariant_history_depth: properties["invariant_history_depth"],
  };
}

export function adaptProjectionNodes(nodes: ReadonlyArray<SpecOpsGraphNode>): ProjectionEntity[] {
  return nodes.map(adaptProjectionNode);
}

/**
 * Relationship rows, whether the projection sent them as JSON text, as an array,
 * or as a single `{ target, type }` object. All three are read here so that
 * `normaliseRelationships` receives one shape and owns the semantics.
 */
function relationshipRows(raw: string | undefined): Array<Record<string, string>> {
  const parsed = parseMaybeJson(raw);
  if (parsed === undefined) return [];
  if (Array.isArray(parsed)) {
    return parsed.filter(
      (entry): entry is Record<string, string> => typeof entry === "object" && entry !== null,
    );
  }
  if (typeof parsed === "object") {
    const record = parsed as Record<string, unknown>;
    if (typeof record["target"] === "string") return [record as Record<string, string>];
    if (typeof record["relationships"] === "string") {
      const inner = parseMaybeJson(record["relationships"]);
      if (Array.isArray(inner)) {
        return inner.filter(
          (entry): entry is Record<string, string> => typeof entry === "object" && entry !== null,
        );
      }
    }
  }
  return [{ relationships: raw ?? "" }];
}

function evidenceRows(raw: string | undefined): ProjectionEntity["evidence"] {
  const parsed = parseMaybeJson(raw);
  if (!Array.isArray(parsed)) return [];
  const out: NonNullable<ProjectionEntity["evidence"]> = [];
  for (const entry of parsed) {
    if (typeof entry !== "object" || entry === null) continue;
    const record = entry as Record<string, unknown>;
    if (typeof record["observation_id"] !== "string") continue;
    out.push({
      evidence_id: typeof record["evidence_id"] === "string" ? record["evidence_id"] : "",
      observation_id: record["observation_id"],
      immutable: record["immutable"] === true || record["immutable"] === "true",
    });
  }
  return out;
}

function timelineRows(raw: string | undefined): ProjectionEntity["timeline"] {
  const parsed = parseMaybeJson(raw);
  if (!Array.isArray(parsed)) return [];
  const out: NonNullable<ProjectionEntity["timeline"]> = [];
  for (const entry of parsed) {
    if (typeof entry !== "object" || entry === null) continue;
    const record = entry as Record<string, unknown>;
    if (typeof record["observation_id"] !== "string") continue;
    const row: NonNullable<ProjectionEntity["timeline"]>[number] = {
      observation_id: record["observation_id"],
      uri: typeof record["uri"] === "string" ? record["uri"] : "",
      immutable: record["immutable"] === true || record["immutable"] === "true",
    };
    if (typeof record["observed_at"] === "string") row.observed_at = record["observed_at"];
    if (typeof record["source_id"] === "string") row.source_id = record["source_id"];
    out.push(row);
  }
  return out;
}

function parseMaybeJson(raw: string | undefined): unknown {
  if (raw === undefined) return undefined;
  try {
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
}

function recordOfStrings(raw: string | undefined): Record<string, string> {
  const parsed = parseMaybeJson(raw);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return {};
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
    if (typeof value === "string") out[key] = value;
    else if (value !== null && value !== undefined) out[key] = String(value);
  }
  return out;
}
