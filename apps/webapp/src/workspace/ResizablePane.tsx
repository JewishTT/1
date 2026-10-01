import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { DEFAULT_PANE_WIDTHS, useWorkspace } from "./store";
import { buildWorkspaceSearch, parseWorkspaceSearch } from "./url";

/**
 * Pane resize (§6: all three panes resize independently).
 *
 * Pointer-driven, keyboard-driven, and clamped. Widths live in the workspace
 * store, so they survive a view switch (§76) and are deliberately absent from
 * the URL (§77 — a shared link must not override how someone arranges their
 * own screen).
 *
 * The handle is a real `separator` with arrow-key steps and Home/End, so a
 * keyboard user can resize without a pointer (§67).
 */

export type ResizablePaneName = "rail" | "inspector" | "activity";

export interface PaneResizeHandleProps {
  pane: ResizablePaneName;
  orientation: "vertical" | "horizontal";
  min: number;
  max: number;
  /** Width/height before the drag, so a pointer cancel does not leave it skewed. */
  current: number;
  label: string;
}

/** The inspector is on the right and the activity bar at the bottom, so their
 * handles grow the pane when dragged left/up. */
const INVERTED: ReadonlySet<ResizablePaneName> = new Set(["inspector", "activity"]);

export function PaneResizeHandle({
  pane,
  orientation,
  min,
  max,
  current,
  label,
}: PaneResizeHandleProps) {
  const setPaneWidth = useWorkspace((state) => state.setPaneWidth);
  const origin = useRef<{ pointer: number; size: number } | null>(null);
  const sign = INVERTED.has(pane) ? -1 : 1;

  const apply = useCallback(
    (next: number) => setPaneWidth(pane, Math.min(max, Math.max(min, Math.round(next)))),
    [setPaneWidth, pane, min, max],
  );

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    origin.current = {
      pointer: orientation === "vertical" ? event.clientX : event.clientY,
      size: current,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const start = origin.current;
    if (!start) return;
    const delta = (orientation === "vertical" ? event.clientX : event.clientY) - start.pointer;
    apply(start.size + delta * sign);
  };

  const endDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    if (origin.current) event.currentTarget.releasePointerCapture(event.pointerId);
    origin.current = null;
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 32 : 8;
    const decrease = orientation === "vertical" ? "ArrowLeft" : "ArrowUp";
    const increase = orientation === "vertical" ? "ArrowRight" : "ArrowDown";

    if (event.key === decrease) {
      event.preventDefault();
      apply(current - step * sign);
    } else if (event.key === increase) {
      event.preventDefault();
      apply(current + step * sign);
    } else if (event.key === "Home") {
      event.preventDefault();
      apply(min);
    } else if (event.key === "End") {
      event.preventDefault();
      apply(max);
    }
  };

  return (
    <div
      role="separator"
      tabIndex={0}
      aria-label={label}
      aria-orientation={orientation}
      aria-valuenow={current}
      aria-valuemin={min}
      aria-valuemax={max}
      className="ui-resizer"
      data-orientation={orientation}
      data-testid={`resizer-${pane}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onKeyDown={onKeyDown}
      onDoubleClick={() => apply(DEFAULT_PANE_WIDTHS[pane])}
    />
  );
}

export interface ResizablePaneProps {
  pane: ResizablePaneName;
  orientation: "vertical" | "horizontal";
  min: number;
  max: number;
  children: ReactNode;
  className?: string;
  label: string;
}

/** A resizable pane, with its own trailing-edge handle so callers cannot omit it. */
export function ResizablePane({
  pane,
  orientation,
  min,
  max,
  children,
  className,
  label,
}: ResizablePaneProps) {
  const size = useWorkspace((state) => state.paneWidths[pane]);

  return (
    <>
      <div
        className={className}
        style={{ [orientation === "vertical" ? "width" : "height"]: `${size}px` }}
        data-pane={pane}
        data-testid={`pane-${pane}`}
      >
        {children}
      </div>
      <PaneResizeHandle
        pane={pane}
        orientation={orientation}
        min={min}
        max={max}
        current={size}
        label={label}
      />
    </>
  );
}

/* ── URL <-> store sync (§77) ────────────────────────────────────────── */

export interface UrlSyncOptions {
  /** react-router's navigate, or any `(to: string) => void`. */
  navigate: (to: string) => void;
  /** The location currently rendered, so an unchanged context never navigates. */
  currentPath: string;
  /**
   * The query string the app was loaded with, supplied by the router rather than
   * read from `window.location`. Hydration must follow the router, not the
   * document: a MemoryRouter test and a server-side render both have a
   * `window.location` that has nothing to do with the current route.
   */
  initialSearch: string;
  /**
   * Whether an investigation is addressable yet. The route learns its id from
   * params in an effect, so before that the store has no id and the base path
   * is unknown. Navigating on that intermediate state would replace the current
   * route with a different one and unmount the workspace.
   */
  ready: boolean;
}

/**
 * Two jobs, in this order:
 *   1. Hydrate the store from the URL the app was loaded with, so a refresh does
 *      not zero the workspace (§77).
 *   2. Then keep the address bar in step with the context.
 *
 * Hydration happens synchronously during the first render, before any effect
 * and before the first paint. Doing it in an effect would let the first
 * navigation effect run against a default store and immediately overwrite the
 * URL the user arrived on.
 */
export function useWorkspaceUrlSync({ navigate, currentPath, initialSearch, ready }: UrlSyncOptions) {
  // `useState`'s initialiser runs exactly once, on the first render only.
  useState(() => {
    useWorkspace.getState().hydrateFromUrl(parseWorkspaceSearch(initialSearch));
    return true;
  });

  const investigationId = useWorkspace((state) => state.investigationId);
  const view = useWorkspace((state) => state.view);
  const selection = useWorkspace((state) => state.selection);
  const evidenceQuery = useWorkspace((state) => state.evidenceFilter.query);
  const timeRange = useWorkspace((state) => state.timeRange);

  const next = useMemo(() => {
    const query = buildWorkspaceSearch({
      view,
      selection,
      evidenceQuery: evidenceQuery === "" ? undefined : evidenceQuery,
      timeFrom: timeRange.from ?? undefined,
      timeTo: timeRange.to ?? undefined,
    });
    return `${investigationId === null ? "/investigations" : `/investigations/${investigationId}`}${query}`;
  }, [view, selection, evidenceQuery, timeRange, investigationId]);

  useEffect(() => {
    // Until the route has told the store which investigation it is, `next` would
    // point at a different route. Navigating there would unmount the workspace
    // and lose everything the hydration just restored.
    if (!ready || investigationId === null) return;
    if (next === currentPath) return;
    navigate(next);
  }, [ready, investigationId, next, currentPath, navigate]);
}

/**
 * Escape ladder (§50): the first active handler wins, so Escape always closes
 * the topmost thing rather than every layer at once.
 */
export function useEscapeLadder(handlers: ReadonlyArray<{ active: boolean; run: () => void }>) {
  const run = useCallback(() => {
    for (const handler of handlers) {
      if (handler.active) {
        handler.run();
        return;
      }
    }
  }, [handlers]);

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      run();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [run]);
}