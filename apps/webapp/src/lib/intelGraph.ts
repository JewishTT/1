import { Correlation, EntityView } from "./api";

export type IntelNodeKind = "entity" | "correlate" | "relationship";

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
  kind: "possible_match" | "relationship" | "assertion";
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