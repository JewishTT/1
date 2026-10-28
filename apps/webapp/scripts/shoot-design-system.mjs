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
    text: (document.body.innerText || "").replace(/\\s+/g, " ").slice(0, 140),
  }));
  const filename = `${name}.png`;
  await page.screenshot({ path: join(OUT, filename), fullPage: true, animations: "disabled" });
  const entry = { filename, ...metrics, ...extra };
  manifest.push(entry);
  process.stdout.write(`${JSON.stringify(entry)}\\n`);

  if (!metrics.shell || !metrics.catalogue) problems.push(`${name}: shell or catalogue did not mount`);
  if (extra.expectedTheme && metrics.theme !== extra.expectedTheme) {
    problems.push(`${name}: expected theme ${extra.expectedTheme}, got ${metrics.theme}`);
  }
  if (metrics.document > metrics.viewport + 1 || metrics.body > metrics.viewport + 1) {
    problems.push(`${name}: horizontal overflow (viewport=${metrics.viewport}, document=${metrics.document}, body=${metrics.body})`);
  }
  return entry;
}

try {
  await page.goto(new URL("/ui-kit", BASE).href, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.getByTestId("ui-kit-page").waitFor({ timeout: 20000 });
  await page.getByTestId("app-shell").waitFor({ timeout: 20000 });

  // Core primitives at every spec-mandated viewport: layout regression first.
  for (const [width, height, label] of VIEWPORTS) {
    await page.setViewportSize({ width, height });
    await capture(`primitives-dark-${label}`, { surface: "primitives", expectedTheme: "dark" });
  }

  // All visible catalogue sections at the review baseline.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("tab", { name: /Data & state/ }).click();
  await page.getByRole("table", { name: "Design system sample observations" }).waitFor();
  await capture("data-table-dark-baseline", { surface: "data-table" });

  await page.getByRole("tab", { name: /Feedback/ }).click();
  await page.getByText("No entities selected").waitFor();
  await capture("feedback-dark-baseline", { surface: "feedback" });

  // Density preview lives in the fields tab. Use it through the actual radio
  // group, then revisit feedback so screenshots test propagated UI, not just state.
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

  // The actual shell menu drives the global theme. Do not fake the attribute:
  // doing that can create a screenshot that looks right while the app state is wrong.
  const topbar = page.getByTestId("app-shell-topbar");
  await topbar.getByRole("button").nth(1).click();
  await page.getByTestId("theme-light").click();
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => document.querySelector(".ui-shell")?.getAttribute("data-theme") === "light");
  await capture("feedback-light-baseline", { surface: "feedback", expectedTheme: "light" });

  await topbar.getByRole("button", { name: /comfortable/i }).click();
  await page.getByTestId("theme-dark").click();
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => document.querySelector(".ui-shell")?.getAttribute("data-theme") === "dark");

  // Screenshot stateful overlays as well as the underlying page. Close via
  // their real keyboard semantics to exercise focus restoration.
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
  problems.push(`sweep aborted: ${String(error).slice(0, 300)}`);
} finally {
  await browser.close();
  writeFileSync(join(OUT, "manifest.json"), JSON.stringify({ baseUrl: BASE, shots: manifest, problems }, null, 2));
}

if (problems.length) {
  process.stderr.write(`\\n${problems.length} visual sweep issue(s):\\n${problems.map((p) => `- ${p}`).join("\\n")}\\n`);
  process.exitCode = 1;
} else {
  process.stdout.write(`\\nVisual sweep passed: ${manifest.length} PNGs in ${OUT}. Open the artifact and review the images.\\n`);
}
