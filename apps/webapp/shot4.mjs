import { chromium } from "playwright";
const OUT = "C:/Users/tim/Desktop/COGNITIVE/1/apps/webapp/tmp/shots/";
const b = await chromium.launch();
for (const [path, name] of JSON.parse(process.argv[2])) {
  const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
  const errs = [];
  p.on("pageerror", (e) => errs.push(String(e).slice(0, 110)));
  await p.goto("http://localhost:5173" + path, { waitUntil: "domcontentloaded", timeout: 30000 });
  // the API answers /investigations in ~4s; do not screenshot a loading state
  await p.waitForTimeout(12000);
  const txt = (await p.evaluate(() => document.body.innerText || "")).replace(/\s+/g, " ");
  await p.screenshot({ path: `${OUT}${name}.png`, fullPage: true });
  console.log(JSON.stringify({ name, placeholder: txt.includes("No investigation loaded"),
    loading: txt.includes("Loading investigations"), errs: errs.slice(0, 1),
    txt: txt.slice(120, 300) }));
  await p.close();
}
await b.close();
