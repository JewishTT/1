import { Badge } from "../ui/Badge";
import { EmptyState } from "../ui/Feedback";
import type { WorkspaceSelection } from "../workspace/types";
import {
  DERIVATION_STEP_ORDER,
  EVIDENCE_STEP_ORDER,
  assertChainsSeparate,
  routeDerivationStep,
  routeEvidenceStep,
  type DerivationLineageChain,
  type EvidenceLineageChain,
  type LineageModel,
} from "./lineage";
import { chainSummary } from "./lineageBuilder";

/**
 * LineageViewer (§31, §32).
 *
 * TWO CHAINS, RENDERED AS TWO CHAINS.
 *
 * The visual argument matters as much as the type argument. The evidence chain
 * reads top-down — Finding at the top, Source at the bottom — with a downward
 * arrow between rungs, because that is the direction provenance flows. The
 * derivation chain reads BOTTOM-UP — Claim at the bottom, Observation at the top
 * — with an upward arrow, because that is the direction a claim was arrived at.
 *
 * Two opposite directions on one screen is the clearest possible signal that
 * these are two different questions. A single merged chain with one arrow
 * direction is what the legacy walker does, and it is indistinguishable from
 * one long provenance list.
 *
 * Every node is a real button that routes to the inspector via the global
 * selection (§7). A node whose rung has no `WorkspaceObjectKind` renders as
 * static text with a stated reason — never as a button that goes nowhere (§69).
 *
 * `assertChainsSeparate` runs on every render. If server data ever arrives with
 * a derivation rung in the provenance chain, the viewer says so in the data
 * rather than drawing it, because drawing it would be the lie this component
 * exists to avoid.
 */

export interface LineageViewerProps {
  model: LineageModel;
  /** Route a node to the inspector. One global selection, written here only. */
  onGoTo: (selection: WorkspaceSelection) => void;
  /** The selected object's id, so its rung is marked. */
  selectedId: string | null;
  loading?: boolean;
}

export function LineageViewer({ model, onGoTo, selectedId, loading = false }: LineageViewerProps) {
  const separation = assertChainsSeparate(model);

  return (
    <section className="ui-lineage" aria-label="Lineage" data-testid="lineage-viewer">
      <header className="ui-lineage-head">
        <h3 className="ui-pane-title">Lineage</h3>
        <Badge tone="neutral" testId="lineage-evidence-summary">
          evidence: {chainSummary(model.evidence)}
        </Badge>
        <Badge tone="neutral" testId="lineage-derivation-summary">
          derivation: {chainSummary(model.derivation)}
        </Badge>
      </header>

      {!separation.separated ? (
        <div className="ui-lineage-violation" role="alert" data-testid="lineage-violation">
          <Badge tone="danger" role="classification">
            chains mixed
          </Badge>
          <ul>
            {separation.violations.map((violation) => (
              <li key={violation}>{violation}</li>
            ))}
          </ul>
          <p className="ui-rail-hint">
            The two chains are drawn separately below. The entries above are what failed
            the separation check.
          </p>
        </div>
      ) : null}

      {loading ? (
        <p className="ui-rail-hint" data-testid="lineage-loading">
          Reading the record…
        </p>
      ) : null}

      <EvidenceChainView chain={model.evidence} onGoTo={onGoTo} selectedId={selectedId} />
      <DerivationChainView chain={model.derivation} onGoTo={onGoTo} selectedId={selectedId} />
    </section>
  );
}

/* ── Evidence chain (§31) ────────────────────────────────────────────── */

function EvidenceChainView({
  chain,
  onGoTo,
  selectedId,
}: {
  chain: EvidenceLineageChain | null;
  onGoTo: (selection: WorkspaceSelection) => void;
  selectedId: string | null;
}) {
  if (chain === null) {
    return (
      <section className="ui-lineage-chain" data-testid="evidence-chain-empty" aria-label="Evidence lineage">
        <ChainHeader
          title="Evidence lineage"
          caption="Finding → Claim → Evidence → Observation → Capture → Raw object → Source"
          testId="evidence-chain-header"
        />
        <EmptyState
          size="sm"
          icon="view-evidence"
          title="No evidence lineage for this record"
          description="Provenance runs from a finding down to the bytes it rests on. Select a finding, a claim or an observation to read its chain."
          testId="evidence-chain-none"
        />
      </section>
    );
  }

  return (
    <section className="ui-lineage-chain" data-testid="evidence-chain" aria-label="Evidence lineage">
      <ChainHeader
        title="Evidence lineage"
        caption="what this rests on, read downwards to the source"
        testId="evidence-chain-header"
        missing={chain.missingRungs}
      />
      {chain.steps.length === 0 ? (
        <EmptyState
          size="sm"
          icon="view-evidence"
          title="No rung has a record"
          description="Every rung on the provenance spine is empty for this record, which is itself the answer: nothing has been traced yet."
          testId="evidence-chain-none"
        />
      ) : (
        <ol className="ui-lineage-steps" data-direction="down">
          {chain.steps.map((step, position) => {
            const route = routeEvidenceStep(step);
            const last = position === chain.steps.length - 1;
            return (
              <li key={step.kind} className="ui-lineage-step" data-testid={`evidence-step-${step.kind}`}>
                <StepButton
                  label={step.kind}
                  ref_={step.ref}
                  detail={step.note}
                  at={step.at}
                  route={route}
                  selected={selectedId !== null && selectedId === step.ref}
                  onGoTo={onGoTo}
                  testId={`evidence-node-${step.kind}`}
                />
                {last ? null : (
                  <span className="ui-lineage-arrow" aria-hidden="true" data-testid={`evidence-arrow-${step.kind}`}>
                    ↓
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

/* ── Derivation chain (§32) ──────────────────────────────────────────── */

function DerivationChainView({
  chain,
  onGoTo,
  selectedId,
}: {
  chain: DerivationLineageChain | null;
  onGoTo: (selection: WorkspaceSelection) => void;
  selectedId: string | null;
}) {
  return (
    <section
      className="ui-lineage-chain"
      data-testid="derivation-chain"
      aria-label="Derivation lineage"
      data-empty={chain === null ? "true" : "false"}
    >
      <ChainHeader
        title="Derivation lineage"
        caption="how the claim was arrived at, read upwards from the observation"
        testId="derivation-chain-header"
        missing={chain?.missingRungs ?? []}
      />
      {chain === null || chain.steps.length === 0 ? (
        <EmptyState
          size="sm"
          icon="view-analysis"
          title="No derivation chain"
          description="A derivation chain says which candidate, on which signal, over which observation produced a claim. No endpoint serves that trail yet, so there is nothing to draw — and nothing is inferred from the provenance chain to fill the gap."
          testId="derivation-chain-none"
        />
      ) : (
        <ol className="ui-lineage-steps" data-direction="up">
          {chain.steps.map((step, position) => {
            const route = routeDerivationStep(step);
            const last = position === chain.steps.length - 1;
            return (
              <li key={step.kind} className="ui-lineage-step" data-testid={`derivation-step-${step.kind}`}>
                <StepButton
                  label={step.kind}
                  ref_={step.ref}
                  detail={step.relation}
                  at={[]}
                  score={step.score}
                  route={route}
                  selected={selectedId !== null && selectedId === step.ref}
                  onGoTo={onGoTo}
                  testId={`derivation-node-${step.kind}`}
                />
                {last ? null : (
                  <span className="ui-lineage-arrow" aria-hidden="true" data-testid={`derivation-arrow-${step.kind}`}>
                    ↑
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

/* ── Shared parts ────────────────────────────────────────────────────── */

function ChainHeader({
  title,
  caption,
  testId,
  missing,
}: {
  title: string;
  caption: string;
  testId: string;
  missing?: ReadonlyArray<string>;
}) {
  return (
    <header className="ui-lineage-chain-head" data-testid={testId}>
      <span className="ui-pane-title">{title}</span>
      <span className="ui-rail-hint">{caption}</span>
      {missing != null && missing.length > 0 ? (
        <Tooltipish
          message={`${missing.length} rung(s) have no record: ${missing.join(", ")}`}
          testId={`${testId}-missing`}
        />
      ) : null}
    </header>
  );
}

/** A one-line tooltip without pulling in the Overlay primitive's anchor span. */
function Tooltipish({ message, testId }: { message: string; testId: string }) {
  return (
    <span className="ui-rail-hint" title={message} data-testid={testId}>
      {message}
    </span>
  );
}

interface StepButtonProps {
  label: string;
  ref_: string | null;
  detail: string | null;
  at: ReadonlyArray<string>;
  score?: number | null;
  route: WorkspaceSelection | null;
  selected: boolean;
  onGoTo: (selection: WorkspaceSelection) => void;
  testId: string;
}

function StepButton({ label, ref_, detail, at, score, route, selected, onGoTo, testId }: StepButtonProps) {
  const body = (
    <>
      <span className="ui-lineage-step-label">{label}</span>
      <span className="ui-lineage-step-ref ui-mono">{ref_ ?? "not reported"}</span>
      {detail !== null && detail !== "" ? <span className="ui-lineage-step-detail">{detail}</span> : null}
      {at.length > 0 ? <span className="ui-lineage-step-at ui-mono">{at[0]}</span> : null}
      {score != null && score !== null ? (
        <span className="ui-lineage-step-score ui-mono" data-testid={`${testId}-score`}>
          {score}
        </span>
      ) : null}
    </>
  );

  return (
    <span className="ui-lineage-node" data-kind={label} data-selected={selected} data-testid={testId}>
      {route === null ? (
        // No route means no button. A node the inspector cannot open is not a
        // control, and rendering it as one is §69's dead end with a different
        // shape.
        <span className="ui-lineage-node-static" data-testid={`${testId}-static`}>
          {body}
          <span className="ui-rail-hint">no inspector route for this rung</span>
        </span>
      ) : (
        <button
          type="button"
          className="ui-lineage-node-button"
          onClick={() => onGoTo(route)}
          title={`Open ${route.kind} ${route.id}`}
          aria-current={selected ? "true" : undefined}
          data-testid={`${testId}-go`}
        >
          {body}
        </button>
      )}
    </span>
  );
}

/** The rung vocabularies, re-exported so the viewer's test can walk them. */
export const LINEAGE_RUNG_ORDER = {
  evidence: EVIDENCE_STEP_ORDER,
  derivation: DERIVATION_STEP_ORDER,
} as const;