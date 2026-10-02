import { useEffect } from "react";

import { DEFAULT_DENSITY, DEFAULT_THEME } from "./types";
import { useWorkspace } from "./store";
import type { Density, ThemeName } from "./types";

/**
 * Appearance → DOM (ui-upgrade §4.2, FR-103).
 *
 * THE DEFECT THIS EXISTS TO CLOSE.
 *
 * `styles/tokens/color.css` and `styles/tokens/density.css` declare their token
 * blocks under `[data-theme="light"]`, `[data-density="compact"]` and
 * `[data-density="comfortable"]`. Until now nothing in the application ever
 * wrote either attribute. The consequence was not cosmetic and not subtle:
 *
 *   - `toggleDensity()` moved a Zustand field and changed **zero pixels**. The
 *     token blocks were declared; no element matched them, so the whole density
 *     system was unreachable from the UI.
 *   - `setTheme("light")` did the same, and because `color.css` keeps the dark
 *     values on `:root` as well as `[data-theme="dark"]`, light mode was not
 *     merely unstyled — it was *unreachable*. No path in the app could render
 *     it, so the light palette could never be seen, reviewed, or found broken.
 *
 * The attributes therefore belong on `document.documentElement` and nowhere
 * else. Two reasons that is the only correct host:
 *
 *   1. `:root` IS `documentElement`. A token declared on `:root` resolves
 *      against it, so a single write themes the whole document — including the
 *      legacy pages and the scoped donor sheets, which live outside every
 *      `.ui-root` subtree and would keep the old palette otherwise.
 *   2. A modal, a native `<dialog>`, a fullscreen element or a
 *      `position: fixed` overlay is rendered outside the workspace subtree.
 *      Scoping the attribute to the shell would leave those on the default
 *      theme, which is the same class of bug one level down.
 *
 * `documentElement` rather than `body`: `body` is replaced by some hosts and is
 * absent during the first paint, and a density that arrives one frame late is a
 * layout shift (§11 forbids layout shift on data arrival; a density flip that
 * lands after first paint is the same defect with a different cause).
 *
 * @returns the resolved density and theme, so a caller can render them as
 *          `data-` attributes too and stay in step with the DOM.
 */
export interface AppearanceAttributes {
  density: Density;
  theme: ThemeName;
}

export function useAppearanceAttributes(): AppearanceAttributes {
  const density = useWorkspace((state) => state.density);
  const theme = useWorkspace((state) => state.theme);

  useEffect(() => {
    const root = document.documentElement;
    // `setAttribute` rather than `dataset`, so the write is visible to a test
    // that reads the attribute directly and to any tooling that snapshots the
    // markup. The values are the store's own literals; there is no third
    // spelling to keep in sync.
    root.setAttribute("data-density", density);
    root.setAttribute("data-theme", theme);
    root.style.colorScheme = theme;
  }, [density, theme]);

  return { density, theme };
}

/**
 * The values that must be on `documentElement` before the first paint.
 *
 * `main.tsx` calls this once, synchronously, before `createRoot(...).render`.
 * The store's own defaults are the source, so this cannot disagree with the
 * effect above — the effect only re-writes on a *change*.
 */
export function applyInitialAppearanceAttributes(): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.setAttribute("data-density", DEFAULT_DENSITY);
  root.setAttribute("data-theme", DEFAULT_THEME);
  root.style.colorScheme = DEFAULT_THEME;
}