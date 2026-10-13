import { chromium } from "playwright";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
const errs = [];
p.on("console", (m) => { if (m.type() === "error") errs.push("C " + m.text().slice(0, 200)); });
p.on("pageerror", (e) => errs.push("PE " + String(e.stack || e).slice(0, 600)));
await p.goto("http://localhost:5173/investigations", { waitUntil: "domcontentloaded" });
await p.waitForTimeout(12000);
const before = await p.evaluate(() => document.getElementById("root").innerHTML.length);
const clicked = await p.evaluate(() => {
  const chips = [...document.querySelectorAll("button, a")].filter((e) => /^1111|^whales/.test((e.innerText || "").trim()));
  if (!chips.length) return "no chip found";
  chips[0].click();
  return "clicked " + chips[0].innerText.trim();
});
await p.waitForTimeout(9000);
const after = await p.evaluate(() => ({
  url: location.pathname,
  rootLen: document.getElementById("root").innerHTML.length,
  canvas: !!document.querySelector("canvas"),
}));
await p.screenshot({ path: "C:/Users/tim/Desktop/COGNITIVE/1/apps/webapp/tmp/shots/click_nav.png" });
console.log(JSON.stringify({ before, clicked, after, errs: errs.slice(-4) }, null, 1));
await b.close();
