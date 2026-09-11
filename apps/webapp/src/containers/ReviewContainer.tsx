import { useEffect, useMemo, useState } from "react";

import {
  api,
  ResolutionPair,
  ReviewDecision,
} from "../lib/api";
import { CONFIDENCE_COLOR, CONFIDENCE_LABEL, Confidence } from "../lib/donor/confidence";
import {
  DEFAULT_REVIEW_FILTERS,
  ReviewAssertion,
  ReviewFilters,
  SourceRecord,
  buildDerivedReviewAssertions,
  buildNodeReviewStatusMap,
  filterReviewAssertions,
} from "../lib/donor/review";

const STATE_COLOR: Record<ReviewAssertion["review_state"], string> = {
  unreviewed: "#2f6f9f",
  disputed: "#d97706",
  rejected: "#b42318",
  accepted: "#2e7d4f",
};

const EVIDENCE_LABEL: Record<string, string> = {
  none: "No evidence",
  single: "Single source",
  multiple: "Multiple sources",
};

interface Props {
  investigationId: string;
}

export function ReviewContainer({ investigationId }: Props) {
  const [pairs, setPairs] = useState<ResolutionPair[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<ReviewFilters>(DEFAULT_REVIEW_FILTERS);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.listResolutions(investigationId);
      setPairs(data.pairs);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // reload only when the investigation changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [investigationId]);

  const assertions = useMemo(() => pairsToReviewAssertions(pairs), [pairs]);
  const derived = useMemo(
    () => buildDerivedReviewAssertions(assertions, EMPTY_SOURCES, { nodes: [] }),
    [assertions],
  );
  const items = useMemo(() => filterReviewAssertions(derived, filters), [derived, filters]);
  const statusMap = useMemo(() => buildNodeReviewStatusMap(derived), [derived]);

  const handleDecide = async (pairKey: string, decision: ReviewDecision) => {
    try {
      await api.decideResolution(investigationId, pairKey, decision);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
    await load();
  };

  const setFilter = <K extends keyof ReviewFilters>(key: K, value: ReviewFilters[K]) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <section data-testid="review-queue" className="panel">
      <h2>Resolution review queue</h2>

      <div className="review-filters" data-testid="review-filters">
        <input
          aria-label="Filter review queue"
          placeholder="Filter by pair, subject or source…"
          value={filters.query}
          onChange={(e) => setFilter("query", e.target.value)}
        />
        <select
          aria-label="Review state"
          value={filters.reviewState}
          onChange={(e) =>
            setFilter("reviewState", e.target.value as ReviewFilters["reviewState"])
          }
        >
          <option value="all">Any state</option>
          <option value="unreviewed">Unreviewed</option>
          <option value="disputed">Disputed</option>
          <option value="rejected">Rejected</option>
          <option value="accepted">Accepted</option>
        </select>
        <select
          aria-label="Evidence"
          value={filters.evidence}
          onChange={(e) => setFilter("evidence", e.target.value as ReviewFilters["evidence"])}
        >
          <option value="all">Any evidence</option>
          <option value="none">No evidence</option>
          <option value="weak">Weak evidence</option>
        </select>
        <select
          aria-label="Confidence"
          value={filters.confidence}
          onChange={(e) => setFilter("confidence", e.target.value as ReviewFilters["confidence"])}
        >
          <option value="all">Any confidence</option>
          {(["verified", "unverified", "asserted"] as Confidence[]).map((c) => (
            <option key={c} value={c}>
              {CONFIDENCE_LABEL[c]}
            </option>
          ))}
        </select>
        <select
          aria-label="Sort"
          value={filters.sort}
          onChange={(e) => setFilter("sort", e.target.value as ReviewFilters["sort"])}
        >
          <option value="unreviewed_first">Unreviewed first</option>
          <option value="newest">Newest</option>
          <option value="oldest">Oldest</option>
          <option value="weakest_evidence">Weakest evidence</option>
        </select>
      </div>

      {error && <p className="review-error">Error: {error}</p>}
      {loading ? (
        <p className="review-empty">Loading review queue…</p>
      ) : items.length === 0 ? (
        <p className="review-empty" data-testid="review-queue-empty">
          Nothing to review yet.
        </p>
      ) : (
        <ol className="review-queue-items" data-testid="review-queue-items">
          {items.map((item) => {
            const nodeStatus = statusMap.get(item.subject_id);
            return (
              <li key={item.id} className="review-item" data-testid={`review-item-${item.id}`}>
                <div className="review-item-head">
                  <span className="review-subject" data-testid="review-subject">
                    {item.subjectLabel}
                  </span>
                  <span
                    className="review-state-badge"
                    data-testid="review-state-badge"
                    style={{ color: STATE_COLOR[item.review_state] }}
                  >
                    {item.review_state}
                  </span>
                  {item.conflictStatus === "conflict" && (
                    <span className="review-conflict" data-testid="review-conflict">
                      conflict
                    </span>
                  )}
                </div>
                <p className="review-path">{item.path}</p>
                <p className="review-value" data-testid="review-value">
                  {item.valueSummary}
                </p>
                <div className="review-item-meta">
                  <span
                    className="confidence-badge"
                    data-testid={`review-confidence-${item.id}`}
                    style={{ color: CONFIDENCE_COLOR[item.confidence] }}
                  >
                    {CONFIDENCE_LABEL[item.confidence]}
                  </span>
                  <span className="review-evidence" data-testid="review-evidence">
                    {EVIDENCE_LABEL[item.evidenceStatus]}
                  </span>
                  {item.corroborationCount > 0 && (
                    <span className="review-corroboration">
                      +{item.corroborationCount} corroborating
                    </span>
                  )}
                  {nodeStatus && (
                    <span
                      className="review-tone"
                      data-testid="review-tone"
                      title={`review=${nodeStatus.reviewTone}, evidence=${nodeStatus.evidenceTone}`}
                    >
                      {nodeStatus.evidenceTone === "supported" ? "supported" : "evidence gap"}
                    </span>
                  )}
                  {item.review_state === "unreviewed" && (
                    <span className="review-actions" data-testid="review-actions">
                      {(["ACCEPT", "REJECT", "UNCERTAIN"] as ReviewDecision[]).map((d) => (
                        <button
                          key={d}
                          type="button"
                          data-testid={`decide-${item.id}-${d.toLowerCase()}`}
                          onClick={() => void handleDecide(item.subject_id, d)}
                        >
                          {d}
                        </button>
                      ))}
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

/** Resolution reviews don't describe source records (no source table yet). */
const EMPTY_SOURCES: SourceRecord[] = [];

export function pairsToReviewAssertions(pairs: ResolutionPair[]): ReviewAssertion[] {
  return pairs.map((pair) => ({
    id: pair.review_id,
    subject_id: pair.pair_key,
    path: "resolution-candidate",
    value: { pair_key: pair.pair_key },
    source_id: null,
    review_state: reviewStateFromDecision(pair.decision),
    confidence: confidenceFromDecision(pair.decision),
    created_at: Date.parse(pair.reviewed_at) || 0,
  }));
}

function reviewStateFromDecision(decision: string): ReviewAssertion["review_state"] {
  switch (decision) {
    case "ACCEPT":
      return "accepted";
    case "REJECT":
      return "rejected";
    case "UNCERTAIN":
      return "disputed";
    default:
      return "unreviewed";
  }
}

function confidenceFromDecision(decision: string): Confidence {
  switch (decision) {
    case "ACCEPT":
      return "verified";
    case "REJECT":
      return "asserted";
    default:
      return "unverified";
  }
}