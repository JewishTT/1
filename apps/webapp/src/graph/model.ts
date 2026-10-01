import type { Correlation, FindingView } from "../lib/api";
import { nodeIdFor } from "./types";
import type { AdmissionState, EdgeFamily, GraphEdge, GraphModel, GraphNode } from "./types";

/**
 * Graph projection from server records (§16, §81, §99).
 *
 * WHAT IS TAKEN FROM WHERE, and nothing is invented:
 *
 *   Entity        ← EntityView / SpecOpsGraphNode. Materialised by definition:
 *                   the platform only materialises an entity from an invariant.
 *   Observation   ← the observation_id on EntityView.evidence / .timeline and
 *                   on FindingView.observations. Only what the platform names.
 *   Claim         ← ONLY when a relation row carries a claim id. The graph does
 *                   not manufacture claims from relationship rows: a
 *                   relationship row with no claim id becomes an *edge* whose
 *                   claim count is 0 and whose claim id is null, which the edge
 *                   panel reports as "not reported" rather than guessing.
 *   Finding       ← FindingView.
 *   Hypothesis    ← a Correlation whose non-materialised side is not yet a
 *                   materialised entity. This is the platform's own
 *                   `possible_match` / unmaterialised candidate, renamed for
 *                   display because the UI must be able to say "not admitted".
 *
 * §81, concretely: there are NO Source nodes and NO Capture nodes. Those are
 * peers of the graph in the evidence workspace (§82), not subgraphs of it. An
 * observation node carries its `sourceId` as an attribute, which is how the
 * canvas reaches a source without containing one.
 *
 * Every edge id is derived from its own content, so the same records always
 * produce the same graph — a graph whose ids churn between reloads cannot be
 * reasoned about.
 */

export interface WireEntity {
  entity_id: string;
  /** Optional display name; absent ⇒ the label falls back to the identifier. */
  label?: string;
  canonical_identity?: Record<string, string>;
  /** The platform's relationship rows: `{ type, target }`. */
  relationships?: Array<Record<string, string>>;
  evidence?: Array<{ evidence_id: string; observation_id: string; immutable: boolean }>;
  timeline?: Array<{ observation_id: string; uri: string; immutable: boolean; observed_at?: string }>;
  correlations?: Correlation[];
  /** `MATERIALIZED` / anything else, verbatim from the invariant projection. */
  invariantStatus?: string;
  sourceIds?: string[];
  investigationId?: string | null;
}

export interface GraphInput {
  entities: readonly WireEntity[];
  findings: readonly FindingView[];
  /** Correlation candidates across the loaded neighbourhoods. */
  correlations: readonly (Correlation & { origin_entity?: string })[];
  /** Relations the platform reports directly with a claim id, when available. */
  claims?: readonly ClaimRelationInput[];
}

export interface ClaimRelationInput {
  relation_id: string;
  relation_type: string;
  subject_ref: string;
  object_ref: string;
  status: string;
  valid_from?: string | null;
  valid_to?: string | null;
  observation_refs?: readonly string[];
  evidence_grade?: string | null;
  confidence?: number | null;
  contradicts?: readonly string[];
  investigation_id?: string | null;
}

/* ── Admission projection ────────────────────────────────────────────── */

/**
 * Map a platform status string onto the four display states. Closed, and
 * conservative: an unrecognised spelling is `unknown`, which is a *statement
 * that the UI does not know*, never `admitted`. Getting this wrong in the
 * permissive direction would paint an unadmitted object as fact, which is the
 * single worst thing this file could do.
 */
export function projectAdmission(status: string | null | undefined): AdmissionState {
  if (!status) return "unknown";
  const key = status.trim().toUpperCase();
  if (["ADMITTED", "ACCEPTED", "MATERIALIZED", "CONFIRMED", "VALID", "PROMOTED", "APPROVED"].includes(key)) {
    return "admitted";
  }
  if (
    ["PROVISIONAL", "PENDING", "CANDIDATE", "PROPOSED", "UNCONFIRMED", "SUGGESTED", "TENTATIVE", "OPEN"].includes(
      key,
    )
  ) {
    return "provisional";
  }
  if (["REJECTED", "REFUTED", "QUARANTINED", "INVALID", "WITHDRAWN", "SUPERSEDED", "CONTRADICTED"].includes(key)) {
    return "rejected";
  }
  return "unknown";
}

/* ── Ids ─────────────────────────────────────────────────────────────── */

/** Content-derived edge id. Same records ⇒ same id, always. */
function edgeId(parts: readonly string[]): string {
  return `E:${parts.join("|")}`;
}

const byId = (a: { id: string }, b: { id: string }): number => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);

/* ── The builder ─────────────────────────────────────────────────────── */

export function buildGraphModel(input: GraphInput): GraphModel {
  const nodes = new Map<string, GraphNode>();
  const edges = new Map<string, GraphEdge>();
  /** Entity ids that exist as materialised nodes, for correlation resolution. */
  const materialised = new Set<string>();
  /**
   * Relationship rows, queued until every entity node exists. A row may point
   * forward — at an entity that appears later in the input list — and emitting
   * it inline would silently drop every such row depending on input order.
   */
  const relationships: Array<{
    from: string;
    to: string;
    predicate: string;
    row: Record<string, string>;
  }> = [];

  const upsert = (node: GraphNode): void => {
    const existing = nodes.get(node.id);
    if (!existing) {
      nodes.set(node.id, node);
      return;
    }
    // Enrichment wins: a later record with evidence must not erase the counts an
    // earlier record established.
    nodes.set(node.id, {
      ...existing,
      ...node,
      evidenceCount: Math.max(existing.evidenceCount, node.evidenceCount),
      claimCount: Math.max(existing.claimCount, node.claimCount),
      observedAt: mergeInstants(existing.observedAt, node.observedAt),
      sourceId: node.sourceId ?? existing.sourceId,
      admission: node.admission ?? existing.admission,
      admissionRaw: node.admissionRaw ?? existing.admissionRaw,
      label: existing.label !== existing.identifier ? existing.label : node.label,
    });
  };

  const addEdge = (edge: GraphEdge): void => {
    if (edges.has(edge.id)) return;
    if (!nodes.has(edge.source) || !nodes.has(edge.target)) return;
    edges.set(edge.id, edge);
  };

  /* Entities ------------------------------------------------------------ */

  // Collect every materialised id FIRST. A relationship row pointing at an
  // entity that appears later in the list must still resolve to an Entity node,
  // not become a Hypothesis — otherwise the iteration order of the input would
  // decide which objects are candidates, which is exactly the kind of
  // order-dependence §99 forbids.
  for (const entity of input.entities) materialised.add(entity.entity_id);

  for (const entity of input.entities) {
    const identifier = entity.entity_id;
    const label =
      entity.label ??
      Object.values(entity.canonical_identity ?? {})[0] ??
      identifier;

    const observedAt = (entity.timeline ?? [])
      .map((entry) => entry.observed_at)
      .filter((value): value is string => typeof value === "string" && value.length > 0);

    upsert({
      id: nodeIdFor("Entity", identifier),
      kind: "Entity",
      label,
      identifier,
      admission: entity.invariantStatus ? projectAdmission(entity.invariantStatus) : "admitted",
      admissionRaw: entity.invariantStatus ?? null,
      // A materialised entity is not provisional: the platform decides that.
      provisional: false,
      evidenceCount: (entity.evidence ?? []).length + (entity.timeline ?? []).length,
      claimCount: 0,
      sourceId: entity.sourceIds?.[0] ?? null,
      observedAt,
      originEntityId: null,
    });

    /* Observations anchored by this entity. Deduplicated by observation id:
       an observation mentioned by two entities is one record, and rendering it
       twice would invent a second one. */
    const seenObservations = new Set<string>();
    const recordEntries: Array<{
      observation_id: string;
      immutable: boolean;
      observed_at?: string;
      evidence_id?: string;
    }> = [
      ...(entity.evidence ?? []).map((entry) => ({ ...entry })),
      ...(entity.timeline ?? []).map((entry) => ({ ...entry })),
    ];
    for (const entry of recordEntries) {
      const observationId = entry.observation_id;
      if (!observationId || seenObservations.has(observationId)) continue;
      seenObservations.add(observationId);
      const at = entry.observed_at;

      upsert({
        id: nodeIdFor("Observation", observationId),
        kind: "Observation",
        label: observationId,
        identifier: observationId,
        // An observation record is immutable by construction (I-1), but the
        // platform's own lifecycle is what the canvas reports; unreported is
        // `unknown`, not `admitted`.
        admission: projectAdmission(entry.immutable ? "IMMUTABLE" : null),
        admissionRaw: entry.immutable ? "IMMUTABLE" : null,
        provisional: false,
        evidenceCount: 1,
        claimCount: 0,
        sourceId: entity.sourceIds?.[0] ?? null,
        observedAt: typeof at === "string" && at.length > 0 ? [at] : [],
        originEntityId: null,
      });

      addEdge({
        id: edgeId(["Entity", identifier, "observes", observationId]),
        source: nodeIdFor("Entity", identifier),
        target: nodeIdFor("Observation", observationId),
        predicate: "observed",
        family: "observes",
        status: entry.immutable ? "IMMUTABLE" : null,
        validFrom: typeof at === "string" && at.length > 0 ? at : null,
        validTo: null,
        evidenceCount: 1,
        claimCount: 0,
        observationIds: [observationId],
        claimId: null,
        reason: entry.evidence_id ?? null,
      });
    }

    /* Relationship rows. These are asserted relations the platform reports
       directly, so they are edges — not claims. §99: the graph does not
       promote a relationship row into a Claim object it was never told about.

       The edges are QUEUED, not emitted: a row may point at an entity that
       appears later in the input list, and emitting now would silently drop
       every forward reference. See the relationship pass below. */
    for (const relationship of entity.relationships ?? []) {
      const target = relationship["target"];
      const predicate = relationship["type"];
      if (!target || !predicate) continue;
      relationships.push({ from: identifier, to: target, predicate, row: relationship });
    }
  }

  /* Relationships, once every entity node exists ------------------------- */

  for (const relationship of relationships) {
    const { from, to, predicate, row } = relationship;
    // A relationship to something the server has not materialised is a
    // candidate, not a node: it is a Hypothesis (§16), and the edge to it is
    // `possible` — a relation the platform has not admitted.
    const materialisedTarget = materialised.has(to);
    if (!materialisedTarget) addHypothesis(nodes, to, from);

    addEdge({
      id: edgeId(["Entity", from, predicate, to]),
      source: nodeIdFor("Entity", from),
      target: nodeIdFor(materialisedTarget ? "Entity" : "Hypothesis", to),
      predicate,
      family: materialisedTarget ? "asserts" : "possible",
      status: row["status"] ?? null,
      validFrom: row["valid_from"] ?? null,
      validTo: row["valid_to"] ?? null,
      evidenceCount: 0,
      claimCount: 0,
      observationIds: [],
      claimId: row["claim_id"] ?? null,
      reason: row["reason"] ?? null,
    });
  }

  /* Claims, only when the platform hands us one ------------------------ */

  for (const claim of input.claims ?? []) {
    upsert({
      id: nodeIdFor("Claim", claim.relation_id),
      kind: "Claim",
      label: claim.relation_type,
      identifier: claim.relation_id,
      admission: projectAdmission(claim.status),
      admissionRaw: claim.status,
      provisional: projectAdmission(claim.status) !== "admitted",
      evidenceCount: (claim.observation_refs ?? []).length,
      claimCount: 1,
      sourceId: null,
      observedAt: claim.valid_from ? [claim.valid_from] : [],
      originEntityId: null,
    });

    for (const [ref, predicate] of [
      [claim.subject_ref, "subject"],
      [claim.object_ref, "object"],
    ] as const) {
      if (!ref) continue;
      if (!nodes.has(nodeIdFor("Entity", ref))) {
        // The participant exists on the platform but was not loaded. Saying so
        // is better than rendering a node the server did not describe.
        continue;
      }
      addEdge({
        id: edgeId(["Claim", claim.relation_id, predicate, ref]),
        source: nodeIdFor("Claim", claim.relation_id),
        target: nodeIdFor("Entity", ref),
        predicate,
        family: "asserts",
        status: claim.status,
        validFrom: claim.valid_from ?? null,
        validTo: claim.valid_to ?? null,
        evidenceCount: (claim.observation_refs ?? []).length,
        claimCount: 1,
        observationIds: [...(claim.observation_refs ?? [])],
        claimId: claim.relation_id,
        reason: claim.relation_type,
      });
    }
  }

  /* Findings ----------------------------------------------------------- */

  for (const finding of input.findings) {
    upsert({
      id: nodeIdFor("Finding", finding.finding_id),
      kind: "Finding",
      label: finding.finding_id,
      identifier: finding.finding_id,
      admission: projectAdmission(finding.status),
      admissionRaw: finding.status,
      provisional: projectAdmission(finding.status) !== "admitted",
      evidenceCount: (finding.structural_evidence ?? []).length + (finding.semantic_evidence ?? []).length,
      claimCount: (finding.supporting_assertions ?? []).length,
      sourceId: null,
      observedAt: [],
      originEntityId: null,
    });

    for (const observation of finding.observations ?? []) {
      const observationId = observation.observation_id;
      if (!observationId) continue;
      if (!nodes.has(nodeIdFor("Observation", observationId))) {
        upsert({
          id: nodeIdFor("Observation", observationId),
          kind: "Observation",
          label: observationId,
          identifier: observationId,
          admission: projectAdmission(observation.immutable ? "IMMUTABLE" : null),
          admissionRaw: observation.immutable ? "IMMUTABLE" : null,
          provisional: false,
          evidenceCount: 1,
          claimCount: 0,
          sourceId: null,
          observedAt: [],
          originEntityId: null,
        });
      }
      addEdge({
        id: edgeId(["Finding", finding.finding_id, "supports", observationId]),
        source: nodeIdFor("Finding", finding.finding_id),
        target: nodeIdFor("Observation", observationId),
        predicate: "detected in",
        family: "supports",
        status: finding.status,
        validFrom: null,
        validTo: null,
        evidenceCount: 1,
        claimCount: 0,
        observationIds: [observationId],
        claimId: null,
        reason: finding.why_detected,
      });
    }
  }

  /* Correlations, pass 1: relations between two MATERIALISED entities ----- */

  for (const correlation of input.correlations) {
    const a = correlation.candidate_a;
    const b = correlation.candidate_b;
    if (!a || !b) continue;
    if (!nodes.has(nodeIdFor("Entity", a)) || !nodes.has(nodeIdFor("Entity", b))) continue;

    addEdge({
      id: edgeId(["correlation", correlation.edge_id]),
      source: nodeIdFor("Entity", a),
      target: nodeIdFor("Entity", b),
      predicate: correlation.kind,
      // `possible_match` is explicitly not a merge, so it can never read as an
      // asserted relation, no matter what state the edge is in.
      family: correlation.kind === "possible_match" ? "possible" : "asserts",
      status: correlation.state,
      validFrom: null,
      validTo: null,
      evidenceCount: 0,
      claimCount: 0,
      observationIds: [],
      claimId: null,
      reason: (correlation.reasons ?? []).join(", ") || correlation.kind,
    });
  }

  /* Second correlation pass: hypothesis edges, now that every hypothesis
     node exists. Done last so a hypothesis introduced by a relationship row
     and one introduced by a correlation resolve to the same node — a
     candidate must be ONE node, or the canvas would show it twice. */
  for (const correlation of input.correlations) {
    const a = correlation.candidate_a;
    const b = correlation.candidate_b;
    if (!a || !b) continue;

    const aMaterialised = nodes.has(nodeIdFor("Entity", a));
    const bMaterialised = nodes.has(nodeIdFor("Entity", b));

    // Anchor each unmaterialised side to the materialised side, or to the
    // entity whose neighbourhood the correlation came from when neither side
    // is materialised. Without an anchor a candidate has no route to the
    // inspector at all, which would be a dead end (§69).
    if (aMaterialised) addHypothesis(nodes, b, a);
    if (bMaterialised) addHypothesis(nodes, a, b);
    if (!aMaterialised && !bMaterialised && correlation.origin_entity != null) {
      if (nodes.has(nodeIdFor("Entity", correlation.origin_entity))) {
        addHypothesis(nodes, a, correlation.origin_entity);
        addHypothesis(nodes, b, correlation.origin_entity);
      }
    }

    for (const [materialisedSide, candidateSide] of [
      [a, b],
      [b, a],
    ] as const) {
      if (!nodes.has(nodeIdFor("Entity", materialisedSide))) continue;
      if (!nodes.has(nodeIdFor("Hypothesis", candidateSide))) continue;
      addEdge({
        id: edgeId(["possible", materialisedSide, candidateSide]),
        source: nodeIdFor("Entity", materialisedSide),
        target: nodeIdFor("Hypothesis", candidateSide),
        predicate: correlation.kind,
        family: "possible",
        status: correlation.state,
        validFrom: null,
        validTo: null,
        evidenceCount: 0,
        claimCount: 0,
        observationIds: [],
        claimId: null,
        reason: (correlation.reasons ?? []).join(", ") || correlation.kind,
      });
    }
  }

  const nodeList = [...nodes.values()].sort(byId);
  const edgeList = [...edges.values()].sort(byId);
  return {
    nodes: nodeList,
    edges: edgeList,
    nodeIndex: new Map(nodeList.map((node) => [node.id, node])),
    edgeIndex: new Map(edgeList.map((edge) => [edge.id, edge])),
  };
}

/**
 * Create the node for an unmaterialised correlation candidate. Idempotent: a
 * candidate is one node however many rows mention it.
 */
function addHypothesis(nodes: Map<string, GraphNode>, candidateId: string, originEntityId: string): void {
  const id = nodeIdFor("Hypothesis", candidateId);
  if (nodes.has(id)) return;
  nodes.set(id, {
    id,
    kind: "Hypothesis",
    label: candidateId,
    identifier: candidateId,
    // Provisional by definition. The canvas also draws it dashed, so the
    // provisionality survives greyscale.
    admission: "provisional",
    admissionRaw: null,
    provisional: true,
    evidenceCount: 0,
    claimCount: 0,
    sourceId: null,
    observedAt: [],
    originEntityId,
  });
}

function mergeInstants(a: readonly string[], b: readonly string[]): string[] {
  return [...new Set([...a, ...b])].sort();
}

/** Every source id the model knows about, for the source facet and the expansion menu. */
export function collectSourceIds(model: GraphModel): string[] {
  const ids = new Set<string>();
  for (const node of model.nodes) if (node.sourceId !== null) ids.add(node.sourceId);
  return [...ids].sort();
}

/** Every relation predicate in the model, for the relation facet. */
export function collectPredicates(model: GraphModel): string[] {
  return [...new Set(model.edges.map((edge) => edge.predicate))].sort();
}

/** Families actually present, so the facet does not offer absent relations. */
export function collectFamilies(model: GraphModel): EdgeFamily[] {
  const seen = new Set<EdgeFamily>();
  for (const edge of model.edges) seen.add(edge.family);
  return [...seen].sort();
}