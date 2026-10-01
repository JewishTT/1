import { useMemo, type ReactNode } from "react";

import type { IconName } from "../ui/Icon";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/Feedback";
import { Tabs } from "../ui/Tabs";
import { GraphCanvas } from "../graph/GraphCanvas";
import { TimelineCanvas } from "../timeline/TimelineCanvas";
import { EvidenceWorkspace } from "../evidence/EvidenceWorkspace";
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
 * is what makes this one workstation rather than eight screens (§24).
 *
 * §76 is structural, not conventional: `setView` writes one field
 * (workspace/store.ts), and nothing else in the store can be reached from a
 * view switch. store.test.ts walks all eight views asserting that selection,
 * secondary selection, filters, time range, investigation and layout are
 * byte-identical afterwards.
 *
 * §95 governs the scope: the view switcher is complete, but only Overview has
 * content. The other seven views are switchable and honestly labelled with the
 * stage that owns them. That is the finding stages 1–2 exist to produce — the
 * workspace, canvas, inspector, selection and server state are now settled, so
 * stages 3–8 can be added without re-deciding any of it.
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

/* ── Canvas ──────────────────────────────────────────────────────────── */

function StagePlaceholder({ view }: { view: WorkspaceView }) {
  const selectionId = useWorkspace(selectSelectionId);
  const setView = useWorkspace((state) => state.setView);
  const meta = VIEW_META[view];

  return (
    <div className="ui-canvas-body" data-view={view} data-testid={`canvas-${view}`}>
      <EmptyState
        icon={meta.icon}
        title={`${meta.label} belongs to ${meta.stage}`}
        description={
          <>
            <span className="ui-body">{meta.purpose}</span>
            <span className="ui-body">
              The destination is switchable now so the workspace abstraction can be judged against a
              real set of views. Its contents are deliberately not built: stage 2 exists to settle
              the workspace, canvas, inspector, selection and server state first.
            </span>
          </>
        }
        action={
          <div className="ui-canvas-actions">
            {selectionId !== null ? (
              <Badge tone="gold" role="classification" testId={`canvas-${view}-selection`}>
                {selectionId} still selected
              </Badge>
            ) : (
              <span className="ui-rail-hint">nothing selected</span>
            )}
            <Button size="sm" icon="view-overview" onClick={() => setView("overview")}>
              Back to Overview
            </Button>
          </div>
        }
        testId={`placeholder-${view}`}
      />
    </div>
  );
}

/**
 * The Overview canvas. Stage 2 mounts the *existing* InvestigationPage content
 * here instead of rewriting it — §97 (legacy routes become thin wrappers) and
 * §63 (do not rewrite working logic for a UI rewrite). The page keeps receiving
 * exactly the props it receives today, so its behaviour is unchanged.
 */
function OverviewCanvas({ children }: { children?: ReactNode }) {
  return (
    <div className="ui-canvas-body ui-canvas-overview" data-view="overview" data-testid="canvas-overview">
      {children ?? <OverviewFallback />}
    </div>
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
 * The canvas body. Views are switchable in the centre pane while the left rail and
 * the right inspector persist — §24, and that persistence is what makes the product
 * read as one workstation rather than a set of pages.
 *
 * **§76 is what this switch must not break.** Selection, filters, timeframe,
 * investigation and layout live in the store and are never touched here; the view
 * components read the same store, so switching views moves the *lens* over
 * unchanged state rather than rebuilding it.
 *
 * Each surface receives the investigation id from the store and resolves its own
 * server state, so mounting one here is a wiring change and not a re-implementation.
 * A view whose endpoints do not exist yet renders an honest statement of the gap
 * from inside the surface — not a placeholder, and not a fabricated zero.
 */
function CanvasBody({ view }: { view: WorkspaceView }) {
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
  if (view === "timeline") {
    return <TimelineCanvas variant="full" />;
  }
  return <StagePlaceholder view={view} />;
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

  return (
    <section className="ui-workspace" aria-label="Investigation workspace" data-view={view} data-testid="investigation-workspace">
      <div className="ui-canvas">
        <div className="ui-canvas-head">
          <ViewSwitcher />
          <div className="ui-canvas-head-meta">
            <span className="ui-meta" data-testid="canvas-stage">
              {meta.stage}
            </span>
            {actions.length > 0 ? (
              <span className="ui-canvas-next" data-testid="canvas-next-step">
                next: {actions[0].label}
              </span>
            ) : null}
          </div>
        </div>

        {view === "overview" ? <OverviewCanvas>{overview}</OverviewCanvas> : <CanvasBody view={view} />}
      </div>

      {/* Announces the view change without moving focus (§67). */}
      <span className="ui-sr-only" role="status" aria-live="polite" data-testid="workspace-live-region">
        {view === "overview" ? "Overview view" : `${VIEW_META[view].label} view, ${meta.stage}`}
      </span>
    </section>
  );
}

export { VIEW_META };