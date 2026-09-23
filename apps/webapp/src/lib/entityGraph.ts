/** Entity graph builder for the webapp (T057, FR-004).

Turns the entity detail + possible_match correlation edges from the control
plane into Cytoscape ``GraphElement``s. Correlation edges are rendered WITHOUT
implying a merge (FR-004): the counterpart is a separate node reached by a
``possible_match`` edge.

Edges are formed by the deterministic edge factory (src/lib/edgeFormation.ts):
content-addressed ids, order-invariant dedupe, sorted emit order — the same
entity yields the same graph on every reload (W5 persistence).
*/

import type { GraphElement } from "../components/GraphPanel";
import type { Correlation, EntityView } from "./api";
import { formEdges, EdgeSeed } from "./edgeFormation";

export function buildEntityGraphElements(
  entity: EntityView,
  correlations: Correlation[],
): GraphElement[] {
  const nodeLabels = new Map<string, string>();
  const addNode = (id: string) => {
    if (!nodeLabels.has(id)) {
      nodeLabels.set(id, id === entity.entity_id ? (entity.canonical_identity.account ?? id) : id);
    }
  };
  addNode(entity.entity_id);

  const seeds: EdgeSeed[] = [];
  for (const corr of correlations) {
    // Only edges touching this entity belong to its neighbourhood.
    if (corr.candidate_a !== entity.entity_id && corr.candidate_b !== entity.entity_id) continue;
    addNode(corr.candidate_a);
    addNode(corr.candidate_b);
    seeds.push({
      a: corr.candidate_a,
      b: corr.candidate_b,
      kind: corr.kind === "possible_match" ? "possible_match" : "assertion",
      source: corr.edge_id,
      reason: `${corr.kind} (${corr.state})`,
    });
  }

  const nodeIds = [...nodeLabels.keys()].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const formed = formEdges(nodeIds, { observations: [], seeds });

  const nodes: GraphElement[] = nodeIds.map((id) => ({
    id,
    label: nodeLabels.get(id) ?? id,
    kind: "node",
  }));
  const edges: GraphElement[] = formed.map((e) => ({
    id: e.id,
    label: e.reason,
    kind: "edge",
    source: e.source,
    target: e.target,
  }));
  return [...nodes, ...edges];
}