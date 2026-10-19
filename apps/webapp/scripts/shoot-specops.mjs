/**
 * Screenshot sweep for the SpecOps department.
 *
 * Exists because "the design is good" is not a claim anyone should have to take on
 * trust, and because a re-skin that breaks at one viewport width or one theme is
 * invisible in a unit test. It drives the real app in a real browser and writes PNGs
 * an operator can look at.
 *
 * The path matters and is worth recording: GhostLine is not a route. It is the
 * `CI / SpecOps` view inside an investigation's workspace, and within that view it is
 * the last of the department's panel tabs. Two clicks, not one URL.
 *
 * Usage: node scripts/shoot-specops.mjs [baseUrl] [outDir]
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const BASE = process.argv[2] ?? "http://127.0.0.1:5173";
const OUT = process.argv[3] ?? "C:/Users/tim/AppData/Local/Temp/opencode/shots";
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";

const PANELS = [
  ["GhostLine", "gl-runtime"],
  ["Playbooks", "gl-playbooks"],
  ["Simulator", "gl-simulate"],
  ["Voices", "gl-voices"],
  ["Dialler", "gl-dialer"],
  ["Transcripts", "gl-transcripts"],
  ["Analytics", "gl-analytics"],
  ["Phishing / SAT", "ci-phishing"],
  ["Social reaction", "ci-social"],
];

mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const page = await browser.newPage({
  viewport: { width: 1680, height: 1050 },
  deviceScaleFactor: 2,
});

const problems = [];
page.on("console", (m) => {
  const t = m.text();
  // A 404 on an investigation that does not exist is the workspace's own loading
  // state, not a defect in the surface being photographed.
  if (m.type() === "error" && !t.includes("404")) problems.push(`console: ${t.slice(0, 160)}`);
});
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message.slice(0, 160)}`));

await page.goto(`${BASE}/investigations/ci`, { waitUntil: "networkidle", timeout: 60000 });

// View 1: the department is a workspace view, not a route.
await page.getByRole("tab", { name: /CI \/ SpecOps/i }).click();
await page.waitForSelector('[data-testid="ci-canvas"]', { timeout: 20000 });
await page.waitForTimeout(1200);
await page.screenshot({ path: join(OUT, "00-department.png") });
process.stdout.write("shot 00-department\n");

for (const [label, name] of PANELS) {
  const tab = page.locator(`[role="tab"]:has-text("${label}")`);
  if ((await tab.count()) === 0) {
    problems.push(`missing tab: ${label}`);
    continue;
  }
  await tab.first().click();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: join(OUT, `${name}.png`) });
  process.stdout.write(`shot ${name}\n`);
}

// Light theme: the re-skin layers translucency over tokens, so it has to be proven
// against the light ground rather than assumed.
//
// Through the app's own command bar, not by writing `data-theme` directly. AppShell
// renders that attribute from the workspace store on every render, so a direct
// `setAttribute` is overwritten on the next paint — which is exactly what happened
// the first time this was written, and why the "light" screenshot came back dark.
await page.getByRole("tab", { name: /GhostLine/i }).click();
await page.keyboard.press("Control+k");
await page.waitForTimeout(400);
await page.keyboard.type("Toggle theme");
await page.waitForTimeout(400);
await page.keyboard.press("Enter");
await page.waitForTimeout(1000);
const theme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
if (theme !== "light") problems.push(`theme toggle did not take: data-theme=${theme}`);
await page.screenshot({ path: join(OUT, "gl-runtime-light.png") });
process.stdout.write(`shot gl-runtime-light (theme=${theme})\n`);

// Narrow viewport: the split grids collapse, and that is where a re-skin usually
// breaks first.
await page.getByRole("tab", { name: /GhostLine/i }).click();
await page.setViewportSize({ width: 1100, height: 900 });
await page.waitForTimeout(800);
await page.screenshot({ path: join(OUT, "gl-runtime-narrow.png") });
process.stdout.write("shot gl-runtime-narrow\n");

await browser.close();

if (problems.length) {
  process.stdout.write(`\n${problems.length} console problem(s):\n${problems.join("\n")}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write("\nno console errors\n");
}
