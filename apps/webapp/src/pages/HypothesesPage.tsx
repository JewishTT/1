import { useRef, useState } from "react";

import type { HypothesisWithCoverage, RankedOpportunity } from "../lib/science/types";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/Feedback";

/**
 * The coverage read-out, shaped by what the endpoint actually serves.
 *
 * `CoverageView` in `lib/science/types.ts` declares `covered` and `ratio`; the
 * endpoint `GET /api/science/hypotheses/coverage` serves neither. It answers
 * `{project_id, hypotheses, alive, dead, with_evidence, without_evidence,
 * evidence_links, direction_counts, requirements_covered}` (see
 * `apps/science/hypotheses/coverage.py`), so `ratio` arrives as `undefined` while
 * the type says it is a `number`.
 *
 * That gap is what blanked `/hypotheses`. `coverage.ratio.toFixed(2)` on an absent
 * `ratio` threw `TypeError: Cannot read properties of undefined (reading 'toFixed')`
 * during render; React unmounted the tree and `#root` ended up empty, with the
 * hypotheses list — which was empty and would have rendered an empty state — never
 * reached. A field a type promises is not a field a payload carries, so every field
 * here is optional and every read goes through `finiteOrNull`.
 */
interface CoverageReadout {
  project_id?: string;
  alive?: number;
  covered?: number;
  /** The name the endpoint uses for `covered`. Both are read; neither is assumed. */
  with_evidence?: number;
  ratio?: number;
}

interface Props {
  hypotheses: HypothesisWithCoverage[];
  plan: RankedOpportunity[];
  coverage: CoverageReadout | null;
  onRegister?: (projectId: string, text: string) => void;
  onAttach?: (hypothesisId: string) => void;
  onDiscard?: (hypothesisId: string) => void;
  onPlan?: () => void;
  onRefresh?: () => void;
}

/**
 * A number the payload actually carried, or null.
 *
 * `null` and not `0` is the whole point: an unmeasured count and a measured zero are
 * different facts, and collapsing them renders a claim nobody made.
 */
function finiteOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** A non-empty string the payload carried, or null. */
function textOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

/**
 * Everything the coverage panel is allowed to say, assembled only from numbers the
 * payload carried. Null when it can say nothing true: the heading then carries no
 * coverage claim at all rather than a fabricated `0.00`.
 */
function coverageNote(coverage: CoverageReadout | null): string | null {
  if (coverage === null) return null;
  const parts: string[] = [];
  const ratio = finiteOrNull(coverage.ratio);
  const alive = finiteOrNull(coverage.alive);
  const covered = finiteOrNull(coverage.covered) ?? finiteOrNull(coverage.with_evidence);
  if (ratio !== null) parts.push(`coverage ${ratio.toFixed(2)}`);
  // With no alive hypothesis there is no population to be covered. `0/0` states
  // nothing, and a ratio of zero would claim a measurement nobody took.
  if (covered !== null && alive !== null && alive > 0) parts.push(`(${covered}/${alive} covered)`);
  return parts.length > 0 ? parts.join(" ") : null;
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
  const textRef = useRef<HTMLInputElement>(null);

  // A payload that omits a collection is an empty collection, not a crash. The page is
  // reachable from a route that renders it before its fetch settles, and every list
  // here is `.map`ped, so the guard belongs here rather than in one caller.
  const rows = Array.isArray(hypotheses) ? hypotheses : [];
  const opportunities = Array.isArray(plan) ? plan : [];
  const note = coverageNote(coverage);

  return (
    <section data-testid="hypotheses-page">
      <h1>Hypotheses</h1>
      {onRefresh && (
        <div className="panel-actions">
          <Button size="sm" variant="ghost" data-testid="refresh-btn" onClick={onRefresh}>
            Refresh
          </Button>
        </div>
      )}

      <div className="panel">
        <h2>Register a hypothesis</h2>
        <div className="panel-actions">
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
            ref={textRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="explanatory hypothesis…"
          />
          <Button
            data-testid="register-btn"
            onClick={() => {
              if (text.trim() && onRegister) onRegister(projectId, text.trim());
              setText("");
            }}
          >
            Propose
          </Button>
        </div>
      </div>

      <div className="panel">
        <h2>
          Hypothesis list
          {note !== null && (
            <span data-testid="coverage" className="op-label">
              {" "}
              — {note}
            </span>
          )}
        </h2>
        {rows.length === 0 ? (
          <EmptyState
            icon="list"
            title="No hypotheses recorded"
            description="Nothing has been proposed for this project. A hypothesis names something that would explain an observation if it were true, and until one is proposed there is nothing here for the fabric to weigh."
            action={
              <Button size="sm" onClick={() => textRef.current?.focus()}>
                Propose one
              </Button>
            }
            testId="no-hypotheses"
          />
        ) : (
          <ul data-testid="hyp-list">
            {rows.map((hyp, index) => {
              const id = textOrNull(hyp.hypothesis_id);
              // An unnamed record still renders, keyed by position: dropping it would
              // hide a row the server returned, and two `undefined` keys collide.
              const key = id ?? `unidentified-${index}`;
              const links = finiteOrNull(hyp.evidence_count);
              return (
                <li key={key} data-testid={`hyp-item-${key}`} data-status={hyp.status ?? undefined}>
                  <strong>{textOrNull(hyp.text) ?? "Unnamed hypothesis"}</strong>
                  {textOrNull(hyp.status) !== null && ` — ${hyp.status}`}
                  {links !== null && ` (${links} links)`}
                  <div className="panel-actions">
                    <Button
                      size="sm"
                      variant="ghost"
                      data-testid={`attach-${key}`}
                      disabled={id === null}
                      onClick={() => {
                        if (id === null) return;
                        setAttachFor(id);
                        if (attachFor === id && onAttach) onAttach(id);
                      }}
                    >
                      Attach evidence
                    </Button>
                    {onDiscard && id !== null && hyp.status !== "discarded" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        data-testid={`discard-${key}`}
                        onClick={() => onDiscard(id)}
                      >
                        Discard
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="panel">
        <h2>Information-gain plan</h2>
        {onPlan && (
          <div className="panel-actions">
            <Button size="sm" data-testid="plan-btn" onClick={onPlan}>
              Run plan
            </Button>
          </div>
        )}
        {opportunities.length === 0 ? (
          <EmptyState
            icon="diagram"
            title="No ranked opportunities"
            description="The gain planner has not ranked anything yet. Run the plan above to score which untested hypothesis would move the account first."
            testId="no-plan"
          />
        ) : (
          <ul data-testid="plan-list">
            {opportunities.map((opp, index) => {
              const id = textOrNull(opp.opportunity_id) ?? `unranked-${index}`;
              const gain = finiteOrNull(opp.expected_gain);
              return (
                <li key={id} data-testid={`plan-item-${id}`}>
                  {id} —{" "}
                  {gain === null
                    ? "expected gain not reported"
                    : `expected gain ${gain.toFixed(4)}`}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
