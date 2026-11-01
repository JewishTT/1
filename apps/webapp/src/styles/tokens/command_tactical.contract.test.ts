import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

function readShipped(...segments: string[]): string {
  let dir = process.cwd();
  for (let depth = 0; depth < 6; depth += 1) {
    const candidate = path.join(dir, "src", ...segments);
    if (existsSync(candidate)) return readFileSync(candidate, "utf8");
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error(`not found above ${process.cwd()}: ${segments.join("/")}`);
}

describe("command tactical visual system", () => {
  const css = readShipped("styles", "command-tactical.css");
  const layers = readShipped("styles", "layers.css");
  const shell = readShipped("AppShell.tsx");
  const nav = readShipped("shell", "TopNav.tsx");

  it("is the final global design layer after normalization", () => {
    expect(layers.indexOf('@import "./normalization.css";')).toBeGreaterThan(-1);
    expect(layers.indexOf('@import "./command-tactical.css";')).toBeGreaterThan(
      layers.indexOf('@import "./normalization.css";'),
    );
  });

  it("defines the command palette as semantic roles", () => {
    for (const token of [
      "--cmd-void", "--cmd-graphite", "--cmd-panel", "--cmd-raised",
      "--cmd-line", "--cmd-cyan", "--cmd-ice", "--cmd-lime", "--cmd-amber", "--cmd-red",
    ]) expect(css).toContain(token);
  });

  it("applies to shell, navigation, analytical surfaces and operational panels", () => {
    for (const selector of [
      ".ui-topbar", ".ui-primary-nav", ".ui-primary-nav-link[data-active=\"true\"]",
      ".ui-shell-main", ".ui-ops-block", ".ui-signal", ".ui-command-strip",
    ]) expect(css).toContain(selector);
  });

  it("keeps a truthful operating-cycle label and an identifiable command workspace", () => {
    expect(shell).toContain("C2 / ANALYST COMMAND");
    expect(shell).toContain("OPERATING CYCLE");
    expect(nav).toContain("COMMAND ROUTE INDEX");
  });

  it("preserves reduced motion and forced-colors behavior", () => {
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
    expect(css).toContain("@media (forced-colors: active)");
  });
});
