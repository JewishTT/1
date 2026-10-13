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
console.log(JSON.stringify(await p.evaluate(() => {
  const g = window.__cyProbe;
  return { probe: g ?? "нет", canvas: document.querySelectorAll("canvas").length };
})));
await b.close();
