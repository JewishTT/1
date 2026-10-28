import { useEffect, useId, useRef, type ReactNode } from "react";

import { IconButton } from "./Button";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  closeOnBackdrop?: boolean;
  testId?: string;
}

/**
 * Modal dialog (§11–12). Focus is moved into the dialog, Tab is contained,
 * Escape closes it, body scrolling is temporarily locked, and focus returns
 * to its trigger on close. Use Drawer for non-modal inspector/activity panels.
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  actions,
  children,
  closeOnBackdrop = true,
  testId,
}: ModalProps) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef<HTMLElement>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;

    const previouslyFocused = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const previousOverflow = document.body.style.overflow;
    const panel = panelRef.current;
    const selector =
      'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])';

    document.body.style.overflow = "hidden";
    const focusFirst = () => {
      const focusable = panel?.querySelector<HTMLElement>(selector);
      (focusable ?? panel)?.focus();
    };
    focusFirst();

    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onCloseRef.current();
        return;
      }

      if (event.key !== "Tab" || !panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(selector)).filter(
        (element) => element.getAttribute("aria-hidden") !== "true",
      );
      if (focusable.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }

      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown, true);
    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="ui-modal-root" data-testid={testId}>
      <div
        className="ui-modal-scrim"
        aria-hidden="true"
        data-testid={testId != null ? `${testId}-scrim` : undefined}
        onMouseDown={(event) => {
          if (closeOnBackdrop && event.target === event.currentTarget) onCloseRef.current();
        }}
      />
      <section
        ref={panelRef}
        className="ui-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        data-testid={testId != null ? `${testId}-dialog` : undefined}
      >
        <header className="ui-modal-head">
          <div className="ui-modal-heading">
            <h2 className="ui-modal-title" id={titleId}>{title}</h2>
            {description ? <div className="ui-modal-description" id={descriptionId}>{description}</div> : null}
          </div>
          <IconButton icon="close" label="Close dialog" size="sm" onClick={() => onCloseRef.current()} />
        </header>
        <div className="ui-modal-body">{children}</div>
        {actions ? <footer className="ui-modal-actions">{actions}</footer> : null}
      </section>
    </div>
  );
}
