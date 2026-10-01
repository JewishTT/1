import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";

import { api, type FindingView } from "../lib/api";
import { hostOf } from "../timeline/useTimelineEvents";
import type { ClaimRecord, ObservationRecord } from "../workspace/inspector/types";
import {
  EMPTY_LINEAGE,
  type DerivationLineageChain,
  type EvidenceLineageChain,
  type LineageModel,
} from "./lineage";
import { buildEvidenceChain } from "./lineageBuilder";
import type { EvidenceRow } from "./types";

/**
 * Server state for evidence (§7, §28, §82).
 *
 * §82 makes evidence a PEER of the graph, so this is not a detail panel hanging
 * off the canvas — it has its own query keys, its own loading and error states,
 * its own toolbar, and its own density. What it borrows from the graph is
 * nothing; what it shares is the global selection (§7) and the store's evidence
 * filter, which is the workspace-wide narrowing for exactly this surface.
 *
 * WHAT IS AVAILABLE TODAY, precisely:
 *
 *   Observation  ← the observation rows the entity projection's timeline and
 *                  evidence arrays name, plus the rows on `FindingView`. Each
 *                  carries its locator, its URI and its immutable flag. That is
 *                  a real observation identity (§33), so these are real rows.
 *   Capture      ← NOT available. There is no capture endpoint. The list shows
 *                  zero captures and says why in `missing`, rather than deriving
 *                  a pseudo-capture from an observation's URI — a derived
 *                  capture would be a model the platform does not have (§99).
 *   Claim        ← NOT available. `/relations` is unserved (the graph reports
 *                  the same gap), so the claim count is 0 with a stated reason.
 *   Raw payload  ← NOT available. No capture-payload endpoint, so no row carries
 *                  a payload and the Content tab says so per row.
 *
 * The consequence is that today's evidence workspace shows Observation rows and
 * an honest account of what is missing. That is the correct stage-4 outcome: the
 * surface, the density, the toolbar and the lineage chains all exist and work,
 * and the missing endpoints are a named list rather than a blank pane.
 */

export interface EvidenceServerState {
  rows: EvidenceRow[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
  /** Endpoints that answered. */
  loaded: ReadonlyArray<string>;
  /** Endpoints this surface needs and the platform does not expose. */
  missing: ReadonlyArray<string>;
  counts: { Observation: number; Capture: number; Claim: number };
}

export const EVIDENCE_COVERAGE_MISSING: ReadonlyArray<string> = [
  "GET /observations (a list endpoint; today rows come from the entity projection's evidence/timeline arrays)",
  "GET /observations/{id}/record (the observation record with locator, digest and producer)",
  "GET /captures and GET /captures/{id} (Capture rows and their provenance)",
  "GET /relations (Claim rows with relation_type, subject_ref, object_ref, valid_from/valid_to)",
  "GET /captures/{id}/raw and GET /observations/{id}/processing (raw payloads and the processing log)",
  "GET /observations/{id}/revisions (the revision list)",
];

interface ProjectionNodeLike {
  id: string;
  label: string;
  properties: Record<string, string>;
}

export function useEvidenceRecords(investigationId: string | null): EvidenceServerState {
  const results = useQueries({
    queries: [
      {
        queryKey: ["evidence", "entity-projection", investigationId],
        queryFn: () => api.specOpsGraph(),
        enabled: investigationId !== null,
        staleTime: 60_000,
      },
      {
        queryKey: ["evidence", "findings", investigationId],
        queryFn: () => api.listFindings(),
        enabled: investigationId !== null,
        staleTime: 60_000,
      },
    ],
  });

  const [entitiesQuery, findingsQuery] = results;
  const loading = investigationId !== null && (entitiesQuery.isPending || findingsQuery.isPending);
  const firstError = [entitiesQuery.error, findingsQuery.error].find(Boolean);

  return useMemo<EvidenceServerState>(() => {
    if (investigationId === null) {
      return {
        rows: [],
        loading: false,
        error: null,
        refetch: () => undefined,
        loaded: [],
        missing: [...EVIDENCE_COVERAGE_MISSING],
        counts: { Observation: 0, Capture: 0, Claim: 0 },
      };
    }

    const rows = rowsFromProjection(
      (entitiesQuery.data?.nodes ?? []) as ProjectionNodeLike[],
      (findingsQuery.data?.findings ?? []) as FindingView[],
    );

    return {
      rows,
      loading,
      error: firstError instanceof Error ? firstError.message : null,
      refetch: () => {
        void entitiesQuery.refetch();
        void findingsQuery.refetch();
      },
      loaded: ["/entities/graph", "/findings"],
      missing: [...EVIDENCE_COVERAGE_MISSING],
      counts: {
        Observation: rows.filter((row) => row.kind === "Observation").length,
        Capture: 0,
        Claim: 0,
      },
    };
  }, [investigationId, entitiesQuery, findingsQuery, loading, firstError]);
}

/**
 * Observation rows from the projection.
 *
 * Deduplicated by observation id across every entity: an observation two
 * entities both anchor is ONE record, and listing it twice would overstate the
 * evidence base by however many entities reference it.
 */
export function rowsFromProjection(
  nodes: ReadonlyArray<ProjectionNodeLike>,
  findings: ReadonlyArray<FindingView>,
): EvidenceRow[] {
  const rows = new Map<string, EvidenceRow>();

  for (const node of nodes) {
    const properties = node.properties ?? {};
    const sourceId = typeof properties["source_ids"] === "string" ? properties["source_ids"] : null;

    for (const row of parseTimeline(properties["timeline"])) {
      const observationId = typeof row["observation_id"] === "string" ? row["observation_id"] : "";
      if (observationId === "") continue;
      const existing = rows.get(observationId);
      if (existing !== undefined) {
        // Enrich rather than replace: the second mention may carry the instant
        // or the source the first one lacked. An observation is ONE record, so
        // the row keeps its identity and gains facts.
        rows.set(observationId, {
          ...existing,
          at: existing.at ?? (typeof row["observed_at"] === "string" ? row["observed_at"] : null),
          label:
            existing.label !== observationId
              ? existing.label
              : typeof row["uri"] === "string" && row["uri"] !== ""
                ? row["uri"]
                : observationId,
          sourceId:
            existing.sourceId ??
            sourceId ??
            (typeof row["uri"] === "string" ? hostOf(row["uri"]) : null),
          status:
            existing.status ??
            (row["immutable"] === true || row["immutable"] === "true" ? "IMMUTABLE" : null),
          contentType:
            existing.contentType ?? (typeof row["content_type"] === "string" ? row["content_type"] : null),
        });
        continue;
      }
      const uri = typeof row["uri"] === "string" ? row["uri"] : "";
      rows.set(observationId, {
        kind: "Observation",
        ref: observationId,
        label: uri !== "" ? uri : observationId,
        at: typeof row["observed_at"] === "string" ? row["observed_at"] : null,
        sourceId: sourceId ?? hostOf(uri),
        status: row["immutable"] === true || row["immutable"] === "true" ? "IMMUTABLE" : null,
        contentType: typeof row["content_type"] === "string" ? row["content_type"] : null,
        // No capture-payload endpoint is wired, so no row carries bytes. The
        // Content tab reports that per row rather than rendering an empty pane.
        payload: null,
      });
    }
  }

  // A finding's observation with no timeline twin is still a named record. It
  // joins the list with no instant, which sorts last rather than being dropped.
  for (const finding of findings) {
    for (const observation of finding.observations ?? []) {
      const observationId = observation.observation_id;
      if (typeof observationId !== "string" || observationId === "") continue;
      if (rows.has(observationId)) continue;
      rows.set(observationId, {
        kind: "Observation",
        ref: observationId,
        label: observation.uri !== "" ? observation.uri : observationId,
        at: null,
        sourceId: finding.sources?.[0] ?? null,
        status: observation.immutable ? "IMMUTABLE" : null,
        contentType: null,
        payload: null,
      });
    }
  }

  return [...rows.values()].sort((a, b) => (a.ref < b.ref ? -1 : a.ref > b.ref ? 1 : 0));
}

function parseTimeline(raw: string | undefined): Array<Record<string, unknown>> {
  if (raw === undefined) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((entry): entry is Record<string, unknown> => typeof entry === "object" && entry !== null)
      : [];
  } catch {
    return [];
  }
}

/* ── Selected row ────────────────────────────────────────────────────── */

export interface SelectedEvidence {
  row: EvidenceRow | null;
  loading: boolean;
  error: string | null;
  observation: ObservationRecord | null;
  claim: ClaimRecord | null;
  lineage: LineageModel;
}

/**
 * The selected row's chains.
 *
 * Two separate chains, built by two separate builders from two separate inputs.
 * When the platform has no capture, claim or raw object — which is the case
 * today for every observation beyond the entity projection — the affected rungs
 * are REPORTED as missing rather than filled in. The spine the analyst does get
 * is the Observation, plus whatever the entity rows give.
 */
export function useSelectedEvidence(row: EvidenceRow | null): SelectedEvidence {
  return useMemo<SelectedEvidence>(() => {
    if (row === null) {
      return { row: null, loading: false, error: null, observation: null, claim: null, lineage: EMPTY_LINEAGE };
    }

    if (row.kind !== "Observation") {
      // A Capture or Claim row would need its own record fetch. No endpoint is
      // wired for either, so the chains are empty and the viewer says so rather
      // than rendering an Observation-shaped spine for a different record kind.
      return {
        row,
        loading: false,
        error: null,
        observation: null,
        claim: null,
        lineage: EMPTY_LINEAGE,
      };
    }

    const observation: ObservationRecord = {
      observation_id: row.ref,
      capture_id: null,
      locator: null,
      record_digest: null,
      content_type: row.contentType,
      runtime_producer: null,
      runtime_producer_version: null,
      parser_hint: null,
      source_id: row.sourceId,
      uri: row.label === row.ref ? null : row.label,
      collected_at: row.at,
      lifecycle: row.status,
      tenant_id: null,
    };

    const evidence: EvidenceLineageChain = buildEvidenceChain({
      finding: null,
      claim: null,
      observation,
      capture: null,
      rawObject: null,
      source: row.sourceId === null ? null : { source_id: row.sourceId, name: null, kind: null },
    });
    const derivation: DerivationLineageChain | null = null;

    return { row, loading: false, error: null, observation, claim: null, lineage: { evidence, derivation } };
  }, [row]);
}