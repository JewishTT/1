import { chromium } from "playwright";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
await p.goto("http://localhost:5173/investigations", { waitUntil: "domcontentloaded" });
await p.waitForTimeout(12000);
await p.evaluate(() => {
  const c = [...document.querySelectorAll("button")].find((e) => e.innerText.trim() === "1111");
  if (c) c.click();
});
await p.waitForTimeout(9000);
const r = await p.evaluate(() => {
  const host = document.querySelector(".ui-graph-host");
  const canvases = host ? [...host.querySelectorAll("canvas")] : [];
  const out = { host: !!host, canvasCount: canvases.length, boxes: [] };
  for (const cv of canvases) {
    const b = cv.getBoundingClientRect();
    out.boxes.push(`[x${Math.round(b.x)} y${Math.round(b.y)} w${Math.round(b.width)} h${Math.round(b.height)}]`);
  }
  // Any non-blank canvas?
  out.nonBlank = canvases.filter((cv) => {
    try {
      const ctx = cv.getContext("2d");
      const d = ctx.getImageData(0, 0, cv.width, cv.height).data;
      for (let i = 3; i < d.length; i += 400) if (d[i] !== 0) return true;
      return false;
    } catch { return "n/a"; }
  }).length;
  return out;
});
console.log(JSON.stringify(r, null, 1));
await b.close();
