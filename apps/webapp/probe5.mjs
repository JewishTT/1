import { chromium } from "playwright";
const id = process.argv[2];
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
const errs = [];
p.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 200)); });
p.on("pageerror", (e) => errs.push("PAGEERROR " + String(e).slice(0, 300)));
await p.goto("http://localhost:5173/investigations/" + id, { waitUntil: "domcontentloaded" });
await p.waitForTimeout(12000);
const r = await p.evaluate(() => ({
  rootLen: (document.getElementById("root") || {}).innerHTML?.length ?? -1,
  topbar: !!document.querySelector(".ui-topbar"),
  scripts: document.querySelectorAll("script").length,
}));
console.log(JSON.stringify({ ...r, errs: errs.slice(0, 6) }, null, 1));
await b.close();
