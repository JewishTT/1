import "@testing-library/jest-dom";

interface StubbedContext {
  canvas: HTMLCanvasElement;
  [key: string]: unknown;
}

const CONTEXT_METHODS = [
  "save",
  "restore",
  "scale",
  "rotate",
  "translate",
  "transform",
  "setTransform",
  "resetTransform",
  "clearRect",
  "fillRect",
  "strokeRect",
  "beginPath",
  "closePath",
  "moveTo",
  "lineTo",
  "bezierCurveTo",
  "quadraticCurveTo",
  "arc",
  "arcTo",
  "ellipse",
  "rect",
  "fill",
  "stroke",
  "clip",
  "fillText",
  "strokeText",
  "drawImage",
  "putImageData",
  "setLineDash",
] as const;

/** Attributes Cytoscape reads while laying out (font metrics, dash patterns). */
const CONTEXT_DEFAULTS = {
  lineWidth: 1,
  lineCap: "butt",
  lineJoin: "miter",
  miterLimit: 10,
  font: "10px sans-serif",
  textAlign: "start",
  textBaseline: "alphabetic",
  globalAlpha: 1,
  globalCompositeOperation: "source-over",
  shadowBlur: 0,
  shadowColor: "rgba(0, 0, 0, 0)",
  shadowOffsetX: 0,
  shadowOffsetY: 0,
  lineDashOffset: 0,
} as const;

function stubContext(canvas: HTMLCanvasElement): StubbedContext {
  const context: StubbedContext = { canvas };

  for (const method of CONTEXT_METHODS) {
    (context as Record<string, unknown>)[method] = () => undefined;
  }
  for (const [property, value] of Object.entries(CONTEXT_DEFAULTS)) {
    (context as Record<string, unknown>)[property] = value;
  }

  // `measureText` must return a usable object: a renderer that lays out labels
  // reads `.width`, and returning `undefined` there turns a stub into a crash.
  context.measureText = () => ({ width: 0 }) as unknown as TextMetrics;
  // Zero-size `ImageData` is enough for `putImageData` to have something to take.
  context.createImageData = (width: number, height: number) =>
    ({ width, height, data: new Uint8ClampedArray(0) }) as unknown as ImageData;
  context.getImageData = (_x: number, _y: number, width: number, height: number) =>
    ({ width, height, data: new Uint8ClampedArray(0) }) as unknown as ImageData;
  context.createLinearGradient = () => ({ addColorStop: () => undefined });
  context.createRadialGradient = () => ({ addColorStop: () => undefined });
  context.createPattern = () => null;

  return context;
}

if (typeof HTMLCanvasElement !== "undefined") {
  // One stub per canvas element, so two renderers never share a context object.
  const contexts = new WeakMap<HTMLCanvasElement, StubbedContext>();

  HTMLCanvasElement.prototype.getContext = function getContext(
    this: HTMLCanvasElement,
    // The id is deliberately unused: one stub serves every context type the
    // renderers here ask for. Naming it would imply the stub distinguishes
    // "2d" from "webgl", and it does not — a test that needed a real WebGL
    // context would need a real implementation, not a better stub.
    _contextId: string,
  ): unknown {
    const existing = contexts.get(this);
    if (existing !== undefined) return existing;
    const created = stubContext(this);
    contexts.set(this, created);
    return created;
  } as HTMLCanvasElement["getContext"];
}

/**
 * WHAT IS DELIBERATELY NOT STUBBED HERE: layout.
 *
 * `getBoundingClientRect`, `clientWidth`/`clientHeight` and
 * `getComputedStyle`'s box metrics all answer zero or `""` under jsdom, and every
 * one of them was tried as a fix for the Cytoscape rejection above. All three
 * were reverted, for the same reason: making jsdom answer layout queries turns
 * the environment into something that is neither jsdom nor a browser, and every
 * unrelated measurement in the suite shifts with it. The suite ran 82s with
 * honest zero-size geometry and 180s with faked geometry, for the same result.
 *
 * The consequence is stated so nobody re-adds it as a fix: a component that needs
 * to measure itself has to be tested against a value the test supplies (see
 * `ObjectGrid`'s `data-viewport-height`, which is why the windowing assertions
 * read the geometry from the DOM instead of hard-coding a number), or tested in a
 * real browser. Quietly handing it a plausible-looking 1024×768 would make the
 * test pass without making the component correct.
 */

if (typeof window !== "undefined" && typeof window.ResizeObserver === "undefined") {
  // Cytoscape and ECharts both observe their container. jsdom has no
  // ResizeObserver, so they would throw on construction the same way the canvas
  // did. A no-op observer is the honest stub: these tests assert on the DOM the
  // components render, never on paint geometry.
  class NoopResizeObserver implements ResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  window.ResizeObserver = NoopResizeObserver as unknown as typeof ResizeObserver;
  globalThis.ResizeObserver = NoopResizeObserver as unknown as typeof ResizeObserver;
}
