import { Correlation, EntityView, IdentityInvariant } from "./api";
import { formEdges, EdgeSeed, ObservationCoOccurrence } from "./edgeFormation";

export type IntelNodeKind = "entity" | "correlate" | "relationship" | "observation" | "source";

export type EntityType =
  | "account"
  | "organisation"
  | "device"
  | "location"
  | "infrastructure"
  | "tool"
  | "unknown";

export interface IntelNode {
  id: string;
  label: string;
  kind: IntelNodeKind;
  materialized: boolean;
  type: EntityType;
  counts?: { ev: number; tl: number; versions: number; signals: number };
  attrs?: Record<string, string>;
  aliases?: string[];
  assertions?: string[];
  evidence?: Array<{ evidence_id: string; observation_id: string; immutable: boolean }>;
  /** Backend invariant projection — present only on materialized entity nodes. */
  invariant?: IdentityInvariant;
  currentState?: Record<string, unknown>;
  reason?: string;
}

export interface IntelEdge {
  id: string;
  source: string;
  target: string;
  kind: "possible_match" | "relationship" | "assertion" | "evidence" | "source_host" | "co_occurrence";
  reason: string;
}

export interface IntelGraph {
  nodes: IntelNode[];
  edges: IntelEdge[];
}

function displayLabel(entityId: string, entity?: EntityView): string {
  if (!entity) return entityId;
  const identity = entity.canonical_identity;
  const account = identity["account"];
  if (account) return String(account);
  return entity.aliases[0] ?? entityId;
}

/**
 * Classify an atomic entity into a presentation-type by its canonical identity
 * dimensions and current_state. Used only for node colour/iconography — the
 * catalog remains type-less; this is a read-only view projection (I-3).
 */
export function classifyEntity(entity: EntityView): EntityType {
  const identity = new Set(Object.keys(entity.canonical_identity ?? {}));

  const has = (...keys: string[]) => keys.some((k) => identity.has(k));
  const state = entity.current_state ?? {};
  const stateKind = (["entity_type", "type", "primary_type"] as const)
    .map((k) => state[k])
    .find((v): v is string => typeof v === "string" && v.length > 0)
    ?.toLowerCase();

  if (has("account", "username", "handle", "email", "social", "phone", "telegram")) return "account";
  if (has("organisation", "company", "legal_name", "org", "organisation_name")) return "organisation";
  if (has("device", "imei", "idfa", "mac", "hardware", "serial")) return "device";
  if (has("lat", "lon", "latlon", "coordinate", "city", "address", "geo")) return "location";
  if (has("domain", "hostname", "alexa", "asn", "ip", "infrastructure", "netblock", "tld")) {
    return "infrastructure";
  }
  if (has("tool", "exploit", "malware", "software", "cve")) return "tool";

  if (stateKind?.includes("account") || stateKind === "person" || stateKind === "user") return "account";
  if (stateKind?.includes("org")) return "organisation";
  if (stateKind?.includes("device") || stateKind === "hardware") return "device";
  if (stateKind?.includes("geo") || stateKind === "location" || stateKind === "place") return "location";
  if (stateKind?.includes("domain") || stateKind === "host" || stateKind === "ip") return "infrastructure";
  if (stateKind?.includes("tool") || stateKind === "malware") return "tool";

  return "unknown";
}

function sourceHost(uri: string): string | null {
  try {
    const parsed = new URL(uri);
    return parsed.hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

/**
 * Assemble a Maltego-style intelligence graph from loaded entities and their
 * correlation neighbourhoods (FR-004 possible_match edges — no merge implied)
 * plus explicit relationships. Correlate nodes keep their materialised flag so
 * the UI can offer "materialize this candidate" actions.
 *
 * All edges flow through the deterministic edge factory (edgeFormation.ts):
 * content-addressed ids over (ordered pair, provenance kind, source), dedupe,
 * stable id-sorted emit order — same entities ⇒ identical graph across reloads.
 */
export function buildIntelGraph(
  entities: Record<string, EntityView>,
  correlations: Record<string, Correlation[]>,
): IntelGraph {
  const nodes = new Map<string, IntelNode>();

  // Kind priority: a node re-anchored from a weaker kind (e.g. correlate) to a
  // stronger kind (entity) must not degrade back, and rich per-entity payload
  // (counts/attrs/aliases/invariant) must survive every upsert.
  const kindPriority: Record<IntelNodeKind, number> = {
    source: 0,
    observation: 1,
    relationship: 2,
    correlate: 3,
    entity: 4,
  };

  const upsertNode = (
    id: string,
    label: string | undefined,
    kind: IntelNodeKind,
    materialized: boolean,
    type?: EntityType,
  ) => {
    const existing = nodes.get(id);
    if (!existing) {
      nodes.set(id, { id, label: label ?? id, kind, materialized, type: type ?? "unknown" });
      return;
    }
    const preferredKind =
      kindPriority[kind] > kindPriority[existing.kind] ? kind : existing.kind;
    nodes.set(id, {
      ...existing,
      label: existing.label === id && label ? label : existing.label,
      kind: preferredKind,
      materialized: existing.materialized || materialized,
      type: type && (preferredKind === kind || existing.type === "unknown") ? type : existing.type,
    });
  };

  const seeds: EdgeSeed[] = [];
  // Same observation hosting two materialized entities ⇒ co-mention edge,
  // provenance-anchored on the observation (co_occurrence kind).
  const coOccurrence = new Map<string, string[]>();

  for (const entity of Object.values(entities)) {
    const type = classifyEntity(entity);
    upsertNode(entity.entity_id, displayLabel(entity.entity_id, entity), "entity", true, type);
    nodes.set(entity.entity_id, {
      ...nodes.get(entity.entity_id)!,
      counts: {
        ev: (entity.evidence ?? []).length,
        tl: (entity.timeline ?? []).length,
        versions: (entity.historical_versions ?? []).length,
        signals: (entity.structural_signals ?? []).length,
      },
      attrs: { ...(entity.canonical_identity ?? {}) },
      aliases: entity.aliases ?? [],
      assertions: entity.supporting_assertions ?? [],
      evidence: entity.evidence ? entity.evidence.map((e) => ({ ...e })) : [],
      invariant: entity.identity_invariant,
      currentState: entity.current_state,
    });
    for (const rel of entity.relationships ?? []) {
      const target = rel["target"] as string | undefined;
      if (!target) continue;
      upsertNode(target, target, "relationship", Boolean(entities[target]));
      seeds.push({
        a: entity.entity_id,
        b: target,
        kind: "relationship",
        source: String(rel["type"] ?? "linked"),
        reason: String(rel["type"] ?? "linked"),
      });
    }

    // Immutable observations anchored to this entity (I-1) plus their hosting
    // source domains — observation/source node kinds keep provenance visible
    // on the intelligence map.
    const uriByObs = new Map(
      (entity.timeline ?? [])
        .filter((t) => t.observation_id && t.uri)
        .map((t) => [t.observation_id as string, t.uri as string]),
    );
    for (const t of entity.timeline ?? []) {
      if (!t.observation_id) continue;
      const list = coOccurrence.get(t.observation_id) ?? [];
      if (!list.includes(entity.entity_id)) list.push(entity.entity_id);
      coOccurrence.set(t.observation_id, list);
    }
    for (const ev of entity.evidence ?? []) {
      const obsId = ev.observation_id;
      if (!obsId) continue;
      upsertNode(obsId, obsId, "observation", false);
      seeds.push({
        a: entity.entity_id,
        b: obsId,
        kind: "evidence",
        source: ev.evidence_id,
        reason: ev.immutable ? "immutable" : "volatile",
      });
      const uri = uriByObs.get(obsId);
      if (uri) {
        const host = sourceHost(uri);
        if (host) {
          const srcId = `SRC-${host}`;
          upsertNode(srcId, host, "source", false);
          seeds.push({
            a: obsId,
            b: srcId,
            kind: "source_host",
            source: host,
            reason: host,
          });
        }
      }
    }
  }

  for (const edgeList of Object.values(correlations)) {
    for (const corr of edgeList ?? []) {
      const { candidate_a: a, candidate_b: b, kind, reasons } = corr;
      // Priority-aware upsert keeps a materialized entity node anchored to
      // kind "entity" with all of its invariant payload intact.
      upsertNode(a, displayLabel(a, entities[a]), "correlate", Boolean(entities[a]));
      upsertNode(b, displayLabel(b, entities[b]), "correlate", Boolean(entities[b]));
      seeds.push({
        a,
        b,
        kind: kind === "possible_match" ? "possible_match" : "assertion",
        source: corr.edge_id,
        reason: (reasons ?? []).join(", ") || kind,
      });
    }
  }

  const observations: ObservationCoOccurrence[] = [...coOccurrence.entries()]
    .filter(([, ids]) => ids.length > 1)
    .map(([observation_id, ids]) => ({ observation_id, nodes: ids.sort() }));

  const nodeIds = [...nodes.keys()].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const edges = formEdges(nodeIds, { observations, seeds });

  return {
    nodes: nodeIds.map((id) => nodes.get(id)!),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      kind: e.kind,
      reason: e.reason,
    })),
  };
}

/** Drop provenance (observation/source) nodes and their edges, keeping the map to entities only. */
export function stripProvenance(graph: IntelGraph): IntelGraph {
  const dropped = new Set(
    graph.nodes.filter((n) => n.kind === "observation" || n.kind === "source").map((n) => n.id),
  );
  if (dropped.size === 0) return graph;
  return {
    nodes: graph.nodes.filter((n) => !dropped.has(n.id)),
    edges: graph.edges.filter((e) => !dropped.has(e.source) && !dropped.has(e.target)),
  };
}