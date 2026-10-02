/**
 * The Cytoscape test double.
 *
 * WHY THIS IS A MODULE AND NOT A `vi.mock` FACTORY.
 *
 * `graph/GraphCanvas.tsx`, `components/GraphPanel.tsx`,
 * `components/SpecOpsGraphPanel.tsx` and `components/IntelligenceGraph.tsx` each
 * reach Cytoscape through `await import("cytoscape")` — a dynamic import, and
 * the only shape that keeps the engine out of the initial bundle (§13). Three of
 * the four test files that mount them already declare `vi.mock("cytoscape", …)`
 * and those work: the mock is consulted when the module is first resolved *in
 * that file's module runner*.
 *
 * It does not work when a WORKER has already resolved the real module. Vitest
 * reuses worker threads across files, and a dynamic import whose promise is
 * already in flight resolves from the shared transform cache — so a later file's
 * `vi.mock` finds nothing left to replace, and the real engine constructs. That
 * is what produced a run-level failure attributed to a file that cannot cause it:
 * a suite where every file was green and `Errors 1` named
 * `src/containers/IntelligenceContainer.test.tsx`, which mocks Cytoscape and is
 * clean on its own.
 *
 * Aliasing the specifier resolves the promise to this module for every test, in
 * every worker, before any of the four call sites can ask for the real one. A
 * per-file `vi.mock("cytoscape", factory)` still takes precedence — so a test that
 * needs particular renderer behaviour can declare it — but no longer depends on
 * being the first file in the worker to reach it.
 *
 * WHAT THE ENGINE COSTS IF IT RAN HERE, since the double has to earn its
 * existence. Three failures in sequence, each surfacing only after the previous
 * one was stubbed out:
 *
 *   1. `getContext("2d")` is unimplemented in jsdom → `Could not create canvas
 *      of type 2d`, inside a promise nobody awaits → a global unhandled rejection.
 *   2. With a canvas, `findContainerClientCoords` divides `rect.width` by
 *      `parseFloat(getComputedStyle(...).getPropertyValue("border-left-width"))`;
 *      jsdom answers `""`, so `0 / NaN` is `NaN`, `NaN` reaches `cy.width()`, and
 *      cose's `makeBoundingBox` rejects it → `Cannot read properties of undefined
 *      (reading 'w')`.
 *   3. With layout faked too, the layout runs for real and its animation frame
 *      outlives `destroy()` → `Cannot read properties of null (reading 'notify')`,
 *      thrown from a timer after the owning test finished.
 *
 * Each is a third-party library asking for a canvas, a used border width, or a
 * live animation frame — none of which jsdom has. So the engine is replaced here
 * rather than the environment being taught to lie: faking layout made the suite
 * take 180s instead of 82s for the same result, and shifted every unrelated
 * measurement in it.
 *
 * WHAT THE DOUBLE ANSWERS: the surface the four call sites use — subscription,
 * element access, style writes, layout, zoom/fit/centre, teardown. All recorded
 * no-ops. It asserts nothing and remembers nothing, because no test in this
 * repository asserts on Cytoscape's behaviour: the graph's semantics live in
 * `graph/semantics.ts`, which is pure and is tested directly.
 */

/** A collection. Chainable, empty, and safe to call any method on. */
function collection(): Record<string, unknown> {
  const self: Record<string, unknown> = {
    length: 0,
    size: () => 0,
    nodes: () => self,
    edges: () => self,
    elements: () => self,
    filter: () => self,
    remove: () => undefined,
    style: () => undefined,
    data: () => self,
    position: () => undefined,
    positions: () => undefined,
    renderedPosition: { x: 0, y: 0 },
    connectedNodes: () => self,
    connectedEdges: () => self,
    neighborhood: () => self,
    nodesInside: () => self,
    isNode: () => false,
    isEdge: () => false,
  };
  return self;
}

export interface CytoscapeTestOptions {
  container?: unknown;
  elements?: unknown;
  layout?: Record<string, unknown>;
  [key: string]: unknown;
}

/** Constructed for each call; kept on the instance so a test can inspect calls. */
export interface CytoscapeTestCore {
  container: () => null;
  nodes: () => Record<string, unknown>;
  edges: () => Record<string, unknown>;
  elements: () => Record<string, unknown>;
  getElementById: () => Record<string, unknown>;
  getElementByIdOrDie: () => Record<string, unknown>;
  collection: () => Record<string, unknown>;
  add: () => CytoscapeTestCore;
  remove: () => CytoscapeTestCore;
  batch: (fn: () => void) => void;
  on: () => CytoscapeTestCore;
  one: () => CytoscapeTestCore;
  off: () => CytoscapeTestCore;
  emit: () => CytoscapeTestCore;
  emitAndNotify: () => CytoscapeTestCore;
  style: () => undefined;
  layout: () => { run: () => undefined; stop: () => undefined; position: () => undefined };
  forceRender: () => undefined;
  resize: () => undefined;
  fit: () => CytoscapeTestCore;
  center: () => CytoscapeTestCore;
  zoom: () => 1;
  pan: () => { x: number; y: number };
  userZoomingEnabled: () => boolean;
  userPanningEnabled: () => boolean;
  boxSelectionEnabled: () => boolean;
  destroy: () => undefined;
  startAnimationLoop: () => undefined;
  stopAnimationLoop: () => undefined;
}

export default function cytoscapeTestDouble(_options: CytoscapeTestOptions = {}): CytoscapeTestCore {
  const core: CytoscapeTestCore = {
    container: () => null,
    nodes: () => collection(),
    edges: () => collection(),
    elements: () => collection(),
    getElementById: () => collection(),
    getElementByIdOrDie: () => collection(),
    collection: () => collection(),
    add: () => core,
    remove: () => core,
    batch: (fn: () => void) => {
      fn();
    },
    on: () => core,
    one: () => core,
    off: () => core,
    emit: () => core,
    emitAndNotify: () => core,
    style: () => undefined,
    layout: () => ({ run: () => undefined, stop: () => undefined, position: () => undefined }),
    forceRender: () => undefined,
    resize: () => undefined,
    fit: () => core,
    center: () => core,
    zoom: () => 1,
    pan: () => ({ x: 0, y: 0 }),
    userZoomingEnabled: () => false,
    userPanningEnabled: () => false,
    boxSelectionEnabled: () => false,
    destroy: () => undefined,
    startAnimationLoop: () => undefined,
    stopAnimationLoop: () => undefined,
  };
  return core;
}