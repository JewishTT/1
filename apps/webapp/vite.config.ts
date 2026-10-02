import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    alias: {
      /**
       * Cytoscape is replaced for tests, at the specifier.
       *
       * Four components reach it through `await import("cytoscape")` so the
       * engine stays out of the initial bundle. Per-file `vi.mock("cytoscape")`
       * cannot reliably intercept that: Vitest reuses worker threads, and a
       * dynamic import already in flight resolves from the shared transform
       * cache, so whichever file got there first wins and every later file's mock
       * finds nothing to replace.
       *
       * The observable consequence was a suite where all 60 files and 812 tests
       * passed and the summary still said `Errors 1` — an unhandled rejection
       * from inside the real engine, attributed to whichever file was running when
       * its animation frame fired.
       *
       * Aliasing the specifier makes the resolution unconditional. A per-file
       * `vi.mock("cytoscape", factory)` still overrides it, so a test that needs
       * specific renderer behaviour can declare it. The reason the real engine
       * cannot run under jsdom is documented in the double itself; the short
       * version is that it needs a canvas, a used border width and a live
       * animation frame, and faking those makes the environment lie about layout
       * for every other component too.
       */
      cytoscape: fileURLToPath(new URL("./src/test-support/cytoscape-test-double.ts", import.meta.url)),
    },
  },
});