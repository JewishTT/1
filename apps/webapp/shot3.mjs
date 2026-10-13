import { chromium } from "playwright";
const OUT = "C:/Users/tim/Desktop/COGNITIVE/1/apps/webapp/tmp/shots/";
const b = await chromium.launch();
for (const [path, name] of JSON.parse(process.argv[2])) {
  const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
  const errs = [];
  p.on("pageerror", (e) => errs.push("JS: " + String(e).slice(0, 110)));
  p.on("console", (m) => { if (m.type() === "error") errs.push("API: " + m.text().slice(0, 110)); });
  await p.goto("http://localhost:5173" + path, { waitUntil: "networkidle", timeout: 30000 }).catch(() => {});
  await p.waitForTimeout(1400);
  const root = await p.evaluate(() => document.getElementById("root")?.innerHTML.length ?? -1);
  const over = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
  await p.screenshot({ path: `${OUT}${name}.png`, fullPage: true });
  console.log(JSON.stringify({ name, root, overflow: over, errs: [...new Set(errs)].slice(0, 2) }));
  await p.close();
}
await b.close();
