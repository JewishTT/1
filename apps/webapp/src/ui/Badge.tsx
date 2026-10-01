import type { ReactNode } from "react";

import { statusTone, type WorkStatus } from "./status";

/** Badge roles. Green/gold/red/cyan carry the meanings fixed in §57; `neutral` carries none. */
export type BadgeTone = "neutral" | "accent" | "gold" | "danger" | "analytical" | "strong";

export interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  /**
   * `label` renders as the visible text. `labelAs` marks the badge as carrying a
   * domain classification rather than UI chrome — used so gold reads as
   * metadata/classification and never as "warning" (§57).
   */
  role?: "chrome" | "classification";
  title?: string;
  mono?: boolean;
  testId?: string;
}

/**
 * Badge (§60). Small, low-radius, one line, no fill except for a 12% wash of
 * its own tone — a wash, not a chip with a glow.
 *
 * Callers: ContextInspector (object kind, status), AppShell top bar
 * (counts, status), workspace filter summary.
 */
export function Badge({ children, tone = "neutral", role = "chrome", title, mono, testId }: BadgeProps) {
  return (
    <span
      className="ui-badge"
      data-tone={tone}
      data-role={role}
      data-mono={mono ? "true" : undefined}
      title={title}
      data-testid={testId}
    >
      {children}
    </span>
  );
}

export interface StatusDotProps {
  status: WorkStatus;
  /** Visible text next to the dot. Omit only in a context that already names the status. */
  label?: string;
  /** Pulses only while `Running`; removed under prefers-reduced-motion (§67). */
  live?: boolean;
  testId?: string;
}

/**
 * StatusDot (§60, §92). The dot carries tone; the label carries the word.
 * Colour alone never conveys state.
 *
 * Callers: AppShell top bar (investigation state), ContextInspector
 * (processing state), workspace view headers, activity layer.
 */
export function StatusDot({ status, label, live = false, testId }: StatusDotProps) {
  const tone = statusTone(status);
  const pulse = live && status === "Running";
  return (
    <span className="ui-status" data-tone={tone} data-testid={testId}>
      <span className="ui-status-dot" data-live={pulse ? "true" : undefined} aria-hidden="true" />
      {label != null ? <span className="ui-status-label">{label}</span> : null}
      <span className="ui-sr-only">{status}</span>
    </span>
  );
}