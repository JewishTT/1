import { Correlation, EntityView } from "./api";

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
  reason?: string;
}

export interface IntelEdge {
  id: string;
  source: string;
  target: string;
  kind: "possible_match" | "relationship" | "assertion" | "evidence" | "source_host";
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
 */
export function buildIntelGraph(
  entities: Record<string, EntityView>,
  correlations: Record<string, Correlation[]>,
): IntelGraph {
  const nodes = new Map<string, IntelNode>();
  const edges = new Map<string, IntelEdge>();

  const upsertNode = (
    id: string,
    label: string | undefined,
    kind: IntelNodeKind,
    materialized: boolean,
    type?: EntityType,
  ) => {
    if (!nodes.has(id)) {
      nodes.set(id, { id, label: label ?? id, kind, materialized, type: type ?? "unknown" });
    }
  };

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
    });
    for (const rel of entity.relationships ?? []) {
      const target = rel["target"] as string | undefined;
      if (!target) continue;
      upsertNode(target, target, "relationship", Boolean(entities[target]));
      const edgeId = `REL-${entity.entity_id}-${target}`;
      edges.set(edgeId, {
        id: edgeId,
        source: entity.entity_id,
        target,
        kind: "relationship",
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
    for (const ev of entity.evidence ?? []) {
      const obsId = ev.observation_id;
      if (!obsId) continue;
      upsertNode(obsId, obsId, "observation", false);
      edges.set(`EV-${entity.entity_id}-${obsId}`, {
        id: `EV-${entity.entity_id}-${obsId}`,
        source: entity.entity_id,
        target: obsId,
        kind: "evidence",
        reason: ev.immutable ? "immutable" : "volatile",
      });
      const uri = uriByObs.get(obsId);
      if (uri) {
        const host = sourceHost(uri);
        if (host) {
          const srcId = `SRC-${host}`;
          upsertNode(srcId, host, "source", false);
          edges.set(`SRC-${obsId}-${srcId}`, {
            id: `SRC-${obsId}-${srcId}`,
            source: obsId,
            target: srcId,
            kind: "source_host",
            reason: host,
          });
        }
      }
    }
  }

  for (const edgeList of Object.values(correlations)) {
    for (const corr of edgeList ?? []) {
      const { candidate_a: a, candidate_b: b, kind, reasons } = corr;
      upsertNode(a, displayLabel(a, entities[a]), "correlate", Boolean(entities[a]));
      upsertNode(b, displayLabel(b, entities[b]), "correlate", Boolean(entities[b]));
      // Re-anchor a materialised entity node to kind "entity".
      const aNode = nodes.get(a)!;
      const bNode = nodes.get(b)!;
      if (entities[a]) {
        aNode.kind = "entity";
        aNode.type = classifyEntity(entities[a]);
      }
      if (entities[b]) {
        bNode.kind = "entity";
        bNode.type = classifyEntity(entities[b]);
      }
      edges.set(corr.edge_id, {
        id: corr.edge_id,
        source: a,
        target: b,
        kind: kind === "possible_match" ? "possible_match" : "assertion",
        reason: (reasons ?? []).join(", ") || kind,
      });
    }
  }

  return { nodes: [...nodes.values()], edges: [...edges.values()] };
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