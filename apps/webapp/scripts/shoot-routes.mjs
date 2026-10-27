/**
 * Portable route-level visual sweep for the COGNITIVE workbench.
 *
 * Usage: npm run ui:shoot:routes -- http://127.0.0.1:5173/investigations ...
 *
 * Captures the normative desktop widths and narrow breakpoints, reports
 * browser errors and fails on empty shells or document-level horizontal
 * overflow. It needs a running app and usable fixture/backend services.
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const TARGETS = process.argv.slice(2);
const OUT = process.env.UI_SHOTS_DIR ?? join(tmpdir(), "cognitive-ui-route-shots");
const CHROME = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
const VIEWPORTS = [
  [2560, 1440, "ultrawide"],
  [1920, 1080, "wide"],
  [1440, 900, "baseline"],
  [1023, 900, "tablet"],
  [767, 900, "small-tablet"],
  [390, 844, "phone"],
];

if (TARGETS.length === 0) {
  process.stderr.write(
    "Pass one or more absolute route URLs, e.g. http://127.0.0.1:5173/investigations\n",
  );
  process.exitCode = 2;
} else {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({
    ...(CHROME ? { executablePath: CHROME } : {}),
    headless: true,
  });
  const problems = [];

  for (const target of TARGETS) {
    let slug = "route";
    try {
      slug = new URL(target).pathname.replace(/[\\/]/g, "_").replace(/^_+|_+$/g, "") || "root";
    } catch {
      problems.push(`invalid absolute URL: ${target}`);
      continue;
    }

    for (const [width, height, label] of VIEWPORTS) {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = [];
      page.on("pageerror", (error) => errors.push(`pageerror: ${error.message.slice(0, 160)}`));
      page.on("console", (message) => {
        const text = message.text();
        if (message.type() === "error" && !text.includes("404")) {
          errors.push(`console: ${text.slice(0, 160)}`);
        }
      });

      try {
        await page.goto(target, { waitUntil: "domcontentloaded", timeout: 60000 });
      } catch (error) {
        errors.push(`navigation: ${String(error).slice(0, 160)}`);
      }
      await page.waitForTimeout(1200);

      const metrics = await page.evaluate(() => ({
        viewport: window.innerWidth,
        document: document.documentElement.scrollWidth,
        body: document.body.scrollWidth,
        rootLength: document.getElementById("root")?.innerHTML.length ?? -1,
        shellMounted: Boolean(document.querySelector('[data-testid="app-shell"]')),
        text: (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 180),
      }));

      await page.screenshot({
        path: join(OUT, `${slug}-${label}.png`),
        fullPage: true,
      });

      const report = { target, viewport: label, width, ...metrics, errors: errors.slice(0, 3) };
      process.stdout.write(`${JSON.stringify(report)}\n`);

      if (!metrics.shellMounted || metrics.rootLength < 1) {
        problems.push(`empty shell at ${target} / ${label}`);
      }
      if (metrics.document > metrics.viewport + 1 || metrics.body > metrics.viewport + 1) {
        problems.push(
          `horizontal page overflow at ${target} / ${label}: document=${metrics.document}, body=${metrics.body}`,
        );
      }
      problems.push(...errors.map((error) => `${target} / ${label}: ${error}`));
      await page.close();
    }
  }

  await browser.close();
  if (problems.length) {
    process.stderr.write(`\n${problems.length} issue(s):\n${problems.join("\n")}\n`);
    process.exitCode = 1;
  } else {
    process.stdout.write(`\nNo route, browser-console or document-overflow issues. Screenshots: ${OUT}\n`);
  }
}
