/**
 * Continuous visual regression sweep for the shared component library.
 *
 * Captures six normative viewport widths, the three catalogue tabs, all density
 * states, light/dark themes, modal focus overlay, and success/error toasts. It
 * writes PNGs plus a JSON manifest and fails on page errors, missing UI, or
 * document-level horizontal overflow. Review the uploaded screenshot artifact;
 * a successful assertion does not replace visual inspection.
 *
 * Usage: npm run ui:shoot:design-system -- [baseUrl] [outDir]
 */
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const BASE = process.argv[2] ?? "http://127.0.0.1:5173";
const OUT = resolve(process.argv[3] ?? process.env.UI_SHOTS_DIR ?? "artifacts/ui-screenshots");
const CHROME = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
const VIEWPORTS = [
  [2560, 1440, "ultrawide"],
  [1920, 1080, "wide"],
  [1440, 900, "baseline"],
  [1023, 900, "tablet"],
  [767, 900, "small-tablet"],
  [390, 844, "phone"],
];

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ ...(CHROME ? { executablePath: CHROME } : {}), headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const problems = [];
const manifest = [];
let stage = "launching browser";

page.on("pageerror", (error) => problems.push(`pageerror: ${error.message.slice(0, 220)}`));
page.on("console", (message) => {
  if (message.type() === "error" && !message.text().includes("404")) {
    problems.push(`console: ${message.text().slice(0, 220)}`);
  }
});

async function capture(name, extra = {}) {
  await page.evaluate(() => document.fonts.ready.then(() => true));
  await page.waitForTimeout(180);
  const metrics = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    shell: Boolean(document.querySelector('[data-testid="app-shell"]')),
    catalogue: Boolean(document.querySelector('[data-testid="ui-kit-page"]')),
    theme: document.querySelector(".ui-shell")?.getAttribute("data-theme") ?? null,
    density: document.querySelector(".ui-shell")?.getAttribute("data-density") ?? null,
    text: (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 140),
    nav: (() => {
      const nav = document.querySelector(".ui-topnav");
      return nav ? {
        clientWidth: nav.clientWidth,
        scrollWidth: nav.scrollWidth,
        overflowX: getComputedStyle(nav).overflowX,
      } : null;
    })(),
  }));
  const filename = `${name}.png`;
  await page.screenshot({ path: join(OUT, filename), fullPage: false, animations: "disabled" });
  const entry = { filename, ...metrics, ...extra };
  manifest.push(entry);
  process.stdout.write(`${JSON.stringify(entry)}\n`);

  if (!metrics.shell || !metrics.catalogue) problems.push(`${name}: shell or catalogue did not mount`);
  if (extra.expectedTheme && metrics.theme !== extra.expectedTheme) {
    problems.push(`${name}: expected theme ${extra.expectedTheme}, got ${metrics.theme}`);
  }
  if (metrics.document > metrics.viewport + 1 || metrics.body > metrics.viewport + 1) {
    problems.push(`${name}: horizontal overflow (viewport=${metrics.viewport}, document=${metrics.document}, body=${metrics.body})`);
  }
  if (metrics.nav && metrics.nav.scrollWidth > metrics.nav.clientWidth + 1) {
    problems.push(`${name}: top navigation is clipped at ${metrics.viewport}px (client=${metrics.nav.clientWidth}, scroll=${metrics.nav.scrollWidth})`);
  }
  return entry;
}

try {
  stage = "navigating to development UI kit";
  await page.goto(new URL("/ui-kit", BASE).href, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.getByTestId("ui-kit-page").waitFor({ timeout: 20000 });
  await page.getByTestId("app-shell").waitFor({ timeout: 20000 });

  // Core primitives at every spec-mandated viewport: layout regression first.
  for (const [width, height, label] of VIEWPORTS) {
    stage = `primitive top/bottom screenshots at ${label} (${width}px)`;
    await page.setViewportSize({ width, height });
    await page.locator(".ui-kit-page").evaluate((element) => { element.scrollTop = 0; });
    await capture(`primitives-dark-${label}`, { surface: "primitives", viewportPosition: "top", expectedTheme: "dark" });
    await page.locator(".ui-kit-page").evaluate((element) => { element.scrollTop = element.scrollHeight; });
    await capture(`primitives-dark-${label}-bottom`, { surface: "primitives", viewportPosition: "bottom", expectedTheme: "dark" });
    await page.locator(".ui-kit-page").evaluate((element) => { element.scrollTop = 0; });
  }

  // All visible catalogue sections at the review baseline.
  stage = "capturing the data-table tab";
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.locator(".ui-kit-page").evaluate((element) => { element.scrollTop = 0; });
  await page.getByRole("tab", { name: /Data & state/ }).click();
  await page.getByRole("table", { name: "Design system sample observations" }).waitFor();
  await capture("data-table-dark-baseline", { surface: "data-table" });

  stage = "capturing the feedback tab";
  await page.getByRole("tab", { name: /Feedback/ }).click();
  await page.getByText("No entities selected").waitFor();
  await capture("feedback-dark-baseline", { surface: "feedback" });

  // Density preview lives in the fields tab. Use it through the actual radio
  // group, then revisit feedback so screenshots test propagated UI, not just state.
  stage = "capturing local density control states";
  await page.getByRole("tab", { name: /Primitives/ }).click();
  const shellDensityBefore = await page.locator(".ui-shell").getAttribute("data-density");
  await page.getByLabel(/Compact/).click();
  if (await page.getByTestId("ui-kit-page").getAttribute("data-density") !== "compact") {
    problems.push("density preview: compact selection did not apply");
  }
  if (await page.locator(".ui-shell").getAttribute("data-density") !== shellDensityBefore) {
    problems.push("density preview leaked into global shell state");
  }
  await page.getByRole("tab", { name: /Feedback/ }).click();
  await capture("feedback-density-compact", { surface: "feedback", localDensity: "compact" });

  await page.getByRole("tab", { name: /Primitives/ }).click();
  await page.getByLabel(/Comfortable/).click();
  if (await page.getByTestId("ui-kit-page").getAttribute("data-density") !== "comfortable") {
    problems.push("density preview: comfortable selection did not apply");
  }
  await page.getByRole("tab", { name: /Feedback/ }).click();
  await capture("feedback-density-comfortable", { surface: "feedback", localDensity: "comfortable" });

  // The actual shell menu drives global theme; never fake its DOM attribute.
  // The popover may remain open after a choice, so check state before re-clicking
  // its trigger. That avoids toggling an open menu closed and then clicking a hidden item.
  stage = "capturing light theme and restoring dark theme";
  const topbar = page.getByTestId("app-shell-topbar");
  const appearanceTrigger = topbar.locator('button[aria-haspopup="dialog"]');
  const appearancePanel = page.getByTestId("appearance-menu");

  async function chooseTheme(themeName) {
    const option = page.getByTestId("theme-" + themeName);
    if (!(await option.isVisible())) {
      await appearanceTrigger.click();
      await option.waitFor({ state: "visible", timeout: 5000 });
    }
    await option.click();
    await page.waitForFunction(
      (expected) => document.querySelector(".ui-shell")?.getAttribute("data-theme") === expected,
      themeName,
    );
  }

  async function closeAppearanceMenu() {
    if (await appearancePanel.getAttribute("data-open") !== "true") return;
    await page.keyboard.press("Escape");
    await page.waitForTimeout(100);
    if (await appearancePanel.getAttribute("data-open") === "true") await appearanceTrigger.click();
  }

  await chooseTheme("light");
  await closeAppearanceMenu();
  await capture("feedback-light-baseline", { surface: "feedback", expectedTheme: "light" });
  await chooseTheme("dark");
  await closeAppearanceMenu();

  // Screenshot stateful overlays as well as the underlying page. Close via
  // their real keyboard semantics to exercise focus restoration.
  stage = "capturing modal and toast overlay states";
  const modalTrigger = page.getByRole("button", { name: "Open modal preview" });
  await modalTrigger.click();
  await page.getByRole("dialog", { name: "Acquisition preview" }).waitFor();
  await capture("modal-dark-baseline", { surface: "modal" });
  await page.keyboard.press("Escape");
  await page.getByRole("dialog", { name: "Acquisition preview" }).waitFor({ state: "detached" });

  await page.getByRole("button", { name: "Preview success toast" }).click();
  await page.getByTestId("ui-kit-toast").waitFor();
  await capture("toast-success-dark-baseline", { surface: "toast", tone: "success" });
  await page.getByRole("button", { name: "Dismiss notification" }).click();

  await page.getByRole("button", { name: "Preview error toast" }).click();
  await page.getByTestId("ui-kit-toast").waitFor();
  await capture("toast-danger-dark-baseline", { surface: "toast", tone: "danger" });
} catch (error) {
  problems.push(`sweep aborted during ${stage}: ${String(error).slice(0, 300)}\n${error?.stack ?? ""}`);
} finally {
  await browser.close();
  writeFileSync(join(OUT, "manifest.json"), JSON.stringify({ baseUrl: BASE, shots: manifest, problems }, null, 2));
}

if (problems.length) {
  process.stderr.write(`\n${problems.length} visual sweep issue(s):\n${problems.map((p) => `- ${p}`).join("\n")}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write(`\nVisual sweep passed: ${manifest.length} PNGs in ${OUT}. Open the artifact and review the images.\n`);
}
