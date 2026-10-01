import { useEffect, useRef } from "react";

import { useWorkspace } from "../workspace/store";
import { actionsForSelection, destinationForAction } from "../workspace/commands";

/**
 * ContextMenu shell (§60).
 *
 * Right-click affordance over the canvas. A shell: it takes the item list from
 * the caller, closes on Escape / outside click, restores focus, and positions
 * itself inside the viewport. It does not decide *what* the items are.
 *
 * The canvas's menu is built from `actionsForSelection` (§69), so it offers the
 * same next steps as the inspector and cannot drift from it. The menu is only
 * mounted when the store holds coordinates, so it never steals selection.
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

  useEffect(() => {
    if (!menu) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) close();
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [menu, close]);

  if (!menu) return null;

  // Flip toward the opposite edge when the anchor would overflow.
  const flipX = menu.x > window.innerWidth - 220;
  const flipY = menu.y > window.innerHeight - 200;

  return (
    <div
      ref={rootRef}
      role="menu"
      aria-label="Object actions"
      className="ui-ctxmenu"
      style={{ left: `${menu.x}px`, top: `${menu.y}px` }}
      data-flip-x={flipX}
      data-flip-y={flipY}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          close();
        }
      }}
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

