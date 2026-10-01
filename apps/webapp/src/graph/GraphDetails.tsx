import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/Feedback";
import { Tooltip } from "../ui/Overlay";
import { actionsForSelection, destinationForAction } from "../workspace/commands";
import type { WorkspaceSelection, WorkspaceView } from "../workspace/types";
import { ADMISSION_LABELS } from "./filters";
import { NODE_SEMANTICS } from "./semantics";
import type { GraphEdge, GraphModel, GraphNode } from "./types";
import { routeForNode } from "./types";

/**
 * Selection detail (§17, §18, §33, §34, §69).
 *
 * §17 for an EDGE names exactly seven things, and this panel shows exactly
 * those seven: predicate, participants, temporal scope, status, evidence count,
 * claims count, actions. Nothing else, because a panel that shows twelve
 * things about a relation shows none of them.
 *
 * The NODE panel is the same discipline applied to a node: what kind it is, what
 * the platform says about it, what anchors it, and where to go next.
 *
 * Both panels are pure presentational components. They read the model they are
 * given and call back; they own no state and hold no fetch. That is what lets
 * the whole §17 surface be tested without a canvas.
 */

export interface EdgeDetailsProps {
  edge: GraphEdge | null;
  model: GraphModel;
  /** Navigate the global selection to another object (§7 — the one entry point). */
  onGoTo: (selection: WorkspaceSelection) => void;
  /** Change the centre view, so an action actually moves the analyst (§69). */
  onGoToView: (view: WorkspaceView) => void;
  onExpandEdge: (edge: GraphEdge) => void;
}

export function EdgeDetails({ edge, model, onGoTo, onGoToView, onExpandEdge }: EdgeDetailsProps) {
  if (!edge) {
    return (
      <section className="ui-graph-detail" aria-label="Relation detail" data-testid="graph-edge-details">
        <EmptyState
          size="sm"
          icon="view-graph"
          title="No relation selected"
          description="Click an edge to read its predicate, participants, temporal scope and status."
          testId="graph-edge-empty"
        />
      </section>
    );
  }

  const source = model.nodeIndex.get(edge.source) ?? null;
  const target = model.nodeIndex.get(edge.target) ?? null;
  const actions = claimSelectionFor(edge);

  return (
    <section className="ui-graph-detail" aria-label="Relation detail" data-testid="graph-edge-details">
      <header className="ui-graph-detail-head">
        <h3 className="ui-pane-title">Relation</h3>
        <Badge tone="neutral" role="classification" testId="edge-family">
          {edge.family}
        </Badge>
        {edge.status !== null ? (
          <Badge tone="gold" role="classification" testId="edge-status">
            {edge.status}
          </Badge>
        ) : (
          <Badge tone="neutral" testId="edge-status-unreported">
            status not reported
          </Badge>
        )}
      </header>

      {/* 1 — predicate */}
      <Row label="predicate" value={edge.predicate} mono testId="edge-predicate" />

      {/* 2 — participants */}
      <div className="ui-graph-detail-block" data-testid="edge-participants">
        <span className="ui-insp-field-label">participants</span>
        <Participant node={source} side="subject" onGoTo={onGoTo} />
        <Participant node={target} side="object" onGoTo={onGoTo} />
      </div>

      {/* 3 — temporal scope */}
      <Row
        label="valid scope"
        value={`${edge.validFrom ?? "open"} → ${edge.validTo ?? "open"}`}
        mono
        testId="edge-temporal"
      />

      {/* 4 — status, in words as well as colour */}
      <Row label="status" value={edge.status ?? "not reported"} testId="edge-status-value" />

      {/* 5 — evidence count */}
      <Row label="evidence" value={String(edge.evidenceCount)} mono testId="edge-evidence-count" />

      {/* 6 — claims count */}
      <Row label="claims" value={String(edge.claimCount)} mono testId="edge-claim-count" />

      {edge.reason !== null && edge.reason !== "" ? (
        <Row label="why formed" value={edge.reason} testId="edge-reason" />
      ) : null}

      {edge.observationIds.length > 0 ? (
        <div className="ui-graph-detail-block" data-testid="edge-observations">
          <span className="ui-insp-field-label">records</span>
          <div className="ui-insp-refs">
            {edge.observationIds.slice(0, 6).map((id) => (
              <Button
                key={id}
                size="sm"
                onClick={() => onGoTo({ kind: "Observation", id })}
                title={`Open Observation ${id}`}
                data-testid={`edge-observation-${id}`}
              >
                {id}
              </Button>
            ))}
            {edge.observationIds.length > 6 ? (
              <Tooltip content={`${edge.observationIds.length} records in total`}>
                <span className="ui-rail-hint">+{edge.observationIds.length - 6} more</span>
              </Tooltip>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* 7 — actions. Every one of them moves the analyst somewhere. */}
      <div className="ui-insp-next" data-testid="edge-actions">
        <span className="ui-pane-title">Next</span>
        <div className="ui-insp-next-list">
          {edge.claimId !== null ? (
            <Button
              size="sm"
              onClick={() => onGoTo({ kind: "Claim", id: edge.claimId as string })}
              data-testid="edge-action-claim"
            >
              Open claim {edge.claimId}
            </Button>
          ) : null}
          {actions.map((action) => {
            const destination = destinationForAction(action.id);
            if (destination === null) return null;
            return (
              <Button
                key={action.id}
                size="sm"
                onClick={() => onGoToView(destination)}
                data-testid={`edge-action-${action.id}`}
              >
                {action.label}
              </Button>
            );
          })}
          <Button size="sm" onClick={() => onExpandEdge(edge)} data-testid="edge-action-expand">
            Expand this relation
          </Button>
          <Button size="sm" onClick={() => onGoToView("timeline")} data-testid="edge-action-timeline">
            Show in time window
          </Button>
        </div>
      </div>
    </section>
  );
}

function Participant({
  node,
  side,
  onGoTo,
}: {
  node: GraphNode | null;
  side: string;
  onGoTo: (selection: WorkspaceSelection) => void;
}) {
  if (!node) {
    return (
      <span className="ui-graph-participant" data-testid={`edge-${side}-missing`}>
        <span className="ui-insp-field-label">{side}</span>
        <span className="ui-insp-unreported">not loaded</span>
      </span>
    );
  }
  const route = routeForNode(node);
  const semantics = NODE_SEMANTICS[node.kind];
  return (
    <span className="ui-graph-participant" data-testid={`edge-${side}`}>
      <span className="ui-insp-field-label">{side}</span>
      {route === null ? (
        <span className="ui-body">{semantics.token} {node.identifier}</span>
      ) : (
        <button
          type="button"
          className="ui-insp-link"
          onClick={() => onGoTo(route)}
          title={`Open ${route.kind} ${route.id}`}
          data-testid={`edge-${side}-go`}
        >
          {semantics.token} {node.label}
        </button>
      )}
      <Badge
        tone={node.admission === "admitted" ? "accent" : "neutral"}
        role="classification"
        testId={`edge-${side}-admission`}
      >
        {ADMISSION_LABELS[node.admission ?? "unknown"]}
      </Badge>
    </span>
  );
}

/* ── Node detail ─────────────────────────────────────────────────────── */

export interface NodeDetailsProps {
  node: GraphNode | null;
  model: GraphModel;
  onGoTo: (selection: WorkspaceSelection) => void;
  onGoToView: (view: WorkspaceView) => void;
  onExpandNode: (node: GraphNode) => void;
  onToggleSecondary: (selection: WorkspaceSelection) => void;
  isSecondary: boolean;
}

export function NodeDetails({
  node,
  model,
  onGoTo,
  onGoToView,
  onExpandNode,
  onToggleSecondary,
  isSecondary,
}: NodeDetailsProps) {
  if (!node) {
    return (
      <section className="ui-graph-detail" aria-label="Object detail" data-testid="graph-node-details">
        <EmptyState
          size="sm"
          icon="view-objects"
          title="No object selected"
          description="Click an object to read what the platform reports about it and what anchors it."
          testId="graph-node-empty"
        />
      </section>
    );
  }

  const semantics = NODE_SEMANTICS[node.kind];
  const route = routeForNode(node);
  const actions = route === null ? [] : actionsForSelection(route, 0);
  const relations = model.edges.filter((edge) => edge.source === node.id || edge.target === node.id);

  return (
    <section className="ui-graph-detail" aria-label="Object detail" data-testid="graph-node-details">
      <header className="ui-graph-detail-head">
        <h3 className="ui-pane-title">
          <span className="ui-mono">{semantics.token}</span> {node.label}
        </h3>
        <Badge
          tone={node.admission === "admitted" ? "accent" : node.admission === "rejected" ? "danger" : "neutral"}
          role="classification"
          testId="node-admission"
        >
          {ADMISSION_LABELS[node.admission ?? "unknown"]}
        </Badge>
        {node.provisional ? (
          <Badge tone="gold" role="classification" testId="node-provisional">
            provisional · dashed
          </Badge>
        ) : null}
      </header>

      <Row label="kind" value={semantics.label} testId="node-kind" />
      <Row label="identifier" value={node.identifier} mono testId="node-identifier" />
      <Row
        label="platform status"
        value={node.admissionRaw ?? "not reported"}
        mono
        testId="node-status-raw"
      />
      <Row label="records" value={String(node.evidenceCount)} mono testId="node-evidence-count" />
      <Row label="claims" value={String(node.claimCount)} mono testId="node-claim-count" />
      <Row label="source" value={node.sourceId ?? "not reported"} mono testId="node-source" />
      <Row
        label="observed"
        value={node.observedAt.length === 0 ? "not reported" : node.observedAt.slice(0, 4).join(", ")}
        mono
        testId="node-observed"
      />
      {node.kind === "Hypothesis" && node.originEntityId !== null ? (
        <div className="ui-graph-detail-block" data-testid="node-origin">
          <span className="ui-insp-field-label">candidate of</span>
          <button
            type="button"
            className="ui-insp-link ui-mono"
            onClick={() => onGoTo({ kind: "Entity", id: node.originEntityId as string })}
            title={`Open Entity ${node.originEntityId}`}
            data-testid="node-origin-go"
          >
            {node.originEntityId}
          </button>
        </div>
      ) : null}

      {relations.length > 0 ? (
        <div className="ui-graph-detail-block" data-testid="node-relations">
          <span className="ui-insp-field-label">relations ({relations.length})</span>
          <ul className="ui-menu">
            {relations.slice(0, 8).map((edge) => (
              <li key={edge.id}>
                <span className="ui-graph-relation-line" data-testid={`node-relation-${edge.id}`}>
                  <span className="ui-mono">{edge.predicate}</span>
                  <span className="ui-rail-hint">{edge.family}</span>
                </span>
              </li>
            ))}
            {relations.length > 8 ? (
              <li className="ui-rail-hint">+{relations.length - 8} more</li>
            ) : null}
          </ul>
        </div>
      ) : null}

      <div className="ui-insp-next" data-testid="node-actions">
        <span className="ui-pane-title">Next</span>
        <div className="ui-insp-next-list">
          <Button size="sm" onClick={() => onExpandNode(node)} data-testid="node-action-expand">
            Expand +1 hop
          </Button>
          {actions.map((action) => {
            const destination = destinationForAction(action.id);
            if (destination === null) return null;
            return (
              <Button
                key={action.id}
                size="sm"
                onClick={() => onGoToView(destination)}
                data-testid={`node-action-${action.id}`}
              >
                {action.label}
              </Button>
            );
          })}
          {route !== null ? (
            <Button
              size="sm"
              variant={isSecondary ? "primary" : "default"}
              aria-pressed={isSecondary}
              onClick={() => onToggleSecondary(route)}
              data-testid="node-action-compare"
            >
              {isSecondary ? "In comparison" : "Add to comparison"}
            </Button>
          ) : null}
        </div>
      </div>
    </section>
  );
}

/* ── Shared row ──────────────────────────────────────────────────────── */

function Row({
  label,
  value,
  mono,
  testId,
}: {
  label: string;
  value: string;
  mono?: boolean;
  testId: string;
}) {
  return (
    <div className="ui-insp-field" data-testid={testId}>
      <span className="ui-insp-field-label">{label}</span>
      <span className="ui-insp-field-value" data-mono={mono ? "true" : undefined}>
        {value === "not reported" ? <span className="ui-insp-unreported">not reported</span> : value}
      </span>
    </div>
  );
}

/** The next steps an edge offers, from the one action table (§69, no drift). */
function claimSelectionFor(edge: GraphEdge): Array<{ id: string; label: string }> {
  if (edge.claimId !== null) return [];
  if (edge.observationIds.length === 0) return [];
  return [{ id: "observation.show-source", label: "Show supporting evidence" }];
}