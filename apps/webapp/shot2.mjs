import { chromium } from "playwright";
const OUT = "C:/Users/tim/Desktop/COGNITIVE/1/apps/webapp/tmp/shots/";
const b = await chromium.launch();
for (const [url, name, w] of JSON.parse(process.argv[2])) {
  const p = await b.newPage({ viewport: { width: w, height: 1000 } });
  const errs = [];
  p.on("pageerror", (e) => errs.push(String(e).slice(0, 120)));
  await p.goto(url, { waitUntil: "networkidle", timeout: 30000 }).catch(() => {});
  await p.waitForTimeout(1500);
  const txt = (await p.evaluate(() => document.body.innerText || "")).replace(/\s+/g, " ").slice(0, 170);
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
  await p.screenshot({ path: `${OUT}${name}.png`, fullPage: true });
  console.log(JSON.stringify({ name, w, horizontalOverflow: overflow, errs: errs.slice(0, 1), txt }));
  await p.close();
}
await b.close();
