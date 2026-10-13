import { chromium } from "playwright";

/**
 * Screenshot every destination the nav advertises, and report what actually rendered.
 *
 * The point is not the picture alone. `#root` length and the first 300 characters of visible
 * text say whether a destination rendered *something*, an empty state, or nothing -- which is
 * the difference between "the screen is ugly" and "the screen is lying", and which a
 * screenshot at a glance cannot separate from a dark theme.
 */
const TARGETS = process.argv.slice(2);
const OUT = "C:/Users/tim/Desktop/COGNITIVE/1/apps/webapp/tmp/shots";

const browser = await chromium.launch();
for (const target of TARGETS) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 160)));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push("console: " + m.text().slice(0, 160));
  });
  await page.goto(target, { waitUntil: "networkidle", timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(1800);
  const slug = new URL(target).pathname.replace(/[\\/]/g, "_") || "_root";
  const rootHtmlLength = await page.evaluate(
    () => document.getElementById("root")?.innerHTML.length ?? -1,
  );
  const text = (await page.evaluate(() => document.body.innerText || ""))
    .replace(/\s+/g, " ")
    .slice(0, 260);
  await page.screenshot({ path: `${OUT}${slug}.png`, fullPage: true });
  console.log(JSON.stringify({ target, rootHtmlLength, errors: errors.slice(0, 2), text }));
  await page.close();
}
await browser.close();