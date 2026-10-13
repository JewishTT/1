import { chromium } from "playwright";
const id = process.argv[2];
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
await p.goto("http://localhost:5173/investigations/" + id, { waitUntil: "domcontentloaded" });
await p.waitForTimeout(12000);
const info = await p.evaluate(() => {
  const out = [];
  const walk = (el, depth) => {
    const r = el.getBoundingClientRect();
    if (r.top < 60 && r.height > 0 && r.width > 0) {
      out.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className || "").toString().slice(0, 70),
        pos: getComputedStyle(el).position,
        z: getComputedStyle(el).zIndex,
        top: Math.round(r.top), h: Math.round(r.height), w: Math.round(r.width),
        depth,
      });
    }
    for (const c of el.children) walk(c, depth + 1);
  };
  walk(document.body, 0);
  return out.slice(0, 25);
});
console.log(JSON.stringify(info, null, 1));
await b.close();
