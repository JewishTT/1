import { describe, expect, it } from "vitest";

import { buildRegistry, commandIds } from "./CommandBar";

/**
 * Registry contract (§9). Ids are the documented interface: a command is
 * referenced by id in docs, tests and (later) in saved layouts, so duplicates
 * and drift are defects, not cosmetic.
 */

describe("command registry", () => {
  const registry = buildRegistry();

  it("has unique ids", () => {
    const ids = commandIds(registry);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("uses the documented dotted namespace", () => {
    // Segment depth varies (`selection.clear` through `layout.pane.rail.toggle`);
    // what the id must guarantee is a known namespace prefix and lower-case
    // kebab segments, so ids stay machine-addressable.
    for (const id of commandIds(registry)) {
      expect(id, id).toMatch(/^(workspace|selection|filter|layout|palette)(\.[a-z0-9-]+)+$/);
    }
  });

  it("registers every one of the eight workspace views (§4)", () => {
    for (const view of [
      "overview",
      "graph",
      "objects",
      "evidence",
      "timeline",
      "acquisition",
      "findings",
      "analysis",
    ]) {
      expect(commandIds(registry)).toContain(`workspace.view.${view}`);
    }
  });

  it("binds exactly the five §50 view chords, and no duplicate key", () => {
    const keyed = registry.filter((command) => command.key !== undefined);
    expect(keyed.map((command) => command.key).sort()).toEqual(["A", "E", "G", "O", "T"]);
  });

  it("binds each chord to its matching view", () => {
    const byKey = new Map(registry.filter((c) => c.key).map((c) => [c.key, c.id]));
    expect(byKey.get("G")).toBe("workspace.view.graph");
    expect(byKey.get("O")).toBe("workspace.view.objects");
    expect(byKey.get("E")).toBe("workspace.view.evidence");
    expect(byKey.get("T")).toBe("workspace.view.timeline");
    expect(byKey.get("A")).toBe("workspace.view.acquisition");
  });

  it("gives every command a label, a group and a handler", () => {
    for (const command of registry) {
      expect(command.label.length, command.id).toBeGreaterThan(0);
      expect(command.group.length, command.id).toBeGreaterThan(0);
      expect(typeof command.run, command.id).toBe("function");
    }
  });

  it("never uses a text glyph as an icon", () => {
    for (const command of registry) {
      if (command.icon === undefined) continue;
      expect(command.icon, command.id).toMatch(
        /^(view-(overview|graph|objects|evidence|timeline|acquisition|findings|analysis|ops)|search|command|panel-(left|right|bottom)|sun|moon|density|chevron-(left|right|down)|close|copy|open-external|alert|clock)$/,
      );
    }
  });

  it("gates selection commands behind a context predicate", () => {
    for (const id of ["selection.clear", "selection.pin", "selection.compare"]) {
      const command = registry.find((entry) => entry.id === id);
      expect(command, id).toBeDefined();
      expect(command?.when, `${id} must have a predicate`).toBeTypeOf("function");
    }
  });

  it("gives every pane toggle a command (§5)", () => {
    for (const pane of ["rail", "inspector", "activity"]) {
      expect(commandIds(registry)).toContain(`layout.pane.${pane}.toggle`);
    }
  });
});