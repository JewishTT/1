import { useMemo } from "react";

import type { IconName } from "./ui/Icon";
import { useWorkspace } from "./workspace/store";
import { useCommandPalette, type Command, type CommandContext } from "./workspace/commands";
import type { WorkspaceView } from "./workspace/types";
import { WORKSPACE_VIEWS } from "./workspace/types";

/**
 * The command registry (§9, §49, §50).
 *
 * One table, used by both ⌘K and the single-key chords, so the two can never
 * drift apart. Every entry has a stable, documented id — the id is the
 * contract; labels may be reworded.
 *
 *   workspace.view.overview|graph|objects|evidence|timeline|acquisition|findings|analysis|ops
 *   selection.clear | selection.pin | selection.compare
 *   filter.evidence.clear | filter.time.clear
 *   layout.density.toggle | layout.theme.toggle
 *   layout.pane.rail.toggle | layout.pane.inspector.toggle | layout.pane.activity.toggle
 *   palette.toggle
 *
 * Commands whose *content* belongs to stages 3–8 are still registered and
 * still move the workspace to the view that will host that work. They do not
 * pretend the screen exists.
 *
 * ONE TABLE, ONE LIST OF VIEWS: the view commands are generated from
 * `WORKSPACE_VIEWS`, not from a hand-written copy of it. A second list would be
 * a place for a view to exist in the switcher and not in ⌘K, which is the drift
 * §9 forbids.
 */

const VIEW_ICON: Record<WorkspaceView, IconName> = {
  overview: "view-overview",
  graph: "view-graph",
  objects: "view-objects",
  evidence: "view-evidence",
  timeline: "view-timeline",
  acquisition: "view-acquisition",
  findings: "view-findings",
  analysis: "view-analysis",
  ops: "view-ops",
};

/** §50 chords. Only these five views get a single key. */
const VIEW_KEYS: Partial<Record<WorkspaceView, string>> = {
  graph: "G",
  objects: "O",
  evidence: "E",
  timeline: "T",
  acquisition: "A",
};

export function buildRegistry(): Array<Command> {
  const store = () => useWorkspace.getState();

  const views: Array<Command> = WORKSPACE_VIEWS.map((view) => ({
    id: `workspace.view.${view}`,
    label: `Go to ${view[0].toUpperCase()}${view.slice(1)}`,
    group: "View",
    icon: VIEW_ICON[view],
    keywords: ["canvas", "switch", view],
    ...(VIEW_KEYS[view] ? { key: VIEW_KEYS[view] } : {}),
    run: () => store().setView(view),
  }));

  return [
    ...views,

    {
      id: "selection.clear",
      label: "Clear selection",
      group: "Selection",
      icon: "close",
      keywords: ["deselect", "esc"],
      when: (ctx) => ctx.selection !== null,
      run: () => store().clearSelection(),
    },
    {
      id: "selection.pin",
      label: "Pin selected object in inspector",
      group: "Selection",
      icon: "copy",
      keywords: ["keep", "inspector"],
      when: (ctx) => ctx.selection !== null,
      run: () => {
        const { selection, pinnedInspectors, pinInspector } = store();
        if (!selection) return;
        const already = pinnedInspectors.some((entry) => entry.id === selection.id);
        pinInspector(already ? null : selection);
      },
    },
    {
      id: "selection.compare",
      label: "Compare with secondary selection",
      group: "Selection",
      icon: "view-analysis",
      keywords: ["diff", "contrast"],
      when: (ctx) => ctx.secondaryCount > 0,
      run: () => store().setView("analysis"),
    },

    {
      id: "filter.evidence.clear",
      label: "Clear evidence filter",
      group: "Filter",
      keywords: ["reset", "query", "evidence"],
      run: () => store().resetEvidenceFilter(),
    },
    {
      id: "filter.time.clear",
      label: "Clear time range",
      group: "Filter",
      icon: "clock",
      keywords: ["reset", "timeline", "window"],
      run: () => store().clearTimeRange(),
    },

    {
      id: "layout.density.toggle",
      label: "Toggle density (Compact / Comfortable)",
      group: "Layout",
      icon: "density",
      keywords: ["compact", "comfortable", "spacing"],
      run: () => store().toggleDensity(),
    },
    {
      id: "layout.theme.toggle",
      label: "Toggle theme (dark / light)",
      group: "Layout",
      keywords: ["dark", "light", "appearance"],
      run: () => store().toggleTheme(),
    },
    {
      id: "layout.pane.rail.toggle",
      label: "Toggle left context rail",
      group: "Layout",
      icon: "panel-left",
      keywords: ["sidebar", "hide", "show"],
      run: () => store().togglePane("rail"),
    },
    {
      id: "layout.pane.inspector.toggle",
      label: "Toggle right inspector",
      group: "Layout",
      icon: "panel-right",
      keywords: ["panel", "hide", "show"],
      run: () => store().togglePane("inspector"),
    },
    {
      id: "layout.pane.activity.toggle",
      label: "Toggle bottom activity layer",
      group: "Layout",
      icon: "panel-bottom",
      keywords: ["activity", "log", "hide", "show"],
      run: () => store().togglePane("activity"),
    },
    {
      id: "palette.toggle",
      label: "Open command palette",
      group: "Palette",
      icon: "command",
      keywords: ["cmdk", "search", "commands"],
      run: () => store().setCommandPaletteOpen(true),
    },
  ];
}

/** Command ids are unique and stable — asserted by the registry test. */
export function commandIds(registry: ReadonlyArray<Command>): string[] {
  return registry.map((command) => command.id);
}

export interface CommandContextBinding {
  registry: Array<Command>;
  context: CommandContext;
  palette: ReturnType<typeof useCommandPalette>;
}

/**
 * The registry plus the palette interaction state, bound to the live workspace
 * context. The registry itself is built once: it contains no closures over
 * changing values (every `run` reads `getState()`), so a stable array keeps
 * the palette's memoisation honest.
 */
export function useCommandContext(
  /**
   * Wraps every execution path — click, Enter, anything the palette triggers.
   * The palette closes here rather than in each handler, so "run a command"
   * cannot mean "run it and leave the palette open".
   */
  onExecute: (command: Command) => void = (command) => command.run(),
): CommandContextBinding {
  const view = useWorkspace((state) => state.view);
  const selection = useWorkspace((state) => state.selection);
  const secondaryCount = useWorkspace((state) => state.secondarySelection.length);
  const paletteOpen = useWorkspace((state) => state.commandPaletteOpen);

  const context = useMemo<CommandContext>(
    () => ({ view, selection, secondaryCount, paletteOpen }),
    [view, selection, secondaryCount, paletteOpen],
  );

  const registry = useMemo(() => buildRegistry(), []);

  const palette = useCommandPalette(registry, context, onExecute);

  return { registry, context, palette };
}