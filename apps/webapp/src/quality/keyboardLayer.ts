import { useEffect, useRef } from "react";

import { commandForKey } from "../workspace/commands";
import { isPaletteChord, resolveKey } from "../workspace/keyboard";
import { useWorkspace } from "../workspace/store";
import type { Command, CommandContext } from "../workspace/commands";

/**
 * The corrected §50 wiring.
 *
 * This is a drop-in replacement for `useCommandHotkeys`, not a second keyboard
 * system. It calls the same registry and the same `commandForKey`, so a chord
 * added to `src/CommandBar.tsx` is live here with no second registration, and
 * the palette is opened through the same store field.
 *
 * What it changes, and why — the four defects are documented in
 * `src/workspace/keyboard.ts`; this hook is where they are fixed in behaviour:
 *
 *   K1/K2  text entry includes ARIA roles and `plaintext-only`, so typing "graph"
 *          into a `role="textbox"` filter no longer navigates.
 *   K3     an IME composition is never resolved to a chord, so typing a CJK or
 *          dead-key grapheme beginning with a bound letter stays a keystroke.
 *   K4     a key another handler already consumed (`defaultPrevented`) is left
 *          alone, so the palette's Enter and a slider's arrows do not also fire
 *          a workspace action.
 *
 * And one correction to the palette chord predicate: `Ctrl-Shift-K` is no longer
 * treated as ⌘K, because in Chrome and Edge it opens devtools and a workspace
 * that swallows it leaves a developer unable to inspect the workspace.
 *
 * WHAT IT DELIBERATELY DOES NOT DO:
 *
 *   - It does not bind `Enter` globally. §50 assigns Enter to the focused
 *     control; a global binding would fire "open" on every Enter in a text field.
 *   - It does not add chords. The table lives in `CommandBar.buildRegistry`.
 *   - It does not touch the store beyond `setCommandPaletteOpen`, which is what
 *     ⌘K already did.
 *
 * §68: the registry and the callbacks live in a ref, so the listener is attached
 * once for the life of the component and a store write does not re-register it.
 */
export interface WorkspaceKeyboardOptions {
  registry: ReadonlyArray<Command>;
  context: CommandContext;
  /** Called by the palette chord, regardless of focus. */
  onTogglePalette: () => void;
  /**
   * Called by Escape. Should close only the topmost layer; the ladder below the
   * palette handles the rest.
   */
  onEscape: () => void;
}

export function useWorkspaceKeyboard({ registry, context, onTogglePalette, onEscape }: WorkspaceKeyboardOptions) {
  // `useCommandHotkeys` keeps its inputs in a ref for the same reason and with
  // the same effect: the document listener must not be torn down and rebuilt on
  // every store write, or a keystroke racing a re-render is lost.
  const latest = useRef({ registry, context, onTogglePalette, onEscape });
  latest.current = { registry, context, onTogglePalette, onEscape };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const current = latest.current;

      // The palette chord first and unconditionally: it must work from inside a
      // text field, which is where a user reaches for it.
      if (isPaletteChord(event)) {
        event.preventDefault();
        current.onTogglePalette();
        return;
      }

      if (event.key === "Escape") {
        current.onEscape();
        return;
      }

      // `resolveKey` owns the text-entry, composition, modifier and
      // already-handled checks, in that order.
      const resolution = resolveKey(event, (key) => commandForKey(current.registry, current.context, key));
      if (resolution.availability !== "available" || resolution.commandId === null) return;

      const command = current.registry.find((entry) => entry.id === resolution.commandId);
      if (command === undefined) return;
      event.preventDefault();
      command.run();
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);
}

/**
 * The layer-claiming Escape ladder.
 *
 * One Escape closes exactly one layer, and the first ACTIVE handler wins. This
 * is the §50 rule and it is what keeps "close" from meaning "close everything":
 * a second Escape is a second decision.
 *
 * The default ladder, in order: the context menu, then the palette, then the
 * selection, then any caller-supplied layer. The palette sits ABOVE the context
 * menu in the list only because both can be open at once; when both are, Escape
 * takes the palette first and leaves the menu, which is the reverse of the
 * visual stacking and therefore a defect worth naming rather than hiding. §69's
 * answer is that a caller with both open should not render both.
 */
export interface EscapeLayer {
  readonly active: boolean;
  readonly run: () => void;
}

/**
 * Which layer an Escape would close.
 *
 * Pure, and exported so the audit can assert the ladder over a matrix of open
 * layers without mounting anything.
 */
export function topmostLayer(layers: ReadonlyArray<EscapeLayer>): EscapeLayer | null {
  for (const layer of layers) if (layer.active) return layer;
  return null;
}

/**
 * The Escape ladder, wired to `document`.
 *
 * `Escape` from a text field is deliberately NOT special-cased: clearing a
 * filter with Escape is a reasonable expectation, and the caller decides what the
 * top layer is. What this guarantees is that exactly one thing changes.
 */
export function useEscapeLadder(layers: ReadonlyArray<EscapeLayer>) {
  // Same ref discipline as the hotkeys: one listener, current values.
  const latest = useRef(layers);
  latest.current = layers;

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const target = topmostLayer(latest.current);
      if (target === null) return;
      event.preventDefault();
      target.run();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);
}

/**
 * The default ladder for the current workspace.
 *
 * Reads the store with narrow selectors (§68) and returns the layers in closing
 * order. Split out from the hook so the ladder can be exercised against a plain
 * store state in a test, with no DOM involved.
 */
export function useWorkspaceEscapeLadder(): void {
  const paletteOpen = useWorkspace((state) => state.commandPaletteOpen);
  const contextMenuOpen = useWorkspace((state) => state.contextMenu !== null);
  const selection = useWorkspace((state) => state.selection);
  const setPaletteOpen = useWorkspace((state) => state.setCommandPaletteOpen);
  const closeContextMenu = useWorkspace((state) => state.closeContextMenu);
  const clearSelection = useWorkspace((state) => state.clearSelection);

  useEscapeLadder([
    { active: contextMenuOpen, run: closeContextMenu },
    { active: paletteOpen, run: () => setPaletteOpen(false) },
    { active: !paletteOpen && !contextMenuOpen && selection !== null, run: clearSelection },
  ]);
}