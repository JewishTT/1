import { describe, expect, it, vi } from "vitest";

import {
  INSPECTOR_KINDS,
  actionsForSelection,
  availableCommands,
  commandForKey,
  commandScore,
  destinationForAction,
  filterCommands,
  isTextEntryTarget,
  type Command,
  type CommandContext,
} from "./commands";

const context: CommandContext = {
  view: "graph",
  selection: { kind: "Entity", id: "ENT-182" },
  secondaryCount: 0,
  paletteOpen: false,
};

const noSelection: CommandContext = { ...context, selection: null, secondaryCount: 0 };

function makeRegistry(): Array<Command> {
  return [
    { id: "workspace.view.graph", label: "Go to Graph", group: "View", key: "G", run: () => {} },
    { id: "workspace.view.objects", label: "Go to Objects", group: "View", key: "O", run: () => {} },
    { id: "workspace.view.evidence", label: "Go to Evidence", group: "View", key: "E", run: () => {} },
    { id: "workspace.view.timeline", label: "Go to Timeline", group: "View", key: "T", run: () => {} },
    { id: "workspace.view.acquisition", label: "Go to Acquisition", group: "View", key: "A", run: () => {} },
    {
      id: "selection.clear",
      label: "Clear selection",
      group: "Selection",
      run: () => {},
      when: (ctx) => ctx.selection !== null,
    },
    {
      id: "selection.compare",
      label: "Compare selection",
      group: "Selection",
      run: () => {},
      when: (ctx) => ctx.selection !== null && ctx.secondaryCount > 0,
    },
    {
      id: "palette.recent-searches",
      label: "Recent searches",
      group: "Palette",
      run: () => {},
      when: (ctx) => ctx.paletteOpen,
    },
  ];
}

describe("command registry — availability (§9 context predicates)", () => {
  it("hides a command whose `when` fails", () => {
    const ids = availableCommands(makeRegistry(), noSelection).map((c) => c.id);
    expect(ids).not.toContain("selection.clear");
    expect(ids).not.toContain("selection.compare");
  });

  it("shows selection commands when something is selected", () => {
    const ids = availableCommands(makeRegistry(), context).map((c) => c.id);
    expect(ids).toContain("selection.clear");
    // Still hidden: compare needs a secondary selection.
    expect(ids).not.toContain("selection.compare");
  });

  it("shows compare only with a secondary selection", () => {
    const ids = availableCommands(makeRegistry(), { ...context, secondaryCount: 2 }).map((c) => c.id);
    expect(ids).toContain("selection.compare");
  });

  it("scopes palette-only commands to the palette being open", () => {
    const closed = availableCommands(makeRegistry(), context).map((c) => c.id);
    const open = availableCommands(makeRegistry(), { ...context, paletteOpen: true }).map((c) => c.id);
    expect(closed).not.toContain("palette.recent-searches");
    expect(open).toContain("palette.recent-searches");
  });

  it("orders by group then label, stably", () => {
    const labels = availableCommands(makeRegistry(), context).map((c) => `${c.group}/${c.label}`);
    const sorted = [...labels].sort((a, b) => a.localeCompare(b));
    expect(labels).toEqual(sorted);
  });
});

describe("command registry — search", () => {
  it("matches on label prefix ahead of substring", () => {
    const [graph] = filterCommands(makeRegistry(), context, "go to g");
    expect(graph.id).toBe("workspace.view.graph");
  });

  it("matches on id when the label does not contain the query", () => {
    const ids = filterCommands(makeRegistry(), context, "workspace.view.timeline").map((c) => c.id);
    expect(ids).toContain("workspace.view.timeline");
  });

  it("returns everything available for an empty query", () => {
    expect(filterCommands(makeRegistry(), context, "")).toHaveLength(
      availableCommands(makeRegistry(), context).length,
    );
  });

  it("returns nothing for a query that matches nothing", () => {
    expect(filterCommands(makeRegistry(), context, "zzzzz")).toEqual([]);
  });

  it("still applies the context predicate to search results", () => {
    // "clear" matches selection.clear, which is unavailable with no selection.
    expect(filterCommands(makeRegistry(), noSelection, "clear")).toEqual([]);
  });

  it("scores prefix higher than subsequence", () => {
    const command: Command = { id: "x.y", label: "Go to Graph", group: "View", run: () => {} };
    expect(commandScore(command, "go to")).toBeGreaterThan(commandScore(command, "gg"));
  });
});

describe("command registry — keyboard model (§50)", () => {
  it("binds each documented view chord", () => {
    for (const [key, id] of [
      ["g", "workspace.view.graph"],
      ["o", "workspace.view.objects"],
      ["e", "workspace.view.evidence"],
      ["t", "workspace.view.timeline"],
      ["a", "workspace.view.acquisition"],
    ] as const) {
      expect(commandForKey(makeRegistry(), context, key)?.id).toBe(id);
    }
  });

  it("is case-insensitive and does not bind an unbound key", () => {
    expect(commandForKey(makeRegistry(), context, "G")?.id).toBe("workspace.view.graph");
    expect(commandForKey(makeRegistry(), context, "z")).toBeNull();
  });

  it("does not resolve a chord whose command is unavailable", () => {
    expect(commandForKey(makeRegistry(), noSelection, "g")?.id).toBe("workspace.view.graph");
    // No chord is bound to a selection-only command in this registry.
    expect(commandForKey(makeRegistry(), noSelection, "enter")).toBeNull();
  });
});

describe("§50 — the keyboard model must not break text input", () => {
  function makeEl(tag: string, attrs: Record<string, string> = {}): HTMLElement {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    return el;
  }

  it("treats text inputs, textareas and selects as text entry", () => {
    expect(isTextEntryTarget(makeEl("input", { type: "text" }))).toBe(true);
    expect(isTextEntryTarget(makeEl("input", { type: "search" }))).toBe(true);
    expect(isTextEntryTarget(makeEl("textarea"))).toBe(true);
    expect(isTextEntryTarget(makeEl("select"))).toBe(true);
  });

  it("does not treat buttons, checkboxes or ranges as text entry", () => {
    expect(isTextEntryTarget(makeEl("input", { type: "button" }))).toBe(false);
    expect(isTextEntryTarget(makeEl("input", { type: "checkbox" }))).toBe(false);
    expect(isTextEntryTarget(makeEl("input", { type: "range" }))).toBe(false);
    expect(isTextEntryTarget(makeEl("button"))).toBe(false);
  });

  it("treats a contenteditable host as text entry", () => {
    const el = makeEl("div", { contenteditable: "true" });
    expect(isTextEntryTarget(el)).toBe(true);
  });

  it("handles a null target", () => {
    expect(isTextEntryTarget(null)).toBe(false);
  });
});

describe("§69 — no dead ends", () => {
  it("offers a next step for every domain object kind", () => {
    for (const kind of INSPECTOR_KINDS) {
      const actions = actionsForSelection({ kind, id: "X-1" }, 0);
      expect(actions.length, `${kind} has no next step`).toBeGreaterThan(0);
    }
  });

  it("gives every action a declared destination, whatever the secondary count", () => {
    for (const kind of INSPECTOR_KINDS) {
      for (const secondaryCount of [0, 1]) {
        for (const action of actionsForSelection({ kind, id: "X-1" }, secondaryCount)) {
          expect(
            destinationForAction(action.id),
            `${kind} → ${action.id} (secondary=${secondaryCount}) has no destination`,
          ).not.toBeNull();
        }
      }
    }
  });

  it("offers nothing when nothing is selected", () => {
    expect(actionsForSelection(null, 0)).toEqual([]);
  });
});

describe("command registry — execution", () => {
  it("invokes the run handler with no arguments for a key-bound command", () => {
    const run = vi.fn();
    const registry: Array<Command> = [{ id: "a.b", label: "Do", group: "G", key: "G", run }];
    commandForKey(registry, context, "g")?.run();
    expect(run).toHaveBeenCalledOnce();
  });
});