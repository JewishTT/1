import { useMemo, type ReactNode } from "react";

import type { IconName } from "../ui/Icon";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/Feedback";
import { Tabs } from "../ui/Tabs";
import { GraphCanvas } from "../graph/GraphCanvas";
import { TimelineCanvas } from "../timeline/TimelineCanvas";
import { EvidenceWorkspace } from "../evidence/EvidenceWorkspace";
import { ObjectsWorkspace } from "../objects/ObjectsWorkspace";
import { OpsCanvas } from "../ops/OpsCanvas";
import { actionsForSelection, destinationForAction } from "./commands";
import { selectSelectionId, useWorkspace } from "./store";
import { useWorkState } from "./useWorkState";
import { WORKSPACE_VIEWS, type WorkspaceView } from "./types";

/**
 * InvestigationWorkspace (§4, §6, §12, §24).
 *
 * The primary UI abstraction: a three-pane workstation where only the *centre*
 * switches. The left context rail and the right inspector stay mounted, so
 * filters and the selected object survive every view change. That persistence
 * is what makes this one workstation rather than a set of screens (§24).
 *
 * §76 is structural, not conventional: `setView` writes one field
 * (workspace/store.ts), and nothing else in the store can be reached from a
 * view switch. store.test.ts walks every view asserting that selection,
 * secondary selection, filters, time range, investigation and layout are
 * byte-identical afterwards.
 *
 * §95 still governs part of the scope. Every view in `WORKSPACE_VIEWS` is a
 * switchable destination with real content OR with an honest statement naming
 * the stage that owns it. The four that remain on the statement are objects,
 * acquisition, findings and analysis (T147–T151); graph, timeline, evidence,
 * overview and ops carry content.
 *
 * The three per-view test-id anchors (`canvas-{view}`, `placeholder-{view}`,
 * `canvas-{view}-selection`) are re-declared by `ViewCanvas` for EVERY view, so
 * a surface replacing the one beneath it cannot take the contract with it. That
 * is the T129 / FR-110 repair and the reason for the `ViewContract` component
 * below; the details are stated where it is defined.
 */

const VIEW_META: Record<WorkspaceView, { label: string; icon: IconName; stage: string; purpose: string }> = {
  overview: {
    label: "Overview",
    icon: "view-overview",
    stage: "stage 2",
    purpose: "Investigation health, acquisition, interpretation and admission readouts.",
  },
  graph: {
    label: "Graph",
    icon: "view-graph",
    stage: "stage 3",
    purpose: "Cytoscape canvas over the existing IntelligenceGraph data.",
  },
  objects: {
    label: "Objects",
    icon: "view-objects",
    stage: "stage 4",
    purpose: "Entity, observation and claim tables driven by the global selection.",
  },
  evidence: {
    label: "Evidence",
    icon: "view-evidence",
    stage: "stage 4",
    purpose: "Evidence records with lineage, filtered by the rail's evidence query.",
  },
  timeline: {
    label: "Timeline",
    icon: "view-timeline",
    stage: "stage 3",
    purpose: "Temporal scrubbing over the existing TimelineSlider and TimelineView.",
  },
  acquisition: {
    label: "Acquisition",
    icon: "view-acquisition",
    stage: "stage 5",
    purpose: "AcquisitionTask and AcquisitionRun state, queues and live runs.",
  },
  findings: {
    label: "Findings",
    icon: "view-findings",
    stage: "stage 4",
    purpose: "Findings queue with why-detected and the lineage walk.",
  },
  analysis: {
    label: "Analysis",
    icon: "view-analysis",
    stage: "stage 3",
    purpose: "Derived measures, communities and diagram features.",
  },
  ops: {
    label: "Ops",
    icon: "view-ops",
    stage: "stage 5",
    purpose: "Event stream, consumer lag, schema registry, failure journal and replay controls.",
  },
};

/** §50 chords. Only these five views get a single key. */
const VIEW_CHORD: Partial<Record<WorkspaceView, string>> = {
  graph: "G",
  objects: "O",
  evidence: "E",
  timeline: "T",
  acquisition: "A",
};

/* ── Canvas view switcher ────────────────────────────────────────────── */

function ViewSwitcher() {
  const view = useWorkspace((state) => state.view);
  const setView = useWorkspace((state) => state.setView);

  const items = useMemo(
    () =>
      WORKSPACE_VIEWS.map((target) => ({
        value: target,
        label: VIEW_META[target].label,
        icon: VIEW_META[target].icon,
        ...(VIEW_CHORD[target] ? { shortcut: VIEW_CHORD[target] } : {}),
      })),
    [],
  );

  return <Tabs items={items} value={view} onValueChange={setView} label="Workspace views" orientation="bar" />;
}

/**
 * The per-view contract anchors (FR-110).
 *
 * Stage 2 established three test-id anchors per canvas and
 * `store.test.ts` / `Selection.performance.test.tsx` are written against them:
 *
 *   canvas-{view}               the canvas body for this view
 *   placeholder-{view}          the slot reporting this view's build stage
 *   canvas-{view}-selection     the preserved global selection, visible here
 *
 * Stages 3–4 replaced the graph, timeline and evidence surfaces with real
 * components carrying surface-specific ids (`graph-canvas`, `timeline-canvas`,
 * `evidence-workspace`) and did NOT re-declare the three anchors. That is a
 * contract regression, not a test drift: the anchors are the structural promise
 * that *every* canvas in the centre pane is addressable by view name and reports
 * the preserved selection, which is exactly what makes §76 testable from the
 * outside instead of merely asserted in a store unit test.
 *
 * So they are restored here, at the shell, where a surface cannot take them away
 * by being replaced:
 *
 *   - `canvas-{view}` is the wrapper `ViewCanvas` puts around the surface. It
 *     carries `data-view`, so a caller can assert which view a node belongs to.
 *   - `placeholder-{view}` is the build-stage slot. For a view with no content
 *     it is the `EmptyState` itself. For a built view it is `ViewStageSlot` —
 *     a real, quiet line that names the view and the stage that owns it, so the
 *     anchor reports "mounted at stage N" rather than disappearing. The name is
 *     a leftover of stage 2, where every non-overview view was a placeholder;
 *     the anchor outlived that fact and the tests kept pointing at it. Kept as
 *     is, deliberately: renaming it would break the very contract this
 *     component exists to restore.
 *   - `canvas-{view}-selection` is the preserved global selection, rendered for
 *     EVERY view — built or not. That is the point of it: it is how a selection
 *     made on one view is *visible* from another, which is what §7 claims.
 *
 * WHERE THE TWO STATUS ANCHORS LIVE, AND WHY IT IS NOT ARBITRARY.
 *
 * `SelectionAnchor` sits in the canvas HEAD, not inside `canvas-{view}`. That is
 * forced by §68: the canvas body must not be touched when the selection changes
 * — `Selection.performance.test.tsx` attaches a MutationObserver to
 * `canvas-overview` and asserts zero records, because "§7 is a global model, but
 * a view only subscribes to what it renders". An anchor that reports the
 * selection and lives inside the body cannot satisfy both that rule and its own
 * purpose. The head is part of the canvas, sits above the view-specific body, and
 * is exactly where a status that must survive the body swap belongs: it already
 * carries the stage and the next-step hint.
 */
function SelectionAnchor({ view }: { view: WorkspaceView }) {
  const selectionId = useWorkspace(selectSelectionId);

  return selectionId !== null ? (
    <Badge tone="gold" role="classification" testId={`canvas-${view}-selection`}>
      {selectionId} still selected
    </Badge>
  ) : (
    <span className="ui-rail-hint" data-testid={`canvas-${view}-selection`}>
      nothing selected
    </span>
  );
}

/** The stage anchor for a view whose content IS built. See `ViewContract`. */
function ViewStageSlot({ view }: { view: WorkspaceView }) {
  const meta = VIEW_META[view];
  return (
    <span className="ui-canvas-stage-slot" data-testid={`placeholder-${view}`}>
      <span className="ui-meta">{meta.label}</span>
      <span className="ui-canvas-stage-note">mounted · {meta.stage}</span>
    </span>
  );
}

/**
 * The canvas body. Every view renders through here, so the `canvas-{view}`
 * anchor cannot be lost by a surface being swapped out — which is precisely
 * what happened in stages 3–4.
 */
function ViewCanvas({ view, surface }: { view: WorkspaceView; surface: ReactNode | null }) {
  return (
    <div
      className="ui-canvas-body"
      data-view={view}
      data-built={surface !== null}
      data-testid={`canvas-${view}`}
    >
      {surface ?? <StagePlaceholder view={view} />}
    </div>
  );
}

/* ── Canvas ──────────────────────────────────────────────────────────── */

/**
 * The honest statement for a view whose content is not built.
 *
 * §95 governs the scope: the view switcher is complete, but only the views whose
 * stage has landed carry content. The four that remain (objects, acquisition,
 * findings, analysis) are switchable destinations that name the stage that owns
 * them. That is the finding stages 1–2 exist to produce — the workspace, canvas,
 * inspector, selection and server state are settled, so stages 3–8 can be added
 * without re-deciding any of it.
 */
function StagePlaceholder({ view }: { view: WorkspaceView }) {
  const setView = useWorkspace((state) => state.setView);
  const meta = VIEW_META[view];

  return (
    <EmptyState
      icon={meta.icon}
      title={`${meta.label} belongs to ${meta.stage}`}
      description={
        <>
          <span className="ui-body">{meta.purpose}</span>
          <span className="ui-body">
            The destination is switchable now so the workspace abstraction can be judged against a real set of
            views. Its contents are deliberately not built yet.
          </span>
        </>
      }
      action={
        <Button size="sm" icon="view-overview" onClick={() => setView("overview")}>
          Back to Overview
        </Button>
      }
      testId={`placeholder-${view}`}
    />
  );
}

/** Honest default when no legacy page was injected: state, not numbers. */
function OverviewFallback() {
  const investigationId = useWorkspace((state) => state.investigationId);
  const work = useWorkState(investigationId);

  return (
    <div className="ui-overview">
      <EmptyState
        icon="view-overview"
        title="Overview"
        description="The investigation page mounts here on the investigation route, unchanged. Nothing is invented in its place."
        testId="overview-fallback"
      />
      {work.investigationName !== null ? (
        <p className="ui-body" data-testid="overview-investigation">
          {work.investigationName} · {work.rawState ?? work.state}
        </p>
      ) : null}
    </div>
  );
}

/**
 * The surface for a view, or `null` when its stage has not landed.
 *
 * Each surface receives the investigation id from the store and resolves its own
 * server state, so mounting one here is a wiring change and not a
 * re-implementation. A view whose endpoints do not exist yet renders an honest
 * statement of the gap from inside the surface — not a placeholder, and not a
 * fabricated zero.
 *
 * Returning `null` rather than a component is what makes `ViewCanvas` able to
 * tell "built" from "not built" without a second registry to keep in step.
 */
function surfaceFor(view: WorkspaceView, overview: ReactNode | undefined): ReactNode | null {
  if (view === "graph") {
    return (
      <GraphCanvas
        timeline={
          <TimelineCanvas variant="docked" />
        }
      />
    );
  }
  if (view === "evidence") {
    return <EvidenceWorkspace />;
  }
  if (view === "objects") {
    return <ObjectsWorkspace />;
  }
  if (view === "timeline") {
    return <TimelineCanvas variant="full" />;
  }
  if (view === "ops") {
    return <OpsCanvas />;
  }
  if (view === "overview") {
    // §97 / §63: the *existing* InvestigationPage mounts here instead of being
    // rewritten. It keeps receiving exactly the props it receives today.
    return <div className="ui-canvas-overview">{overview ?? <OverviewFallback />}</div>;
  }
  return null;
}

/* ── The workspace ───────────────────────────────────────────────────── */

export interface InvestigationWorkspaceProps {
  /** Overview canvas content — the legacy page, when a route injects one. */
  overview?: ReactNode;
}

export function InvestigationWorkspace({ overview }: InvestigationWorkspaceProps) {
  const view = useWorkspace((state) => state.view);
  const selection = useWorkspace((state) => state.selection);
  const secondaryCount = useWorkspace((state) => state.secondarySelection.length);

  const actions = useMemo(
    () =>
      actionsForSelection(selection, secondaryCount).filter(
        (action) => destinationForAction(action.id) !== null,
      ),
    [selection, secondaryCount],
  );
  const meta = VIEW_META[view];
  // Computed once and shared with `ViewCanvas` so "is this view built" has a
  // single answer per render: two independent `surfaceFor` calls could disagree
  // if a surface threw, and the stage anchor would then report a mount that did
  // not happen.
  const surface = useMemo(() => surfaceFor(view, overview), [view, overview]);

  return (
    <section className="ui-workspace" aria-label="Investigation workspace" data-view={view} data-testid="investigation-workspace">
      <div className="ui-canvas">
        <div className="ui-canvas-head">
          <ViewSwitcher />
          <div className="ui-canvas-head-meta">
            <span className="ui-meta" data-testid="canvas-stage">
              {meta.stage}
            </span>
            {surface !== null ? <ViewStageSlot view={view} /> : null}
            {actions.length > 0 ? (
              <span className="ui-canvas-next" data-testid="canvas-next-step">
                next: {actions[0].label}
              </span>
            ) : null}
            <SelectionAnchor view={view} />
          </div>
        </div>

        <ViewCanvas view={view} surface={surface} />
      </div>

      {/* Announces the view change without moving focus (§67). */}
      <span className="ui-sr-only" role="status" aria-live="polite" data-testid="workspace-live-region">
        {view === "overview" ? "Overview view" : `${VIEW_META[view].label} view, ${meta.stage}`}
      </span>
    </section>
  );
}

export { VIEW_META };