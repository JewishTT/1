import { chromium } from "playwright";
const id = process.argv[2];
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
await p.goto("http://localhost:5173/investigations/" + id, { waitUntil: "domcontentloaded" });
await p.waitForTimeout(12000);
const wide = await p.evaluate(() => {
  const out = [];
  for (const el of document.querySelectorAll("*")) {
    const w = el.getBoundingClientRect().width;
    if (w > 1605) {
      const par = el.parentElement;
      out.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.className || "").toString().slice(0, 60),
        w: Math.round(w),
        sw: el.scrollWidth,
        overflowX: getComputedStyle(el).overflowX,
        parentCls: par ? (par.className || "").toString().slice(0, 40) : null,
        parentW: par ? Math.round(par.getBoundingClientRect().width) : null,
      });
    }
  }
  return out.slice(0, 14);
});
console.log(JSON.stringify(wide, null, 1));
await b.close();
