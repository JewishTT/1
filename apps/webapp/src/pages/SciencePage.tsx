import { useState } from "react";

import { TDAPanel } from "../components/TDAPanel";
import type {
  ClaimRecord,
  ClaimReviewView,
  InvariantParams,
  InvariantResult,
  LadderGates,
  RobustnessReport,
} from "../lib/science/types";

export interface ScienceClaim extends ClaimRecord {
  review: ClaimReviewView;
}

interface Props {
  claims: ScienceClaim[];
  reports: RobustnessReport[];
  onComment?: (claimId: string, body: string) => void;
  onRefresh?: () => void;
  /** Topology panel is rendered only when the container wires an invariant runner. */
  onInvariant?: (params: InvariantParams) => void;
  invariant?: InvariantResult | null;
  invariantLoading?: boolean;
  invariantError?: string | null;
  entityId?: string;
}

const GATE_LABELS: Array<keyof LadderGates> = [
  "calibrated",
  "null_model",
  "robustness",
  "reproduction",
];

function rungCells(gates: LadderGates): React.ReactNode {
  return GATE_LABELS.map((gate) => (
    <td key={gate} data-testid={`gate-${gate}`}>
      {gates[gate] ? "✔" : "—"}
    </td>
  ));
}

export function SciencePage({
  claims,
  reports,
  onComment,
  onRefresh,
  onInvariant,
  invariant,
  invariantLoading = false,
  invariantError = null,
  entityId = "ENT-2001",
}: Props) {
  const [commentText, setCommentText] = useState<Record<string, string>>({});

  return (
    <section data-testid="science-page">
      <h1>Scientific review</h1>
      {onRefresh && (
        <button type="button" data-testid="refresh-btn" onClick={onRefresh}>
          Refresh
        </button>
      )}

      <div className="panel">
        <h2>Evidence ladder</h2>
        <p className="op-label">
          Top rung (4) requires calibration + null model + robustness + reproduction artifacts
          (FR-013).
        </p>
        {claims.length === 0 ? (
          <p data-testid="no-claims">No claims registered.</p>
        ) : (
          <table data-testid="ladder-table">
            <thead>
              <tr>
                <th>Claim</th>
                <th>Status</th>
                <th>Calibrated</th>
                <th>Null</th>
                <th>Robustness</th>
                <th>Reproduction</th>
                <th>Rung</th>
                <th>Review state</th>
              </tr>
            </thead>
            <tbody>
              {claims.map((claim) => (
                <tr key={claim.claim_id} data-testid="ladder-row">
                  <td data-testid="claim-statement">{claim.statement}</td>
                  <td>{claim.status}</td>
                  {rungCells(claim.review.gates)}
                  <td data-testid="ladder-position">
                    {claim.review.ladder_position ?? "—"} / {claim.review.top_rung}
                  </td>
                  <td>
                    <span
                      data-testid="review-state"
                      data-pending={claim.review.review_state === "review_pending"}
                    >
                      {claim.review.review_state === "review_pending"
                        ? "REVIEW_PENDING"
                        : claim.review.review_state.toUpperCase()}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <h2>Robustness context</h2>
        {reports.length === 0 ? (
          <p data-testid="no-reports">No robustness reports recorded.</p>
        ) : (
          <ul data-testid="report-list">
            {reports.map((report) => (
              <li key={report.report_id} data-testid="report-item">
                {report.report_id} → claim {report.claim_ref}: flip rates [missing{" "}
                {report.flip_rates.missing}, flip {report.flip_rates.flip}, subsample{" "}
                {report.flip_rates.biased_subsample}]
                {report.downgraded_to_uncertain ? " (claim downgraded to UNCERTAIN)" : ""}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel">
        <h2>Review comments</h2>
        {claims.map((claim) => (
          <div key={claim.claim_id} className="op-tile" data-testid="comment-block">
            <p>
              {claim.claim_id} — {claim.statement}
            </p>
            <input
              type="text"
              data-testid={`comment-input-${claim.claim_id}`}
              value={commentText[claim.claim_id] ?? ""}
              onChange={(e) => setCommentText({ ...commentText, [claim.claim_id]: e.target.value })}
              placeholder="Add a review comment…"
            />
            <button
              type="button"
              data-testid={`comment-btn-${claim.claim_id}`}
              onClick={() => {
                const body = (commentText[claim.claim_id] ?? "").trim();
                if (body && onComment) onComment(claim.claim_id, body);
                setCommentText({ ...commentText, [claim.claim_id]: "" });
              }}
            >
              Comment
            </button>
          </div>
        ))}
      </div>

      {onInvariant && (
        <div className="panel">
          <h2>Topology · persistence invariant</h2>
          <p className="op-label">
            Series → Takens delay embedding → VR persistence (pure-python, no gudhi) → barcode +
            digest + drift. Results are structural shape descriptors (I-6), not identity claims.
          </p>
          <TDAPanel
            entityId={entityId}
            result={invariant ?? null}
            loading={invariantLoading}
            error={invariantError ?? null}
            onRun={onInvariant}
          />
        </div>
      )}
    </section>
  );
}
