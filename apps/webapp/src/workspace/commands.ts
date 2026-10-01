import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { IconName } from "../ui/Icon";
import type { WorkspaceObjectKind, WorkspaceSelection, WorkspaceView } from "./types";

/**
 * Command engine (§9, §49, §50).
 *
 * Not a search box. A *registry* of commands, each with:
 *   - a stable, documented `id` (the id is the contract; labels may be reworded)
 *   - a context `when` predicate — a command can declare that it only exists
 *     when something is selected, or only in a certain view, or only when the
 *     palette itself is open
 *   - grouping and search terms, so ⌘K and the single-key chords resolve from
 *     the same table
 *
 * `filterCommands` is a pure function over (registry, query, context): it is
 * what the palette renders and what the command tests assert on.
 */

export interface CommandContext {
  view: WorkspaceView;
  selection: WorkspaceSelection | null;
  secondaryCount: number;
  /** True while ⌘K is open. Some commands only make sense there. */
  paletteOpen: boolean;
}

export interface Command<Args extends unknown[] = []> {
  /** Stable identifier, e.g. `workspace.view.graph`. Documented, never reused. */
  id: string;
  label: string;
  group: string;
  icon?: IconName;
  /** Extra search terms not present in the label ("jump", "canvas"). */
  keywords?: ReadonlyArray<string>;
  /** Context predicate. Absent ⇒ always available. */
  when?: (context: CommandContext) => boolean;
  run: (...args: Args) => void;
  /** Single-key chord (§50). Never bound while a text field has focus. */
  key?: string;
}

/** Sort by group order, then by label, so the list is stable between opens. */
function byGroupThenLabel(a: Command, b: Command): number {
  if (a.group !== b.group) return a.group.localeCompare(b.group);
  return a.label.localeCompare(b.label);
}

/** The commands available in the current context. */
export function availableCommands(
  registry: ReadonlyArray<Command>,
  context: CommandContext,
): Array<Command> {
  return registry.filter((command) => (command.when ? command.when(context) : true)).sort(byGroupThenLabel);
}

/**
 * Fuzzy-ish subsequence match over label, id, group and keywords, scored so
 * prefix > word-start > subsequence. Stable: equal scores keep registry order.
 */
export function commandScore(command: Command, query: string): number {
  const needle = query.trim().toLowerCase();
  if (needle === "") return 1;
  const label = command.label.toLowerCase();
  if (label.startsWith(needle)) return 1000 - label.length;
  if (label.includes(needle)) return 700 - label.length;
  if (command.id.toLowerCase().includes(needle)) return 500 - command.id.length;
  for (const keyword of command.keywords ?? []) {
    if (keyword.toLowerCase().startsWith(needle)) return 400 - keyword.length;
    if (keyword.toLowerCase().includes(needle)) return 300 - keyword.length;
  }
  const haystack = label.replace(/\s+/g, "");
  let cursor = 0;
  for (const char of needle.replace(/\s+/g, "")) {
    cursor = haystack.indexOf(char, cursor);
    if (cursor === -1) return 0;
    cursor += 1;
  }
  return 100 - needle.length;
}

/** The commands the palette shows: context-filtered, then scored, then cut. */
export function filterCommands(
  registry: ReadonlyArray<Command>,
  context: CommandContext,
  query: string,
  limit = 50,
): Array<Command> {
  const available = availableCommands(registry, context);
  const scored = available
    .map((command, index) => ({ command, index, score: commandScore(command, query) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => (b.score === a.score ? a.index - b.index : b.score - a.score));
  return scored.slice(0, limit).map((entry) => entry.command);
}

/** The single-key chord bound to `key`, or null. (§50) */
export function commandForKey(
  registry: ReadonlyArray<Command>,
  context: CommandContext,
  key: string,
): Command | null {
  const upper = key.toUpperCase();
  return (
    registry.find(
      (command) =>
        command.key !== undefined &&
        command.key.toUpperCase() === upper &&
        (command.when ? command.when(context) : true),
    ) ?? null
  );
}

/**
 * Is this event target a place where a plain letter must stay a letter?
 * §50 is explicit that the keyboard model must not break text input.
 */
export function isTextEntryTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  // `isContentEditable` is unreliable under jsdom and on nested nodes, so the
  // attribute and the ancestor chain are consulted directly.
  if (target.isContentEditable || target.closest("[contenteditable='true'], [contenteditable='']")) return true;
  const tag = target.tagName;
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag !== "INPUT") return false;
  const type = (target as HTMLInputElement).type;
  // Buttons, checkboxes and the like are not text entry; ⌘K still applies.
  return !["button", "checkbox", "radio", "submit", "reset", "range", "file"].includes(type);
}

/* ── Keyboard wiring ─────────────────────────────────────────────────── */

export interface CommandHotkeysOptions {
  registry: ReadonlyArray<Command>;
  context: CommandContext;
  /** Fired by the ⌘K / Ctrl-K chord regardless of focus, unless in text entry. */
  onTogglePalette: () => void;
  /** Fired by Escape when there is nothing else to clear. */
  onEscape: () => void;
}

/**
 * Document-level keyboard handling for §50:
 *   ⌘K / Ctrl-K  open the command palette
 *   G O E T A    switch the centre canvas view
 *   Esc          clear the selection, or close the palette, or close an overlay
 *
 * Single-key chords are suppressed inside text entry (§50), and are ignored
 * when a modifier is held, so ⌘R / Ctrl-R and browser chords still work.
 * `Enter` is deliberately not bound globally: it belongs to the focused
 * control, and the palette's own input handles it.
 */
export function useCommandHotkeys({ registry, context, onTogglePalette, onEscape }: CommandHotkeysOptions) {
  const latest = useRef({ registry, context, onTogglePalette, onEscape });
  latest.current = { registry, context, onTogglePalette, onEscape };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const { registry: reg, context: ctx, onTogglePalette: toggle, onEscape: escape } = latest.current;

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        toggle();
        return;
      }

      if (event.key === "Escape") {
        escape();
        return;
      }

      // Modifier combinations belong to the browser and the OS, not to us.
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTextEntryTarget(event.target)) return;

      const command = commandForKey(reg, ctx, event.key);
      if (command) {
        event.preventDefault();
        command.run();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);
}

/* ── Command palette interaction ─────────────────────────────────────── */

export interface PaletteState {
  query: string;
  index: number;
  results: Array<Command>;
}

/** Query + highlight-aware selection state for the palette's listbox. */
export function useCommandPalette(
  registry: ReadonlyArray<Command>,
  context: CommandContext,
  onRun: (command: Command) => void,
) {
  const [state, setState] = useState<PaletteState>({ query: "", index: 0, results: [] });
  const results = useMemo(() => filterCommands(registry, context, state.query), [registry, context, state.query]);

  // Clamp the highlighted row whenever the result set changes under us.
  useEffect(() => {
    setState((prev) => (prev.index >= results.length ? { ...prev, index: Math.max(0, results.length - 1) } : prev));
  }, [results.length]);

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLInputElement>) => {
      switch (event.key) {
        case "ArrowDown":
          event.preventDefault();
          setState((prev) => ({ ...prev, index: results.length === 0 ? 0 : (prev.index + 1) % results.length }));
          return;
        case "ArrowUp":
          event.preventDefault();
          setState((prev) => ({
            ...prev,
            index: results.length === 0 ? 0 : (prev.index - 1 + results.length) % results.length,
          }));
          return;
        case "Home":
          setState((prev) => ({ ...prev, index: 0 }));
          return;
        case "End":
          setState((prev) => ({ ...prev, index: Math.max(0, results.length - 1) }));
          return;
        case "Enter": {
          // §50: Enter opens the highlighted command.
          event.preventDefault();
          const command = results[state.index];
          if (command) onRun(command);
          return;
        }
        default:
      }
    },
    [results, state.index, onRun],
  );

  const select = useCallback((index: number) => setState((prev) => ({ ...prev, index })), []);

  /** Typing resets the highlight to the top row — the expected listbox behaviour. */
  const setQuery = useCallback((query: string) => setState((prev) => ({ ...prev, query, index: 0 })), []);

  /** Called after a command runs: the palette closes and the query is dropped. */
  const reset = useCallback(() => setState({ query: "", index: 0, results: [] }), []);

  return { query: state.query, index: state.index, results, select, setQuery, reset, onKeyDown };
}

/* ── Selection-bound commands (§69: no dead ends) ────────────────────── */

/**
 * Every selection of a domain object must offer a way forward. This maps the
 * primary selection to the actions the shell can perform on it, and the
 * inspector uses it to render a "next step" list rather than a dead end.
 *
 * `needsSecondary` currently filters nothing, because no stage-2 action needs
 * a second object. The gate is kept rather than deleted: the comparison
 * surface it was written for is stage-3+ work, and removing the hook now would
 * only mean re-adding it there. `secondarySelection` is live state in the
 * meantime — the rail counts it and the ⌘K palette gates `selection.compare`
 * on it.
 */
export function actionsForSelection(
  selection: WorkspaceSelection | null,
  secondaryCount: number,
): Array<{ id: string; label: string; needsSecondary: boolean }> {
  if (!selection) return [];
  const base: Array<{ id: string; label: string; needsSecondary: boolean }> = [];
  switch (selection.kind) {
    case "Entity":
      base.push({ id: "entity.show-in-graph", label: "Show in graph", needsSecondary: false });
      // No `entity.compare`: a comparison surface is stage-3+ work, and a
      // button that promises a comparison the workspace cannot perform is
      // exactly the dead end §69 forbids.
      break;
    case "Observation":
      base.push({ id: "observation.show-source", label: "Show source capture", needsSecondary: false });
      base.push({ id: "observation.show-on-timeline", label: "Show on timeline", needsSecondary: false });
      break;
    case "Claim":
      base.push({ id: "claim.show-participants", label: "Show participants", needsSecondary: false });
      base.push({ id: "claim.show-evidence", label: "Show supporting evidence", needsSecondary: false });
      break;
    case "Finding":
      base.push({ id: "finding.walk-lineage", label: "Walk lineage to source", needsSecondary: false });
      break;
    case "AcquisitionTask":
    case "AcquisitionRun":
      base.push({ id: "acquisition.show-task", label: "Show acquisition task", needsSecondary: false });
      break;
    case "Source":
    case "Capture":
      base.push({ id: "source.show-observations", label: "Show observations", needsSecondary: false });
      break;
    case "Investigation":
      base.push({ id: "investigation.show-findings", label: "Show findings", needsSecondary: false });
      base.push({ id: "investigation.show-acquisition", label: "Show acquisition", needsSecondary: false });
      break;
  }
  return secondaryCount === 0 ? base.filter((action) => !action.needsSecondary) : base;
}

/**
 * Every action resolves to a concrete destination view, declared here rather
 * than inferred at the call site.
 *
 * §69 is a floor, not an aspiration: a next step that does not move the
 * analyst anywhere is a dead end, and the earlier `id.endsWith(...)` chain in
 * the inspector silently left four of the eight actions inert. Declaring the
 * destination in one table makes an unmapped action a type error rather than a
 * button that does nothing, and lets the §69 tests assert the whole set.
 */
export const ACTION_DESTINATIONS: Readonly<Record<string, WorkspaceView>> = {
  "entity.show-in-graph": "graph",
  "observation.show-source": "evidence",
  "observation.show-on-timeline": "timeline",
  "claim.show-participants": "objects",
  "claim.show-evidence": "evidence",
  "finding.walk-lineage": "evidence",
  "acquisition.show-task": "acquisition",
  "source.show-observations": "evidence",
  "investigation.show-findings": "findings",
  "investigation.show-acquisition": "acquisition",
};

/** The view an action navigates to, or null if it has no destination. */
export function destinationForAction(actionId: string): WorkspaceView | null {
  return ACTION_DESTINATIONS[actionId] ?? null;
}

/** Kinds the inspector knows how to describe (§33, §34). Anything else gets the generic path. */
export const INSPECTOR_KINDS: ReadonlyArray<WorkspaceObjectKind> = [
  "Entity",
  "Observation",
  "Capture",
  "Claim",
  "Finding",
  "AcquisitionTask",
  "AcquisitionRun",
  "Source",
  "Investigation",
];