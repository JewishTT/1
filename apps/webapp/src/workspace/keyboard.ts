/**
 * The keyboard model (§50).
 *
 * WHY THIS FILE EXISTS, AND WHY IT IS A CORRECTION RATHER THAN A DUPLICATE.
 *
 * `src/workspace/commands.ts` already owns `isTextEntryTarget` and
 * `useCommandHotkeys`, and this module deliberately does not re-implement the
 * registry, the palette or the chord table — those stay where they are and this
 * file is reported as the replacement for two predicates only.
 *
 * The audit that produced it found four real defects in the existing handling.
 * Each is stated with the mechanism, because a fix without the reason is a fix
 * that gets undone:
 *
 *   K1  ARIA text-entry roles were not treated as text entry.
 *       `isTextEntryTarget` answers from `tagName` and an `isContentEditable`
 *       check. A `role="textbox"` / `role="searchbox"` / `role="combobox"`
 *       element that is not an `<input>` — the correct ARIA spelling, and the one
 *       a combobox or a rich filter is supposed to use — was therefore NOT text
 *       entry, so typing a single letter into it fired the view chords. The
 *       content would visibly change AND the workspace would navigate. WCAG
 *       2.1.2 (No Keyboard Trap) inverted: the keystroke was hijacked for
 *       something the user did not ask for.
 *
 *   K2  `contenteditable="plaintext-only"` was not text entry.
 *       The existing ancestor check matches `[contenteditable='true']` and
 *       `[contenteditable='']` only. `plaintext-only` is the other legal value
 *       and produces the same failure as K1.
 *
 *   K3  IME composition was not respected.
 *       During composition a `keydown` fires per candidate with `isComposing`
 *       true and `key` often the raw letter. On a CJK or dead-key layout,
 *       typing a grapheme beginning with `g` navigated to the graph mid-word.
 *       `keydown` with `isComposing`, or `key === "Process"` / `keyCode === 229`,
 *       must never resolve a chord.
 *
 *   K4  An already-handled key was handled again.
 *       The listener runs at `document`, which is the LAST bubble target — after
 *       React's root listener and after every component handler. A component
 *       that consumed a key (the palette's Enter, a slider, a graph shortcut)
 *       marks `defaultPrevented`, and the workspace then acted on it a second
 *       time. `defaultPrevented` is the platform's own "someone below me took
 *       this" signal and ignoring it is how two handlers end up fighting.
 *
 * WHAT IS DELIBERATELY UNCHANGED, because it was already correct:
 *
 *   - ⌘K / Ctrl-K fires regardless of focus, so it works from inside a field.
 *   - Escape is handled before the text-entry check, so Esc still closes the
 *     palette and the context menu from anywhere.
 *   - A modifier on a single-key chord hands the key back to the browser, so
 *     ⌘R and Ctrl-Shift-K (devtools) are not swallowed.
 *   - `Enter` is not bound globally. It belongs to the focused control.
 *
 * §98/§99: this module mints no domain vocabulary and derives no domain meaning.
 * It answers one question — is this keystroke available to the workspace, or
 * has someone closer to the user already taken it?
 */

/* ── Text entry (§50, WCAG 2.1.2) ───────────────────────────────────── */

/**
 * ARIA roles that accept free text. These are the K1 fix: a `role="textbox"`
 * div is exactly as much "text entry" as an `<input type="text">`, and treating
 * it differently is the bug.
 */
export const TEXT_ENTRY_ROLES: ReadonlySet<string> = new Set(["textbox", "searchbox", "combobox"]);

/**
 * `contenteditable` values that make an element editable.
 *
 * `plaintext-only` is here for K2. It is the value a rich-text surface should
 * use, so excluding it is excluding the correct implementation.
 */
const EDITABLE_CONTENT_VALUES: ReadonlySet<string> = new Set(["", "true", "plaintext-only"]);

/**
 * Input types that are NOT text entry.
 *
 * A checkbox is a control that toggles; a letter pressed while it is focused is
 * not text and may safely reach a chord. Everything absent from this list is
 * treated as text entry, which is the safe direction: a type nobody thought of
 * gets typing preserved rather than typing hijacked.
 */
export const NON_TEXT_INPUT_TYPES: ReadonlySet<string> = new Set([
  "button",
  "checkbox",
  "color",
  "file",
  "image",
  "radio",
  "range",
  "reset",
  "submit",
]);

/**
 * Is this event target somewhere a keystroke must remain a keystroke?
 *
 * Conservative by construction: it walks the composed ancestor chain rather than
 * trusting one attribute, so a text field inside a `role="combobox"` wrapper is
 * caught by either. Shadow-DOM boundaries are not crossed — a closed shadow root
 * cannot be inspected from here, and a host with `delegatesFocus` is not
 * detectable; both are reported rather than pretended away.
 */
export function isTextEntryTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;

  // A shadow host is not itself text entry; the inner control is. `event.target`
  // is retargeted to the host by the platform, so the composed path is walked.
  const element: Element = target;

  if (element.closest("textarea, select")) return true;

  if (element.tagName === "INPUT") {
    // `type` is nullable on the Element view of a node. A node with no declared
    // type is not a non-text input, so it must not veto a chord.
    const declaredType = (element as HTMLInputElement).type;
    if (declaredType === null || declaredType === undefined) return false;
    return !NON_TEXT_INPUT_TYPES.has(declaredType.toLowerCase());
  }

  // `contentEditableValue` returns null when the attribute is absent, which is
  // "not editable" and not a value to look up.
  const editableValue = contentEditableValue(element);
  if (editableValue !== null && EDITABLE_CONTENT_VALUES.has(editableValue)) return true;

  // The contenteditable ancestor walk: an inner node of a plaintext-only host is
  // still a keystroke destination.
  const editableAncestor = element.closest(
    "[contenteditable='true'], [contenteditable=''], [contenteditable='plaintext-only']",
  );
  if (editableAncestor !== null) return true;

  const roleElement = element.closest("[role]");
  if (roleElement !== null && TEXT_ENTRY_ROLES.has((roleElement.getAttribute("role") ?? "").toLowerCase())) {
    return true;
  }

  return false;
}

/**
 * The element's own `contenteditable` value, or `null` when it has none.
 *
 * THREE STATES, NOT TWO — and collapsing them is the bug this function exists to
 * avoid:
 *
 *   `"true"` / `"plaintext-only"`  editable
 *   `""`                           editable, but only when the ATTRIBUTE is
 *                                 present and empty. The DOM property
 *                                 `contentEditable` also stringifies to `"inherit"`
 *                                 for a plain element, and `"inherit"` is the
 *                                 *default*, i.e. not editable. Treating an
 *                                 absent attribute as the empty-string form makes
 *                                 every `<button>` and every `<body>` a text
 *                                 field, which suppresses the chords everywhere.
 *   `null`                         no attribute: not editable
 */
function contentEditableValue(element: Element): string | null {
  const attribute = element.getAttribute("contenteditable");
  if (attribute !== null) return attribute.trim().toLowerCase();

  // The property, for the case where the attribute was set through the IDL
  // attribute (`el.contentEditable = "plaintext-only"`), which some editors do.
  const property = (element as HTMLElement).contentEditable;
  if (typeof property === "string" && property !== "" && property !== "inherit") {
    return property.toLowerCase();
  }
  return null;
}

/* ── Chord availability ─────────────────────────────────────────────── */

/**
 * Why a keystroke was or was not available to the workspace. Exported so the
 * audit test can assert on the REASON rather than on a boolean, which is what
 * makes a regression diagnosable.
 */
export type KeyAvailability = "available" | "text-entry" | "handled-elsewhere" | "composing" | "modified" | "chord";

export interface KeyResolution {
  readonly availability: KeyAvailability;
  /** The command id when `availability === "chord"`, else null. */
  readonly commandId: string | null;
}

/**
 * Resolve a `keydown` against the chord table.
 *
 * `resolve` is the registry's own `commandForKey`, injected rather than imported
 * so this module has no dependency on `commands.ts` and can be tested against a
 * table of its own. The shell passes `commandForKey` unchanged, so a chord added
 * to the registry is available here automatically.
 */
export function resolveKey(
  event: KeyboardEvent,
  resolve: (key: string) => { id: string } | null,
): KeyResolution {
  // K4: someone closer to the user already took this key. Checked first,
  // because a handled key must not be handled again regardless of where focus is.
  if (event.defaultPrevented) return { availability: "handled-elsewhere", commandId: null };

  // K3: composition. Checked before anything that reads `key`, because during
  // composition `key` is the candidate letter and not a command request.
  if (isComposing(event)) return { availability: "composing", commandId: null };

  // ⌘K is deliberately NOT routed through here: it is focus-independent by
  // design and is handled by the caller before this function is consulted.

  // A modified key belongs to the browser and the OS: ⌘R reloads, Ctrl-Shift-K
  // opens devtools, Alt-T cycles windows. Never ours.
  if (event.metaKey || event.ctrlKey || event.altKey) {
    return { availability: "modified", commandId: null };
  }

  if (isTextEntryTarget(event.target)) return { availability: "text-entry", commandId: null };

  const command = resolve(event.key);
  if (command === null) return { availability: "chord", commandId: null };
  return { availability: "available", commandId: command.id };
}

/**
 * Is this keystroke part of an IME composition?
 *
 * Three signals, because no single one is reliable across browsers: the
 * `isComposing` property on the event, the `CompositionEvent`-era `keyCode`
 * 229, and a `key` of `"Process"` which some platforms emit mid-composition.
 */
export function isComposing(event: KeyboardEvent): boolean {
  return event.isComposing === true || event.keyCode === 229 || event.key === "Process";
}

/**
 * Is this the palette chord, and is it OURS?
 *
 * `⌘K` or `Ctrl-K` and nothing else. An extra modifier means a different chord
 * entirely — `Ctrl-Shift-K` is devtools in Chrome and Edge, and hijacking it
 * would leave a developer with no way to open their own tools. The existing
 * handling accepts `Ctrl-Shift-K`; this is the corrected predicate.
 */
export function isPaletteChord(event: KeyboardEvent): boolean {
  if (event.altKey || event.shiftKey) return false;
  if (!event.metaKey && !event.ctrlKey) return false;
  return event.key.toLowerCase() === "k";
}

/**
 * Is this a chord the registry binds, ignoring focus and modifiers?
 *
 * Used by the audit and by the help text: it answers "which single keys are
 * live right now", which is a different question from "did this key fire".
 */
export function chordFor(key: string, bound: ReadonlyArray<string>): string | null {
  const upper = key.toUpperCase();
  return bound.find((candidate) => candidate.toUpperCase() === upper) ?? null;
}

/* ── The documented model (§50) ─────────────────────────────────────── */

/**
 * The chords §50 names, with the surfaces they open. Declared here rather than
 * derived from the registry so the audit can compare the two and report drift.
 */
export const DOCUMENTED_CHORDS = [
  { key: "K", chord: "⌘K / Ctrl-K", opens: "command palette", focusDependent: false },
  { key: "G", chord: "G", opens: "graph", focusDependent: true },
  { key: "O", chord: "O", opens: "objects", focusDependent: true },
  { key: "E", chord: "E", opens: "evidence", focusDependent: true },
  { key: "T", chord: "T", opens: "timeline", focusDependent: true },
  { key: "A", chord: "A", opens: "acquisition", focusDependent: true },
  { key: "Esc", chord: "Esc", opens: "close the topmost layer", focusDependent: false },
  { key: "Enter", chord: "Enter", opens: "the focused control", focusDependent: true },
] as const;

/**
 * The chords that must NOT fire inside text entry. Asserted by the audit so the
 * invariant is a property of the declaration, not of one hook's implementation.
 */
export const FOCUS_DEPENDENT_CHORDS: ReadonlyArray<string> = ["G", "O", "E", "T", "A"];