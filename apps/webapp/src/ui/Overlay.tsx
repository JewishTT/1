import {
  cloneElement,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
} from "react";

type Placement = "top" | "right" | "bottom" | "left";

/* ── Tooltip ──────────────────────────────────────────────────────────── */

export interface TooltipProps {
  /** Single focusable element. It receives aria-describedby and the handlers. */
  children: ReactElement;
  content: ReactNode;
  placement?: Placement;
}

/**
 * Tooltip (§60). Hover/focus reveal, Escape dismisses, and the content is
 * also exposed via `aria-describedby` so it is not mouse-only.
 *
 * Callers: IconButton wrappers where the icon needs a longer explanation than
 * its aria-label, inspector field affordances.
 */
export function Tooltip({ children, content, placement = "top" }: TooltipProps) {
  const [open, setOpen] = useState(false);
  const id = useId();

  const show = useCallback(() => setOpen(true), []);
  const hide = useCallback(() => setOpen(false), []);

  return (
    <span className="ui-tip-anchor" onPointerEnter={show} onPointerLeave={hide} onBlur={hide}>
      {cloneElement(children, {
        "aria-describedby": open ? id : undefined,
        onFocus: show,
        onBlur: hide,
        onKeyDown: (event: KeyboardEvent) => {
          if (event.key === "Escape") hide();
          const childHandler = (children.props as { onKeyDown?: (e: KeyboardEvent) => void }).onKeyDown;
          childHandler?.(event);
        },
      } as Record<string, unknown>)}
      <span
        id={id}
        role="tooltip"
        className="ui-tooltip"
        data-placement={placement}
        data-open={open ? "true" : "false"}
        hidden={!open}
      >
        {content}
      </span>
    </span>
  );
}

/* ── Popover ──────────────────────────────────────────────────────────── */

export interface PopoverProps {
  /** Trigger element. Must be focusable; receives aria-expanded/haspopup. */
  trigger: ReactElement;
  children: ReactNode;
  label: string;
  placement?: Placement;
  /** Align the panel's edge to the trigger's edge instead of centring it. */
  align?: "start" | "center" | "end";
  testId?: string;
}

/**
 * Popover (§60). A non-modal anchored panel: focus moves into it, Escape
 * returns focus to the trigger, click-outside dismisses. Deliberately not a
 * modal — the workbench behind it stays readable and operable, which is what
 * a single-workstation layout (§24) requires.
 *
 * Callers: AppShell top bar density/theme menu, left rail filter options,
 * inspector per-field overflow actions.
 */
export function Popover({ trigger, children, label, placement = "bottom", align = "start", testId }: PopoverProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLSpanElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const focusables = panelRef.current?.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    focusables?.[0]?.focus();
  }, [open]);

  const close = useCallback((restoreFocus = true) => {
    setOpen(false);
    if (restoreFocus) triggerRef.current?.focus();
  }, []);

  const onPanelKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      close();
    }
  };

  return (
    <span className="ui-pop-anchor" ref={rootRef}>
      {cloneElement(trigger, {
        "aria-haspopup": "dialog",
        "aria-expanded": open,
        "aria-controls": open ? id : undefined,
        // `currentTarget` is how the trigger node is captured: an arbitrary
        // ReactElement cannot carry a typed ref through cloneElement.
        onClick: (event: { currentTarget: HTMLElement }) => {
          triggerRef.current = event.currentTarget;
          setOpen((v) => !v);
        },
      } as Record<string, unknown>)}
      <div
        id={id}
        ref={panelRef}
        role="dialog"
        aria-label={label}
        className="ui-popover"
        data-placement={placement}
        data-align={align}
        data-open={open ? "true" : "false"}
        hidden={!open}
        onKeyDown={onPanelKeyDown}
        data-testid={testId}
      >
        {children}
      </div>
    </span>
  );
}

/* ── Drawer ───────────────────────────────────────────────────────────── */

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  label: string;
  children: ReactNode;
  side?: "bottom" | "right";
  testId?: string;
}

/**
 * Drawer (§60). The activity layer's container: a panel that slides in over
 * the canvas edge without unmounting what is behind it. Because it overlays
 * rather than replaces, the workspace keeps its selection and scroll
 * position — which is the whole point of the §24 single-workstation model.
 *
 * Callers: InvestigationWorkspace activity layer (§5 bottom layer),
 * object detail drawer from the canvas.
 */
export function Drawer({ open, onClose, label, children, side = "bottom", testId }: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="ui-drawer-root" data-side={side} data-testid={testId}>
      <div
        className="ui-drawer-scrim"
        onClick={onClose}
        aria-hidden="true"
        data-testid={testId != null ? `${testId}-scrim` : undefined}
      />
      <div
        ref={panelRef}
        className="ui-drawer"
        role="dialog"
        aria-modal="false"
        aria-label={label}
        data-side={side}
      >
        {children}
      </div>
    </div>
  );
}