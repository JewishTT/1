import { chromium } from "playwright";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
await p.goto("http://localhost:5173/investigations", { waitUntil: "domcontentloaded" });
await p.waitForTimeout(11000);
await p.evaluate(() => {
  const c = [...document.querySelectorAll("button")].find((e) => e.innerText.trim() === "1111");
  if (c) c.click();
});
await p.waitForTimeout(8000);
const r = await p.evaluate(async () => {
  const host = document.querySelector(".ui-graph-host");
  const out = {
    hostChildren: host ? host.childNodes.length : -1,
    hostHTML: host ? host.innerHTML.slice(0, 120) : "",
    hostRect: host ? JSON.stringify(host.getBoundingClientRect().toJSON()) : "",
    totalCanvas: document.querySelectorAll("canvas").length,
  };
  const mod = await import("/node_modules/.vite/deps/cytoscape.js");
  // a detached host
  const d = document.createElement("div");
  document.body.appendChild(d);
  const cy1 = mod.default({ container: d, elements: [{ data: { id: "a" } }] });
  out.detached = { canvas: d.querySelectorAll("canvas").length, destroyed: cy1.destroyed(), renderer: !!cy1.renderer() };
  // a sized host
  const s = document.createElement("div");
  s.style.width = "400px"; s.style.height = "300px";
  document.body.appendChild(s);
  const cy2 = mod.default({ container: s, elements: [{ data: { id: "a" } }, { data: { id: "b" } }] });
  cy2.layout({ name: "preset" }).run();
  out.sized = { canvas: s.querySelectorAll("canvas").length, destroyed: cy2.destroyed() };
  return out;
});
console.log(JSON.stringify(r, null, 1));
await b.close();
