import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

import {
  DEFAULT_DENSITY,
  DEFAULT_THEME,
  EMPTY_EVIDENCE_FILTER,
  OPEN_TIME_RANGE,
  DENSITIES,
  isWorkspaceView,
  type Density,
  type EvidenceFilter,
  type PaneVisibility,
  type PaneWidths,
  type ThemeName,
  type TimeRange,
  type WorkspaceObjectKind,
  type WorkspaceSelection,
  type WorkspaceView,
} from "./types";

/**
 * WorkspaceState (§7, §8, §76, §77).
 *
 * WHAT BELONGS HERE: client state only. The investigation being worked, the
 * active view, the selection, the secondary selection, filters, the time
 * range, which inspectors are open, pane widths and layout.
 *
 * WHAT DOES NOT: anything the server owns. Observations, entities, findings,
 * source registries, counts and timestamps are TanStack Query's job. This
 * store never caches a server payload and never has an action that writes one
 * — mixing the two is the failure mode §7 forbids, because it produces two
 * truths for the same object.
 *
 * §76 — view switching is a single-field write. `setView` touches `view` and
 * nothing else. Selection, secondary selection, filters, time range,
 * investigation id, pane widths and pane visibility are all unreachable from
 * that action, which is what makes context survival a structural property
 * rather than a promise. See workspaceStore.test.ts.
 *
 * §68 — components subscribe with selectors (`useWorkspace(selector)`), never
 * to the whole store, so selecting an object re-renders the inspector, the
 * rail's selection indicator and the top bar, and not the canvas.
 */

export const DEFAULT_PANE_WIDTHS: PaneWidths = { rail: 264, inspector: 340, activity: 168 };

export const DEFAULT_PANE_VISIBILITY: PaneVisibility = { rail: true, inspector: true, activity: true };

/** Investigating id used before an investigation is chosen. */
export const NO_INVESTIGATION: string | null = null;

export interface WorkspaceStateShape {
  /* ── Work context ──────────────────────────────────────────────────── */
  /** `null` means "no investigation chosen yet"; the shell then prompts for one. */
  investigationId: string | null;
  /** Shown in the top bar. Server-owned text, but the *choice* of investigation is client state. */
  investigationLabel: string | null;

  /* ── Navigation ────────────────────────────────────────────────────── */
  view: WorkspaceView;

  /* ── Selection: one global model (§7) ──────────────────────────────── */
  selection: WorkspaceSelection | null;
  /** Supporting objects: comparison targets, path endpoints, filter chips. */
  secondarySelection: WorkspaceSelection[];

  /* ── Filtering ─────────────────────────────────────────────────────── */
  evidenceFilter: EvidenceFilter;
  /** Free-text narrowing of the left rail's object list. */
  railQuery: string;
  /** Object kinds the rail lists. Empty means "all kinds". */
  railKinds: WorkspaceObjectKind[];

  /* ── Time ──────────────────────────────────────────────────────────── */
  timeRange: TimeRange;

  /* ── Inspectors ────────────────────────────────────────────────────── */
  /** Which inspector sections are expanded, keyed by section id. */
  openInspectorSections: Record<string, boolean>;
  /** Objects explicitly pinned open in the inspector, e.g. a second claim. */
  pinnedInspectors: WorkspaceSelection[];

  /* ── Layout ────────────────────────────────────────────────────────── */
  paneWidths: PaneWidths;
  paneVisibility: PaneVisibility;
  density: Density;
  theme: ThemeName;
  /** Command palette open. Layout state, so it survives a view switch (§76). */
  commandPaletteOpen: boolean;

  /* ── Overlays ──────────────────────────────────────────────────────── */
  /** Coordinate-anchored context menu (primitives shell), null when closed. */
  contextMenu: { x: number; y: number; targetKind: WorkspaceObjectKind | null } | null;
}

export interface WorkspaceStateActions {
  /* ── Work context ──────────────────────────────────────────────────── */
  setInvestigation: (investigationId: string, label?: string | null) => void;
  setInvestigationLabel: (label: string | null) => void;

  /* ── Navigation: §76 — the ONLY action that writes `view` ──────────── */
  setView: (view: WorkspaceView) => void;

  /* ── Selection ─────────────────────────────────────────────────────── */
  /** Replace the primary selection. This is the single global entry point (§7). */
  select: (selection: WorkspaceSelection | null) => void;
  /** Select only when nothing is selected — used by "focus on open" affordances. */
  selectIfEmpty: (selection: WorkspaceSelection) => void;
  /** Toggle a supporting object. Never promotes to primary. */
  toggleSecondary: (selection: WorkspaceSelection) => void;
  setSecondary: (selection: WorkspaceSelection[]) => void;
  clearSelection: () => void;

  /* ── Filtering ─────────────────────────────────────────────────────── */
  setEvidenceFilter: (patch: Partial<EvidenceFilter>) => void;
  resetEvidenceFilter: () => void;
  setRailQuery: (query: string) => void;
  toggleRailKind: (kind: WorkspaceObjectKind) => void;

  /* ── Time ──────────────────────────────────────────────────────────── */
  setTimeRange: (range: TimeRange) => void;
  clearTimeRange: () => void;

  /* ── Inspectors ────────────────────────────────────────────────────── */
  toggleInspectorSection: (sectionId: string) => void;
  setInspectorSection: (sectionId: string, open: boolean) => void;
  pinInspector: (selection: WorkspaceSelection | null) => void;

  /* ── Layout ────────────────────────────────────────────────────────── */
  setPaneWidth: (pane: keyof PaneWidths, width: number) => void;
  togglePane: (pane: keyof PaneVisibility) => void;
  setDensity: (density: Density) => void;
  toggleDensity: () => void;
  setTheme: (theme: ThemeName) => void;
  toggleTheme: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
  openContextMenu: (menu: NonNullable<WorkspaceStateShape["contextMenu"]>) => void;
  closeContextMenu: () => void;

  /* ── URL hydration (§77) ──────────────────────────────────────────── */
  /**
   * Apply a URL-derived patch. Only the keys present in `patch` are written,
   * so `?view=graph` changes the view and leaves the selection alone, while
   * `?entity=ENT-182` selects without touching the view.
   */
  hydrateFromUrl: (patch: Partial<WorkspaceContextPatch>) => void;
}

/**
 * The subset of state the URL is allowed to carry (§77). Kept separate from
 * the full shape so a hand-written URL cannot reach layout internals.
 */
export interface WorkspaceContextPatch {
  investigation?: string;
  view?: WorkspaceView;
  /** Primary selection, encoded as `kind:id`. */
  selection?: WorkspaceSelection | null;
  evidenceQuery?: string;
  timeFrom?: string | null;
  timeTo?: string | null;
}

export type WorkspaceStore = WorkspaceStateShape & WorkspaceStateActions;

const INITIAL_STATE: WorkspaceStateShape = {
  investigationId: NO_INVESTIGATION,
  investigationLabel: null,
  view: "overview",
  selection: null,
  secondarySelection: [],
  evidenceFilter: EMPTY_EVIDENCE_FILTER,
  railQuery: "",
  railKinds: [],
  timeRange: OPEN_TIME_RANGE,
  openInspectorSections: {},
  pinnedInspectors: [],
  paneWidths: DEFAULT_PANE_WIDTHS,
  paneVisibility: DEFAULT_PANE_VISIBILITY,
  density: DEFAULT_DENSITY,
  theme: DEFAULT_THEME,
  commandPaletteOpen: false,
  contextMenu: null,
};

export const useWorkspace = create<WorkspaceStore>()(subscribeWithSelector((set) => ({
  ...INITIAL_STATE,

  setInvestigation: (investigationId, label) =>
    set((state) => ({
      investigationId,
      // Only overwrite the label when one was supplied: re-selecting the same
      // investigation must not blank the top bar.
      investigationLabel: label !== undefined ? label : state.investigationLabel,
    })),

  setInvestigationLabel: (investigationLabel) => set({ investigationLabel }),

  // §76. One field. Nothing else is reachable from here. This is the whole
  // mechanism by which context survival is guaranteed.
  setView: (view) => set({ view }),

  select: (selection) => set({ selection }),
  selectIfEmpty: (selection) =>
    set((state) => (state.selection === null ? { selection } : {})),
  toggleSecondary: (selection) =>
    set((state) => {
      const exists = state.secondarySelection.some(
        (entry) => entry.kind === selection.kind && entry.id === selection.id,
      );
      return {
        secondarySelection: exists
          ? state.secondarySelection.filter(
              (entry) => !(entry.kind === selection.kind && entry.id === selection.id),
            )
          : [...state.secondarySelection, selection],
      };
    }),
  setSecondary: (secondarySelection) => set({ secondarySelection }),
  clearSelection: () => set({ selection: null, secondarySelection: [] }),

  setEvidenceFilter: (patch) => set((state) => ({ evidenceFilter: { ...state.evidenceFilter, ...patch } })),
  resetEvidenceFilter: () => set({ evidenceFilter: EMPTY_EVIDENCE_FILTER }),
  setRailQuery: (railQuery) => set({ railQuery }),
  toggleRailKind: (kind) =>
    set((state) => ({
      railKinds: state.railKinds.includes(kind)
        ? state.railKinds.filter((entry) => entry !== kind)
        : [...state.railKinds, kind],
    })),

  setTimeRange: (timeRange) => set({ timeRange }),
  clearTimeRange: () => set({ timeRange: OPEN_TIME_RANGE }),

  toggleInspectorSection: (sectionId) =>
    set((state) => ({
      openInspectorSections: {
        ...state.openInspectorSections,
        [sectionId]: !(state.openInspectorSections[sectionId] ?? false),
      },
    })),
  setInspectorSection: (sectionId, open) =>
    set((state) => ({ openInspectorSections: { ...state.openInspectorSections, [sectionId]: open } })),
  pinInspector: (selection) =>
    set((state) => ({
      pinnedInspectors:
        selection === null
          ? state.pinnedInspectors.filter(
              (entry) => !(entry.kind === state.selection?.kind && entry.id === state.selection.id),
            )
          : [
              ...state.pinnedInspectors.filter(
                (entry) => !(entry.kind === selection.kind && entry.id === selection.id),
              ),
              selection,
            ],
    })),

  setPaneWidth: (pane, width) =>
    set((state) => ({ paneWidths: { ...state.paneWidths, [pane]: Math.max(0, Math.round(width)) } })),
  togglePane: (pane) =>
    set((state) => ({
      paneVisibility: { ...state.paneVisibility, [pane]: !state.paneVisibility[pane] },
    })),
  setDensity: (density) => set({ density }),
  // Walks the canonical order rather than flipping a boolean, because there are
  // now three modes and a flip has no answer for the middle one. The Appearance
  // control renders `DENSITIES` in this same order, so ⌘K's toggle and the menu
  // agree on what "next" means.
  toggleDensity: () =>
    set((state) => {
      const index = DENSITIES.indexOf(state.density);
      const next = DENSITIES[(index + 1) % DENSITIES.length];
      return { density: next };
    }),
  setTheme: (theme) => set({ theme }),
  toggleTheme: () => set((state) => ({ theme: state.theme === "dark" ? "light" : "dark" })),
  setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),
  openContextMenu: (contextMenu) => set({ contextMenu }),
  closeContextMenu: () => set({ contextMenu: null }),

  hydrateFromUrl: (patch) =>
    set((state) => {
      const next: Partial<WorkspaceStateShape> = {};
      if (patch.investigation !== undefined) next.investigationId = patch.investigation;
      if (patch.view !== undefined && isWorkspaceView(patch.view)) next.view = patch.view;
      if (patch.selection !== undefined) next.selection = patch.selection;
      if (patch.evidenceQuery !== undefined) {
        next.evidenceFilter = { ...state.evidenceFilter, query: patch.evidenceQuery };
      }
      if (patch.timeFrom !== undefined || patch.timeTo !== undefined) {
        next.timeRange = {
          from: patch.timeFrom !== undefined ? patch.timeFrom : state.timeRange.from,
          to: patch.timeTo !== undefined ? patch.timeTo : state.timeRange.to,
        };
      }
      return next;
    }),
})));

/* ── Selectors (§68) ───────────────────────────────────────────────────
 *
 * Every consumer picks the narrowest slice it can. These are the selectors
 * used by the shell, the workspace and the inspector; components import them
 * rather than inlining object literals, so a store change that would cause a
 * broad re-render is visible in one place.
 */

/** Stable reference while the id is unchanged — safe for effect deps. */
export function selectSelectionId(state: WorkspaceStore): string | null {
  return state.selection?.id ?? null;
}

export function selectSelectionKind(state: WorkspaceStore): WorkspaceObjectKind | null {
  return state.selection?.kind ?? null;
}

export function selectView(state: WorkspaceStore): WorkspaceView {
  return state.view;
}

export function selectInvestigationId(state: WorkspaceStore): string | null {
  return state.investigationId;
}

export function selectSecondaryIds(state: WorkspaceStore): string[] {
  return state.secondarySelection.map((entry) => entry.id);
}

/**
 * Predicates take the id as an argument so they can be memoised per row.
 * Graph nodes and table rows call `isSelected(state, id)` and only re-render
 * when *their* boolean flips — not when any other node's selection changes.
 */
export function makeIsSelected(id: string) {
  return (state: WorkspaceStore): boolean => state.selection?.id === id;
}

export function makeIsSecondarySelected(id: string) {
  return (state: WorkspaceStore): boolean =>
    state.secondarySelection.some((entry) => entry.id === id);
}

export function makeIsPinned(id: string) {
  return (state: WorkspaceStore): boolean => state.pinnedInspectors.some((entry) => entry.id === id);
}

export function selectPaneWidth(pane: keyof PaneWidths) {
  return (state: WorkspaceStore): number => state.paneWidths[pane];
}

export function selectPaneVisible(pane: keyof PaneVisibility) {
  return (state: WorkspaceStore): boolean => state.paneVisibility[pane];
}

/**
 * The URL-projected context: exactly the keys `buildWorkspaceSearch` writes
 * and `parseWorkspaceSearch` reads. The investigation id is *not* included —
 * it is carried by the path (see `buildWorkspacePath`) — which is what makes
 * `parseWorkspaceSearch(buildWorkspaceSearch(workspaceContext(s)))` a lossless
 * round trip.
 */
export function workspaceContext(state: WorkspaceStore): WorkspaceContextPatch {
  return {
    view: state.view,
    selection: state.selection,
    evidenceQuery: state.evidenceFilter.query === "" ? undefined : state.evidenceFilter.query,
    timeFrom: state.timeRange.from ?? undefined,
    timeTo: state.timeRange.to ?? undefined,
  };
}