import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const OUT = "C:/Users/tim/Desktop/COGNITIVE/1/tmp/ui-review";
mkdirSync(OUT, { recursive: true });

const routes = [
  ["/investigations", "investigations"],
  ["/investigations/INV-9a7c383d6345", "investigation"],
  ["/search", "search"],
  ["/findings", "findings"],
  ["/science", "science"],
  ["/specops", "specops"],
  ["/research-cases/new", "research-case-new"],
  ["/dossier", "dossier"],
  ["/ui-kit", "ui-kit"],
];

const browser = await chromium.launch();

for (const [path, name] of routes) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  const errors = [];
  const bad = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push("console: " + m.text().slice(0, 200));
  });
  page.on("response", (r) => {
    if (r.status() >= 400) bad.push(`${r.status()} ${r.url()}`);
  });

  await page.goto("http://127.0.0.1:5173" + path, {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  await page.waitForTimeout(8000);

  const metrics = await page.evaluate(() => ({
    scrollW: document.documentElement.scrollWidth,
    innerW: window.innerWidth,
    root: document.getElementById("root")?.innerHTML.length ?? 0,
  }));
  const txt = (await page.evaluate(() => document.body.innerText || ""))
    .replace(/\s+/g, " ")
    .trim();

  await page.screenshot({ path: `${OUT}/${name}-desktop.png`, fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(1000);
  const phone = await page.evaluate(() => ({
    scrollW: document.documentElement.scrollWidth,
    innerW: window.innerWidth,
  }));
  await page.screenshot({ path: `${OUT}/${name}-phone.png`, fullPage: true });

  console.log(
    JSON.stringify({
      name,
      textLen: txt.length,
      head: txt.slice(0, 200),
      metrics,
      phone,
      errors: [...new Set(errors)].slice(0, 4),
      bad: [...new Set(bad)].slice(0, 6),
    }),
  );
  await page.close();
}

await browser.close();
