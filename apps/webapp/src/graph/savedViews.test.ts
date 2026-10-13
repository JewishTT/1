import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  TENANT_SCOPE,
  deleteView,
  loadViews,
  saveView,
  scopeKeyFor,
  type SavedView,
} from "./savedViews";

/**
 * Saved views (§15 "report state").
 *
 * The module's whole claim is that a view is a named snapshot of the SETUP and
 * nothing else, scoped so two investigations cannot restore each other's framing.
 * Both claims are asserted directly here rather than inferred from the UI, because
 * both are the kind of thing that rots silently: a view that quietly starts carrying
 * a node list looks identical from the toolbar, and a scope that stops being scoped
 * still works right up until an analyst restores the wrong investigation.
 */

const PREFIX = "cognitive:saved-views:";

/** A setup with every field set to something distinguishable. */
const SETUP = {
  mode: "lasso" as const,
  layout: "circle" as const,
  query: "acme",
  temporalActive: true,
  expandedIds: ["Entity:ENT-1", "Entity:ENT-2"],
};

const OTHER_SETUP = {
  mode: "select" as const,
  layout: "grid" as const,
  query: "",
  temporalActive: false,
  expandedIds: [],
};

function stored(scope: string): unknown {
  const raw = window.localStorage.getItem(PREFIX + scope);
  return raw === null ? null : JSON.parse(raw);
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("savedViews — save and load", () => {
  it("returns the saved view with a timestamp, and reads it back unchanged", () => {
    const written = saveView("inv-1", { name: "morning", ...SETUP });

    expect(written).toHaveLength(1);
    const [view] = written;
    expect(view.name).toBe("morning");
    expect(view.mode).toBe("lasso");
    expect(view.layout).toBe("circle");
    expect(view.query).toBe("acme");
    expect(view.temporalActive).toBe(true);
    expect(view.expandedIds).toEqual(["Entity:ENT-1", "Entity:ENT-2"]);
    // An ISO instant, not a formatted string nobody can sort.
    expect(view.savedAt).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);

    expect(loadViews("inv-1")).toEqual(written);
  });

  it("writes only the setup — never a node or an edge", () => {
    // The load-bearing assertion in this file. A view that carried records would
    // restore yesterday's world under today's settings, which is the one failure
    // this feature exists to prevent.
    saveView("inv-1", { name: "framing", ...SETUP });

    const persisted = stored("inv-1") as Record<string, unknown>[];
    expect(Object.keys(persisted[0]).sort()).toEqual([
      "expandedIds",
      "layout",
      "mode",
      "name",
      "query",
      "savedAt",
      "temporalActive",
    ]);
    for (const record of persisted) {
      expect(record).not.toHaveProperty("nodes");
      expect(record).not.toHaveProperty("edges");
    }
  });

  it("persists under the namespaced key, never a bare scope", () => {
    saveView("inv-1", { name: "a", ...SETUP });
    expect(window.localStorage.getItem(PREFIX + "inv-1")).not.toBeNull();
    expect(window.localStorage.getItem("inv-1")).toBeNull();
  });
});

describe("savedViews — one name, one view", () => {
  it("replaces a view that reuses a name rather than appending a second one", () => {
    saveView("inv-1", { name: "default", ...SETUP });
    const second = saveView("inv-1", { name: "default", ...OTHER_SETUP });

    expect(second).toHaveLength(1);
    expect(second[0].layout).toBe("grid");
    expect(second[0].query).toBe("");
  });

  it("moves a replaced view to the end, so the newest is the most recent", () => {
    saveView("inv-1", { name: "a", ...SETUP });
    saveView("inv-1", { name: "b", ...SETUP });
    const after = saveView("inv-1", { name: "a", ...OTHER_SETUP });

    expect(after.map((view) => view.name)).toEqual(["b", "a"]);
    expect(after[1].layout).toBe("grid");
  });

  it("keeps views of different names side by side", () => {
    saveView("inv-1", { name: "a", ...SETUP });
    const views = saveView("inv-1", { name: "b", ...SETUP });

    expect(views.map((view) => view.name)).toEqual(["a", "b"]);
  });
});

describe("savedViews — delete", () => {
  it("removes the named view and leaves the others", () => {
    saveView("inv-1", { name: "a", ...SETUP });
    saveView("inv-1", { name: "b", ...SETUP });
    saveView("inv-1", { name: "c", ...SETUP });

    const views = deleteView("inv-1", "b");

    expect(views.map((view) => view.name)).toEqual(["a", "c"]);
    expect(loadViews("inv-1").map((view) => view.name)).toEqual(["a", "c"]);
  });

  it("is a no-op for a name that was never saved", () => {
    saveView("inv-1", { name: "a", ...SETUP });

    expect(deleteView("inv-1", "ghost").map((view) => view.name)).toEqual(["a"]);
  });

  it("writes the shortened list back, so the deletion survives a reload", () => {
    saveView("inv-1", { name: "a", ...SETUP });
    saveView("inv-1", { name: "b", ...SETUP });
    deleteView("inv-1", "a");

    expect((stored("inv-1") as SavedView[]).map((view) => view.name)).toEqual(["b"]);
  });
});

describe("savedViews — malformed payloads cost one view, not the feature", () => {
  it("returns nothing for an unreadable or non-array payload", () => {
    window.localStorage.setItem(PREFIX + "inv-1", "{not json");
    expect(loadViews("inv-1")).toEqual([]);

    window.localStorage.setItem(PREFIX + "inv-1", JSON.stringify({ name: "a" }));
    expect(loadViews("inv-1")).toEqual([]);

    window.localStorage.setItem(PREFIX + "inv-1", JSON.stringify("a"));
    expect(loadViews("inv-1")).toEqual([]);
  });

  it("returns nothing when the key was never written", () => {
    expect(loadViews("never-seen")).toEqual([]);
  });

  it("drops entries that are not objects at all", () => {
    window.localStorage.setItem(
      PREFIX + "inv-1",
      JSON.stringify([
        null,
        7,
        "a view",
        true,
        { name: "good", ...SETUP, savedAt: "2026-01-01T00:00:00.000Z" },
      ]),
    );

    expect(loadViews("inv-1").map((view) => view.name)).toEqual(["good"]);
  });

  it("drops a view missing any field the restore path assigns", () => {
    // Restore writes mode, layout, query, temporalActive and expandedIds straight
    // into canvas state. A payload missing one of them throws inside the setter
    // rather than degrading, so it is dropped here instead.
    const complete = { name: "good", savedAt: "2026-01-01T00:00:00.000Z", ...SETUP };
    const without = (field: string, name: string): Record<string, unknown> => {
      const copy: Record<string, unknown> = { ...complete, name };
      delete copy[field];
      return copy;
    };
    const partials = [
      without("savedAt", "no-savedAt"),
      without("mode", "no-mode"),
      without("query", "no-query"),
      without("temporalActive", "no-temporal"),
      without("expandedIds", "no-expanded"),
      without("name", "no-name"),
    ];
    window.localStorage.setItem(PREFIX + "inv-1", JSON.stringify([...partials, complete]));

    expect(loadViews("inv-1").map((view) => view.name)).toEqual(["good"]);
  });

  it("drops a view whose mode or layout is not one the toolbar offers", () => {
    // Both are assigned without a re-check at the restore site, so an out-of-range
    // value has to be rejected at the door.
    const complete = { name: "good", savedAt: "2026-01-01T00:00:00.000Z", ...SETUP };
    window.localStorage.setItem(
      PREFIX + "inv-1",
      JSON.stringify([
        { ...complete, name: "ghost-layout", layout: "dagre" },
        { ...complete, name: "ghost-mode", mode: "paint" },
        { ...complete, name: "bad-expanded", expandedIds: ["Entity:ENT-1", 42] },
        complete,
      ]),
    );

    expect(loadViews("inv-1").map((view) => view.name)).toEqual(["good"]);
  });

  it("survives a localStorage that throws — quota exceeded, or private mode", () => {
    // A view is a convenience. Failing to store one must not take the graph with it,
    // and the canvas calls these directly from an event handler.
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("SecurityError");
    });

    expect(() => saveView("inv-1", { name: "a", ...SETUP })).not.toThrow();
    expect(loadViews("inv-1")).toEqual([]);
    // The return value is the new list even though the write did not land, so the
    // menu still shows the view the analyst just made.
    expect(saveView("inv-1", { name: "a", ...SETUP })).toHaveLength(1);

    setItem.mockRestore();
    getItem.mockRestore();
  });
});

describe("savedViews — one investigation cannot reach another's framing", () => {
  it("keeps each scope's views separate", () => {
    saveView("inv-1", { name: "same name", ...SETUP });
    saveView("inv-2", { name: "same name", ...OTHER_SETUP });

    expect(loadViews("inv-1")[0].layout).toBe("circle");
    expect(loadViews("inv-2")[0].layout).toBe("grid");

    // Deleting from one scope leaves the other one intact.
    deleteView("inv-1", "same name");
    expect(loadViews("inv-1")).toEqual([]);
    expect(loadViews("inv-2")).toHaveLength(1);
  });

  it("does not write the tenant scope when an investigation is chosen", () => {
    saveView(scopeKeyFor("inv-1"), { name: "a", ...SETUP });

    expect(loadViews(TENANT_SCOPE)).toEqual([]);
    expect(loadViews(scopeKeyFor("inv-1"))).toHaveLength(1);
  });
});

describe("savedViews — the scope key", () => {
  it("scopes a real investigation to itself", () => {
    expect(scopeKeyFor("inv-1")).toBe("investigation:inv-1");
  });

  it("gives the tenant scope one stable key for both ways of saying 'none'", () => {
    expect(scopeKeyFor(null)).toBe(TENANT_SCOPE);
    expect(scopeKeyFor("")).toBe(TENANT_SCOPE);
  });

  it("cannot be made to collide with the tenant scope by an investigation id", () => {
    // Without the prefix this would be `TENANT_SCOPE === scopeKeyFor("tenant")`, and
    // restoring the tenant framing would overwrite one investigation's views.
    expect(scopeKeyFor("tenant")).not.toBe(TENANT_SCOPE);
  });

  it("gives two different investigations two different keys", () => {
    expect(scopeKeyFor("inv-1")).not.toBe(scopeKeyFor("inv-2"));
  });
});
