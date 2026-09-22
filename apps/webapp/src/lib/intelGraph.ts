import { Correlation, EntityView } from "./api";

export type IntelNodeKind = "entity" | "correlate" | "relationship" | "observation" | "source";

export interface IntelNode {
  id: string;
  label: string;
  kind: IntelNodeKind;
  materialized: boolean;
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

  const upsertNode = (id: string, label: string | undefined, kind: IntelNodeKind, materialized: boolean) => {
    if (!nodes.has(id)) {
      nodes.set(id, { id, label: label ?? id, kind, materialized });
    }
  };

  for (const entity of Object.values(entities)) {
    upsertNode(entity.entity_id, displayLabel(entity.entity_id, entity), "entity", true);
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
      if (entities[a]) aNode.kind = "entity";
      if (entities[b]) bNode.kind = "entity";
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