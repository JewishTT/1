import { useEffect, useRef } from "react";

import { useWorkspace } from "../workspace/store";
import { actionsForSelection, destinationForAction } from "../workspace/commands";

/**
 * ContextMenu shell (§60). Opens at the workspace-owned coordinates, moves
 * focus into the first enabled action, supports arrow/Home/End navigation,
 * closes on Escape/outside pointer/Tab, and restores the previous focus target.
 * The caller supplies the action vocabulary; this component owns mechanics only.
 */
export interface ContextMenuItem {
  id: string;
  label: string;
  disabled?: boolean;
  run: () => void;
}

export function ContextMenu({ items }: { items: ReadonlyArray<ContextMenuItem> }) {
  const menu = useWorkspace((state) => state.contextMenu);
  const close = useWorkspace((state) => state.closeContextMenu);
  const rootRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const menuOpen = menu !== null;

  useEffect(() => {
    if (!menuOpen) return;

    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const firstItem = rootRef.current?.querySelector<HTMLButtonElement>(
      'button[role="menuitem"]:not(:disabled)',
    );
    (firstItem ?? rootRef.current)?.focus();

    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) close();
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      previousFocusRef.current?.focus();
      previousFocusRef.current = null;
    };
  }, [menuOpen, close]);

  if (!menu) return null;

  // Flip toward the opposite edge when the anchor would overflow.
  const flipX = menu.x > window.innerWidth - 220;
  const flipY = menu.y > window.innerHeight - 200;

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    }
    if (event.key === "Tab") {
      close();
      return;
    }

    const enabledItems = Array.from(
      rootRef.current?.querySelectorAll<HTMLButtonElement>('button[role="menuitem"]:not(:disabled)') ?? [],
    );
    if (enabledItems.length === 0) return;
    const activeIndex = enabledItems.indexOf(document.activeElement as HTMLButtonElement);
    let nextIndex = -1;

    if (event.key === "ArrowDown") nextIndex = activeIndex < 0 ? 0 : (activeIndex + 1) % enabledItems.length;
    else if (event.key === "ArrowUp") nextIndex = activeIndex < 0 || activeIndex === 0 ? enabledItems.length - 1 : activeIndex - 1;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = enabledItems.length - 1;

    if (nextIndex >= 0) {
      event.preventDefault();
      enabledItems[nextIndex]?.focus();
    }
  };

  return (
    <div
      ref={rootRef}
      role="menu"
      aria-label="Object actions"
      className="ui-ctxmenu"
      tabIndex={-1}
      style={{ left: `${menu.x}px`, top: `${menu.y}px` }}
      data-flip-x={flipX}
      data-flip-y={flipY}
      onKeyDown={onKeyDown}
      data-testid="context-menu"
    >
      {items.length === 0 ? (
        <span className="ui-ctxmenu-empty">Nothing selected</span>
      ) : (
        items.map((item) => (
          <button
            key={item.id}
            type="button"
            role="menuitem"
            className="ui-ctxmenu-item"
            disabled={item.disabled}
            onClick={() => {
              item.run();
              close();
            }}
            data-testid={`ctx-${item.id}`}
          >
            {item.label}
          </button>
        ))
      )}
    </div>
  );
}

/**
 * Canvas context menu: the same action set the inspector offers, so a
 * right-click and the "Next" row never disagree (§69).
 */
export function CanvasContextMenu() {
  const selection = useWorkspace((state) => state.selection);
  const secondaryCount = useWorkspace((state) => state.secondarySelection.length);
  const setView = useWorkspace((state) => state.setView);
  const toggleSecondary = useWorkspace((state) => state.toggleSecondary);
  const clearSelection = useWorkspace((state) => state.clearSelection);

  const actions = actionsForSelection(selection, secondaryCount);

  // The destination table is the single source of truth, shared with the
  // inspector's "Next" row, so a right-click and the inspector can never
  // disagree about where an action goes. Actions with no destination are
  // dropped rather than rendered as inert rows (§69).
  const items: Array<ContextMenuItem> = [
    ...actions.flatMap((action) => {
      const destination = destinationForAction(action.id);
      if (destination === null) return [];
      return [{ id: action.id, label: action.label, run: () => setView(destination) }];
    }),
    ...(selection
      ? [
          {
            id: "context.add-to-comparison",
            label: "Add to comparison",
            run: () => toggleSecondary(selection),
          },
        ]
      : []),
    ...(selection
      ? [{ id: "context.clear", label: "Clear selection", run: clearSelection }]
      : []),
  ];

  return <ContextMenu items={items} />;
}

