/** Entity graph builder for the webapp (T057, FR-004).

Turns the entity detail + possible_match correlation edges from the control
plane into Cytoscape ``GraphElement``s. Correlation edges are rendered WITHOUT
implying a merge (FR-004): the counterpart is a separate node reached by a
``possible_match`` edge.
*/

import type { GraphElement } from "../components/GraphPanel";
import type { Correlation, EntityView } from "./api";

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

  const edges: GraphElement[] = [];
  for (const corr of correlations) {
    // Only edges touching this entity belong to its neighbourhood.
    if (corr.candidate_a !== entity.entity_id && corr.candidate_b !== entity.entity_id) continue;
    addNode(corr.candidate_a);
    addNode(corr.candidate_b);
    edges.push({
      id: `${corr.edge_id}:correlation`,
      label: `${corr.kind} (${corr.state})`,
      kind: "edge",
      source: corr.candidate_a,
      target: corr.candidate_b,
    });
  }

  const nodes: GraphElement[] = [...nodeLabels.entries()].map(([id, label]) => ({
    id,
    label,
    kind: "node",
  }));
  return [...nodes, ...edges];
}