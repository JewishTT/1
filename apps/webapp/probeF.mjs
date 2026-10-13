import { chromium } from "playwright";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
const errs = [];
p.on("pageerror", (e) => errs.push(String(e).slice(0, 120)));
await p.goto("http://localhost:5173/investigations", { waitUntil: "domcontentloaded" });
await p.waitForTimeout(11000);
await p.evaluate(() => {
  const c = [...document.querySelectorAll("button")].find((e) => e.innerText.trim() === "1111");
  if (c) c.click();
});
await p.waitForTimeout(9000);
await p.screenshot({ path: "C:/Users/tim/Desktop/COGNITIVE/1/apps/webapp/tmp/shots/graph_fixed.png" });
console.log(JSON.stringify({ canvases: await p.evaluate(() => document.querySelectorAll("canvas").length), errs }));
await b.close();
