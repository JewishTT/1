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
 * context and right inspector persist — that persistence is what produces the
 * single-workstation feeling (§24).
 *
 * The set is derived from `VIEW_META`/`ACTION_DESTINATIONS` nowhere and
 * duplicated nowhere: `CommandBar.buildRegistry` generates its view commands
 * from this list and `InvestigationWorkspace` renders its switcher from it, so a
 * view cannot exist in one and be missing from the other.
 *
 * `ops` (T130, FR-109) is tenant-wide by content — pipeline health, quarantine,
 * the source fabric — and is a view here because ui-upgrade §1 is explicit that
 * "Acquisition, Findings, Analysis, Quality, and Ops are views *within* an
 * investigation, not peer products". The surface keeps its own prominent
 * "tenant-wide · not scoped to one investigation" label, which is what stops a
 * tenant-wide failure rate from reading as a statement about the case in hand.
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
  "ops",
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

/**
 * Density (ui-upgrade §4.2, FR-103).
 *
 * THREE modes, not two. `STANDARD` is the default the spec names, and it is the
 * only one of the three that existed until T137 — the store previously shipped
 * `compact` as both the default and the first mode, so a fresh session was
 * denser than the design intends and there was no middle setting at all.
 *
 * The order is the canonical one: compact → standard → comfortable. The
 * Appearance control renders `DENSITIES` in this order and ⌘K's
 * `layout.density.toggle` walks it, so the two can never disagree about which
 * mode comes next.
 *
 * §4.2 is emphatic that density is GLOBAL — "a density that applies to tables
 * but not to the graph is a defect" — so this union has no per-surface
 * variants. The px values live in `styles/tokens/density.css` and are mirrored
 * as numbers in `objects/virtualization.ts`.
 */
export const DENSITIES = ["compact", "standard", "comfortable"] as const;

export type Density = (typeof DENSITIES)[number];

/** §4.2: "default STANDARD". */
export const DEFAULT_DENSITY: Density = "standard";

export function isDensity(value: string | null | undefined): value is Density {
  return typeof value === "string" && (DENSITIES as ReadonlyArray<string>).includes(value);
}

export type ThemeName = "dark" | "light";

/** §4.1/§3.2. Both themes are first class; neither is an inverted other. */
export const THEME_NAMES = ["dark", "light"] as const;

export const DEFAULT_THEME: ThemeName = "dark";

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