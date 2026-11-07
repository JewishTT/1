import type { ReactNode } from "react";

import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import type { LabTone } from "../model";

export function LabPanelShell({
  title,
  status,
  children,
  testId,
}: {
  title: string;
  status?: ReactNode;
  children: ReactNode;
  testId: string;
}) {
  return (
    <section className="ui-ci-panel" data-testid={testId}>
      <header className="ui-ci-panel-head">
        <span className="ui-pane-title">{title}</span>
        <span className="ui-id">full red-team · RoE-gated</span>
        {status}
      </header>
      {children}
    </section>
  );
}

export function LabAbsence({
  missing,
  testId,
}: {
  missing: ReadonlyArray<string>;
  testId: string;
}) {
  if (missing.length === 0) return null;
  return (
    <ul className="ui-blockers" data-testid={testId}>
      {missing.map((item) => (
        <li key={item} className="ui-blocker">
          <span className="ui-blocker-name">blocked</span>
          <span className="ui-blocker-settled">{item}</span>
        </li>
      ))}
    </ul>
  );
}

export function LabChip({
  label,
  tone = "neutral",
  testId,
}: {
  label: string;
  tone?: LabTone;
  testId?: string;
}) {
  return (
    <Badge tone={tone} testId={testId}>
      {label}
    </Badge>
  );
}

export function LabMetric({ label, value }: { label: string; value: number | string }) {
  const text = typeof value === "number" ? value.toLocaleString() : value;
  return (
    <div className="ui-ci-metric">
      <span className="op-label">{label}</span>
      <span className="op-value">{text}</span>
    </div>
  );
}

export function LabNote({ note, testId }: { note: string | null; testId: string }) {
  if (!note) return null;
  return (
    <p className="panel-note" data-testid={testId} role="status">
      {note}
    </p>
  );
}

export function LabActionButton({
  onClick,
  disabled,
  children,
  testId,
  variant = "default",
}: {
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
  testId: string;
  variant?: "default" | "primary" | "ghost" | "danger";
}) {
  return (
    <Button size="sm" variant={variant} disabled={disabled} onClick={onClick} data-testid={testId}>
      {children}
    </Button>
  );
}
