/**
 * Workspace domain types (§4, §6, §7, §98, §99).
 *
 * The vocabulary here is the platform's, not the UI's. Investigation /
 * Entity / Observation / Capture / Claim / Finding / AcquisitionTask /
 * AcquisitionRun / Source. No `IntelItem`, no `KnowledgeCard`, no
 * `GraphThing`, no `DataPoint` (§98).
 *
 * §99, precisely: these types let the UI *show* that an observation, a
 * candidate, a claim and an entity are different things. They do not give
 * the frontend its own semantic model — every field is either a platform
 * identifier or a platform-reported value, and nothing is derived here.
 */

/** The closed set of selectable object kinds. Selection is typed by kind. */
export type WorkspaceObjectKind =
  | "Investigation"
  | "Entity"
  | "Observation"
  | "Capture"
  | "Claim"
  | "Finding"
  | "AcquisitionTask"
  | "AcquisitionRun"
  | "Source";

/**
 * A selection is a (kind, id) pair. The id is the platform's own identifier —
 * we never mint one.
 */
export interface WorkspaceSelection {
  kind: WorkspaceObjectKind;
  id: string;
  /**
   * Human-readable label the originating view already had (a node label, a
   * table row's primary column). Carried so the top bar and rail can show
   * what is selected without a second fetch. Not authoritative: the inspector
   * always re-reads the object.
   */
  label?: string;
}

export function isSameSelection(a: WorkspaceSelection | null, b: WorkspaceSelection | null): boolean {
  if (a === b) return true;
  if (a === null || b === null) return false;
  return a.kind === b.kind && a.id === b.id;
}

/**
 * Workspace views (§4). Switchable in the *centre* canvas while the left
 * context and right inspector persist — that persistence is what produces
 * the single-workstation feeling (§24).
 *
 * Stages 3–8 fill in the content of the later views. All eight exist as
 * switchable destinations from stage 2 so the abstraction is real before the
 * screens are built (§95).
 */
export const WORKSPACE_VIEWS = [
  "overview",
  "graph",
  "objects",
  "evidence",
  "timeline",
  "acquisition",
  "findings",
  "analysis",
] as const;

export type WorkspaceView = (typeof WORKSPACE_VIEWS)[number];

export function isWorkspaceView(value: string | null | undefined): value is WorkspaceView {
  return typeof value === "string" && (WORKSPACE_VIEWS as ReadonlyArray<string>).includes(value);
}

/** Time range for the timeline / graph / evidence panes. Client state (§7). */
export interface TimeRange {
  /** ISO-8601 inclusive start, or null for "open at the left". */
  from: string | null;
  /** ISO-8601 inclusive end, or null for "open at the right". */
  to: string | null;
}

export const OPEN_TIME_RANGE: TimeRange = { from: null, to: null };

/** Evidence filter, applied to the evidence pane and the activity layer. */
export interface EvidenceFilter {
  /** Free-text match against evidence URIs, observation ids and backend names. */
  query: string;
  /** Restrict to these source ids. Empty means "all sources". */
  sourceIds: string[];
  /** Hide rejected evidence. Off by default: rejected evidence is still evidence. */
  hideRejected: boolean;
}

export const EMPTY_EVIDENCE_FILTER: EvidenceFilter = {
  query: "",
  sourceIds: [],
  hideRejected: false,
};

/** Resizable pane widths in px (§6 — all three panes resize independently). */
export interface PaneWidths {
  rail: number;
  inspector: number;
  /** Height of the bottom activity layer. */
  activity: number;
}

export type Density = "compact" | "comfortable";
export type ThemeName = "dark" | "light";

/** Which panes are open. Collapsed is remembered so the layout survives (§76). */
export interface PaneVisibility {
  rail: boolean;
  inspector: boolean;
  activity: boolean;
}

/** Server-state summary the top bar reports (§11 — work state, not URL structure). */
export interface WorkStateCounts {
  entities: number;
  observations: number;
  findings: number;
  sources: number;
  /** ISO-8601 of the newest observation the server has for this investigation. */
  lastUpdated: string | null;
}