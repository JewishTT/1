import { chromium } from "playwright";
const id = process.argv[2];
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
await p.goto("http://localhost:5173/investigations/" + id, { waitUntil: "domcontentloaded" });
await p.waitForTimeout(12000);
const r = await p.evaluate(() => {
  const bar = document.querySelector(".ui-topbar");
  const doc = document.documentElement;
  return {
    viewport: window.innerWidth,
    docScrollW: doc.scrollWidth,
    topbarW: bar ? Math.round(bar.getBoundingClientRect().width) : null,
    bodyScrollW: document.body.scrollWidth,
  };
});
await p.screenshot({ path: "C:/Users/tim/Desktop/COGNITIVE/1/apps/webapp/tmp/shots/topbar_fixed.png", fullPage: true });
console.log(JSON.stringify(r));
await b.close();
