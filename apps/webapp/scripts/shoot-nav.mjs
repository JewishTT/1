/**
 * Screenshot and geometry regression for the compact navigation deck.
 * Run from apps/webapp after starting Vite:
 *   npm run ui:shoot:nav -- http://127.0.0.1:5173 artifacts/nav-screenshots
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";

const BASE = process.argv[2] ?? "http://127.0.0.1:5173";
const OUT = resolve(process.argv[3] ?? process.env.UI_SHOTS_DIR ?? "artifacts/nav-screenshots");
const VIEWPORTS = [
  [1440, 900, "desktop"],
  [1023, 900, "tablet"],
  [390, 844, "phone"],
];

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ headless: true });
const problems = [];

for (const [width, height, label] of VIEWPORTS) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  page.on("pageerror", (error) => problems.push(`${label}: ${error.message.slice(0, 180)}`));
  try {
    await page.goto(new URL("/ui-kit", BASE).href, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.getByTestId("app-shell").waitFor({ timeout: 20000 });
    await page.getByTestId("nav-deck-trigger").waitFor({ timeout: 20000 });
    await page.getByTestId("nav-deck-trigger").click();
    const deck = page.getByTestId("nav-deck");
    await deck.waitFor({ state: "visible", timeout: 10000 });
    await page.getByTestId("nav-module-osint").waitFor({ state: "visible" });
    await page.getByTestId("nav-module-economic").waitFor({ state: "visible" });
    await page.getByTestId("nav-module-specops").waitFor({ state: "visible" });
    await page.screenshot({ path: join(OUT, `nav-deck-${label}.png`), fullPage: false, animations: "disabled" });
    const geometry = await page.evaluate(() => {
      const element = document.querySelector(".ui-nav-deck");
      const rect = element?.getBoundingClientRect();
      return {
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        deck: rect ? {
          left: Math.round(rect.left), top: Math.round(rect.top),
          right: Math.round(rect.right), bottom: Math.round(rect.bottom),
          width: Math.round(rect.width), height: Math.round(rect.height)
        } : null
      };
    });
    process.stdout.write(JSON.stringify({ viewport: label, ...geometry }) + "\n");
    if (!geometry.deck) problems.push(`${label}: navigation deck is missing`);
    else if (geometry.deck.left < 0 || geometry.deck.right > width + 1 ||
             geometry.deck.top < 0 || geometry.deck.bottom > height + 1) {
      problems.push(`${label}: navigation deck escapes viewport: ${JSON.stringify(geometry.deck)}`);
    }
    if (geometry.documentWidth > width + 1 || geometry.bodyWidth > width + 1) {
      problems.push(`${label}: page horizontally overflows by document=${geometry.documentWidth}, body=${geometry.bodyWidth}`);
    }
  } catch (error) {
    problems.push(`${label}: ${String(error).slice(0, 220)}`);
  } finally {
    await page.close();
  }
}
await browser.close();
if (problems.length) {
  process.stderr.write(`\nNavigation screenshot regression failed:\n- ${problems.join("\n- ")}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write(`Navigation screenshots and geometry checks passed. Artifacts: ${OUT}\n`);
}
