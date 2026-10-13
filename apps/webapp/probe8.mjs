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
const out = await p.evaluate(() => {
  const lines = [];
  const walk = (el, d) => {
    if (d > 4) return;
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 40) {
      lines.push("  ".repeat(d) + `${(el.className || "").toString().slice(0, 34)} [x${Math.round(r.x)} w${Math.round(r.width)} h${Math.round(r.height)}]`);
    }
    for (const c of el.children) walk(c, d + 1);
  };
  walk(document.querySelector(".ui-workspace"), 0);
  return lines.slice(0, 22).join("\n");
});
await p.screenshot({ path: "C:/Users/tim/Desktop/COGNITIVE/1/apps/webapp/tmp/shots/cols.png" });
console.log(out);
await b.close();
