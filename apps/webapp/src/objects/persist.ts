import { useCallback, useEffect, useRef, useState } from "react";

import type { GridLayout, ObjectFacets, ObjectSort, SavedView } from "./types";

/**
 * Persisted workspace state (§26, §76).
 *
 * WHY PERSISTENCE IS THE §76 ANSWER HERE, stated plainly because it is a design
 * decision rather than an accident:
 *
 * §76 says no view switch may destroy filters or layout. The mechanism the store
 * uses for that is "`setView` writes one field" — anything already IN the store
 * survives by construction. That mechanism does not extend to state the store
 * does not hold, and the store holds no column layout, no saved views, no table
 * sort and no objects-specific facet.
 *
 * The canvas unmounts a view when the view changes (that is what a view switch
 * IS), so `useState` inside `ObjectWorkspace` is destroyed on every switch. A
 * grid whose column widths reset when the analyst looks at the graph and comes
 * back has failed §76 in the most annoying way possible.
 *
 * So the state this module owns is written to `localStorage` under a versioned,
 * investigation-scoped key, and re-read when the view mounts again. That makes
 * §76 a property rather than a hope, and it survives a reload for free, which is
 * the same thing §26 asks for when it says "column persistence".
 *
 * WHAT IS **NOT** HERE, deliberately: server payloads. Nothing in this file ever
 * writes a fetched record. It holds filter and layout choices, which are client
 * state by definition (§7).
 *
 * The facets that DO have a store home — kinds, sources, query, time range — are
 * read from and written to the store by the caller, not mirrored here. Mirroring
 * them would create two truths for one value, which is the failure §7 names.
 */

/** Bumped when a persisted shape changes incompatibly. Old keys are ignored. */
export const PERSIST_VERSION = 1;

/** Per-investigation bucket key. `null` investigation ⇒ the "no case" bucket. */
export function storageKey(investigationId: string | null, surface: string): string {
  return `cognitive.ui2.${surface}.v${PERSIST_VERSION}.${investigationId ?? "none"}`;
}

export interface PersistedGridState {
  layout: GridLayout;
  sort: ObjectSort;
  /** Facets with no store home. The store-owned ones are NOT duplicated here. */
  localFacets: Pick<ObjectFacets, "statuses">;
  savedViews: SavedView[];
  /** Which column the column menu has open, or null. */
  columnMenuKey: string | null;
}

export const EMPTY_PERSISTED: PersistedGridState = {
  layout: { order: [], widths: {}, hidden: [] },
  sort: { columnId: "at", direction: "desc" },
  localFacets: { statuses: [] },
  savedViews: [],
  columnMenuKey: null,
};

/* ── Storage guards ───────────────────────────────────────────────────── */

function storage(): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    const store = window.localStorage;
    // Touching the property is enough to throw in a sandboxed frame.
    store.getItem(PERSIST_PROBE_KEY);
    return store;
  } catch {
    return null;
  }
}

const PERSIST_PROBE_KEY = "cognitive.ui2.probe";

function readRaw(key: string): string | null {
  const store = storage();
  if (store === null) return null;
  try {
    return store.getItem(key);
  } catch {
    return null;
  }
}

function writeRaw(key: string, value: string): boolean {
  const store = storage();
  if (store === null) return false;
  try {
    store.setItem(key, value);
    return true;
  } catch {
    // Quota exceeded, private mode, or a disabled store. The UI keeps working
    // from memory; it simply will not remember across a reload. Reporting that
    // as a failure would be better than silently pretending persistence works.
    return false;
  }
}

/* ── Serialisation ────────────────────────────────────────────────────── */

/**
 * `parsePersistedGridState` is total: any malformed input yields the empty
 * state rather than throwing. A corrupt layout must not be able to blank the
 * table — the analyst would lose their filters to a bad byte and never know why.
 *
 * Every field is validated against its declared type, because `localStorage`
 * holds whatever was written into it, including by an older build or by hand.
 */
export function parsePersistedGridState(raw: string | null): PersistedGridState {
  if (raw === null) return EMPTY_PERSISTED;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return EMPTY_PERSISTED;
  }
  if (typeof parsed !== "object" || parsed === null) return EMPTY_PERSISTED;
  const record = parsed as Record<string, unknown>;
  if (record["version"] !== PERSIST_VERSION) return EMPTY_PERSISTED;

  const layout = record["layout"];
  const sort = record["sort"];
  const local = record["localFacets"];
  const views = record["savedViews"];

  return {
    layout: {
      order: stringArray(layout, "order"),
      widths: numberRecord(layout, "widths"),
      hidden: stringArray(layout, "hidden"),
    },
    sort:
      typeof sort === "object" && sort !== null
        ? {
            columnId: stringOr((sort as Record<string, unknown>)["columnId"], "at"),
            direction:
              (sort as Record<string, unknown>)["direction"] === "asc" ? "asc" : "desc",
          }
        : EMPTY_PERSISTED.sort,
    localFacets: {
      statuses:
        typeof local === "object" && local !== null
          ? stringArray(local, "statuses")
          : [],
    },
    savedViews: Array.isArray(views) ? views.flatMap(parseSavedView) : [],
    columnMenuKey:
      typeof record["columnMenuKey"] === "string" ? record["columnMenuKey"] : null,
  };
}

export function serialisePersistedGridState(state: PersistedGridState): string {
  return JSON.stringify({ version: PERSIST_VERSION, ...state });
}

function parseSavedView(entry: unknown): SavedView[] {
  if (typeof entry !== "object" || entry === null) return [];
  const record = entry as Record<string, unknown>;
  const id = typeof record["id"] === "string" ? record["id"] : "";
  const name = typeof record["name"] === "string" ? record["name"] : "";
  if (id === "" || name === "") return [];
  const layout = record["layout"];
  const sort = record["sort"];
  const facets = record["facets"];
  return [
    {
      id,
      name,
      savedAt: typeof record["savedAt"] === "string" ? record["savedAt"] : "",
      layout: {
        order: stringArray(layout, "order"),
        widths: numberRecord(layout, "widths"),
        hidden: stringArray(layout, "hidden"),
      },
      sort:
        typeof sort === "object" && sort !== null
          ? {
              columnId: stringOr((sort as Record<string, unknown>)["columnId"], "at"),
              direction: (sort as Record<string, unknown>)["direction"] === "asc" ? "asc" : "desc",
            }
          : EMPTY_PERSISTED.sort,
      facets: {
        kinds: readKindList(facets, "kinds"),
        sourceIds: stringArray(facets, "sourceIds"),
        statuses: stringArray(facets, "statuses"),
        timeRange: readTimeRange(facets),
        query: stringOr((facets as Record<string, unknown> | null)?.["query"], ""),
      },
    },
  ];
}

const KNOWN_KINDS = ["Entity", "Observation", "Claim", "Finding", "Capture"] as const;

function readKindList(owner: unknown, field: string): Array<(typeof KNOWN_KINDS)[number]> {
  if (typeof owner !== "object" || owner === null) return [];
  const values = (owner as Record<string, unknown>)[field];
  if (!Array.isArray(values)) return [];
  return values.filter(
    (value): value is (typeof KNOWN_KINDS)[number] =>
      typeof value === "string" && (KNOWN_KINDS as ReadonlyArray<string>).includes(value),
  );
}

function readTimeRange(owner: unknown): { from: string | null; to: string | null } {
  if (typeof owner !== "object" || owner === null) return { from: null, to: null };
  const range = (owner as Record<string, unknown>)["timeRange"];
  if (typeof range !== "object" || range === null) return { from: null, to: null };
  const record = range as Record<string, unknown>;
  return {
    from: typeof record["from"] === "string" ? record["from"] : null,
    to: typeof record["to"] === "string" ? record["to"] : null,
  };
}

function stringArray(owner: unknown, field: string): string[] {
  if (typeof owner !== "object" || owner === null) return [];
  const values = (owner as Record<string, unknown>)[field];
  if (!Array.isArray(values)) return [];
  return values.filter((value): value is string => typeof value === "string");
}

function numberRecord(owner: unknown, field: string): Record<string, number> {
  if (typeof owner !== "object" || owner === null) return {};
  const values = (owner as Record<string, unknown>)[field];
  if (typeof values !== "object" || values === null) return {};
  const out: Record<string, number> = {};
  for (const [key, value] of Object.entries(values as Record<string, unknown>)) {
    if (typeof value === "number" && Number.isFinite(value)) out[key] = value;
  }
  return out;
}

function stringOr(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

/* ── The hook ─────────────────────────────────────────────────────────── */

export interface UsePersistedGridOptions {
  /** Namespacing. `objects` and `acquisition` must not collide. */
  surface: string;
  investigationId: string | null;
  /** Overrides on mount — a test fixture, or an outer owner that seeds state. */
  initial?: Partial<PersistedGridState>;
}

export interface PersistedGridControls {
  state: PersistedGridState;
  /** Replace the whole state. Immutable updater. */
  update: (patch: Partial<PersistedGridState>) => void;
  /** Reset to the empty state and clear the key. */
  reset: () => void;
  /** True when the state came from storage rather than from defaults. */
  restored: boolean;
  /** True when storage rejected the last write — the UI can disclose it. */
  persistFailed: boolean;
}

/**
 * Read once on mount, write on every change.
 *
 * The mount read uses a lazy `useState` initialiser rather than an effect,
 * because an effect would paint the defaults for one frame first — so the grid
 * would visibly snap back to default widths on every view switch, which is the
 * §76 failure with an animation on it.
 */
export function usePersistedGrid(options: UsePersistedGridOptions): PersistedGridControls {
  const { surface, investigationId, initial } = options;
  const key = storageKey(investigationId, surface);

  const [state, setState] = useState<PersistedGridState>(() => {
    const stored = parsePersistedGridState(readRaw(key));
    if (initial === undefined) return stored;
    return { ...stored, ...initial };
  });

  // The key changes when the investigation changes, and the stored state has to
  // be re-read for THAT investigation rather than carried over from the last one.
  const firstKey = useRef(key);
  const [restored, setRestored] = useState(() => readRaw(key) !== null);
  const [persistFailed, setPersistFailed] = useState(false);

  useEffect(() => {
    if (firstKey.current === key) return;
    firstKey.current = key;
    const stored = parsePersistedGridState(readRaw(key));
    setState(stored);
    setRestored(true);
  }, [key]);

  useEffect(() => {
    setPersistFailed(!writeRaw(key, serialisePersistedGridState(state)));
  }, [key, state]);

  const update = useCallback((patch: Partial<PersistedGridState>) => {
    setState((previous) => ({ ...previous, ...patch }));
  }, []);

  const reset = useCallback(() => {
    const store = storage();
    try {
      store?.removeItem(key);
    } catch {
      // Best effort; the in-memory reset already happened.
    }
    setState(EMPTY_PERSISTED);
    setRestored(false);
  }, [key]);

  return { state, update, reset, restored, persistFailed };
}
