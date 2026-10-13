import { chromium } from "playwright";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
const errs = [];
p.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 300)); });
p.on("pageerror", (e) => errs.push("PAGEERROR " + String(e.stack || e).slice(0, 500)));
await p.goto("http://localhost:5173/investigations", { waitUntil: "domcontentloaded" });
await p.waitForTimeout(14000);
const r = await p.evaluate(() => ({
  rootLen: (document.getElementById("root") || {}).innerHTML?.length ?? -1,
  topbar: !!document.querySelector(".ui-topbar"),
  canvas: !!document.querySelector("canvas"),
  txt: (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 200),
}));
await p.screenshot({ path: "C:/Users/tim/Desktop/COGNITIVE/1/apps/webapp/tmp/shots/tenant_blank.png" });
console.log(JSON.stringify({ ...r, errs: errs.slice(0, 4) }, null, 1));
await b.close();
