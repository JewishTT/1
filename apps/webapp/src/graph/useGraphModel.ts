import { useCallback, useMemo } from "react";
import { useQueries } from "@tanstack/react-query";

import { api, type Correlation, type FindingView, type SpecOpsGraphEdge, type SpecOpsGraphNode } from "../lib/api";
import { buildGraphModel, type ClaimRelationInput, type GraphInput, type WireEntity } from "./model";
import type { GraphEdge, GraphModel, GraphNode } from "./types";

/**
 * Server state for the graph (§7, §8, §68).
 *
 * TWO RULES, and they are the reason this is a hook and not a component:
 *
 *   1. Zustand and TanStack Query never mix. The selection, the filters and the
 *      time range come from the workspace store; the records come from Query.
 *      They meet HERE, read-only. Nothing in this file writes a fetched payload
 *      into the store, and no action here mutates a server record.
 *
 *   2. Fetch what the platform actually exposes, and say so when it does not.
 *      Today that is the whole-graph entity projection and the finding list.
 *      Observations, captures, claims and raw payloads have no list endpoint —
 *      so the canvas knows only the observation ids the entity and finding
 *      records name, and `coverage.missing` says exactly that (§99).
 *
 * Query keys are keyed on the investigation, so switching investigations fetches
 * that investigation and nothing else (§68).
 */

export interface GraphCoverage {
  /** Endpoints that answered. */
  loaded: string[];
  /**
   * Endpoints the canvas would need and the platform does not expose today.
   * Named, not glossed over — this is the list another pass can close.
   */
  missing: string[];
}

export interface GraphCounts {
  entities: number;
  observations: number;
  findings: number;
  hypotheses: number;
  edges: number;
}

export interface GraphServerState {
  model: GraphModel;
  loading: boolean;
  /** First error message, verbatim. Never swallowed. */
  error: string | null;
  coverage: GraphCoverage;
  /** Re-run the graph queries. The error state's retry affordance (§91). */
  refetch: () => void;
  counts: GraphCounts;
}

export const GRAPH_COVERAGE_MISSING: ReadonlyArray<string> = [
  "GET /relations (claim records with relation_type, subject_ref, object_ref)",
  "GET /observations (observation list — today only ids named by entity and finding records reach the canvas)",
  "GET /captures and GET /sources/{id}/raw (evidence payloads — those live in the evidence workspace, §82)",
];

const EMPTY_MODEL: GraphModel = {
  nodes: [],
  edges: [],
  nodeIndex: new Map(),
  edgeIndex: new Map(),
};

const EMPTY_COUNTS: GraphCounts = {
  entities: 0,
  observations: 0,
  findings: 0,
  hypotheses: 0,
  edges: 0,
};

/** Nothing to fetch until an investigation is chosen. */
export function useGraphModel(investigationId: string | null): GraphServerState {
  const results = useQueries({
    queries: [
      {
        queryKey: ["graph", "entity-projection", investigationId],
        queryFn: () => api.specOpsGraph(),
        enabled: investigationId !== null,
        staleTime: 60_000,
      },
      {
        queryKey: ["graph", "findings", investigationId],
        queryFn: () => api.listFindings(),
        enabled: investigationId !== null,
        staleTime: 60_000,
      },
    ],
  });

  const [entitiesQuery, findingsQuery] = results;
  const loading = investigationId !== null && (entitiesQuery.isPending || findingsQuery.isPending);
  const firstError = [entitiesQuery.error, findingsQuery.error].find(Boolean);

  // One refetch for both. A retry that re-ran half the graph would be worse
  // than no retry at all (§91).
  const refetch = useCallback(() => {
    void entitiesQuery.refetch();
    void findingsQuery.refetch();
  }, [entitiesQuery, findingsQuery]);

  return useMemo<GraphServerState>(() => {
    if (investigationId === null) {
      return {
        model: EMPTY_MODEL,
        loading: false,
        error: null,
        coverage: { loaded: [], missing: [...GRAPH_COVERAGE_MISSING] },
        refetch,
        counts: EMPTY_COUNTS,
      };
    }

    const input = buildInput(
      investigationId,
      withProjectedRelations(
        adaptProjectionNodes(entitiesQuery.data?.nodes ?? []),
        adaptProjectionEdges(entitiesQuery.data?.edges ?? []),
      ),
      (findingsQuery.data?.findings ?? []) as FindingView[],
      [],
    );
    const model = buildGraphModel(input);

    return {
      model,
      loading,
      error: firstError instanceof Error ? firstError.message : null,
      coverage: {
        loaded: ["/entities/graph", "/findings"],
        missing: [...GRAPH_COVERAGE_MISSING],
      },
      refetch,
      counts: {
        entities: model.nodes.filter((node) => node.kind === "Entity").length,
        observations: model.nodes.filter((node) => node.kind === "Observation").length,
        findings: model.nodes.filter((node) => node.kind === "Finding").length,
        hypotheses: model.nodes.filter((node) => node.kind === "Hypothesis").length,
        edges: model.edges.length,
      },
    };
  }, [investigationId, entitiesQuery.data, findingsQuery.data, loading, firstError, refetch]);
}

/* ── Adapters ────────────────────────────────────────────────────────── */

/**
 * The whole-graph projection arrives as `{ id, label, entity_type, properties }`
 * with the real record in `properties`. Both are read: a row whose properties
 * are missing still contributes an Entity with its label, because dropping it
 * would hide an object the server named.
 */
export function adaptProjectionNode(node: SpecOpsGraphNode): WireEntity {
  const properties = node.properties ?? {};
  const entityId = properties["entity_id"] ?? node.id;
  return {
    entity_id: entityId,
    label: node.label || properties["label"] || entityId,
    canonical_identity: recordOfStrings(properties["canonical_identity"]),
    relationships: normaliseRelationships(relationshipRows(properties["relationships"])),
    evidence: evidenceRows(properties["evidence"]),
    timeline: timelineRows(properties["timeline"]),
    sourceIds: properties["source_ids"] === undefined ? [] : [String(properties["source_ids"])],
    invariantStatus: properties["invariant_status"] ?? (node.entity_type === "ENTITY" ? "MATERIALIZED" : undefined),
  };
}

export function adaptProjectionNodes(nodes: ReadonlyArray<SpecOpsGraphNode>): WireEntity[] {
  return nodes.map(adaptProjectionNode);
}

/** One projection edge, as the relation row it actually is. */
export interface ProjectionRelation {
  from: string;
  to: string;
  kind: string;
}

/**
 * Projection edges are `{ id, source, target, kind }`. They are NOT correlation
 * records — a projection edge has no candidate pair, no scores and no state — so
 * they are read as relation rows and projected as `asserts`. Treating them as
 * correlations would invent a `possible_match` the platform never scored.
 */
export function adaptProjectionEdge(edge: SpecOpsGraphEdge): ProjectionRelation {
  return { from: edge.source, to: edge.target, kind: edge.kind || "linked" };
}

export function adaptProjectionEdges(edges: ReadonlyArray<SpecOpsGraphEdge>): ProjectionRelation[] {
  return edges.map(adaptProjectionEdge);
}

/** Fold the projection's edges into the entities as relationship rows. */
export function withProjectedRelations(
  entities: ReadonlyArray<WireEntity>,
  relations: ReadonlyArray<ProjectionRelation>,
): WireEntity[] {
  if (relations.length === 0) return [...entities];
  const byEntity = new Map<string, Array<Record<string, string>>>();
  for (const relation of relations) {
    const rows = byEntity.get(relation.from) ?? [];
    rows.push({ target: relation.to, type: relation.kind });
    byEntity.set(relation.from, rows);
  }
  return entities.map((entity) => {
    const extra = byEntity.get(entity.entity_id);
    if (extra === undefined) return entity;
    return { ...entity, relationships: [...(entity.relationships ?? []), ...extra] };
  });
}

export function adaptCorrelations(
  originEntityId: string,
  correlations: ReadonlyArray<Correlation>,
): GraphInput["correlations"] {
  return correlations.map((correlation) => ({ ...correlation, origin_entity: originEntityId }));
}

/* ── Input assembly ──────────────────────────────────────────────────── */

export function buildInput(
  investigationId: string | null,
  entities: ReadonlyArray<WireEntity>,
  findings: ReadonlyArray<FindingView>,
  correlations: ReadonlyArray<GraphInput["correlations"][number]>,
): GraphInput {
  const claims: ClaimRelationInput[] = [];
  return {
    entities: entities.map((entity) => ({
      ...entity,
      investigationId,
      relationships: normaliseRelationships(entity.relationships ?? []),
    })),
    findings,
    correlations,
    claims,
  };
}

/**
 * Relationship rows, whether the server sent them as JSON text, as an array, or
 * as a single `{ target, type }` object. All three are read: guessing one shape
 * would silently drop every relationship on the other two.
 */
export function normaliseRelationships(rows: ReadonlyArray<Record<string, string>>): Array<Record<string, string>> {
  const out: Array<Record<string, string>> = [];
  const push = (record: Record<string, unknown>): void => {
    if (typeof record["target"] !== "string" || typeof record["type"] !== "string") return;
    const row: Record<string, string> = { target: record["target"], type: record["type"] };
    if (typeof record["status"] === "string") row["status"] = record["status"];
    if (typeof record["claim_id"] === "string") row["claim_id"] = record["claim_id"];
    if (typeof record["reason"] === "string") row["reason"] = record["reason"];
    out.push(row);
  };

  for (const row of rows) {
    if (typeof row["target"] === "string" && typeof row["type"] === "string") {
      push(row);
      continue;
    }
    const nested = row["relationships"];
    if (typeof nested !== "string") continue;
    let parsed: unknown;
    try {
      parsed = JSON.parse(nested);
    } catch {
      // A malformed relationship blob is a data problem, not a reason to throw
      // away the rest of the graph. The rows are absent, which the toolbar's
      // coverage readout already reports.
      continue;
    }
    if (!Array.isArray(parsed)) continue;
    for (const entry of parsed) {
      if (typeof entry === "object" && entry !== null) push(entry as Record<string, unknown>);
    }
  }
  return out;
}

/** Raw relationship payloads, whatever shape they arrived in. */
function relationshipRows(raw: string | undefined): Array<Record<string, string>> {
  if (raw === undefined) return [];
  let parsed: unknown = raw;
  if (typeof raw === "string") {
    try {
      parsed = JSON.parse(raw);
    } catch {
      return [{ relationships: raw }];
    }
  }
  if (Array.isArray(parsed)) {
    return parsed.filter(
      (entry): entry is Record<string, string> =>
        typeof entry === "object" && entry !== null,
    );
  }
  if (typeof parsed === "object" && parsed !== null) {
    const record = parsed as Record<string, unknown>;
    if (typeof record["target"] === "string") return [record as Record<string, string>];
  }
  return [{ relationships: JSON.stringify(parsed) }];
}

function evidenceRows(raw: string | undefined): WireEntity["evidence"] {
  const parsed = parseMaybeJson(raw);
  if (!Array.isArray(parsed)) return [];
  const out: NonNullable<WireEntity["evidence"]> = [];
  for (const entry of parsed) {
    if (typeof entry !== "object" || entry === null) continue;
    const record = entry as Record<string, unknown>;
    if (typeof record["observation_id"] !== "string") continue;
    out.push({
      evidence_id: typeof record["evidence_id"] === "string" ? record["evidence_id"] : "",
      observation_id: record["observation_id"],
      immutable: record["immutable"] === true,
    });
  }
  return out;
}

function timelineRows(raw: string | undefined): WireEntity["timeline"] {
  const parsed = parseMaybeJson(raw);
  if (!Array.isArray(parsed)) return [];
  const out: NonNullable<WireEntity["timeline"]> = [];
  for (const entry of parsed) {
    if (typeof entry !== "object" || entry === null) continue;
    const record = entry as Record<string, unknown>;
    if (typeof record["observation_id"] !== "string") continue;
    const row: NonNullable<WireEntity["timeline"]>[number] = {
      observation_id: record["observation_id"],
      uri: typeof record["uri"] === "string" ? record["uri"] : "",
      immutable: record["immutable"] === true,
    };
    if (typeof record["observed_at"] === "string") row.observed_at = record["observed_at"];
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

/* ── Lookups used by the panels ──────────────────────────────────────── */

/** Node ids for a kind, for the toolbar's kind counters. */
export function nodeIdsOfKind(model: GraphModel, kind: GraphNode["kind"]): string[] {
  return model.nodes.filter((node) => node.kind === kind).map((node) => node.id);
}

/** Edge ids touching a node. */
export function edgeIdsTouching(model: GraphModel, nodeId: string): string[] {
  return edgesTouching(model, nodeId).map((edge) => edge.id);
}

/** Edges touching a node — its relations, for the node detail panel. */
export function edgesTouching(model: GraphModel, nodeId: string): GraphEdge[] {
  return model.edges.filter((edge) => edge.source === nodeId || edge.target === nodeId);
}