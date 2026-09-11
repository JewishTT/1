import { useCallback, useState } from "react";

import { LineageNode, LineageWalker, ReviewDecisionValue } from "../components/LineageWalker";
import { GraphElement, GraphPanel } from "../components/GraphPanel";

export interface FindingView {
  finding_id: string;
  status: string;
  why_detected: string;
  structural_evidence: Array<Record<string, unknown>>;
  semantic_evidence: Array<Record<string, unknown>>;
  supporting_graph_region: Record<string, unknown>;
  supporting_assertions: string[];
  observations: Array<{ observation_id: string; uri: string; immutable: boolean }>;
  sources: string[];
  evidence_resolves: boolean;
}

interface Props {
  finding: FindingView;
  lineage: LineageNode[];
  graphElements?: GraphElement[];
  reviewApi?: typeof submitReview;
}

/** Vitni pattern: analyst review persisted as immutable provenance (FR-006). */
export async function submitReview(
  targetId: string,
  decision: ReviewDecisionValue,
  targetType: string = "assertion",
): Promise<{ ok: boolean; review_id?: string }> {
      const res = await fetch(`/api/v1/entities/${encodeURIComponent(targetId)}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, reasoning: "", target_type: targetType }),
  });
  if (!res.ok) return { ok: false };
  const body = await res.json();
  return { ok: true, review_id: body?.review?.review_id };
}

export function FindingViewPage({ finding, lineage, graphElements = [], reviewApi = submitReview }: Props) {
  const [reviews, setReviews] = useState<Record<string, ReviewDecisionValue>>({});

  const handleReview = useCallback(
    async (decision: ReviewDecisionValue, node: LineageNode) => {
      const targetType = node.kind === "assertion" ? "assertion" : "candidate";
      const result = await reviewApi(node.id, decision, targetType);
      if (result.ok) {
        setReviews((prev) => ({ ...prev, [node.id]: decision }));
      }
    },
    [reviewApi],
  );

  return (
    <section data-testid="finding-view" data-finding-id={finding.finding_id}>
      <h1>{finding.finding_id}</h1>
      <p data-testid="reason">Why detected: {finding.why_detected}</p>
      <p data-testid="resolves">
        {finding.evidence_resolves
          ? "Evidence chain resolves to immutable observations (I-1)."
          : "Evidence chain is broken."}
      </p>

      <div className="panel">
        <h2>Supporting graph region</h2>
        <pre data-testid="graph-region">
          {JSON.stringify(finding.supporting_graph_region, null, 2)}
        </pre>
      </div>

      <div className="panel">
        <h2>Observations + raw sources</h2>
        <ul data-testid="observation-sources">
          {finding.observations.map((o) => (
            <li key={o.observation_id} data-testid="observation-source">
              <code>{o.observation_id}</code> — {o.uri}
            </li>
          ))}
        </ul>
      </div>

      <div className="panel">
        <h2>Analyst review</h2>
        {Object.keys(reviews).length === 0 ? (
          <p data-testid="review-status">No review decisions yet.</p>
        ) : (
          <ul data-testid="review-status">
            {Object.entries(reviews).map(([id, decision]) => (
              <li key={id} data-testid={`review-status-${id}`}>
                {id}: {decision} (provenance recorded)
              </li>
            ))}
          </ul>
        )}
      </div>

      {lineage.length > 0 && <LineageWalker nodes={lineage} edges={[]} onReview={handleReview} />}
      {graphElements.length > 0 && (
        <GraphPanel elements={graphElements} title="Finding graph region" />
      )}
    </section>
  );
}
