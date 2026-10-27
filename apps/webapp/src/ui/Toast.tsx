import type { ReactNode } from "react";

import { Button } from "./Button";
import { Icon } from "./Icon";

export type ToastTone = "info" | "success" | "warning" | "danger";

export interface ToastProps {
  message: ReactNode;
  title?: string;
  tone?: ToastTone;
  actions?: ReactNode;
  onDismiss?: () => void;
  testId?: string;
}

/**
 * One accessible toast notification. Callers own its lifetime and queue; this
 * primitive owns tone, announcement priority, layout and dismissal affordance.
 * Use ErrorView for persistent failures that must remain in the page.
 */
export function Toast({
  message,
  title,
  tone = "info",
  actions,
  onDismiss,
  testId,
}: ToastProps) {
  const icon = tone === "success" ? "check" : tone === "warning" || tone === "danger" ? "alert" : "activity";
  const urgent = tone === "danger";

  return (
    <div
      className="ui-toast"
      data-tone={tone}
      role={urgent ? "alert" : "status"}
      aria-live={urgent ? "assertive" : "polite"}
      data-testid={testId}
    >
      <span className="ui-toast-icon" aria-hidden="true">
        <Icon name={icon} size={16} />
      </span>
      <div className="ui-toast-content">
        {title ? <p className="ui-toast-title">{title}</p> : null}
        <div className="ui-toast-message">{message}</div>
        {actions ? <div className="ui-toast-actions">{actions}</div> : null}
      </div>
      {onDismiss ? (
        <Button size="sm" variant="ghost" icon="close" onClick={onDismiss} aria-label="Dismiss notification">
          <span className="ui-sr-only">Dismiss notification</span>
        </Button>
      ) : null}
    </div>
  );
}
