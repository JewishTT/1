import type { ReactNode } from "react";

export interface ToastViewportProps {
  children: ReactNode;
  label?: string;
  testId?: string;
}

/**
 * Fixed, safe-area-aware notification stack. Lifetime and queue order remain
 * caller-owned; each Toast provides its own live-region priority and dismissal.
 */
export function ToastViewport({
  children,
  label = "Notifications",
  testId,
}: ToastViewportProps) {
  return (
    <div className="ui-toast-viewport" role="region" aria-label={label} data-testid={testId}>
      {children}
    </div>
  );
}
