import { chromium } from "playwright";
const id = process.argv[2];
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
await p.goto("http://localhost:5173/investigations/" + id, { waitUntil: "domcontentloaded" });
await p.waitForTimeout(12000);
const r = await p.evaluate(() => {
  const bar = document.querySelector(".ui-topbar");
  const cs = getComputedStyle(bar);
  const kids = [...bar.children].map((el) => {
    const b = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return {
      cls: (el.className || "").toString().slice(0, 40),
      x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height),
      pos: s.position, ovf: s.overflowX, flex: s.flex, minW: s.minWidth,
      text: (el.innerText || "").replace(/\s+/g, " ").slice(0, 55),
    };
  });
  return { bar: { display: cs.display, flexWrap: cs.flexWrap, height: Math.round(bar.getBoundingClientRect().height), ovf: cs.overflow }, kids };
});
console.log(JSON.stringify(r, null, 1));
await b.close();
