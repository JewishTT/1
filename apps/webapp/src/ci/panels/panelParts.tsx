import type { ReactNode } from "react";

import { Badge } from "../../ui/Badge";
import type { CiServerState, Unavailable } from "../types";

/**
 * Shared panel furniture for the CI/SpecOps department (027).
 *
 * Every panel renders through these so the department reads as one instrument:
 * a titled head, the scope note, a status badge, and — when the backing donor or
 * endpoint is down — a NAMED ABSENCE list (§90, §99), never a blank pane and
 * never a fabricated zero.
 */

export function CiPanelShell({
  title,
  scope,
  status,
  children,
  testId,
}: {
  title: string;
  scope: CiServerState["scope"];
  status?: ReactNode;
  children: ReactNode;
  testId: string;
}) {
  return (
    <section className="ui-ci-panel" data-testid={testId}>
      <header className="ui-ci-panel-head">
        <span className="ui-pane-title">{title}</span>
        <span className="ui-id" data-testid={`${testId}-scope`}>
          {scope === "tenant-wide"
            ? "tenant-wide · not scoped to one investigation"
            : "investigation-scoped"}
        </span>
        {status}
      </header>
      {children}
    </section>
  );
}

/** The named-absence block. `missing` names each endpoint/field that would close it. */
export function NamedAbsence({
  missing,
  testId,
}: {
  missing: ReadonlyArray<string | Unavailable>;
  testId: string;
}) {
  if (missing.length === 0) return null;
  return (
    <ul className="ui-blockers" data-testid={testId}>
      {missing.map((m) => {
        const text = typeof m === "string" ? m : `${m.reason} — ${m.endpoint}`;
        return (
          <li key={text} className="ui-blocker">
            <span className="ui-blocker-name">not served</span>
            <span className="ui-blocker-settled">{text}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function StatusChip({
  label,
  tone = "neutral",
  testId,
}: {
  label: string;
  tone?: "accent" | "gold" | "danger" | "neutral" | "analytical" | "strong";
  testId?: string;
}) {
  return (
    <Badge tone={tone} testId={testId}>
      {label}
    </Badge>
  );
}

export function CiEmpty({ children }: { children: ReactNode }) {
  return <p className="panel-note">{children}</p>;
}
