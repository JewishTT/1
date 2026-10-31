/**
 * Visual regression for the governed Research Case setup route.
 * Captures the actual route at UI 2.0 breakpoints and checks graphite token surfaces.
 * Usage: npm run ui:shoot:research-case -- [baseUrl] [outDir]
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";

const BASE = process.argv[2] ?? "http://127.0.0.1:5173";
const OUT = resolve(process.argv[3] ?? "artifacts/research-case-screenshots");
const VIEWPORTS = [
  [2560, 1440, "ultrawide"],
  [1920, 1080, "wide"],
  [1440, 900, "desktop"],
  [1023, 900, "tablet"],
  [767, 900, "small-tablet"],
  [390, 844, "phone"],
];

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ headless: true });
const failures = [];
const manifest = [];

try {
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  page.on("pageerror", (error) => failures.push(\`pageerror: \${error.message}\`));
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("404")) {
      failures.push(\`console: \${message.text()}\`);
    }
  });

  for (const [width, height, label] of VIEWPORTS) {
    await page.setViewportSize({ width, height });
    await page.goto(\`\${BASE}/research-cases/new\`, { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Create research case" }).waitFor({ timeout: 15000 });
    await page.locator("form").first().waitFor({ state: "visible" });
    await page.evaluate(() => document.fonts.ready);

    const metrics = await page.evaluate(() => {
      const form = document.querySelector("main.ui-shell-main form");
      const setup = document.querySelector("main.ui-shell-main > main");
      const rect = form?.getBoundingClientRect();
      return {
        viewport: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        shellMounted: Boolean(document.querySelector(".ui-shell")),
        caseHeading: (document.querySelector("main.ui-shell-main")?.textContent ?? "").includes("Create research case"),
        capabilityStatus: Boolean(document.querySelector("[data-testid='research-case-capability-status']")),
        formVisible: Boolean(rect && rect.width > 0 && rect.height > 0),
        formBackground: form ? getComputedStyle(form).backgroundColor : null,
        setupWidth: setup ? Math.round(setup.getBoundingClientRect().width) : null,
        formRight: rect ? Math.round(rect.right) : null,
      };
    });

    const filename = \`research-case-setup-\${label}.png\`;
    await page.screenshot({ path: join(OUT, filename), fullPage: true, animations: "disabled" });
    manifest.push({ filename, width, height, ...metrics });
    process.stdout.write(\`\${JSON.stringify(manifest[manifest.length - 1])}\n\`);

    if (!metrics.shellMounted || !metrics.caseHeading || !metrics.formVisible || !metrics.capabilityStatus) {
      failures.push(\`\${label}: Research Case setup did not mount its shell, heading and form\`);
    }
    if (metrics.documentWidth > width + 1 || metrics.bodyWidth > width + 1 || (metrics.formRight ?? 0) > width + 1) {
      failures.push(\`\${label}: horizontal overflow at \${width}px\`);
    }
    if (metrics.formBackground === "rgb(255, 255, 255)") {
      failures.push(\`\${label}: Research Case form fell back to the white legacy surface\`);
    }
  }

  if (failures.length) {
    process.stderr.write(\`\${JSON.stringify({ failures, manifest }, null, 2)}\n\`);
    process.exitCode = 1;
  }
} finally {
  await browser.close();
}
