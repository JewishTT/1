import { confidenceColor, confidenceLabel } from "../lib/donor/confidence";
import { formatLinkReason } from "../lib/donor/links";
import { lookupRelationshipType } from "../lib/donor/relationshipTypes";
import type { DerivedNodeReviewStatus } from "../lib/donor/review";

export interface LineageNode {
  id: string;
  kind: "finding" | "feature" | "assertion" | "evidence" | "observation" | "source";
  label: string;
  confidence?: number;
}

export interface LineageEdge {
  from: string;
  to: string;
  relation: string;
}

export type ReviewDecisionValue = "ACCEPT" | "REJECT" | "UNCERTAIN";

export interface LineageFact {
  id: string;
  label: string;
  at: string;
}

interface Props {
  nodes: LineageNode[];
  edges: LineageEdge[];
  onReview?: (decision: ReviewDecisionValue, node: LineageNode) => void;
  /** Per-subject fact list (feature 005 US6): rendered grouped by subject, date-ordered. */
  factsBySubject?: Record<string, LineageFact[]>;
  /** Review status badges per subject (feature 005 US6, vitni review model). */
  nodeReviewStatuses?: Map<string, DerivedNodeReviewStatus>;
}

const KIND_LABEL: Record<LineageNode["kind"], string> = {
  finding: "Finding",
  feature: "Feature",
  assertion: "Assertion",
  evidence: "Evidence",
  observation: "Observation",
  source: "Raw source",
};

export function LineageWalker({ nodes, edges, onReview, factsBySubject, nodeReviewStatuses }: Props) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const ordered: LineageNode[] = [
    "finding",
    "feature",
    "assertion",
    "evidence",
    "observation",
    "source",
  ]
    .map((kind): LineageNode[] => nodes.filter((n) => n.kind === kind))
    .flat();

  const factSubjects = Object.entries(factsBySubject ?? {}).map(([subjectId, facts]) => ({
    subjectId,
    facts: [...facts].sort((a, b) => a.at.localeCompare(b.at)),
  }));

  return (
    <section data-testid="lineage-walker">
      <h2>Lineage</h2>
      <p className="lineage-legend">
        Finding → feature → graph/assertion → evidence → observation → raw source
      </p>
      {ordered.length === 0 ? (
        <p className="lineage-empty">No lineage yet.</p>
      ) : edges.length === 0 ? (
        <ol className="lineage-chain" data-testid="lineage-chain">
          {ordered.map((n, i) => (
            <li key={`${n.kind}-${i}`} className="lineage-step">
              <span className={`node-${n.kind}`} data-testid={`node-${n.kind}`}>
                {KIND_LABEL[n.kind]}: {n.label}
                {renderReviewStatus(n, nodeReviewStatuses)}
                {n.kind === "assertion" && (
                  <span className="review-control" data-testid="review-control">
                    {(["ACCEPT", "REJECT", "UNCERTAIN"] as const).map((d) => (
                      <button
                        key={d}
                        type="button"
                        className={`review-btn review-${d.toLowerCase()}`}
                        data-testid={`review-${d.toLowerCase()}`}
                        onClick={() => onReview?.(d, n)}
                      >
                        {d}
                      </button>
                    ))}
                  </span>
                )}
              </span>
              {i < ordered.length - 1 && <span className="edge-relation">→</span>}
            </li>
          ))}
        </ol>
      ) : (
        <ol className="lineage-chain" data-testid="lineage-chain">
          {edges.map((edge, i) => {
            const from = byId.get(edge.from);
            const via = byId.get(edge.to);
            const relation =
              lookupRelationshipType(edge.relation)?.label ?? formatLinkReason(edge.relation);
            return (
              <li key={`${edge.from}-${edge.to}-${i}`} className="lineage-step">
                <span className={`node-${from?.kind}`} data-testid={`node-${from?.kind}`}>
                  {KIND_LABEL[from?.kind ?? "observation"]}: {from?.label ?? edge.from}
                  {typeof from?.confidence === "number" && (
                    <span
                      className="confidence-badge"
                      data-testid={`confidence-${from.id}`}
                      style={{ color: confidenceColor(from.confidence) }}
                    >
                      {confidenceLabel(from.confidence)}
                    </span>
                  )}
                  {renderReviewStatus(from, nodeReviewStatuses)}
                  {from?.kind === "assertion" && (
                    <span className="review-control" data-testid="review-control">
                      {(["ACCEPT", "REJECT", "UNCERTAIN"] as const).map((d) => (
                        <button
                          key={d}
                          type="button"
                          className={`review-btn review-${d.toLowerCase()}`}
                          data-testid={`review-${d.toLowerCase()}`}
                          onClick={() => onReview?.(d, from)}
                        >
                          {d}
                        </button>
                      ))}
                    </span>
                  )}
                </span>
                <span className="edge-relation">{relation}</span>
                {via && (
                  <span className={`node-${via.kind}`} data-testid={`node-${via.kind}`}>
                    {KIND_LABEL[via.kind]}: {via.label}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      )}

      {factSubjects.length > 0 && (
        <div className="lineage-facts" data-testid="lineage-facts">
          <h3>Per-subject facts</h3>
          {factSubjects.map(({ subjectId, facts }) => (
            <div key={subjectId} className="lineage-fact-group" data-testid={`facts-${subjectId}`}>
              <h4>{byId.get(subjectId)?.label ?? subjectId}</h4>
              <ol className="lineage-fact-list">
                {facts.map((fact) => (
                  <li key={fact.id} className="lineage-fact" data-testid={`fact-${fact.id}`}>
                    <time dateTime={fact.at}>{fact.at}</time>
                    <span>{fact.label}</span>
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function renderReviewStatus(
  node: LineageNode | undefined,
  statuses: Map<string, DerivedNodeReviewStatus> | undefined,
) {
  if (!node || !statuses) return null;
  const status = statuses.get(node.id);
  if (!status) return null;
  const toneLabel =
    status.reviewTone === "clear"
      ? "clear"
      : status.reviewTone === "conflict"
        ? "needs attention"
        : "needs review";
  return (
    <span
      className="node-review-status"
      data-testid={`review-status-${node.id}`}
      title={`review=${status.reviewTone}, evidence=${status.evidenceTone}`}
    >
      {toneLabel}
      {status.evidenceTone === "gap" ? " · evidence gap" : ""}
    </span>
  );
}
