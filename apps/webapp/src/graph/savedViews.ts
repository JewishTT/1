/**
 * Saved graph views — a named snapshot of how the canvas was set up.
 *
 * This is the one capability the workspace graph was missing and the retired Intel Board had:
 * SAVE VIEW / RESTORE. It looks like a small feature and is not, because a graph is only
 * usable if you can get back to a framing you already worked out. An analyst who has spent
 * twenty minutes isolating one relationship should not have to rebuild that framing by hand
 * to look at it again tomorrow, and without a snapshot the answer is "don't close the tab",
 * which is not a data-retention strategy.
 *
 * What is saved is the *setup*, never the data: pointer mode, layout, the filter query and
 * facets, whether the temporal layer is on, and which nodes were expanded. The nodes and
 * edges themselves are refetched, because a saved view pointing at a stale copy of the graph
 * would silently show yesterday's world under today's settings — the exact failure the
 * platform's whole provenance discipline exists to prevent.
 *
 * Scoped by investigation so two investigations cannot restore each other's framing, and
 * stored in `localStorage` because a view is a per-analyst convenience, not platform state:
 * putting it in the database would make two people fight over one name.
 */

import { isLayoutName, type LayoutName } from "./layout";
import type { ToolbarMode } from "./GraphToolbar";

export interface SavedView {
  name: string;
  savedAt: string;
  mode: ToolbarMode;
  layout: LayoutName;
  query: string;
  temporalActive: boolean;
  expandedIds: string[];
}

const PREFIX = "cognitive:saved-views:";

/** The scope the whole tenant shares, used when no investigation is chosen. */
export const TENANT_SCOPE = "tenant";

/**
 * The one place a scope key is decided.
 *
 * The canvas takes `investigationId?: string | null` — a prop for tests and previews, and a
 * null that means the tenant-wide scope — so it cannot hand that straight to `loadViews`
 * without deciding what a null means. Deciding it here keeps the rule in one file: a real id
 * scopes to itself, a missing one gets a stable key that no investigation id can collide
 * with, and `localStorage` never sees a bare `"null"`.
 *
 * The `investigation:` prefix on the scoped half is what makes that last claim true rather
 * than merely likely: without it an investigation whose id happened to be the literal string
 * `tenant` would share one key with the tenant-wide scope, and restoring one would silently
 * restore the other.
 */
export function scopeKeyFor(investigationId: string | null): string {
  return investigationId === null || investigationId === ""
    ? TENANT_SCOPE
    : `investigation:${investigationId}`;
}

function scopeKey(scope: string): string {
  return PREFIX + scope;
}

const MODES: ReadonlyArray<ToolbarMode> = ["select", "lasso"];

/**
 * A view is only usable if EVERY field the restore path reads is present and in range.
 *
 * Restore assigns `mode`, `layout`, `query`, `temporalActive` and `expandedIds` straight
 * into canvas state, so a payload missing one of them — or carrying a `layout` the engine
 * has no name for — does not degrade gracefully, it throws inside the setter. Checking the
 * whole shape here is what makes "a malformed payload costs you one view" true.
 */
function isSavedView(value: unknown): value is SavedView {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.name === "string" &&
    typeof v.savedAt === "string" &&
    MODES.includes(v.mode as ToolbarMode) &&
    typeof v.layout === "string" &&
    isLayoutName(v.layout) &&
    typeof v.query === "string" &&
    typeof v.temporalActive === "boolean" &&
    Array.isArray(v.expandedIds) &&
    v.expandedIds.every((id): id is string => typeof id === "string")
  );
}

export function loadViews(scope: string): SavedView[] {
  try {
    const raw = window.localStorage.getItem(scopeKey(scope));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // A view written by an older build can be missing fields the current one relies on.
    // Dropping it is right: restoring a partial snapshot would leave the canvas in a state
    // nobody chose, which is worse than offering nothing.
    return parsed.filter(isSavedView);
  } catch {
    return [];
  }
}

function persist(scope: string, views: SavedView[]): void {
  try {
    window.localStorage.setItem(scopeKey(scope), JSON.stringify(views));
  } catch {
    // Quota or private mode. The view is a convenience; failing to store one must not take
    // the graph down with it.
  }
}

export function saveView(scope: string, view: Omit<SavedView, "savedAt">): SavedView[] {
  const saved: SavedView = { ...view, savedAt: new Date().toISOString() };
  // Replace rather than append on a name collision: two views called "default" where one
  // silently wins is the confusion this feature exists to remove.
  const next = [...loadViews(scope).filter((v) => v.name !== saved.name), saved];
  persist(scope, next);
  return next;
}

export function deleteView(scope: string, name: string): SavedView[] {
  const next = loadViews(scope).filter((v) => v.name !== name);
  persist(scope, next);
  return next;
}
