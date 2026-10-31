/**
 * Screenshot and geometry regression for the persistent field-navigation rail.
 *
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
const pageErrors = [];
const browserPage = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
});
browserPage.on("pageerror", (error) => pageErrors.push(error.message.slice(0, 180)));

async function waitForNav(module) {
  await browserPage.waitForFunction(
    (expected) => document.querySelector(".ui-primary-nav")?.getAttribute("data-module") === expected,
    module,
    { timeout: 15000 },
  );
  await browserPage.locator(".ui-primary-nav").waitFor({ state: "visible" });
}

try {
  await browserPage.goto(new URL("/investigations", BASE).href, {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  await browserPage.getByTestId("app-shell").waitFor({ timeout: 20000 });
  await browserPage.locator(".ui-primary-nav").waitFor({ timeout: 20000 });
  await waitForNav("osint");

  for (const [width, height, label] of VIEWPORTS) {
    await browserPage.setViewportSize({ width, height });
    await browserPage.waitForTimeout(180);
    const metrics = await browserPage.evaluate(() => {
      const bounds = (selector) => {
        const element = document.querySelector(selector);
        if (!element) return null;
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return {
          left: Math.round(rect.left),
          top: Math.round(rect.top),
          right: Math.round(rect.right),
          bottom: Math.round(rect.bottom),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          display: style.display,
          overflowX: style.overflowX,
        };
      };
      return {
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        nav: bounds(".ui-primary-nav"),
        main: bounds(".ui-shell-main"),
        modules: [...document.querySelectorAll(".ui-primary-nav-module")].map((el) => ({
          label: el.innerText.replace(/\s+/g, " ").trim(),
          href: el.getAttribute("href"),
          active: el.getAttribute("data-active") === "true",
        })),
        destinationCount: document.querySelectorAll(".ui-primary-nav-link").length,
      };
    });

    await browserPage.locator(".ui-primary-nav").screenshot({
      path: join(OUT, `nav-field-domains-${label}.png`),
      animations: "disabled",
    });
    process.stdout.write(JSON.stringify({ viewport: label, ...metrics }) + "\n");

    if (!metrics.nav || !metrics.main || metrics.nav.width <= 0 || metrics.nav.height <= 0) {
      problems.push(`${label}: navigation rail or workspace is missing`);
      continue;
    }
    if (metrics.nav.left < -1 || metrics.nav.right > width + 1 ||
        metrics.nav.top < -1 || metrics.nav.bottom > height + 1) {
      problems.push(`${label}: navigation rail escapes viewport: ${JSON.stringify(metrics.nav)}`);
    }
    if (metrics.documentWidth > width + 1 || metrics.bodyWidth > width + 1) {
      problems.push(`${label}: document horizontally overflows: document=${metrics.documentWidth}, body=${metrics.bodyWidth}`);
    }
    if (metrics.modules.length !== 3 || metrics.destinationCount === 0) {
      problems.push(`${label}: expected three domains and at least one current-domain destination`);
    }
    if (width > 1279) {
      if (metrics.nav.width < 200 || metrics.nav.width > 260) {
        problems.push(`${label}: desktop rail width outside 200–260px: ${metrics.nav.width}`);
      }
      if (metrics.main.left < metrics.nav.right - 1) {
        problems.push(`${label}: workspace overlaps the desktop navigation rail`);
      }
    } else if (width > 767) {
      if (metrics.nav.width < 50 || metrics.nav.width > 80) {
        problems.push(`${label}: tablet rail should collapse to 50–80px, got ${metrics.nav.width}`);
      }
      if (metrics.main.left < metrics.nav.right - 1) {
        problems.push(`${label}: workspace overlaps the tablet icon rail`);
      }
    } else {
      if (metrics.nav.height > 150) {
        problems.push(`phone: domain/destination strip is too tall: ${metrics.nav.height}px`);
      }
      if (metrics.main.top < metrics.nav.bottom - 1) {
        problems.push("phone: workspace overlaps the horizontal navigation strip");
      }
    }
  }

  // Capture the two non-default domain states as well as the OSINT default.
  await browserPage.setViewportSize({ width: 1440, height: 900 });
  await browserPage.getByTestId("nav-module-specops").click();
  await waitForNav("specops");
  await browserPage.getByRole("navigation", { name: "specops workspaces" })
    .getByRole("link", { name: /Pipeline Operations/i }).waitFor({ state: "visible" });
  await browserPage.locator(".ui-primary-nav").screenshot({
    path: join(OUT, "nav-specops-desktop.png"),
    animations: "disabled",
  });

  await browserPage.getByTestId("nav-module-economic").click();
  await waitForNav("economic");
  await browserPage.getByRole("navigation", { name: "economic workspaces" })
    .locator("a").first().waitFor({ state: "visible" });
  await browserPage.locator(".ui-primary-nav").screenshot({
    path: join(OUT, "nav-economic-desktop.png"),
    animations: "disabled",
  });
} catch (error) {
  problems.push(`screenshot regression aborted: ${String(error).slice(0, 220)}`);
} finally {
  await browser.close();
}

if (pageErrors.length) problems.push(...pageErrors.map((error) => `pageerror: ${error}`));
if (problems.length) {
  process.stderr.write(`\nPersistent navigation screenshot regression failed:\n- ${problems.join("\n- ")}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write(`Persistent navigation screenshots and geometry checks passed. Artifacts: ${OUT}\n`);
}
