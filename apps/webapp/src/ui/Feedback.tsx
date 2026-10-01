import type { ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

export interface EmptyStateProps {
  title: string;
  /** What is missing and why. Must be honest: never imply data exists. */
  description?: ReactNode;
  /** Concrete next step. §69: no dead ends — every empty state offers the way forward. */
  action?: ReactNode;
  icon?: IconName;
  size?: "sm" | "md";
  testId?: string;
}

/**
 * EmptyState (§60, §99). States an absence honestly. Never renders a
 * placeholder that could be mistaken for data, never fabricates a count.
 *
 * Callers: ContextInspector (no selection), workspace views awaiting stage
 * 3–8 content, left rail with no filter matches, activity layer when idle.
 */
export function EmptyState({
  title,
  description,
  action,
  icon,
  size = "md",
  testId,
}: EmptyStateProps) {
  return (
    <div className="ui-empty" data-size={size} data-testid={testId}>
      {icon ? (
        <span className="ui-empty-icon" aria-hidden="true">
          <Icon name={icon} size={16} />
        </span>
      ) : null}
      <p className="ui-empty-title">{title}</p>
      {description ? <p className="ui-empty-desc">{description}</p> : null}
      {action ? <div className="ui-empty-action">{action}</div> : null}
    </div>
  );
}

export interface SkeletonProps {
  /** Number of placeholder rows. */
  rows?: number;
  /** Render a single bar instead of rows (card / tile placeholder). */
  variant?: "rows" | "block" | "tile";
  /** Accessible text. Announced once, not per row. */
  label: string;
  height?: number;
}

/**
 * Skeleton (§60). Loading placeholder. `aria-busy` on the region plus one
 * polite announcement — screen readers are told "loading", not "blank".
 *
 * Callers: ContextInspector fetching an object, AppShell top bar awaiting
 * work-state counts, workspace views awaiting server state.
 */
export function Skeleton({ rows = 3, variant = "rows", label, height }: SkeletonProps) {
  return (
    <div className="ui-skeleton" aria-busy="true" aria-live="polite" data-variant={variant}>
      <span className="ui-sr-only">{label}</span>
      {variant === "block" ? (
        <span className="ui-skeleton-bar" style={height != null ? { height } : undefined} aria-hidden="true" />
      ) : (
        Array.from({ length: Math.max(1, rows) }, (_, index) => (
          <span
            key={index}
            className="ui-skeleton-row"
            data-variant={variant}
            style={height != null ? { height } : undefined}
            aria-hidden="true"
          />
        ))
      )}
    </div>
  );
}