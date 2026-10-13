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
console.log(JSON.stringify(await p.evaluate(() => ({
  gc: window.__gc ?? "нет данных",
  canvases: document.querySelectorAll("canvas").length,
  hostKids: (document.querySelector(".ui-graph-host") || { childNodes: [] }).childNodes.length,
}))));
await b.close();
