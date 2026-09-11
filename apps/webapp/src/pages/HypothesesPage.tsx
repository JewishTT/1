import { useState } from "react";

import type { CoverageView, HypothesisWithCoverage, RankedOpportunity } from "../lib/science/types";

interface Props {
  hypotheses: HypothesisWithCoverage[];
  plan: RankedOpportunity[];
  coverage: CoverageView | null;
  onRegister?: (projectId: string, text: string) => void;
  onAttach?: (hypothesisId: string) => void;
  onDiscard?: (hypothesisId: string) => void;
  onPlan?: () => void;
  onRefresh?: () => void;
}

export function HypothesesPage({
  hypotheses,
  plan,
  coverage,
  onRegister,
  onAttach,
  onDiscard,
  onPlan,
  onRefresh,
}: Props) {
  const [projectId, setProjectId] = useState("P-science");
  const [text, setText] = useState("");
  const [attachFor, setAttachFor] = useState<string>("");

  return (
    <section data-testid="hypotheses-page">
      <h1>Hypotheses</h1>
      {onRefresh && (
        <button type="button" data-testid="refresh-btn" onClick={onRefresh}>
          Refresh
        </button>
      )}

      <div className="panel">
        <h2>Register a hypothesis</h2>
        <input
          type="text"
          data-testid="project-input"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          placeholder="project id"
        />
        <input
          type="text"
          data-testid="hyp-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="explanatory hypothesis…"
        />
        <button
          type="button"
          data-testid="register-btn"
          onClick={() => {
            if (text.trim() && onRegister) onRegister(projectId, text.trim());
            setText("");
          }}
        >
          Propose
        </button>
      </div>

      <div className="panel">
        <h2>
          Hypothesis list
          {coverage ? (
            <span data-testid="coverage" className="op-label">
              {" "}
              — coverage {coverage.ratio.toFixed(2)} ({coverage.covered}/{coverage.alive} covered)
            </span>
          ) : null}
        </h2>
        {hypotheses.length === 0 ? (
          <p data-testid="no-hypotheses">No hypotheses yet.</p>
        ) : (
          <ul data-testid="hyp-list">
            {hypotheses.map((hyp) => (
              <li
                key={hyp.hypothesis_id}
                data-testid={`hyp-item-${hyp.hypothesis_id}`}
                data-status={hyp.status}
              >
                <strong>{hyp.text}</strong> — {hyp.status}
                {hyp.evidence_count != null ? ` (${hyp.evidence_count} links)` : ""}
                <div className="op-label">
                  <button
                    type="button"
                    data-testid={`attach-${hyp.hypothesis_id}`}
                    onClick={() => {
                      setAttachFor(hyp.hypothesis_id);
                      if (attachFor === hyp.hypothesis_id && onAttach) onAttach(hyp.hypothesis_id);
                      setAttachFor(hyp.hypothesis_id);
                    }}
                  >
                    Attach evidence
                  </button>
                  {onDiscard && hyp.status !== "discarded" && (
                    <button
                      type="button"
                      data-testid={`discard-${hyp.hypothesis_id}`}
                      onClick={() => onDiscard(hyp.hypothesis_id)}
                    >
                      Discard
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel">
        <h2>Information-gain plan</h2>
        {onPlan && (
          <button type="button" data-testid="plan-btn" onClick={onPlan}>
            Run plan
          </button>
        )}
        {plan.length === 0 ? (
          <p data-testid="no-plan">No ranked opportunities yet.</p>
        ) : (
          <ul data-testid="plan-list">
            {plan.map((opp) => (
              <li key={opp.opportunity_id} data-testid={`plan-item-${opp.opportunity_id}`}>
                {opp.opportunity_id} — expected gain {opp.expected_gain.toFixed(4)}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
