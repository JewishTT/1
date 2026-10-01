import type { WorkspaceObjectKind, WorkspaceSelection } from "../workspace/types";

/**
 * Graph domain types (§14–§22, §16, §17, §81, §98, §99).
 *
 * THE GRAPH IS A PROJECTION, NOT A MODEL (§81, §99). Nothing here is a
 * platform object. Every `GraphNode` and `GraphEdge` is a read of something
 * the platform already owns — an entity, an observation, a finding, a
 * correlation candidate, an entity relationship row — projected onto one flat
 * canvas so that four different record types can be compared in one place.
 * The record's own identity always travels with the node (`identifier`), and
 * `routeForNode` maps it back to the global selection so the inspector
 * re-reads the platform record rather than this projection.
 *
 * §98: the vocabulary is the platform's. `Hypothesis` is the one name here
 * that is not a `WorkspaceObjectKind`; it is the UI's word for *an
 * unmaterialised correlation candidate* — the platform calls the thing a
 * `possible_match` between a materialised entity and something it has not
 * yet decided is the same thing. Naming it "hypothesis" is what lets the UI
 * show that it is not admitted fact (§16 requires it to read as visibly
 * provisional). It is never persisted, never returned by an endpoint, and
 * never routed to the inspector as itself: `routeForNode` sends a hypothesis
 * to the Entity whose correlation neighbourhood produced it.
 */

/** The five object kinds the canvas distinguishes (§16). */
export type GraphObjectKind = "Entity" | "Observation" | "Claim" | "Finding" | "Hypothesis";

export const GRAPH_OBJECT_KINDS: readonly GraphObjectKind[] = [
  "Entity",
  "Observation",
  "Claim",
  "Finding",
  "Hypothesis",
];

/**
 * Admission, as the *canvas* needs to read it (§16: exactly one accent is
 * reserved for structural/confirmed meaning, and a provisional object must
 * never be equivalent to an admitted one).
 *
 * This is a projection of `ClaimRecord.status`, `Correlation.state`,
 * `EntityView.identity_invariant.status` and `FindingView.status` into four
 * display states. It is closed: an unreported value is `unknown`, never a
 * fifth colour and never a guess (§92, §99).
 */
export type AdmissionState = "admitted" | "provisional" | "rejected" | "unknown";

/**
 * Relation families. Used for **line weight and dash pattern only** (§17) —
 * never for colour, because colour is reserved for admission.
 */
export type EdgeFamily =
  | "supports" // Finding → Observation: this finding rests on this record
  | "observes" // Entity → Observation: this entity is anchored by this record
  | "asserts" // Entity → Entity: the platform reports an asserted relation
  | "possible"; // Entity → Hypothesis: not yet admitted, no merge implied

export interface GraphNode {
  /** Stable within one model: `kind:id`, so an id reused across kinds cannot collide. */
  id: string;
  kind: GraphObjectKind;
  /** Display name. Falls back to the identifier — never to an invented name. */
  label: string;
  /** The platform's own identifier, always shown as the node's mono line. */
  identifier: string;
  /** Projected admission, or null when the platform reports none. */
  admission: AdmissionState | null;
  /** The raw platform status string, shown verbatim so the projection stays auditable. */
  admissionRaw: string | null;
  /**
   * Provisionality. True for every hypothesis, and for anything the platform
   * has not admitted. Drives the dashed border — the part of the visual
   * language that survives greyscale, colour-blindness and a projector.
   */
  provisional: boolean;
  /** Records anchoring this node, as the platform counts them. 0 is a real 0. */
  evidenceCount: number;
  /** Claims resting on / made by this node, when the platform exposes any. */
  claimCount: number;
  /** Source registry id when one is reported, else null. */
  sourceId: string | null;
  /**
   * ISO instants that place this object in time. Empty means *unknown at any
   * instant* — which is different from "no time", and is treated as such by
   * the timeline (§23).
   */
  observedAt: string[];
  /** Hypothesis nodes only: the Entity whose correlation produced this candidate. */
  originEntityId: string | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  /** The asserted predicate, verbatim from the platform row. */
  predicate: string;
  family: EdgeFamily;
  /** Raw platform status for this relation, or null when unreported. */
  status: string | null;
  /** Temporal scope. A null bound is open, not zero. */
  validFrom: string | null;
  validTo: string | null;
  evidenceCount: number;
  claimCount: number;
  observationIds: string[];
  /**
   * The claim this relation was read from, when the endpoint exposes one.
   * Null ⇒ the inspector reports "not reported" and hides the jump rather
   * than minting a claim id (§99).
   */
  claimId: string | null;
  /** Why the platform formed this edge, verbatim. */
  reason: string | null;
}

export interface GraphModel {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Object id → index, so selection and filtering are O(1) per node. */
  nodeIndex: ReadonlyMap<string, GraphNode>;
  edgeIndex: ReadonlyMap<string, GraphEdge>;
}

/**
 * §81: the model is Graph ↔ Objects ↔ Evidence ↔ Timeline, four peers. The
 * graph is not privileged, so this index is the *only* direction the canvas
 * links outward: an object's other representations live in the evidence and
 * timeline surfaces and are reached by selection, not by subgraph.
 */
export const GRAPH_PEER_SURFACES = ["objects", "evidence", "timeline"] as const;

/** Where a node sends the global selection when the analyst activates it. */
export function routeForNode(node: GraphNode): WorkspaceSelection | null {
  switch (node.kind) {
    case "Entity":
      return { kind: "Entity", id: node.identifier, label: node.label };
    case "Observation":
      return { kind: "Observation", id: node.identifier, label: node.label };
    case "Claim":
      return { kind: "Claim", id: node.identifier, label: node.label };
    case "Finding":
      return { kind: "Finding", id: node.identifier, label: node.label };
    case "Hypothesis":
      // A hypothesis is not an addressable platform object. It routes to the
      // Entity whose correlation neighbourhood produced it, so the inspector
      // shows the correlation context it actually belongs to.
      return node.originEntityId === null
        ? null
        : { kind: "Entity", id: node.originEntityId, label: `${node.identifier} (hypothesis)` };
  }
}

/**
 * The node id scheme. `kind:id`, so the same platform id appearing under two
 * kinds (an Observation id that is also a Claim id) cannot collide, and so a
 * node id is self-describing in an exported file and in the URL.
 */
export const nodeIdFor = (kind: string, identifier: string): string => `${kind}:${identifier}`;

/** Map a `WorkspaceSelection` kind onto the graph kinds that can carry that id. */
export function graphKindForSelection(kind: WorkspaceObjectKind): GraphObjectKind | null {
  switch (kind) {
    case "Entity":
      return "Entity";
    case "Observation":
      return "Observation";
    case "Claim":
      return "Claim";
    case "Finding":
      return "Finding";
    case "Investigation":
    case "Capture":
    case "AcquisitionTask":
    case "AcquisitionRun":
    case "Source":
      // §81: capture, source, acquisition and investigation are not subgraphs
      // of the graph. They are peers, reached from the evidence and
      // acquisition surfaces.
      return null;
  }
}