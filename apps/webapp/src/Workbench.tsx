import { useEffect, useState, type ReactNode } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { AppShell } from "./AppShell";
import { CommandPalette } from "./CommandPalette";
import { buildRegistry } from "./CommandBar";
import { ContextRail } from "./ContextRail";
import { InvestigationContentBridge } from "./LegacyInvestigationBridge";
import { CanvasContextMenu } from "./ui/ContextMenu";
import { ContextInspector } from "./workspace/inspector/ContextInspector";
import { InvestigationWorkspace } from "./workspace/InvestigationWorkspace";
import { ResizablePane, useWorkspaceUrlSync } from "./workspace/ResizablePane";
import { useWorkspaceEscapeLadder, useWorkspaceKeyboard } from "./quality/keyboardLayer";
import { selectView, useWorkspace } from "./workspace/store";
import type { Command } from "./workspace/commands";

/**
 * The mounted UI 2.0 shell (§5, §8) with the workspace wired into it (§10).
 *
 * Composition, top to bottom:
 *   AppShell
 *     top bar   — work state, not URL structure (§11)
 *     body      — rail │ canvas │ inspector, all three resizable (§6)
 *     activity  — bottom layer
 *   CommandPalette — ⌘K over the same registry the chords use (§9, §50)
 *
 * The structural reason context survives a view change (§24, §76): the rail and
 * the inspector are *siblings* of the canvas, mounted outside the view switch.
 * Only `<InvestigationWorkspace>`'s centre body changes when the view does.
 */

/** The registry holds no closures over changing values, so it is built once. */
function useRegistry(): Array<Command> {
  const [registry] = useState(() => buildRegistry());
  return registry;
}

function LeftRail() {
  const visible = useWorkspace((state) => state.paneVisibility.rail);
  if (!visible) return null;
  return (
    <ResizablePane
      pane="rail"
      orientation="vertical"
      min={180}
      max={420}
      label="Resize left context rail"
      className="ui-workbench-rail"
    >
      <ContextRail />
    </ResizablePane>
  );
}

function RightInspector() {
  const visible = useWorkspace((state) => state.paneVisibility.inspector);
  if (!visible) return null;
  return (
    <ResizablePane
      pane="inspector"
      orientation="vertical"
      min={260}
      max={520}
      label="Resize right inspector"
      className="ui-workbench-inspector"
    >
      <ContextInspector />
    </ResizablePane>
  );
}

/**
 * The bottom activity layer (§5). Stage 2 reports session state — the current
 * view and selection — rather than fabricating an event feed. The SSE-backed
 * pipeline feed belongs to the acquisition view (stage 5, §12), and the layer
 * says so instead of implying traffic it does not have.
 */
function ActivityLayer() {
  const view = useWorkspace(selectView);
  const selection = useWorkspace((state) => state.selection?.id ?? null);

  return (
    <div className="ui-activity-row ui-scroll" data-testid="activity-row">
      <span className="ui-meta">view</span>
      <span className="ui-mono">{view}</span>
      <span className="ui-meta">selection</span>
      <span className="ui-mono">{selection ?? "—"}</span>
      <span className="ui-activity-note">
        Session state only. Live pipeline activity arrives with the acquisition view (stage 5).
      </span>
    </div>
  );
}

/**
 * Global keyboard model (§50) and URL sync (§77). Mounted once at the shell
 * root so a chord works from anywhere, including inside the canvas.
 *
 * T131 — WHY THIS IMPORTS FROM `quality/`.
 *
 * The shell used to mount `useCommandHotkeys` from `workspace/commands.ts` and
 * `useEscapeLadder` from `workspace/ResizablePane.tsx`, while the corrected
 * implementations of both sat unused in `src/quality/keyboardLayer.ts`. The
 * defect that correction addresses is real and shipped: the old text-entry
 * predicate did not recognise `role="textbox"`, so typing "graph" into a
 * correctly-marked ARIA filter navigated the workspace to the graph mid-word
 * (WCAG 2.1.2 inverted). `quality/keyboard.test.tsx` asserted that defect with
 * `it.fails` and named this swap as the signal that the fix had landed.
 *
 * So the live implementation is imported here, and the two superseded hooks are
 * gone. `useWorkspaceEscapeLadder` supplies the three declared layers
 * (context menu → palette → selection), which is the same set this component
 * assembled inline plus the palette layer that `onEscape` used to handle
 * separately — one ladder, one order, one place to read it.
 */
function KeyboardLayer({ sync }: { sync: UrlSyncBinding | null }) {
  const registry = useRegistry();

  const paletteOpen = useWorkspace((state) => state.commandPaletteOpen);
  const setPaletteOpen = useWorkspace((state) => state.setCommandPaletteOpen);

  const view = useWorkspace(selectView);
  const selection = useWorkspace((state) => state.selection);
  const secondaryCount = useWorkspace((state) => state.secondarySelection.length);

  useWorkspaceKeyboard({
    registry,
    context: { view, selection, secondaryCount, paletteOpen },
    onTogglePalette: () => setPaletteOpen(!paletteOpen),
    // §50: Escape closes the palette. Everything below it in the stack is the
    // ladder's business, which is mounted immediately after.
    onEscape: () => {
      if (paletteOpen) setPaletteOpen(false);
    },
  });

  useWorkspaceEscapeLadder();

  // Sync is opt-in: a route supplies the router wiring; a bare test render does
  // not, and must not touch the address bar.
  return sync === null ? null : <UrlSync {...sync} />;
}

/**
 * What a route must supply for §77 to work: the router's navigate, the current
 * location, the query string the app was loaded with, and whether an
 * investigation id is known yet.
 */
export interface UrlSyncBinding {
  navigate: (to: string) => void;
  currentPath: string;
  initialSearch: string;
  /**
   * Optional: a bare render (tests, stories) supplies nothing and must not write
   * to the address bar. `InvestigationRoute` overrides this with its own
   * readiness, since the id only reaches the store one render after mount.
   */
  ready?: boolean;
}

/** Isolated so the hook is called unconditionally at one depth. */
function UrlSync({ navigate, currentPath, initialSearch, ready = true }: UrlSyncBinding) {
  useWorkspaceUrlSync({ navigate, currentPath, initialSearch, ready });
  return null;
}

export interface WorkbenchProps {
  /** Overview canvas content. A legacy page may be injected here (§97). */
  overview?: ReactNode;
  /**
   * Router wiring for URL sync (§77). Omitted in tests, which must not touch
   * the address bar.
   */
  sync?: UrlSyncBinding | null;
}

/** Mount point for tests: the workspace and inspector without AppShell chrome. */
export function WorkbenchCanvas({ overview }: { overview?: ReactNode }) {
  return (
    <div className="ui-root ui-workbench" data-testid="workbench-canvas">
      <InvestigationWorkspace overview={overview} />
      <ContextInspector />
    </div>
  );
}

export function Workbench({ overview, sync = null }: WorkbenchProps) {
  return (
    <>
      <AppShell activity={<ActivityLayer />}>
        <div className="ui-workbench">
          <LeftRail />
          <InvestigationWorkspace overview={overview} />
          <RightInspector />
        </div>
      </AppShell>
      <CommandPalette />
      <CanvasContextMenu />
      <KeyboardLayer sync={sync} />
    </>
  );
}

/* ── Route wiring (§10) ──────────────────────────────────────────────── */

/**
 * `/investigations/:id` (§10, §77).
 *
 * The legacy `InvestigationContainer` keeps its own route and its own tests.
 * This route mounts the UI 2.0 shell and hands the legacy `InvestigationPage`
 * element to the Overview canvas as its content, so the existing page becomes a
 * thin wrapper around the workspace rather than something rewritten (§97, §63).
 */
export function InvestigationRoute({
  id,
  overview,
  sync = null,
}: {
  id: string;
  overview?: ReactNode;
  sync?: UrlSyncBinding | null;
}) {
  const setInvestigation = useWorkspace((state) => state.setInvestigation);

  useEffect(() => {
    setInvestigation(id);
  }, [id, setInvestigation]);

  // The id arrives from router params, so the store learns it one render after
  // the route mounts. URL writing waits for it — see UrlSyncBinding.ready.
  const ready = useWorkspace((state) => state.investigationId !== null);

  return (
    <Workbench
      overview={overview}
      sync={sync ? { ...sync, ready: sync.ready && ready } : null}
    />
  );
}

/**
 * The `/investigations/:id` route element (§10, §77).
 *
 * Reads the id from the path, hands react-router's `navigate` and the current
 * location to the workbench so the URL tracks the workspace context, and mounts
 * the legacy investigation page into the Overview canvas.
 */
export function InvestigationWorkspaceRoute() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <InvestigationRoute
      id={id}
      overview={<InvestigationContentBridge id={id} />}
      sync={{
        navigate,
        currentPath: `${location.pathname}${location.search}`,
        initialSearch: location.search,
      }}
    />
  );
}