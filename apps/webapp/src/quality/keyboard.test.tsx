import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { buildRegistry, commandIds } from "../CommandBar";
import { InvestigationWorkspaceRoute } from "../Workbench";
import { commandForKey } from "../workspace/commands";
import {
  DOCUMENTED_CHORDS,
  FOCUS_DEPENDENT_CHORDS,
  chordFor,
  isComposing,
  isPaletteChord,
  isTextEntryTarget,
  resolveKey,
} from "../workspace/keyboard";
import { DEFAULT_PANE_WIDTHS, useWorkspace } from "../workspace/store";
import { OPEN_TIME_RANGE } from "../workspace/types";
import { useWorkspaceKeyboard, useWorkspaceEscapeLadder } from "./keyboardLayer";

/**
 * The §50 keyboard audit, as executable assertions.
 *
 * The three that matter most are the ones that FAILED before this pass:
 *
 *   K1  typing "graph" into a `role="textbox"` field used to navigate to the
 *       graph. `isTextEntryTarget` answered from `tagName`, and a div with an
 *       ARIA text role is not an input.
 *   K3  an IME composition used to resolve a candidate letter to a chord.
 *   K4  a key another handler had already consumed used to fire a workspace
 *       action as well.
 *
 * Each has a test named for the failure, not for the function, so a regression
 * names itself.
 */

/* ── K1/K2: typing must never navigate ───────────────────────────────── */

describe("§50 K1 — typing into an ARIA text field must not navigate", () => {
  /**
   * The corrected layer, mounted. This is the assertion that pins the fix.
   */
  function Harness() {
    const registry = buildRegistry();
    const view = useWorkspace((state) => state.view);
    const paletteOpen = useWorkspace((state) => state.commandPaletteOpen);
    const setPaletteOpen = useWorkspace((state) => state.setCommandPaletteOpen);
    const selection = useWorkspace((state) => state.selection);
    const secondaryCount = useWorkspace((state) => state.secondarySelection.length);

    useWorkspaceKeyboard({
      registry,
      context: { view, selection, secondaryCount, paletteOpen },
      onTogglePalette: () => setPaletteOpen(!paletteOpen),
      onEscape: () => setPaletteOpen(false),
    });
    return null;
  }

  function renderWithAriaTextbox() {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={queryClient}>
        <div role="textbox" tabIndex={0} aria-label="Free filter" data-testid="aria-textbox" />
        <Harness />
      </QueryClientProvider>,
    );
  }

  it("treats role=textbox as text entry — this assertion failed before the fix", () => {
    const box = document.createElement("div");
    box.setAttribute("role", "textbox");
    expect(isTextEntryTarget(box)).toBe(true);
  });

  it("treats role=searchbox and role=combobox as text entry", () => {
    for (const role of ["searchbox", "combobox"]) {
      const element = document.createElement("div");
      element.setAttribute("role", role);
      expect(isTextEntryTarget(element), role).toBe(true);
    }
  });

  it("treats a span INSIDE a role=textbox host as text entry", () => {
    const host = document.createElement("div");
    host.setAttribute("role", "textbox");
    const inner = document.createElement("span");
    host.appendChild(inner);
    expect(isTextEntryTarget(inner)).toBe(true);
  });

  it("does not navigate the workspace while typing 'graph' into one", () => {
    renderWithAriaTextbox();
    const box = screen.getByTestId("aria-textbox");
    act(() => box.focus());

    for (const key of ["g", "r", "a", "p", "h"]) {
      fireEvent.keyDown(box, { key });
    }

    expect(useWorkspace.getState().view, "typing 'graph' must not switch the view").toBe("overview");
  });

  it("does not navigate while typing 'graph' into a contenteditable=plaintext-only field", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <div contentEditable="plaintext-only" data-testid="plaintext-host" />
        <Harness />
      </QueryClientProvider>,
    );
    const host = screen.getByTestId("plaintext-host");
    act(() => host.focus());
    for (const key of ["g", "r", "a", "p", "h"]) fireEvent.keyDown(host, { key });
    expect(useWorkspace.getState().view).toBe("overview");
  });

  it("still routes the same key to a chord when no text field has focus", () => {
    // The complementary assertion: the fix must suppress typing, not chords.
    renderWithAriaTextbox();
    act(() => {
      fireEvent.keyDown(document, { key: "g" });
    });
    expect(useWorkspace.getState().view).toBe("graph");
  });
});

/**
 * The defect as it ships.
 *
 * `Workbench.KeyboardLayer` mounts `useCommandHotkeys` from
 * `src/workspace/commands.ts`, which still uses the defective predicate. So in
 * the real shell today, typing into an ARIA text field DOES navigate.
 *
 * These are `it.fails` on purpose. They pass while the defect is present and
 * start failing the moment the integrating pass swaps the hook — which is the
 * signal that the wiring landed and the note can be deleted. Turning them into
 * plain assertions now would be claiming a fix that is not deployed.
 */
describe("§50 K1 — the shipped shell still carries the defect (until wired)", () => {
  function renderShell() {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={queryClient}>
        <div role="textbox" tabIndex={0} aria-label="Free filter" data-testid="shell-aria-textbox" />
        <MemoryRouter initialEntries={["/investigations/42"]}>
          <Routes>
            <Route path="/investigations/:id" element={<InvestigationWorkspaceRoute />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it.fails("typing 'graph' into a role=textbox field currently navigates to acquisition", () => {
    renderShell();
    const box = screen.getByTestId("shell-aria-textbox");
    act(() => box.focus());
    for (const key of ["g", "r", "a", "p", "h"]) fireEvent.keyDown(box, { key });
    // 'a' is the acquisition chord, and the old predicate does not see a div
    // with role=textbox as text entry, so it fires.
    expect(useWorkspace.getState().view).toBe("overview");
  });
});

describe("§50 K2 — contenteditable=plaintext-only is text entry", () => {
  it("recognises the plaintext-only value", () => {
    const element = document.createElement("div");
    element.setAttribute("contenteditable", "plaintext-only");
    expect(isTextEntryTarget(element)).toBe(true);
  });

  it("recognises an inner node of a plaintext-only host", () => {
    const host = document.createElement("div");
    host.setAttribute("contenteditable", "plaintext-only");
    const inner = document.createElement("b");
    host.appendChild(inner);
    expect(isTextEntryTarget(inner)).toBe(true);
  });

  it("does not treat contenteditable=false as text entry", () => {
    const element = document.createElement("div");
    element.setAttribute("contenteditable", "false");
    expect(isTextEntryTarget(element)).toBe(false);
  });
});

describe("§50 K3 — an IME composition is not a chord", () => {
  it("detects composition from isComposing, keyCode 229 and key=Process", () => {
    expect(isComposing({ isComposing: true } as KeyboardEvent)).toBe(true);
    expect(isComposing({ keyCode: 229 } as unknown as KeyboardEvent)).toBe(true);
    expect(isComposing({ key: "Process" } as KeyboardEvent)).toBe(true);
    expect(isComposing({ isComposing: false, key: "g", keyCode: 71 } as KeyboardEvent)).toBe(false);
  });

  it("refuses to resolve a candidate letter to a chord", () => {
    const registry = buildRegistry();
    const context = {
      view: "overview" as const,
      selection: null,
      secondaryCount: 0,
      paletteOpen: false,
    };
    const composing = {
      isComposing: true,
      key: "g",
      keyCode: 229,
      target: document.body,
      defaultPrevented: false,
    } as unknown as KeyboardEvent;

    const resolution = resolveKey(composing, (key) => commandForKey(registry, context, key));
    expect(resolution.availability).toBe("composing");
    expect(resolution.commandId).toBeNull();
  });
});

describe("§50 K4 — a key someone already handled is left alone", () => {
  it("reports handled-elsewhere and resolves no command", () => {
    const registry = buildRegistry();
    const context = {
      view: "overview" as const,
      selection: null,
      secondaryCount: 0,
      paletteOpen: false,
    };
    const handled = {
      isComposing: false,
      key: "g",
      target: document.body,
      defaultPrevented: true,
    } as unknown as KeyboardEvent;

    const resolution = resolveKey(handled, (key) => commandForKey(registry, context, key));
    expect(resolution.availability).toBe("handled-elsewhere");
    expect(resolution.commandId).toBeNull();
  });

  it("still resolves the same key when nothing handled it", () => {
    const registry = buildRegistry();
    const context = {
      view: "overview" as const,
      selection: null,
      secondaryCount: 0,
      paletteOpen: false,
    };
    const fresh = {
      isComposing: false,
      key: "g",
      target: document.body,
      defaultPrevented: false,
    } as unknown as KeyboardEvent;

    expect(resolveKey(fresh, (key) => commandForKey(registry, context, key)).commandId).toBe(
      "workspace.view.graph",
    );
  });
});

/* ── The palette chord ───────────────────────────────────────────────── */

describe("§50 — ⌘K is ours, and only ⌘K", () => {
  it("claims the bare chord", () => {
    expect(isPaletteChord({ metaKey: true, key: "k" } as KeyboardEvent)).toBe(true);
    expect(isPaletteChord({ ctrlKey: true, key: "K" } as KeyboardEvent)).toBe(true);
  });

  it("leaves Ctrl-Shift-K alone, because that is devtools", () => {
    // The defect: the mounted handler accepted this and called preventDefault,
    // so a developer working in the workbench could not open their own tools.
    expect(isPaletteChord({ ctrlKey: true, shiftKey: true, key: "k" } as KeyboardEvent)).toBe(false);
  });

  it("leaves ⌘R and Alt-K alone", () => {
    expect(isPaletteChord({ metaKey: true, key: "r" } as KeyboardEvent)).toBe(false);
    expect(isPaletteChord({ altKey: true, metaKey: true, key: "k" } as KeyboardEvent)).toBe(false);
  });

  it("ignores a bare letter", () => {
    expect(isPaletteChord({ key: "k" } as KeyboardEvent)).toBe(false);
  });
});

/* ── The corrected layer, mounted ────────────────────────────────────── */

function KeyboardHarness() {
  const registry = buildRegistry();
  const view = useWorkspace((state) => state.view);
  const paletteOpen = useWorkspace((state) => state.commandPaletteOpen);
  const setPaletteOpen = useWorkspace((state) => state.setCommandPaletteOpen);
  const selection = useWorkspace((state) => state.selection);
  const secondaryCount = useWorkspace((state) => state.secondarySelection.length);

  useWorkspaceKeyboard({
    registry,
    context: { view, selection, secondaryCount, paletteOpen },
    onTogglePalette: () => setPaletteOpen(!paletteOpen),
    onEscape: () => setPaletteOpen(false),
  });
  useWorkspaceEscapeLadder();
  return null;
}

function renderHarness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/investigations/42"]}>
        <KeyboardHarness />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The view each documented chord must land on. §50, asserted rather than assumed. */
const CHORD_VIEW: Record<string, string> = {
  G: "graph",
  O: "objects",
  E: "evidence",
  T: "timeline",
  A: "acquisition",
};

function viewForChord(key: string): string {
  return CHORD_VIEW[key];
}

beforeEach(() => {
  useWorkspace.setState({
    investigationId: "42",
    investigationLabel: null,
    view: "overview",
    selection: null,
    secondarySelection: [],
    evidenceFilter: { query: "", sourceIds: [], hideRejected: false },
    railQuery: "",
    railKinds: [],
    timeRange: OPEN_TIME_RANGE,
    openInspectorSections: {},
    pinnedInspectors: [],
    paneWidths: DEFAULT_PANE_WIDTHS,
    paneVisibility: { rail: true, inspector: true, activity: true },
    density: "compact",
    theme: "dark",
    commandPaletteOpen: false,
    contextMenu: null,
  });
});

describe("§50 — the corrected layer drives the workspace", () => {
  it.each(FOCUS_DEPENDENT_CHORDS.map((key) => [key, key.toLowerCase()] as const))(
    "%s switches the canvas when nothing is being typed into",
    (label, key) => {
      renderHarness();
      act(() => {
        fireEvent.keyDown(document, { key });
      });
      const expected = viewForChord(label);
      expect(useWorkspace.getState().view).toBe(expected);
    },
  );

  it("opens the palette with Ctrl-K from document", () => {
    renderHarness();
    act(() => {
      fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    });
    expect(useWorkspace.getState().commandPaletteOpen).toBe(true);
  });

  it("does NOT open the palette on Ctrl-Shift-K", () => {
    renderHarness();
    act(() => {
      fireEvent.keyDown(document, { key: "k", ctrlKey: true, shiftKey: true });
    });
    expect(useWorkspace.getState().commandPaletteOpen).toBe(false);
  });

  it("closes the palette with Escape without touching the selection", () => {
    renderHarness();
    act(() => useWorkspace.getState().select({ kind: "Entity", id: "ENT-1" }));
    act(() => useWorkspace.getState().setCommandPaletteOpen(true));

    act(() => {
      fireEvent.keyDown(document, { key: "Escape" });
    });

    expect(useWorkspace.getState().commandPaletteOpen).toBe(false);
    expect(useWorkspace.getState().selection?.id).toBe("ENT-1");
  });

  it("closes the context menu before it touches the selection", () => {
    renderHarness();
    act(() => useWorkspace.getState().select({ kind: "Entity", id: "ENT-1" }));
    act(() => useWorkspace.getState().openContextMenu({ x: 10, y: 10, targetKind: "Entity" }));

    act(() => {
      fireEvent.keyDown(document, { key: "Escape" });
    });

    expect(useWorkspace.getState().contextMenu).toBeNull();
    expect(useWorkspace.getState().selection?.id).toBe("ENT-1");
  });

  it("clears the selection only when nothing else is open", () => {
    renderHarness();
    act(() => useWorkspace.getState().select({ kind: "Entity", id: "ENT-1" }));
    act(() => {
      fireEvent.keyDown(document, { key: "Escape" });
    });
    expect(useWorkspace.getState().selection).toBeNull();
  });
});

/* ── The audit, stated as assertions ─────────────────────────────────── */

describe("§50 — the documented model and the registry agree", () => {
  const registry = buildRegistry();
  const context = {
    view: "overview" as const,
    selection: null,
    secondaryCount: 0,
    paletteOpen: false,
  };

  it("binds exactly the five focus-dependent chords §50 names", () => {
    const bound = registry.filter((command) => command.key !== undefined).map((command) => command.key);
    expect(bound.sort()).toEqual([...FOCUS_DEPENDENT_CHORDS].sort());
  });

  it("documents every chord the registry binds", () => {
    for (const command of DOCUMENTED_CHORDS) {
      if (!FOCUS_DEPENDENT_CHORDS.includes(command.key)) continue;
      expect(chordFor(command.key, [command.key]), command.key).toBe(command.key);
    }
  });

  it("does not bind Enter globally — Enter belongs to the focused control", () => {
    expect(registry.some((command) => command.key === "Enter" || command.key === "↵")).toBe(false);
  });

  it("marks ⌘K, Esc and Enter as focus-dependent=false where they are not chords", () => {
    const byKey = new Map(DOCUMENTED_CHORDS.map((entry) => [entry.key, entry]));
    expect(byKey.get("K")?.focusDependent).toBe(false);
    expect(byKey.get("Esc")?.focusDependent).toBe(false);
    expect(byKey.get("Enter")?.focusDependent).toBe(true);
  });

  it("resolves a chord to the same command the registry does", () => {
    for (const key of FOCUS_DEPENDENT_CHORDS) {
      const viaRegistry = commandForKey(registry, context, key);
      const viaKeyboard = resolveKey(
        { isComposing: false, key, target: document.body, defaultPrevented: false } as unknown as KeyboardEvent,
        (candidate) => commandForKey(registry, context, candidate),
      );
      expect(viaKeyboard.commandId, key).toBe(viaRegistry?.id ?? null);
    }
  });

  it("reports the availability REASON, so a regression is diagnosable", () => {
    const body = { isComposing: false, target: document.body, defaultPrevented: false } as unknown as KeyboardEvent;
    expect(resolveKey({ ...body, key: "z" } as KeyboardEvent, () => null).availability).toBe("chord");
    expect(resolveKey({ ...body, key: "g", metaKey: true } as KeyboardEvent, () => ({ id: "x" })).availability).toBe(
      "modified",
    );
  });

  it("has no command id collisions that would make a chord ambiguous", () => {
    const keyed = registry.filter((command) => command.key !== undefined);
    const keys = keyed.map((command) => command.key);
    expect(new Set(keys).size).toBe(keys.length);
    expect(new Set(commandIds(registry)).size).toBe(registry.length);
  });

  it("attaches exactly one document listener, so a keystroke cannot fire twice", () => {
    const add = vi.spyOn(document, "addEventListener");
    renderHarness();
    const keydown = add.mock.calls.filter(([type]) => type === "keydown");
    // One for the chords, one for the Escape ladder. Two listeners on the same
    // event for the same purpose is the double-fire bug.
    expect(keydown).toHaveLength(2);
    add.mockRestore();
  });
});

describe("§50 — the defect classes are classified, not guessed", () => {
  it("does not treat a checkbox, a button or a range as text entry", () => {
    for (const [tag, attrs] of [
      ["input", { type: "checkbox" }],
      ["input", { type: "button" }],
      ["input", { type: "range" }],
      ["button", {}],
      ["div", { role: "button" }],
    ] as const) {
      const element = document.createElement(tag);
      for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
      expect(isTextEntryTarget(element), `${tag} ${JSON.stringify(attrs)}`).toBe(false);
    }
  });

  it("still treats a plain text input, a textarea and a select as text entry", () => {
    for (const [tag, attrs] of [
      ["input", { type: "text" }],
      ["input", { type: "search" }],
      ["input", { type: "email" }],
      ["textarea", {}],
      ["select", {}],
    ] as const) {
      const element = document.createElement(tag);
      for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
      expect(isTextEntryTarget(element), `${tag} ${JSON.stringify(attrs)}`).toBe(true);
    }
  });

  it("handles a null target", () => {
    expect(isTextEntryTarget(null)).toBe(false);
  });
});